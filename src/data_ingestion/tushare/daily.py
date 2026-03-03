#!/usr/bin/env python3
"""
Tushare 日线数据抓取模块

功能：
- 批量获取全市场日线数据
- 自动限流（300请求/分钟）
- 增量更新（只抓取缺失日期）
"""

import sqlite3
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Optional
import pandas as pd

# 添加项目根目录到 sys.path
PROJECT_ROOT = Path(__file__).resolve().parents[3]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.database.connection import get_connection, STOCKS_DB_PATH
from src.data_ingestion.tushare.client import TushareAdapter, get_tushare_client


def log(msg: str):
    ts = datetime.now().strftime("%H:%M:%S")
    print(f"[{ts}] {msg}", flush=True)


# ============================================================
# 表初始化
# ============================================================

def init_tables():
    """初始化 Tushare 格式的表结构"""
    conn = get_connection()
    
    # 股票基础信息表
    conn.execute("""
        CREATE TABLE IF NOT EXISTS ts_stock_basic (
            ts_code TEXT PRIMARY KEY,
            symbol TEXT NOT NULL,
            name TEXT NOT NULL,
            area TEXT,
            industry TEXT,
            fullname TEXT,
            market TEXT,
            exchange TEXT,
            list_status TEXT DEFAULT 'L',
            list_date TEXT,
            delist_date TEXT,
            is_hs TEXT,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    # 日线行情表（Tushare 标准）
    conn.execute("""
        CREATE TABLE IF NOT EXISTS ts_daily (
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
            adj_factor REAL,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(ts_code, trade_date)
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_ts_daily_code ON ts_daily(ts_code)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_ts_daily_date ON ts_daily(trade_date)")
    
    # 每日指标表（估值）
    conn.execute("""
        CREATE TABLE IF NOT EXISTS ts_daily_basic (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts_code TEXT NOT NULL,
            trade_date TEXT NOT NULL,
            volume_ratio REAL,
            pe REAL,
            pe_ttm REAL,
            pb REAL,
            ps REAL,
            ps_ttm REAL,
            dv_ratio REAL,
            dv_ttm REAL,
            total_mv REAL,
            circ_mv REAL,
            total_share REAL,
            float_share REAL,
            free_share REAL,
            turnover_rate REAL,
            turnover_rate_f REAL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(ts_code, trade_date)
        )
    """)
    cols = {row[1] for row in conn.execute("PRAGMA table_info(ts_daily_basic)").fetchall()}
    if "volume_ratio" not in cols:
        conn.execute("ALTER TABLE ts_daily_basic ADD COLUMN volume_ratio REAL")
    if "created_at" not in cols:
        conn.execute("ALTER TABLE ts_daily_basic ADD COLUMN created_at TIMESTAMP")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_ts_basic_code ON ts_daily_basic(ts_code)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_ts_basic_date ON ts_daily_basic(trade_date)")
    
    conn.commit()
    conn.close()
    log("✅ Tushare 表结构初始化完成")


# ============================================================
# 股票列表
# ============================================================

def fetch_stock_list(client: TushareAdapter = None) -> int:
    """获取全部上市股票列表"""
    log("📋 获取股票列表...")
    
    if client is None:
        client = get_tushare_client()
    
    conn = get_connection()
    
    try:
        df = client.stock_basic(list_status='L')
        
        if df is None or df.empty:
            log("   ⚠️ 无数据")
            return 0
        
        log(f"   获取到 {len(df)} 只股票")
        
        count = 0
        for _, row in df.iterrows():
            try:
                conn.execute("""
                    INSERT OR REPLACE INTO ts_stock_basic
                    (ts_code, symbol, name, area, industry, fullname, market, 
                     exchange, list_status, list_date, delist_date, is_hs, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    row.get('ts_code'),
                    row.get('symbol'),
                    row.get('name'),
                    row.get('area'),
                    row.get('industry'),
                    row.get('fullname'),
                    row.get('market'),
                    row.get('exchange'),
                    row.get('list_status'),
                    row.get('list_date'),
                    row.get('delist_date'),
                    row.get('is_hs'),
                    datetime.now().isoformat()
                ))
                count += 1
            except Exception as e:
                log(f"   ⚠️ 保存 {row.get('ts_code')} 失败: {e}")
        
        conn.commit()
        log(f"   ✅ 保存 {count} 只股票")
        return count
        
    finally:
        conn.close()


def get_all_ts_codes() -> List[str]:
    """获取所有股票的 ts_code 列表"""
    conn = get_connection()
    cursor = conn.execute("SELECT ts_code FROM ts_stock_basic WHERE list_status = 'L'")
    codes = [
        row["ts_code"] if isinstance(row, sqlite3.Row) else row[0]
        for row in cursor.fetchall()
    ]
    conn.close()
    return codes


# ============================================================
# 日线数据
# ============================================================

def fetch_daily_by_date(trade_date: str, client: TushareAdapter = None) -> int:
    """
    按日期获取全市场日线数据
    
    Args:
        trade_date: 交易日期 (YYYYMMDD)
        client: TushareAdapter 实例
        
    Returns:
        保存的记录数
    """
    log(f"📈 获取 {trade_date} 日线数据...")
    
    if client is None:
        client = get_tushare_client()
    
    conn = get_connection()
    
    try:
        # 获取日线
        df = client.daily(trade_date=trade_date)
        
        if df is None or df.empty:
            log(f"   ⚠️ {trade_date} 无数据（可能非交易日）")
            return 0
        
        log(f"   获取到 {len(df)} 条日线数据")
        
        # 获取复权因子
        adj_df = client.adj_factor(trade_date=trade_date)
        adj_dict = {}
        if adj_df is not None and not adj_df.empty:
            adj_dict = dict(zip(adj_df['ts_code'], adj_df['adj_factor']))
        
        count = 0
        for _, row in df.iterrows():
            try:
                ts_code = row.get('ts_code')
                adj = adj_dict.get(ts_code)
                
                conn.execute("""
                    INSERT OR REPLACE INTO ts_daily
                    (ts_code, trade_date, open, high, low, close, pre_close,
                     change, pct_chg, vol, amount, adj_factor, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    ts_code,
                    trade_date,
                    row.get('open'),
                    row.get('high'),
                    row.get('low'),
                    row.get('close'),
                    row.get('pre_close'),
                    row.get('change'),
                    row.get('pct_chg'),
                    row.get('vol'),
                    row.get('amount'),
                    adj,
                    datetime.now().isoformat()
                ))
                count += 1
            except Exception as e:
                log(f"   ⚠️ 保存 {row.get('ts_code')} 失败: {e}")
        
        conn.commit()
        log(f"   ✅ 保存 {count} 条")
        return count
        
    finally:
        conn.close()


def fetch_daily_basic_by_date(trade_date: str, client: TushareAdapter = None) -> int:
    """
    按日期获取每日指标（估值）
    """
    log(f"📊 获取 {trade_date} 估值数据...")
    
    if client is None:
        client = get_tushare_client()
    
    conn = get_connection()
    
    try:
        df = client.daily_basic(trade_date=trade_date)
        
        if df is None or df.empty:
            log(f"   ⚠️ {trade_date} 无数据")
            return 0
        
        log(f"   获取到 {len(df)} 条估值数据")
        
        count = 0
        for _, row in df.iterrows():
            try:
                conn.execute("""
                    INSERT OR REPLACE INTO ts_daily_basic
                    (ts_code, trade_date, volume_ratio, pe, pe_ttm, pb, ps, ps_ttm,
                     dv_ratio, dv_ttm, total_mv, circ_mv, total_share,
                     float_share, free_share, turnover_rate, turnover_rate_f, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    row.get('ts_code'),
                    trade_date,
                    row.get('volume_ratio'),
                    row.get('pe'),
                    row.get('pe_ttm'),
                    row.get('pb'),
                    row.get('ps'),
                    row.get('ps_ttm'),
                    row.get('dv_ratio'),
                    row.get('dv_ttm'),
                    row.get('total_mv'),
                    row.get('circ_mv'),
                    row.get('total_share'),
                    row.get('float_share'),
                    row.get('free_share'),
                    row.get('turnover_rate'),
                    row.get('turnover_rate_f'),
                    datetime.now().isoformat(),
                    datetime.now().isoformat()
                ))
                count += 1
            except Exception as e:
                log(f"   ⚠️ 保存估值 {row.get('ts_code')} 失败: {e}")
        
        conn.commit()
        log(f"   ✅ 保存 {count} 条")
        return count
        
    finally:
        conn.close()


def fetch_daily_by_stock(ts_code: str, start_date: str, end_date: str, 
                         client: TushareAdapter = None) -> int:
    """
    按股票获取日线数据
    
    Args:
        ts_code: 股票代码
        start_date: 开始日期
        end_date: 结束日期
        
    Returns:
        保存的记录数
    """
    if client is None:
        client = get_tushare_client()
    
    conn = get_connection()
    
    try:
        df = client.daily(ts_code=ts_code, start_date=start_date, end_date=end_date)
        
        if df is None or df.empty:
            return 0
        
        # 获取复权因子
        adj_df = client.adj_factor(ts_code=ts_code, start_date=start_date, end_date=end_date)
        adj_dict = {}
        if adj_df is not None and not adj_df.empty:
            adj_dict = dict(zip(adj_df['trade_date'], adj_df['adj_factor']))
        
        count = 0
        for _, row in df.iterrows():
            try:
                td = row.get('trade_date')
                adj = adj_dict.get(td)
                
                conn.execute("""
                    INSERT OR REPLACE INTO ts_daily
                    (ts_code, trade_date, open, high, low, close, pre_close,
                     change, pct_chg, vol, amount, adj_factor, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    ts_code,
                    td,
                    row.get('open'),
                    row.get('high'),
                    row.get('low'),
                    row.get('close'),
                    row.get('pre_close'),
                    row.get('change'),
                    row.get('pct_chg'),
                    row.get('vol'),
                    row.get('amount'),
                    adj,
                    datetime.now().isoformat()
                ))
                count += 1
            except Exception as e:
                log(f"   ⚠️ 保存日线 {ts_code} {td} 失败: {e}")
        
        conn.commit()
        return count
        
    finally:
        conn.close()


# ============================================================
# 批量抓取
# ============================================================

def fetch_history_by_date_range(start_date: str, end_date: str = None) -> int:
    """
    按日期范围批量抓取数据
    
    Args:
        start_date: 开始日期 (YYYYMMDD)
        end_date: 结束日期，默认今天
        
    Returns:
        总记录数
    """
    log("=" * 50)
    log("Tushare 日线数据批量抓取")
    log("=" * 50)
    
    if end_date is None:
        end_date = datetime.now().strftime('%Y%m%d')
    
    init_tables()
    
    client = get_tushare_client()
    
    # 获取交易日历
    trading_days = client.get_trading_days(start_date=start_date, end_date=end_date)
    log(f"📅 交易日: {len(trading_days)} 天 ({start_date} ~ {end_date})")
    
    total = 0
    for i, trade_date in enumerate(trading_days):
        log(f"\n[{i+1}/{len(trading_days)}] {trade_date}")
        
        # 日线
        count1 = fetch_daily_by_date(trade_date, client)
        
        # 估值
        count2 = fetch_daily_basic_by_date(trade_date, client)
        
        total += count1 + count2
        
        # 显示统计
        stats = client.get_stats()
        log(f"   累计请求: {stats['total_requests']} 次, 速率: {stats['requests_per_minute']:.1f}/分钟")
    
    log(f"\n✅ 完成! 共保存 {total} 条记录")
    return total


def fetch_batch_stocks(ts_codes: List[str], start_date: str, end_date: str = None,
                       batch_size: int = 100) -> int:
    """
    批量按股票抓取（适用于历史数据补全）
    
    Args:
        ts_codes: 股票代码列表
        start_date: 开始日期
        end_date: 结束日期
        batch_size: 每批数量
        
    Returns:
        总记录数
    """
    log(f"📈 批量抓取 {len(ts_codes)} 只股票...")
    
    if end_date is None:
        end_date = datetime.now().strftime('%Y%m%d')
    
    client = get_tushare_client()
    total = 0
    
    for i in range(0, len(ts_codes), batch_size):
        batch = ts_codes[i:i + batch_size]
        log(f"\n[批次 {i//batch_size + 1}] {len(batch)} 只股票")
        
        for ts_code in batch:
            count = fetch_daily_by_stock(ts_code, start_date, end_date, client)
            total += count
        
        stats = client.get_stats()
        log(f"   累计: {total} 条, 请求: {stats['total_requests']} 次")
    
    return total


# ============================================================
# 主函数
# ============================================================

def main():
    """主入口"""
    log("=" * 50)
    log("Tushare 日线数据抓取")
    log("=" * 50)
    
    init_tables()
    
    client = get_tushare_client()
    
    # 1. 获取股票列表
    fetch_stock_list(client)
    
    # 2. 抓取最近 5 个交易日
    end_date = datetime.now().strftime('%Y%m%d')
    start_date = (datetime.now() - timedelta(days=10)).strftime('%Y%m%d')
    
    trading_days = client.get_trading_days(start_date=start_date, end_date=end_date)
    
    for trade_date in trading_days[-5:]:
        fetch_daily_by_date(trade_date, client)
        fetch_daily_basic_by_date(trade_date, client)
    
    # 统计
    stats = client.get_stats()
    log(f"\n📊 Tushare 请求统计:")
    log(f"   总请求: {stats['total_requests']} 次")
    log(f"   耗时: {stats['elapsed_seconds']:.1f} 秒")
    log(f"   速率: {stats['requests_per_minute']:.1f} 次/分钟")
    
    log("\n✅ 完成!")


if __name__ == "__main__":
    main()
