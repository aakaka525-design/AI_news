#!/usr/bin/env python3
"""
Tushare 业绩快报 / 业绩预告数据抓取模块

功能：
- 抓取业绩快报 (express)
- 抓取业绩预告 (forecast)
"""

import sqlite3
import sys
import time
from datetime import datetime
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
    """初始化业绩快报和业绩预告表"""
    own_conn = conn is None
    if own_conn:
        conn = get_connection()

    conn.execute("""
        CREATE TABLE IF NOT EXISTS ts_express (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts_code TEXT NOT NULL,
            ann_date TEXT,
            end_date TEXT NOT NULL,
            revenue REAL,
            operate_profit REAL,
            total_profit REAL,
            n_income REAL,
            total_assets REAL,
            yoy_net_profit REAL,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(ts_code, end_date)
        )
    """)
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_ts_express_code ON ts_express(ts_code)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_ts_express_end_date ON ts_express(end_date)"
    )

    conn.execute("""
        CREATE TABLE IF NOT EXISTS ts_forecast (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts_code TEXT NOT NULL,
            ann_date TEXT,
            end_date TEXT NOT NULL,
            type TEXT,
            p_change_min REAL,
            p_change_max REAL,
            net_profit_min REAL,
            net_profit_max REAL,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(ts_code, end_date)
        )
    """)
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_ts_forecast_code ON ts_forecast(ts_code)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_ts_forecast_end_date ON ts_forecast(end_date)"
    )

    conn.commit()

    if own_conn:
        conn.close()
    log("业绩快报/预告表初始化完成")


# ============================================================
# 单股抓取 — 业绩快报
# ============================================================

def fetch_express(ts_code: str, client: TushareAdapter = None, conn=None) -> int:
    """
    获取指定股票的业绩快报。

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
        df = client.express(ts_code=ts_code)

        if df is None or df.empty:
            return 0

        count = 0
        for _, row in df.iterrows():
            try:
                conn.execute("""
                    INSERT OR REPLACE INTO ts_express
                    (ts_code, ann_date, end_date, revenue, operate_profit,
                     total_profit, n_income, total_assets, yoy_net_profit, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    row.get("ts_code"),
                    row.get("ann_date"),
                    row.get("end_date"),
                    row.get("revenue"),
                    row.get("operate_profit"),
                    row.get("total_profit"),
                    row.get("n_income"),
                    row.get("total_assets"),
                    row.get("yoy_net_profit"),
                    datetime.now().isoformat(),
                ))
                count += 1
            except Exception as e:
                log(f"   保存 {ts_code} 快报 end_date={row.get('end_date')} 失败: {e}")

        conn.commit()
        return count

    finally:
        if own_conn:
            conn.close()


# ============================================================
# 单股抓取 — 业绩预告
# ============================================================

def fetch_forecast(ts_code: str, client: TushareAdapter = None, conn=None) -> int:
    """
    获取指定股票的业绩预告。

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
        df = client.forecast(ts_code=ts_code)

        if df is None or df.empty:
            return 0

        count = 0
        for _, row in df.iterrows():
            try:
                conn.execute("""
                    INSERT OR REPLACE INTO ts_forecast
                    (ts_code, ann_date, end_date, type, p_change_min,
                     p_change_max, net_profit_min, net_profit_max, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    row.get("ts_code"),
                    row.get("ann_date"),
                    row.get("end_date"),
                    row.get("type"),
                    row.get("p_change_min"),
                    row.get("p_change_max"),
                    row.get("net_profit_min"),
                    row.get("net_profit_max"),
                    datetime.now().isoformat(),
                ))
                count += 1
            except Exception as e:
                log(f"   保存 {ts_code} 预告 end_date={row.get('end_date')} 失败: {e}")

        conn.commit()
        return count

    finally:
        if own_conn:
            conn.close()


# ============================================================
# 批量抓取
# ============================================================

def fetch_all(client: TushareAdapter = None) -> int:
    """
    批量抓取所有活跃股票的业绩快报和业绩预告。

    Args:
        client: TushareAdapter 实例（可选）

    Returns:
        总保存记录数
    """
    log("=" * 50)
    log("Tushare 业绩快报/预告批量抓取")
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
                count = fetch_express(ts_code, client=client, conn=conn)
                total += count
            except Exception as e:
                log(f"   {ts_code} 快报抓取失败: {e}")

            try:
                count = fetch_forecast(ts_code, client=client, conn=conn)
                total += count
            except Exception as e:
                log(f"   {ts_code} 预告抓取失败: {e}")

            # Tushare API 限流：每分钟约 200 次
            time.sleep(0.35)
    finally:
        conn.close()

    log(f"完成! 共保存 {total} 条业绩快报/预告记录")
    return total


# ============================================================
# 主函数
# ============================================================

def main():
    log("=" * 50)
    log("Tushare 业绩快报/预告抓取")
    log("=" * 50)
    fetch_all()


if __name__ == "__main__":
    main()
