#!/usr/bin/env python3
"""
一键更新全部数据

按顺序执行所有 Tushare fetcher，填充/更新数据库。
用法: python scripts/update_all_data.py
"""

import sys
import subprocess
from pathlib import Path
from datetime import datetime

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def log(msg: str):
    ts = datetime.now().strftime("%H:%M:%S")
    print(f"[{ts}] {msg}", flush=True)


def run_module(module: str, description: str) -> bool:
    """运行一个 Python 模块"""
    log(f"{'='*50}")
    log(f"▶ {description}")
    log(f"  运行: python -m {module}")
    log(f"{'='*50}")

    result = subprocess.run(
        [sys.executable, "-m", module],
        cwd=str(PROJECT_ROOT),
        capture_output=False,
    )

    if result.returncode != 0:
        log(f"⚠️ {description} 退出码: {result.returncode}")
        return False

    log(f"✅ {description} 完成\n")
    return True


def main():
    log("=" * 60)
    log("AI News — 一键数据更新")
    log("=" * 60)

    steps = [
        ("src.data_ingestion.tushare.daily", "日线 + 估值数据"),
        ("src.data_ingestion.tushare.index", "指数日线数据"),
        ("src.data_ingestion.tushare.block", "板块日线数据"),
        ("src.data_ingestion.tushare.moneyflow", "资金流向 + 北向资金"),
        ("src.data_ingestion.tushare.dragon_tiger", "龙虎榜数据"),
        ("src.data_ingestion.tushare.holder_number", "股东人数数据"),
        ("src.data_ingestion.tushare.northbound", "北向持股全量"),
        ("scripts.compute_industry_valuation", "行业估值中位数计算"),
    ]

    results = []
    for module, desc in steps:
        ok = run_module(module, desc)
        results.append((desc, ok))

    log("\n" + "=" * 60)
    log("更新结果汇总")
    log("=" * 60)
    for desc, ok in results:
        status = "✅" if ok else "❌"
        log(f"  {status} {desc}")

    failed = sum(1 for _, ok in results if not ok)
    if failed:
        log(f"\n⚠️ {failed} 个步骤失败")
    else:
        log("\n✅ 全部完成!")


if __name__ == "__main__":
    main()
