"""CLI entry point for GPU-accelerated historical pattern matching."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from gpu_matcher import find_matches
from report import create_report

PROJECT_DIR = Path(__file__).resolve().parent
DEFAULT_DATA_DIR = PROJECT_DIR / "data" / "kline"
DEFAULT_REPORT_DIR = PROJECT_DIR / "reports"


def main() -> int:
    parser = argparse.ArgumentParser(description="使用 GPU 查找 A 股历史相似走势")
    parser.add_argument("code", help="股票代码，例如 600703")
    parser.add_argument("--start-date", required=True, help="起始日期，格式 YYYYMMDD")
    parser.add_argument("--end-date", required=True, help="结束日期，格式 YYYYMMDD")
    parser.add_argument("--top", type=int, default=10, help="返回前 N 个结果，默认 10")
    parser.add_argument("--batch-size", type=int, default=4096, help="GPU 批大小，默认 4096")
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
    print("相似历史窗口（GPU 距离越小越相似）:")
    for index, match in enumerate(matches, 1):
        print(f"{index}. {match.window.code} {match.window.name} {match.window.start_date} 至 {match.window.end_date} | 距离={match.distance:.4f} 相似度={match.similarity:.4f}")
    report_path = create_report(target, matches, args.data_dir, args.report, 30)
    print(f"K线图报告已生成: {report_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
