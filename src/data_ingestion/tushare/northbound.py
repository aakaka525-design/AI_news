#!/usr/bin/env python3
"""
Tushare 北向持股全量抓取模块

功能：
- 抓取沪深港通全量持股数据 (hk_hold)
- 按日期批量获取所有北向持股记录（4000+ 只股票）
"""

import sqlite3
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

# 添加项目根目录
PROJECT_ROOT = Path(__file__).resolve().parents[3]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.database.connection import get_connection
from src.data_ingestion.tushare.client import TushareAdapter, get_tushare_client


def log(msg: str):
    ts = datetime.now().strftime("%H:%M:%S")
    print(f"[{ts}] {msg}", flush=True)


# ============================================================
# 表初始化
# ============================================================

def init_tables(conn=None):
    """初始化北向持股表"""
    own_conn = conn is None
    if own_conn:
        conn = get_connection()

    conn.execute("""
        CREATE TABLE IF NOT EXISTS ts_hk_hold (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts_code TEXT NOT NULL,
            trade_date TEXT NOT NULL,
            vol INTEGER,
            ratio REAL,
            exchange TEXT,
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(ts_code, trade_date)
        )
    """)
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_ts_hk_hold_code ON ts_hk_hold(ts_code)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_ts_hk_hold_date ON ts_hk_hold(trade_date)"
    )
    conn.commit()

    if own_conn:
        conn.close()
    log("北向持股表初始化完成")


# ============================================================
# 单日抓取
# ============================================================

def fetch_northbound_by_date(trade_date: str, client: TushareAdapter = None, conn=None) -> int:
    """
    获取指定日期的全量北向持股数据。

    Args:
        trade_date: 交易日期 (YYYYMMDD)
        client: TushareAdapter 实例（可选，测试注入用）
        conn: sqlite3 连接（可选，测试注入 :memory: 用）

    Returns:
        保存的记录数
    """
    own_conn = conn is None
    if own_conn:
        conn = get_connection()

    if client is None:
        client = get_tushare_client()

    try:
        df = client.hk_hold(trade_date=trade_date)

        if df is None or df.empty:
            log(f"   {trade_date} 无北向持股数据")
            return 0

        count = 0
        for _, row in df.iterrows():
            try:
                now = datetime.now().isoformat()
                conn.execute("""
                    INSERT OR REPLACE INTO ts_hk_hold
                    (ts_code, trade_date, vol, ratio, exchange, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                """, (
                    row.get("ts_code"),
                    row.get("trade_date"),
                    row.get("vol"),
                    row.get("ratio"),
                    row.get("exchange"),
                    now,
                    now,
                ))
                count += 1
            except Exception as e:
                log(f"   保存 {row.get('ts_code')} trade_date={trade_date} 失败: {e}")

        conn.commit()
        log(f"   {trade_date} 保存 {count} 条北向持股记录")
        return count

    finally:
        if own_conn:
            conn.close()


# ============================================================
# 批量抓取（按日期范围）
# ============================================================

def fetch_northbound_range(start_date: str, end_date: str = None, client: TushareAdapter = None) -> int:
    """
    批量抓取日期范围内的北向持股数据。

    Args:
        start_date: 开始日期 (YYYYMMDD)
        end_date: 结束日期 (YYYYMMDD)，默认为今天
        client: TushareAdapter 实例（可选）

    Returns:
        总保存记录数
    """
    log("=" * 50)
    log("Tushare 北向持股批量抓取")
    log("=" * 50)

    init_tables()

    if client is None:
        client = get_tushare_client()

    if end_date is None:
        end_date = datetime.now().strftime("%Y%m%d")

    trading_days = client.get_trading_days(start_date=start_date, end_date=end_date)
    log(f"日期范围 {start_date} ~ {end_date}，共 {len(trading_days)} 个交易日")

    conn = get_connection()
    total = 0

    try:
        for i, td in enumerate(trading_days):
            if (i + 1) % 10 == 0:
                log(f"[{i + 1}/{len(trading_days)}] 已处理...")

            try:
                count = fetch_northbound_by_date(td, client=client, conn=conn)
                total += count
            except Exception as e:
                log(f"   {td} 抓取失败: {e}")

            # Tushare API 限流
            time.sleep(0.35)
    finally:
        conn.close()

    log(f"完成! 共保存 {total} 条北向持股记录")
    return total


# ============================================================
# 主函数
# ============================================================

def main():
    """抓取最近 5 个交易日的北向持股数据"""
    log("=" * 50)
    log("Tushare 北向持股抓取（最近 5 个交易日）")
    log("=" * 50)

    # 往回推 14 天以确保覆盖至少 5 个交易日（含节假日）
    start_date = (datetime.now() - timedelta(days=14)).strftime("%Y%m%d")
    fetch_northbound_range(start_date=start_date)


if __name__ == "__main__":
    main()
