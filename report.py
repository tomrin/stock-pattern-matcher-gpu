"""Create a self-contained SVG/HTML report for GPU matching results."""
from __future__ import annotations

from html import escape
from pathlib import Path
from typing import Any

from gpu_matcher import Match, Window, parse_date


def _rows(path: Path, start: str, days: int) -> list[dict[str, Any]]:
    import json
    from datetime import timedelta

    payload = json.loads(path.read_text(encoding="utf-8"))
    values = payload.get("kline", [])
    first = parse_date(start)
    last = first + timedelta(days=days)
    return [row for row in values if first <= parse_date(str(row["date"])) <= last]


def _svg(label: str, window: Window, rows: list[dict[str, Any]], path: Path, split_date: str | None = None) -> None:
    dates = [parse_date(str(row["date"])) for row in rows]
    width, height, margin = 1400, 520, 55
    highs = [float(row["high"]) for row in rows]
    lows = [float(row["low"]) for row in rows]
    high, low = max(highs), min(lows)
    span = high - low or 1.0
    plot_width, plot_height = width - margin * 2, height - margin * 2
    x = lambda i: margin + i * plot_width / max(1, len(rows) - 1)
    y = lambda value: margin + (high - value) * plot_height / span
    elements = []
    if split_date:
        split = parse_date(split_date)
        index = next((i for i, current in enumerate(dates) if current > split), len(dates))
        if index < len(rows):
            elements.append(f'<rect x="{x(index):.1f}" y="{margin}" width="{width - margin - x(index):.1f}" height="{plot_height}" fill="#334155" opacity=".35"/>')
            elements.append(f'<line x1="{x(index):.1f}" y1="{margin}" x2="{x(index):.1f}" y2="{height - margin}" stroke="#fbbf24" stroke-dasharray="8 6"/>')
    for index, row in enumerate(rows):
        open_price, close = float(row["open"]), float(row["close"])
        color = "#ef5350" if close >= open_price else "#26a69a"
        candle_width = max(3.0, plot_width / len(rows) * 0.55)
        top, bottom = y(max(open_price, close)), y(min(open_price, close))
        elements.append(f'<line x1="{x(index):.1f}" y1="{y(float(row["high"])):.1f}" x2="{x(index):.1f}" y2="{y(float(row["low"])):.1f}" stroke="{color}" stroke-width="2"/>')
        elements.append(f'<rect x="{x(index) - candle_width / 2:.1f}" y="{top:.1f}" width="{candle_width:.1f}" height="{max(1.5, bottom - top):.1f}" fill="{color}"/>')
    svg = f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}"><rect width="100%" height="100%" fill="#101820"/><text x="{margin}" y="30" fill="white" font-size="20">{escape(label)}: {escape(window.code)} {escape(window.name)} | {dates[0]} 至 {dates[-1]}</text>{"".join(elements)}</svg>'
    path.write_text(svg, encoding="utf-8")


def create_report(target: Window, matches: list[Match], data_dir: Path, report_dir: Path, chart_days: int) -> Path:
    report_dir.mkdir(parents=True, exist_ok=True)
    items = [("目标", target, None)] + [(f"相似 {i}", match.window, match) for i, match in enumerate(matches, 1)]
    cards = []
    for index, (label, window, match) in enumerate(items):
        rows = _rows(data_dir / f"{window.code}.json", window.start_date, chart_days)
        image = report_dir / f"{index:02d}_{window.code}_{window.start_date}.svg"
        _svg(label, window, rows, image, window.end_date)
        detail = f"匹配区间 {window.start_date} 至 {window.end_date}，图表展示至 {rows[-1]['date']}"
        if match:
            detail += f"，距离 {match.distance:.4f}，相似度 {match.similarity:.4f}"
        cards.append(f'<section><h2>{escape(label)} | {escape(window.code)} {escape(window.name)}</h2><p>{detail}</p><img src="{image.name}" alt="{escape(label)}"></section>')
    path = report_dir / "report.html"
    path.write_text('<!doctype html><meta charset="utf-8"><title>GPU 历史相似形态报告</title><style>body{font-family:Arial;background:#0b1120;color:#e2e8f0;margin:24px}section{max-width:1400px;margin:0 auto 28px;padding:16px;background:#111827;border:1px solid #334155}img{width:100%}p{color:#94a3b8}</style><h1>GPU 历史相似形态报告</h1>' + ''.join(cards) + '</html>', encoding="utf-8")
    return path