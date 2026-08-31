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


def feature_vector(rows: list[dict[str, Any]], length: int, previous_close: float | None = None) -> list[float]:
    closes = [float(row["close"]) for row in rows]
    volumes = [max(float(row["volume"]), 0.0) for row in rows]
    average_volume = sum(volumes) / len(volumes) if volumes else 1.0
    channels = [[], [], [], []]
    for index, row in enumerate(rows):
        close = closes[index]
        if index:
            previous = closes[index - 1]
        elif previous_close:
            previous = previous_close
        else:
            previous = close
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


def follow_up_stats(window: Window, data_dir: Path, count: int) -> dict[str, Any] | None:
    """Compute post-window performance of a matched window over the next ``count`` trading days."""
    path = data_dir / f"{window.code}.json"
    if not path.is_file():
        return None
    _, _, rows = load_file(path)
    dates = [row["_date"] for row in rows]
    index = bisect_right(dates, parse_date(window.end_date))
    if index == 0:
        return None
    base = float(rows[index - 1]["close"])
    later = rows[index:index + count]
    if not later or not base:
        return None
    highs = [float(row["high"]) for row in later]
    lows = [float(row["low"]) for row in later]
    end_close = float(later[-1]["close"])
    return {
        "days": len(later),
        "base": base,
        "end_close": end_close,
        "cumulative": end_close / base - 1,
        "max_gain": max(highs) / base - 1,
        "max_loss": min(lows) / base - 1,
    }


def summarize_follow_ups(stats_list: list[dict[str, Any] | None]) -> dict[str, Any] | None:
    """Aggregate per-match follow-up stats into a Top-N summary."""
    valid = [stats for stats in stats_list if stats]
    if not valid:
        return None
    ordered = sorted(stats["cumulative"] for stats in valid)
    middle = len(ordered) // 2
    median = ordered[middle] if len(ordered) % 2 else (ordered[middle - 1] + ordered[middle]) / 2
    up = sum(1 for stats in valid if stats["cumulative"] > 0)
    return {
        "count": len(valid),
        "up": up,
        "down": len(valid) - up,
        "win_rate": up / len(valid),
        "average": sum(stats["cumulative"] for stats in valid) / len(valid),
        "median": median,
        "best": ordered[-1],
        "worst": ordered[0],
        "average_max_gain": sum(stats["max_gain"] for stats in valid) / len(valid),
        "average_max_loss": sum(stats["max_loss"] for stats in valid) / len(valid),
    }


def find_matches(code: str, start_text: str, end_text: str, data_dir: Path, top_n: int, batch_size: int = 4096) -> tuple[Window, list[Match], str]:
    started = time.perf_counter()
    paths = sorted(data_dir.glob("*.json"))
    if not paths:
        raise ValueError(f"没有找到数据: {data_dir}")
    target_path = data_dir / f"{code}.json"
    if not target_path.is_file():
        target_path = next((path for path in paths if path.stem == code), None)
        if target_path is None:
            raise ValueError(f"未找到股票代码 {code}")
    selected = load_file(target_path)
    if selected[0] != code:
        # 文件名与 payload 中的 code 不一致时，退化为全量扫描定位目标
        selected = None
        target_path = None
        for path in paths:
            candidate = load_file(path)
            if candidate[0] == code:
                selected = candidate
                break
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
    target_index = bisect_left(selected_dates, target_start)
    target_previous_close = float(selected_rows[target_index - 1]["close"]) if target_index > 0 else None
    target_vector = torch.tensor(feature_vector(target_rows, len(target_rows), target_previous_close), dtype=torch.float32)
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

    for dataset_index, path in enumerate(paths, 1):
        if target_path is not None and path == target_path:
            candidate_code, candidate_name, rows = selected
        else:
            candidate_code, candidate_name, rows = load_file(path)
        dates = [row["_date"] for row in rows]
        for candidate_end in dates:
            window_start = candidate_end - (target_end - target_start)
            candidate_rows = window(rows, dates, window_start, candidate_end)
            if len(candidate_rows) != len(target_rows):
                continue
            candidate_start = candidate_rows[0]["_date"]
            candidate_finish = candidate_rows[-1]["_date"]
            if candidate_start <= target_end and candidate_finish >= target_start:
                # 与目标时间段重叠的窗口（包括目标股票自身）不参与匹配
                continue
            candidate = Window(candidate_code, candidate_name, str(candidate_rows[0]["date"]), str(candidate_rows[-1]["date"]), tuple(candidate_rows))
            window_index = bisect_left(dates, window_start)
            previous_close = float(rows[window_index - 1]["close"]) if window_index > 0 else None
            pending.append((feature_vector(candidate_rows, len(target_rows), previous_close), candidate))
            if len(pending) >= batch_size:
                score_batch(pending)
                processed += len(pending)
                pending.clear()
        if dataset_index % 500 == 0:
            print(f"匹配数据 {dataset_index}/{len(paths)}，候选 {processed + len(pending)}，设备={device}", flush=True)
    if pending:
        score_batch(pending)
        processed += len(pending)
    matches = [item[2] for item in sorted(best, key=lambda item: item[2].distance)]
    elapsed = f"{time.perf_counter() - started:.1f} 秒"
    return target, matches, elapsed
