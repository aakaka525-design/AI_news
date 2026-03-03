#!/usr/bin/env python3
"""
Tushare 龙虎榜数据抓取模块

功能：
- 获取龙虎榜每日明细 (top_list)
- 获取机构席位明细 (top_inst)
"""

import sqlite3
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import List
import pandas as pd

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

def init_tables():
    """初始化龙虎榜表"""
    conn = get_connection()
    
    # 龙虎榜每日明细
    conn.execute("""
        CREATE TABLE IF NOT EXISTS ts_top_list (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            trade_date TEXT NOT NULL,
            ts_code TEXT NOT NULL,
            name TEXT,
            close REAL,
            pct_change REAL,
            turnover_rate REAL,
            amount REAL,
            l_sell REAL,
            l_buy REAL,
            l_amount REAL,
            net_amount REAL,
            net_rate REAL,
            amount_rate REAL,
            reason TEXT,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(trade_date, ts_code)
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_ts_top_date ON ts_top_list(trade_date)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_ts_top_code ON ts_top_list(ts_code)")
    
    # 机构席位明细
    conn.execute("""
        CREATE TABLE IF NOT EXISTS ts_top_inst (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            trade_date TEXT NOT NULL,
            ts_code TEXT NOT NULL,
            exalter TEXT,
            side TEXT,
            buy REAL,
            buy_rate REAL,
            sell REAL,
            sell_rate REAL,
            net_buy REAL,
            reason TEXT,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(trade_date, ts_code, exalter, side)
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_ts_inst_date ON ts_top_inst(trade_date)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_ts_inst_code ON ts_top_inst(ts_code)")
    
    conn.commit()
    conn.close()
    log("✅ 龙虎榜表初始化完成")


# ============================================================
# 龙虎榜数据
# ============================================================

def fetch_top_list_by_date(trade_date: str, client: TushareAdapter = None) -> int:
    """
    获取指定日期的龙虎榜数据
    
    Args:
        trade_date: 交易日期 (YYYYMMDD)
        
    Returns:
        保存的记录数
    """
    log(f"🐲 获取 {trade_date} 龙虎榜数据...")
    
    if client is None:
        client = get_tushare_client()
    
    conn = get_connection()
    
    try:
        df = client.top_list(trade_date=trade_date)
        
        if df is None or df.empty:
            log(f"   ⚠️ {trade_date} 无龙虎榜数据")
            return 0
        
        log(f"   获取到 {len(df)} 条龙虎榜记录")
        
        count = 0
        for _, row in df.iterrows():
            try:
                conn.execute("""
                    INSERT OR REPLACE INTO ts_top_list
                    (trade_date, ts_code, name, close, pct_change, turnover_rate,
                     amount, l_sell, l_buy, l_amount, net_amount, net_rate,
                     amount_rate, reason, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    trade_date,
                    row.get('ts_code'),
                    row.get('name'),
                    row.get('close'),
                    row.get('pct_change'),
                    row.get('turnover_rate'),
                    row.get('amount'),
                    row.get('l_sell'),
                    row.get('l_buy'),
                    row.get('l_amount'),
                    row.get('net_amount'),
                    row.get('net_rate'),
                    row.get('amount_rate'),
                    row.get('reason'),
                    datetime.now().isoformat()
                ))
                count += 1
            except Exception as e:
                log(f"   ⚠️ 保存龙虎榜 {row.get('ts_code')} 失败: {e}")
        
        conn.commit()
        log(f"   ✅ 保存 {count} 条")
        return count
        
    finally:
        conn.close()


def fetch_top_inst_by_date(trade_date: str, client: TushareAdapter = None) -> int:
    """
    获取机构席位明细
    """
    log(f"🏛️ 获取 {trade_date} 机构席位...")
    
    if client is None:
        client = get_tushare_client()
    
    conn = get_connection()
    
    try:
        df = client.top_inst(trade_date=trade_date)
        
        if df is None or df.empty:
            log(f"   ⚠️ {trade_date} 无机构数据")
            return 0
        
        log(f"   获取到 {len(df)} 条机构记录")
        
        count = 0
        for _, row in df.iterrows():
            try:
                exalter = row.get('exalter') or ''
                side = row.get('side') or ''
                conn.execute("""
                    INSERT OR REPLACE INTO ts_top_inst
                    (trade_date, ts_code, exalter, side, buy, buy_rate,
                     sell, sell_rate, net_buy, reason, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    trade_date,
                    row.get('ts_code'),
                    exalter,
                    side,
                    row.get('buy'),
                    row.get('buy_rate'),
                    row.get('sell'),
                    row.get('sell_rate'),
                    row.get('net_buy'),
                    row.get('reason'),
                    datetime.now().isoformat()
                ))
                count += 1
            except Exception as e:
                log(f"   ⚠️ 保存机构席位 {row.get('ts_code')} 失败: {e}")
        
        conn.commit()
        log(f"   ✅ 保存 {count} 条")
        return count
        
    finally:
        conn.close()


def fetch_top_list_range(start_date: str, end_date: str = None) -> int:
    """
    批量获取龙虎榜数据
    
    Args:
        start_date: 开始日期
        end_date: 结束日期
        
    Returns:
        总记录数
    """
    log("=" * 50)
    log("Tushare 龙虎榜批量抓取")
    log("=" * 50)
    
    if end_date is None:
        end_date = datetime.now().strftime('%Y%m%d')
    
    init_tables()
    client = get_tushare_client()
    
    # 获取交易日
    trading_days = client.get_trading_days(start_date=start_date, end_date=end_date)
    log(f"📅 交易日: {len(trading_days)} 天")
    
    total = 0
    for trade_date in trading_days:
        count1 = fetch_top_list_by_date(trade_date, client)
        count2 = fetch_top_inst_by_date(trade_date, client)
        total += count1 + count2
    
    log(f"\n✅ 完成! 共 {total} 条龙虎榜记录")
    return total


# ============================================================
# 主函数
# ============================================================

def main():
    log("=" * 50)
    log("Tushare 龙虎榜抓取")
    log("=" * 50)
    
    init_tables()
    
    # 抓取最近 5 天
    end_date = datetime.now().strftime('%Y%m%d')
    start_date = (datetime.now() - timedelta(days=10)).strftime('%Y%m%d')
    
    fetch_top_list_range(start_date, end_date)
    
    log("\n✅ 完成!")


if __name__ == "__main__":
    main()
