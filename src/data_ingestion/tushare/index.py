#!/usr/bin/env python3
"""
Tushare 指数日线数据抓取模块

功能：
- 抓取主要指数日线行情 (index_daily)
- 填充 stock_index 和 ts_index_daily 表
"""

import sqlite3
import sys
from datetime import datetime, timedelta
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[3]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.database.connection import get_connection
from src.data_ingestion.tushare.client import TushareAdapter, get_tushare_client


def log(msg: str):
    ts = datetime.now().strftime("%H:%M:%S")
    print(f"[{ts}] {msg}", flush=True)


# 6 大指数
MAJOR_INDICES = [
    "000001.SH",  # 上证指数
    "399001.SZ",  # 深证成指
    "399006.SZ",  # 创业板指
    "000300.SH",  # 沪深300
    "000905.SH",  # 中证500
    "000688.SH",  # 科创50
]


# ============================================================
# 表初始化
# ============================================================

def init_tables():
    """初始化指数相关表"""
    conn = get_connection()

    conn.execute("""
        CREATE TABLE IF NOT EXISTS stock_index (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts_code TEXT NOT NULL,
            trade_date TEXT NOT NULL,
            open REAL,
            high REAL,
            low REAL,
            close REAL,
            pre_close REAL,
            change REAL,
            pct_chg REAL,
            vol REAL,
            amount REAL,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(ts_code, trade_date)
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_si_code ON stock_index(ts_code)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_si_date ON stock_index(trade_date)")

    # ts_index_daily 使用相同 schema（原始数据存储）
    conn.execute("""
        CREATE TABLE IF NOT EXISTS ts_index_daily (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts_code TEXT NOT NULL,
            trade_date TEXT NOT NULL,
            open REAL,
            high REAL,
            low REAL,
            close REAL,
            pre_close REAL,
            change REAL,
            pct_chg REAL,
            vol REAL,
            amount REAL,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(ts_code, trade_date)
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_tid_code ON ts_index_daily(ts_code)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_tid_date ON ts_index_daily(trade_date)")

    conn.commit()
    conn.close()
    log("✅ 指数表初始化完成")


# ============================================================
# 抓取指数日线
# ============================================================

def fetch_index_daily_by_date(trade_date: str, client: TushareAdapter = None) -> int:
    """获取指定日期的主要指数日线"""
    log(f"📈 获取 {trade_date} 指数日线...")

    if client is None:
        client = get_tushare_client()

    conn = get_connection()
    total = 0

    try:
        for ts_code in MAJOR_INDICES:
            try:
                df = client.index_daily(ts_code=ts_code, trade_date=trade_date)

                if df is None or df.empty:
                    continue

                for _, row in df.iterrows():
                    values = (
                        row.get("ts_code"),
                        trade_date,
                        row.get("open"),
                        row.get("high"),
                        row.get("low"),
                        row.get("close"),
                        row.get("pre_close"),
                        row.get("change"),
                        row.get("pct_chg"),
                        row.get("vol"),
                        row.get("amount"),
                        datetime.now().isoformat(),
                    )
                    # 同时写入两张表
                    conn.execute("""
                        INSERT OR REPLACE INTO stock_index
                        (ts_code, trade_date, open, high, low, close, pre_close,
                         change, pct_chg, vol, amount, updated_at)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, values)
                    conn.execute("""
                        INSERT OR REPLACE INTO ts_index_daily
                        (ts_code, trade_date, open, high, low, close, pre_close,
                         change, pct_chg, vol, amount, updated_at)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, values)
                    total += 1
            except Exception as e:
                log(f"   ⚠️ {ts_code} 失败: {e}")

        conn.commit()
        if total > 0:
            log(f"   ✅ 保存 {total} 条指数记录")
        return total

    finally:
        conn.close()


def fetch_index_range(start_date: str, end_date: str = None) -> int:
    """批量抓取指数日线"""
    if end_date is None:
        end_date = datetime.now().strftime("%Y%m%d")

    init_tables()
    client = get_tushare_client()

    trading_days = client.get_trading_days(start_date=start_date, end_date=end_date)
    log(f"📅 交易日: {len(trading_days)} 天")

    total = 0
    for i, trade_date in enumerate(trading_days):
        log(f"\n[{i+1}/{len(trading_days)}] {trade_date}")
        count = fetch_index_daily_by_date(trade_date, client)
        total += count

    log(f"\n✅ 完成! 共 {total} 条指数记录")
    return total


# ============================================================
# 主函数
# ============================================================

def main():
    log("=" * 50)
    log("Tushare 指数日线抓取")
    log("=" * 50)

    init_tables()
    client = get_tushare_client()

    # 抓取最近 30 天
    end_date = datetime.now().strftime("%Y%m%d")
    start_date = (datetime.now() - timedelta(days=45)).strftime("%Y%m%d")

    trading_days = client.get_trading_days(start_date=start_date, end_date=end_date)
    log(f"📅 最近交易日: {len(trading_days)} 天")

    total = 0
    for trade_date in trading_days[-30:]:
        count = fetch_index_daily_by_date(trade_date, client)
        total += count

    stats = client.get_stats()
    log(f"\n📊 请求统计: {stats['total_requests']} 次, {stats['requests_per_minute']:.1f}/分钟")
    log(f"✅ 完成! 共 {total} 条记录")


if __name__ == "__main__":
    main()
