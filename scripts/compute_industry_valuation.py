#!/usr/bin/env python3
"""
行业估值中位数计算脚本

按行业计算 PE/PB 的中位数、P25、P75，用于选股器的行业相对估值评估。
过滤规则:
  - PE < 0 (亏损) 排除
  - PE > 500 (极端值) 排除
  - PB <= 0 排除
"""

import sys
import os
import sqlite3
import statistics
from datetime import datetime

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

from src.database.connection import get_connection


def init_table(conn=None):
    """创建 industry_valuation 表。"""
    close_conn = False
    if conn is None:
        conn = get_connection()
        close_conn = True
    try:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS industry_valuation (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                trade_date TEXT NOT NULL,
                industry TEXT NOT NULL,
                pe_median REAL,
                pe_p25 REAL,
                pe_p75 REAL,
                pb_median REAL,
                stock_count INTEGER,
                valid_pe_count INTEGER,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(trade_date, industry)
            )
        """)
        conn.commit()
    finally:
        if close_conn:
            conn.close()


def _percentile(sorted_data, pct):
    """计算百分位数 (线性插值)。

    pct: 0-100 之间的值。
    sorted_data: 已排序的列表。
    """
    if not sorted_data:
        return None
    n = len(sorted_data)
    if n == 1:
        return sorted_data[0]
    # 使用线性插值法 (与 numpy percentile 的 'linear' 方法一致)
    idx = (pct / 100) * (n - 1)
    lo = int(idx)
    hi = lo + 1
    if hi >= n:
        return sorted_data[-1]
    frac = idx - lo
    return sorted_data[lo] + frac * (sorted_data[hi] - sorted_data[lo])


def compute_for_date(trade_date, conn=None):
    """计算指定日期的行业估值中位数。

    对每个行业:
    - 从 ts_daily_basic JOIN ts_stock_basic 获取 PE/PB 数据
    - 过滤 PE < 0 (亏损) 和 PE > 500 (极端值)
    - 计算 PE 的 median, p25, p75
    - 过滤 PB <= 0，计算 PB median
    - 记录 stock_count (总数) 和 valid_pe_count (有效 PE 数)
    """
    close_conn = False
    if conn is None:
        conn = get_connection()
        close_conn = True
    try:
        rows = conn.execute("""
            SELECT b.industry, d.pe_ttm, d.pb
            FROM ts_daily_basic d
            JOIN ts_stock_basic b ON d.ts_code = b.ts_code
            WHERE d.trade_date = ?
              AND b.industry IS NOT NULL
              AND b.industry != ''
        """, (trade_date,)).fetchall()

        # Group by industry
        industries = {}
        for row in rows:
            industry = row["industry"]
            if industry not in industries:
                industries[industry] = []
            industries[industry].append((row["pe_ttm"], row["pb"]))

        updated_at = datetime.now().isoformat()

        for industry, data in industries.items():
            stock_count = len(data)

            # Filter valid PE: > 0 and <= 500
            valid_pe = sorted([pe for pe, _pb in data if pe is not None and 0 < pe <= 500])
            valid_pe_count = len(valid_pe)

            if valid_pe_count > 0:
                pe_median = _percentile(valid_pe, 50)
                pe_p25 = _percentile(valid_pe, 25)
                pe_p75 = _percentile(valid_pe, 75)
            else:
                pe_median = None
                pe_p25 = None
                pe_p75 = None

            # Filter valid PB: > 0
            valid_pb = sorted([pb for _pe, pb in data if pb is not None and pb > 0])
            pb_median = _percentile(valid_pb, 50) if valid_pb else None

            conn.execute("""
                INSERT OR REPLACE INTO industry_valuation
                    (trade_date, industry, pe_median, pe_p25, pe_p75, pb_median,
                     stock_count, valid_pe_count, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (trade_date, industry, pe_median, pe_p25, pe_p75, pb_median,
                  stock_count, valid_pe_count, updated_at))

        conn.commit()
        print(f"[{datetime.now().strftime('%H:%M:%S')}] "
              f"Computed valuation for {len(industries)} industries on {trade_date}")
    finally:
        if close_conn:
            conn.close()


def main():
    """获取最新交易日并计算行业估值。"""
    conn = get_connection()
    try:
        init_table(conn=conn)

        row = conn.execute("SELECT MAX(trade_date) FROM ts_daily_basic").fetchone()
        if row is None or row[0] is None:
            print("No data in ts_daily_basic, nothing to compute.")
            return

        latest_date = row[0]
        print(f"Computing industry valuation for latest date: {latest_date}")
        compute_for_date(latest_date, conn=conn)
    finally:
        conn.close()


if __name__ == "__main__":
    main()
