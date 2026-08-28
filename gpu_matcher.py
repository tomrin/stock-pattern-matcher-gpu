"""GPU-accelerated relative-pattern matching for existing A-share JSON data."""
from __future__ import annotations

import heapq
import json
import time
from bisect import bisect_left, bisect_right
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

import torch

WINDOW_MIN_TRADING_DAYS = 5

@dataclass(frozen=True)
class Window:
    code: str
    name: str
    start_date: str
    end_date: str
    rows: tuple[dict[str, Any], ...]

@dataclass(frozen=True)
class Match:
    window: Window
    distance: float
    similarity: float


def parse_date(value: str) -> date:
    for fmt in ("%Y%m%d", "%Y-%m-%d"):
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            pass
    raise ValueError(f"日期格式错误: {value}")


def load_file(path: Path) -> tuple[str, str, list[dict[str, Any]]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    rows = payload.get("kline", payload) if isinstance(payload, dict) else payload
    required = ("date", "open", "high", "low", "close", "volume")
    rows = [row for row in rows if all(key in row for key in required)]
    for row in rows:
        row["_date"] = parse_date(str(row["date"]))
    rows.sort(key=lambda row: row["_date"])
    code = str(payload.get("code", path.stem)) if isinstance(payload, dict) else path.stem
    name = str(payload.get("name", code)) if isinstance(payload, dict) else code
    return code, name, rows


def window(rows: list[dict[str, Any]], dates: list[date], start: date, end: date) -> list[dict[str, Any]]:
    return rows[bisect_left(dates, start):bisect_right(dates, end)]


def feature_vector(rows: list[dict[str, Any]], length: int) -> list[float]:
    closes = [float(row["close"]) for row in rows]
    volumes = [max(float(row["volume"]), 0.0) for row in rows]
    average_volume = sum(volumes) / len(volumes) if volumes else 1.0
    channels = [[], [], [], []]
    for index, row in enumerate(rows):
        close = closes[index]
        previous = closes[index - 1] if index else close
        channels[0].append(close / previous - 1 if previous else 0.0)
        channels[1].append((float(row["high"]) - float(row["low"])) / close if close else 0.0)
        channels[2].append((close - float(row["open"])) / close if close else 0.0)
        channels[3].append(volumes[index] / average_volume if average_volume else 0.0)
    if len(rows) != length:
        raise ValueError("候选窗口交易日数量与目标不一致")
    normalized = []
    for values in channels:
        tensor = torch.tensor(values, dtype=torch.float32)
        deviation = torch.std(tensor, unbiased=False)
        normalized.extend(((tensor - tensor.mean()) / deviation if deviation > 1e-12 else torch.zeros_like(tensor)).tolist())
    return normalized


def find_matches(code: str, start_text: str, end_text: str, data_dir: Path, top_n: int, batch_size: int = 4096) -> tuple[Window, list[Match], str]:
    started = time.perf_counter()
    paths = sorted(data_dir.glob("*.json"))
    if not paths:
        raise ValueError(f"没有找到数据: {data_dir}")
    datasets = []
    for index, path in enumerate(paths, 1):
        datasets.append(load_file(path))
        if index % 500 == 0:
            print(f"加载数据 {index}/{len(paths)}", flush=True)
    selected = next((item for item in datasets if item[0] == code), None)
    if selected is None:
        raise ValueError(f"未找到股票代码 {code}")
    target_start, target_end = parse_date(start_text), parse_date(end_text)
    if target_end < target_start:
        raise ValueError("结束日期不能早于起始日期")
    selected_code, selected_name, selected_rows = selected
    selected_dates = [row["_date"] for row in selected_rows]
    target_rows = window(selected_rows, selected_dates, target_start, target_end)
    if len(target_rows) < WINDOW_MIN_TRADING_DAYS:
        raise ValueError(f"目标窗口只有 {len(target_rows)} 个交易日，至少需要 {WINDOW_MIN_TRADING_DAYS} 个")
    target = Window(selected_code, selected_name, str(target_rows[0]["date"]), str(target_rows[-1]["date"]), tuple(target_rows))
    target_vector = torch.tensor(feature_vector(target_rows, len(target_rows)), dtype=torch.float32)
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    target_gpu = target_vector.to(device)
    limit = max(1, top_n)
    best: list[tuple[float, int, Match]] = []
    pending: list[tuple[list[float], Window]] = []
    sequence = 0
    processed = 0

    def score_batch(batch: list[tuple[list[float], Window]]) -> None:
        nonlocal sequence
        vectors = torch.tensor([item[0] for item in batch], dtype=torch.float32, device=device)
        distances = torch.linalg.vector_norm(vectors - target_gpu, dim=1) / (vectors.shape[1] ** 0.5)
        values = distances.detach().cpu().tolist()
        for distance_value, (_, candidate) in zip(values, batch):
            sequence += 1
            match = Match(candidate, distance_value, 1.0 / (1.0 + distance_value))
            item = (-distance_value, sequence, match)
            if len(best) < limit:
                heapq.heappush(best, item)
            elif distance_value < -best[0][0]:
                heapq.heapreplace(best, item)

    for dataset_index, (candidate_code, candidate_name, rows) in enumerate(datasets, 1):
        dates = [row["_date"] for row in rows]
        for candidate_end in dates:
            candidate_rows = window(rows, dates, candidate_end - (target_end - target_start), candidate_end)
            if len(candidate_rows) != len(target_rows):
                continue
            candidate_start = candidate_rows[0]["_date"]
            candidate_finish = candidate_rows[-1]["_date"]
            if candidate_code == code and candidate_start <= target_end and candidate_finish >= target_start:
                continue
            candidate = Window(candidate_code, candidate_name, str(candidate_rows[0]["date"]), str(candidate_rows[-1]["date"]), tuple(candidate_rows))
            pending.append((feature_vector(candidate_rows, len(target_rows)), candidate))
            if len(pending) >= batch_size:
                score_batch(pending)
                processed += len(pending)
                pending.clear()
        if dataset_index % 500 == 0:
            print(f"匹配数据 {dataset_index}/{len(datasets)}，候选 {processed + len(pending)}，设备={device}", flush=True)
    if pending:
        score_batch(pending)
        processed += len(pending)
    matches = [item[2] for item in sorted(best, key=lambda item: item[2].distance)]
    elapsed = f"{time.perf_counter() - started:.1f} 秒"
    return target, matches, elapsed
