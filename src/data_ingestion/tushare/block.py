#!/usr/bin/env python3
"""
Tushare 板块日线数据抓取模块

功能：
- 从已有 ts_ths_daily + ts_ths_index 回填 block_daily
- 通过 Tushare API 增量抓取同花顺板块日线
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


# ============================================================
# 回填: ts_ths_daily + ts_ths_index -> block_daily
# ============================================================

def backfill_from_ths() -> int:
    """从 ts_ths_daily + ts_ths_index 回填 block_daily"""
    log("🔄 从 ts_ths_daily 回填 block_daily...")

    conn = get_connection()
    try:
        # 检查源表数据量
        src_count = conn.execute("SELECT COUNT(*) FROM ts_ths_daily").fetchone()[0]
        existing = conn.execute("SELECT COUNT(*) FROM block_daily").fetchone()[0]
        log(f"   源数据: {src_count} 条, 已有: {existing} 条")

        if src_count == 0:
            log("   ⚠️ ts_ths_daily 无数据，跳过回填")
            return 0

        # 批量插入，跳过已存在
        cursor = conn.execute("""
            SELECT
                d.ts_code,
                COALESCE(i.name, d.ts_code) AS name,
                COALESCE(i.type, 'N') AS type,
                d.trade_date,
                d.open,
                d.high,
                d.low,
                d.close,
                d.pct_change,
                d.vol
            FROM ts_ths_daily d
            LEFT JOIN ts_ths_index i ON d.ts_code = i.ts_code
        """)

        count = 0
        batch = []
        for row in cursor:
            batch.append((
                row[0],       # block_code = ts_code
                row[1],       # block_name = name
                row[2],       # block_type = type
                row[3],       # trade_date
                row[4],       # open
                row[5],       # high
                row[6],       # low
                row[7],       # close
                row[8],       # pct_chg = pct_change
                row[9],       # vol
                None,         # amount
                None,         # turnover_rate
                None,         # lead_stock
                None,         # up_count
                None,         # down_count
                datetime.now().isoformat(),
                datetime.now().isoformat(),
            ))

            if len(batch) >= 500:
                conn.executemany("""
                    INSERT OR IGNORE INTO block_daily
                    (block_code, block_name, block_type, trade_date,
                     open, high, low, close, pct_chg, vol,
                     amount, turnover_rate, lead_stock, up_count, down_count,
                     created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, batch)
                count += len(batch)
                batch = []

        if batch:
            conn.executemany("""
                INSERT OR IGNORE INTO block_daily
                (block_code, block_name, block_type, trade_date,
                 open, high, low, close, pct_chg, vol,
                 amount, turnover_rate, lead_stock, up_count, down_count,
                 created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, batch)
            count += len(batch)

        conn.commit()
        final = conn.execute("SELECT COUNT(*) FROM block_daily").fetchone()[0]
        log(f"   ✅ 回填完成，block_daily 现有 {final} 条")
        return final - existing

    finally:
        conn.close()


# ============================================================
# 增量: Tushare API -> block_daily
# ============================================================

def fetch_ths_daily_by_date(trade_date: str, client: TushareAdapter = None) -> int:
    """通过 Tushare ths_daily API 增量抓取板块日线"""
    log(f"📊 获取 {trade_date} 板块日线...")

    if client is None:
        client = get_tushare_client()

    conn = get_connection()
    try:
        df = client.ths_daily(trade_date=trade_date)

        if df is None or df.empty:
            log(f"   ⚠️ {trade_date} 无板块数据")
            return 0

        log(f"   获取到 {len(df)} 条板块数据")

        # 获取板块名称映射
        name_map = {}
        rows = conn.execute("SELECT ts_code, name, type FROM ts_ths_index").fetchall()
        for r in rows:
            name_map[r[0]] = (r[1], r[2])

        count = 0
        for _, row in df.iterrows():
            ts_code = row.get("ts_code")
            name_info = name_map.get(ts_code, (ts_code, "N"))
            try:
                conn.execute("""
                    INSERT OR REPLACE INTO block_daily
                    (block_code, block_name, block_type, trade_date,
                     open, high, low, close, pct_chg, vol,
                     amount, turnover_rate, lead_stock, up_count, down_count,
                     created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    ts_code,
                    name_info[0],
                    name_info[1],
                    trade_date,
                    row.get("open"),
                    row.get("high"),
                    row.get("low"),
                    row.get("close"),
                    row.get("pct_change"),
                    row.get("vol"),
                    row.get("amount"),
                    row.get("turnover_rate"),
                    None,  # lead_stock
                    None,  # up_count
                    None,  # down_count
                    datetime.now().isoformat(),
                    datetime.now().isoformat(),
                ))
                count += 1
            except Exception as e:
                log(f"   ⚠️ 保存 {ts_code} 失败: {e}")

        conn.commit()
        log(f"   ✅ 保存 {count} 条")
        return count

    finally:
        conn.close()


# ============================================================
# 主函数
# ============================================================

def main():
    log("=" * 50)
    log("Tushare 板块日线抓取")
    log("=" * 50)

    # Step 1: 回填历史数据
    backfill_from_ths()

    # Step 2: 增量抓取最近 5 天
    client = get_tushare_client()
    end_date = datetime.now().strftime("%Y%m%d")
    start_date = (datetime.now() - timedelta(days=10)).strftime("%Y%m%d")

    trading_days = client.get_trading_days(start_date=start_date, end_date=end_date)

    for trade_date in trading_days[-5:]:
        fetch_ths_daily_by_date(trade_date, client)

    stats = client.get_stats()
    log(f"\n📊 请求统计: {stats['total_requests']} 次, {stats['requests_per_minute']:.1f}/分钟")
    log("✅ 完成!")


if __name__ == "__main__":
    main()
