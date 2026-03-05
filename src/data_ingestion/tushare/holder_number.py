#!/usr/bin/env python3
"""
Tushare 股东人数数据抓取模块

功能：
- 抓取个股股东人数 (stk_holdernumber)
- 计算股东人数环比变化率 (holder_num_change)
"""

import sqlite3
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import List

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
    """初始化股东人数表"""
    own_conn = conn is None
    if own_conn:
        conn = get_connection()

    conn.execute("""
        CREATE TABLE IF NOT EXISTS ts_holder_number (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts_code TEXT NOT NULL,
            ann_date TEXT,
            end_date TEXT NOT NULL,
            holder_num INTEGER,
            holder_num_change REAL,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(ts_code, end_date)
        )
    """)
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_ts_hn_code ON ts_holder_number(ts_code)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_ts_hn_end_date ON ts_holder_number(end_date)"
    )
    conn.commit()

    if own_conn:
        conn.close()
    log("股东人数表初始化完成")


# ============================================================
# 单股抓取
# ============================================================

def fetch_holder_number(ts_code: str, client: TushareAdapter = None, conn=None) -> int:
    """
    获取指定股票的股东人数，并计算环比变化率。

    Args:
        ts_code: 股票代码 (e.g. '000001.SZ')
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
        df = client.stk_holdernumber(ts_code=ts_code)

        if df is None or df.empty:
            log(f"   {ts_code} 无股东人数数据")
            return 0

        # 按 end_date 升序排列，以便计算环比
        df = df.sort_values("end_date").reset_index(drop=True)

        count = 0
        prev_holder_num = None

        for _, row in df.iterrows():
            holder_num = row.get("holder_num")
            holder_num_change = None

            if prev_holder_num is not None and prev_holder_num != 0 and holder_num is not None:
                holder_num_change = round(
                    (holder_num - prev_holder_num) / prev_holder_num * 100, 2
                )

            try:
                conn.execute("""
                    INSERT OR REPLACE INTO ts_holder_number
                    (ts_code, ann_date, end_date, holder_num, holder_num_change, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (
                    row.get("ts_code"),
                    row.get("ann_date"),
                    row.get("end_date"),
                    holder_num,
                    holder_num_change,
                    datetime.now().isoformat(),
                ))
                count += 1
            except Exception as e:
                log(f"   保存 {ts_code} end_date={row.get('end_date')} 失败: {e}")

            prev_holder_num = holder_num

        conn.commit()
        return count

    finally:
        if own_conn:
            conn.close()


# ============================================================
# 批量抓取
# ============================================================

def fetch_all_holder_numbers(client: TushareAdapter = None) -> int:
    """
    批量抓取所有活跃股票的股东人数。

    Args:
        client: TushareAdapter 实例（可选）

    Returns:
        总保存记录数
    """
    log("=" * 50)
    log("Tushare 股东人数批量抓取")
    log("=" * 50)

    init_tables()

    if client is None:
        client = get_tushare_client()

    conn = get_connection()

    try:
        cursor = conn.execute("SELECT ts_code FROM ts_stock_basic WHERE list_status = 'L'")
        codes = [
            row["ts_code"] if isinstance(row, sqlite3.Row) else row[0]
            for row in cursor.fetchall()
        ]
        log(f"共 {len(codes)} 只活跃股票")

        total = 0
        for i, ts_code in enumerate(codes):
            if (i + 1) % 50 == 0:
                log(f"[{i + 1}/{len(codes)}] 已处理...")

            try:
                count = fetch_holder_number(ts_code, client=client, conn=conn)
                total += count
            except Exception as e:
                log(f"   {ts_code} 抓取失败: {e}")

            # Tushare API 限流：每分钟约 200 次
            time.sleep(0.35)
    finally:
        conn.close()

    log(f"完成! 共保存 {total} 条股东人数记录")
    return total


# ============================================================
# 主函数
# ============================================================

def main():
    log("=" * 50)
    log("Tushare 股东人数抓取")
    log("=" * 50)
    fetch_all_holder_numbers()


if __name__ == "__main__":
    main()
