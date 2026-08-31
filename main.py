"""CLI entry point for GPU-accelerated historical pattern matching."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from gpu_matcher import find_matches, follow_up_stats, summarize_follow_ups
from report import create_report

PROJECT_DIR = Path(__file__).resolve().parent
DEFAULT_DATA_DIR = PROJECT_DIR / "data" / "kline"
DEFAULT_REPORT_DIR = PROJECT_DIR / "reports"
DEFAULT_TOP = 10
DEFAULT_BATCH_SIZE = 4096
DEFAULT_CHART_DAYS = 30
DEFAULT_NEXT_DAYS = 15

try:
    import config as local_config
except ImportError:
    local_config = None

if local_config is not None:
    DEFAULT_DATA_DIR = Path(getattr(local_config, "DATA_DIR", DEFAULT_DATA_DIR))
    DEFAULT_REPORT_DIR = Path(getattr(local_config, "REPORT_DIR", DEFAULT_REPORT_DIR))
    DEFAULT_TOP = int(getattr(local_config, "TOP_N", DEFAULT_TOP))
    DEFAULT_BATCH_SIZE = int(getattr(local_config, "BATCH_SIZE", DEFAULT_BATCH_SIZE))


def main() -> int:
    parser = argparse.ArgumentParser(description="使用 GPU 查找 A 股历史相似走势")
    parser.add_argument("code", help="股票代码，例如 600703")
    parser.add_argument("--start-date", required=True, help="起始日期，格式 YYYYMMDD")
    parser.add_argument("--end-date", required=True, help="结束日期，格式 YYYYMMDD")
    parser.add_argument("--top", type=int, default=DEFAULT_TOP, help=f"返回前 N 个结果，默认 {DEFAULT_TOP}")
    parser.add_argument("--batch-size", type=int, default=DEFAULT_BATCH_SIZE, help=f"GPU 批大小，默认 {DEFAULT_BATCH_SIZE}")
    parser.add_argument("--chart-days", type=int, default=DEFAULT_CHART_DAYS, help=f"K 线图展示的自然日数，默认 {DEFAULT_CHART_DAYS}")
    parser.add_argument("--next-days", type=int, default=DEFAULT_NEXT_DAYS, help=f"每个匹配窗口后续展示的交易日数，默认 {DEFAULT_NEXT_DAYS}")
    parser.add_argument("--data-dir", type=Path, default=DEFAULT_DATA_DIR, help="本项目 K 线数据目录")
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT_DIR, help="本项目报告目录")
    args = parser.parse_args()
    try:
        target, matches, elapsed = find_matches(args.code.zfill(6), args.start_date, args.end_date, args.data_dir, args.top, args.batch_size)
    except (OSError, ValueError, json.JSONDecodeError, RuntimeError) as error:
        print(f"错误: {error}")
        return 1
    print(f"\n目标: {target.code} {target.name} | {target.start_date} 至 {target.end_date}")
    print(f"实际计算耗时: {elapsed}")
    follow_ups = [follow_up_stats(match.window, args.data_dir, args.next_days) for match in matches]
    print("相似历史窗口（GPU 距离越小越相似）:")
    for index, (match, follow) in enumerate(zip(matches, follow_ups), 1):
        line = f"{index}. {match.window.code} {match.window.name} {match.window.start_date} 至 {match.window.end_date} | 距离={match.distance:.4f} 相似度={match.similarity:.4f}"
        if follow:
            line += f" | 后续{follow['days']}日 {follow['cumulative'] * 100:+.2f}%"
        print(line)
    summary = summarize_follow_ups(follow_ups)
    if summary:
        print(f"\n后续 {args.next_days} 个交易日汇总（{summary['count']} 个有效匹配）:")
        print(f"  上涨 {summary['up']} / 下跌 {summary['down']}，胜率 {summary['win_rate'] * 100:.1f}%")
        print(f"  累计收益 平均 {summary['average'] * 100:+.2f}%，中位 {summary['median'] * 100:+.2f}%，最好 {summary['best'] * 100:+.2f}%，最差 {summary['worst'] * 100:+.2f}%")
        print(f"  平均最大冲高 {summary['average_max_gain'] * 100:+.2f}%，平均最大回撤 {summary['average_max_loss'] * 100:+.2f}%")
    report_path = create_report(target, matches, args.data_dir, args.report, args.chart_days, args.next_days, follow_ups, summary)
    print(f"K线图报告已生成: {report_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
