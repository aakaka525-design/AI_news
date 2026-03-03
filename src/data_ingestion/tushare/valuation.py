#!/usr/bin/env python3
"""
Tushare 估值数据抓取入口。

复用 daily 模块中的公共逻辑，仅抓取 `ts_daily_basic`（PE/PB/市值等）。
"""

import sys
from datetime import datetime, timedelta
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[3]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.data_ingestion.tushare.daily import (  # noqa: E402
    fetch_daily_basic_by_date,
    fetch_stock_list,
    get_all_ts_codes,
    get_tushare_client,
    init_tables,
    log,
)


def main():
    log("=" * 50)
    log("Tushare 估值数据抓取")
    log("=" * 50)

    init_tables()
    client = get_tushare_client()
    fetch_stock_list(client)

    ts_codes = get_all_ts_codes()
    if not ts_codes:
        log("⚠️ 股票列表为空，已退出")
        return

    end_date = datetime.now().strftime("%Y%m%d")
    start_date = (datetime.now() - timedelta(days=30)).strftime("%Y%m%d")
    trading_days = client.get_trading_days(start_date=start_date, end_date=end_date)

    total = 0
    for trade_date in trading_days:
        total += fetch_daily_basic_by_date(trade_date, client)
    log(f"✅ 完成，累计写入 {total} 条估值数据")


if __name__ == "__main__":
    main()
