#!/usr/bin/env python3
"""
Tushare 资金流向数据抓取模块

功能：
- 个股资金流向 (moneyflow)
- 北向资金十大成交股 (hsgt_top10)
"""

import sqlite3
import sys
from datetime import datetime, timedelta
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

def init_tables():
    """初始化资金流向表"""
    conn = get_connection()
    
    # 个股资金流向
    conn.execute("""
        CREATE TABLE IF NOT EXISTS ts_moneyflow (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts_code TEXT NOT NULL,
            trade_date TEXT NOT NULL,
            buy_sm_vol REAL,
            buy_md_vol REAL,
            buy_lg_vol REAL,
            buy_elg_vol REAL,
            sell_sm_vol REAL,
            sell_md_vol REAL,
            sell_lg_vol REAL,
            sell_elg_vol REAL,
            buy_sm_amount REAL,
            buy_md_amount REAL,
            buy_lg_amount REAL,
            buy_elg_amount REAL,
            sell_sm_amount REAL,
            sell_md_amount REAL,
            sell_lg_amount REAL,
            sell_elg_amount REAL,
            net_mf_vol REAL,
            net_mf_amount REAL,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(ts_code, trade_date)
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_ts_mf_code ON ts_moneyflow(ts_code)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_ts_mf_date ON ts_moneyflow(trade_date)")
    
    # 北向资金十大成交股
    conn.execute("""
        CREATE TABLE IF NOT EXISTS ts_hsgt_top10 (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            trade_date TEXT NOT NULL,
            ts_code TEXT NOT NULL,
            name TEXT,
            close REAL,
            change REAL,
            rank INTEGER,
            market_type TEXT,
            amount REAL,
            net_amount REAL,
            buy REAL,
            sell REAL,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(trade_date, ts_code, market_type)
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_ts_hsgt_date ON ts_hsgt_top10(trade_date)")
    
    conn.commit()
    conn.close()
    log("✅ 资金流向表初始化完成")


# ============================================================
# 个股资金流向
# ============================================================

def fetch_moneyflow_by_date(trade_date: str, client: TushareAdapter = None) -> int:
    """
    获取指定日期的全市场资金流向
    """
    log(f"💰 获取 {trade_date} 资金流向...")
    
    if client is None:
        client = get_tushare_client()
    
    conn = get_connection()
    
    try:
        df = client.moneyflow(trade_date=trade_date)
        
        if df is None or df.empty:
            log(f"   ⚠️ {trade_date} 无数据")
            return 0
        
        log(f"   获取到 {len(df)} 条资金流向数据")
        
        count = 0
        for _, row in df.iterrows():
            try:
                conn.execute("""
                    INSERT OR REPLACE INTO ts_moneyflow
                    (ts_code, trade_date, buy_sm_vol, buy_md_vol, buy_lg_vol, buy_elg_vol,
                     sell_sm_vol, sell_md_vol, sell_lg_vol, sell_elg_vol,
                     buy_sm_amount, buy_md_amount, buy_lg_amount, buy_elg_amount,
                     sell_sm_amount, sell_md_amount, sell_lg_amount, sell_elg_amount,
                     net_mf_vol, net_mf_amount, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    row.get('ts_code'),
                    trade_date,
                    row.get('buy_sm_vol'),
                    row.get('buy_md_vol'),
                    row.get('buy_lg_vol'),
                    row.get('buy_elg_vol'),
                    row.get('sell_sm_vol'),
                    row.get('sell_md_vol'),
                    row.get('sell_lg_vol'),
                    row.get('sell_elg_vol'),
                    row.get('buy_sm_amount'),
                    row.get('buy_md_amount'),
                    row.get('buy_lg_amount'),
                    row.get('buy_elg_amount'),
                    row.get('sell_sm_amount'),
                    row.get('sell_md_amount'),
                    row.get('sell_lg_amount'),
                    row.get('sell_elg_amount'),
                    row.get('net_mf_vol'),
                    row.get('net_mf_amount'),
                    datetime.now().isoformat()
                ))
                count += 1
            except Exception as e:
                log(f"   ⚠️ 保存资金流 {row.get('ts_code')} 失败: {e}")
        
        conn.commit()
        log(f"   ✅ 保存 {count} 条")
        return count
        
    finally:
        conn.close()


# ============================================================
# 北向资金
# ============================================================

def fetch_hsgt_top10_by_date(trade_date: str, client: TushareAdapter = None) -> int:
    """
    获取北向资金十大成交股
    """
    log(f"🔥 获取 {trade_date} 北向资金...")
    
    if client is None:
        client = get_tushare_client()
    
    conn = get_connection()
    
    try:
        # 沪股通 + 深股通
        total_count = 0
        for market_type in ['SH', 'SZ']:
            df = client.hsgt_top10(trade_date=trade_date, market_type=market_type)
            
            if df is None or df.empty:
                continue
            
            for _, row in df.iterrows():
                try:
                    conn.execute("""
                        INSERT OR REPLACE INTO ts_hsgt_top10
                        (trade_date, ts_code, name, close, change, rank, market_type,
                         amount, net_amount, buy, sell, updated_at)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, (
                        trade_date,
                        row.get('ts_code'),
                        row.get('name'),
                        row.get('close'),
                        row.get('change'),
                        row.get('rank'),
                        market_type,
                        row.get('amount'),
                        row.get('net_amount'),
                        row.get('buy'),
                        row.get('sell'),
                        datetime.now().isoformat()
                    ))
                    total_count += 1
                except Exception as e:
                    log(f"   ⚠️ 保存北向 {row.get('ts_code')} 失败: {e}")
        
        conn.commit()
        if total_count > 0:
            log(f"   ✅ 保存 {total_count} 条北向资金记录")
        return total_count
        
    finally:
        conn.close()


# ============================================================
# 批量抓取
# ============================================================

def fetch_moneyflow_range(start_date: str, end_date: str = None) -> int:
    """
    批量抓取资金流向数据
    """
    log("=" * 50)
    log("Tushare 资金流向批量抓取")
    log("=" * 50)
    
    if end_date is None:
        end_date = datetime.now().strftime('%Y%m%d')
    
    init_tables()
    client = get_tushare_client()
    
    trading_days = client.get_trading_days(start_date=start_date, end_date=end_date)
    log(f"📅 交易日: {len(trading_days)} 天")
    
    total = 0
    for i, trade_date in enumerate(trading_days):
        log(f"\n[{i+1}/{len(trading_days)}] {trade_date}")
        
        count1 = fetch_moneyflow_by_date(trade_date, client)
        count2 = fetch_hsgt_top10_by_date(trade_date, client)
        
        total += count1 + count2
        
        stats = client.get_stats()
        log(f"   累计请求: {stats['total_requests']} 次")
    
    log(f"\n✅ 完成! 共 {total} 条记录")
    return total


# ============================================================
# 主函数
# ============================================================

def main():
    log("=" * 50)
    log("Tushare 资金流向抓取")
    log("=" * 50)
    
    init_tables()
    client = get_tushare_client()
    
    # 抓取最近 5 天
    end_date = datetime.now().strftime('%Y%m%d')
    start_date = (datetime.now() - timedelta(days=10)).strftime('%Y%m%d')
    
    trading_days = client.get_trading_days(start_date=start_date, end_date=end_date)
    
    for trade_date in trading_days[-5:]:
        fetch_moneyflow_by_date(trade_date, client)
        fetch_hsgt_top10_by_date(trade_date, client)
    
    stats = client.get_stats()
    log(f"\n📊 请求统计: {stats['total_requests']} 次, {stats['requests_per_minute']:.1f}/分钟")
    log("\n✅ 完成!")


if __name__ == "__main__":
    main()
