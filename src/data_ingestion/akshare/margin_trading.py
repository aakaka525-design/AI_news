#!/usr/bin/env python3
"""
融资融券数据获取模块

获取A股融资融券标的每日数据
数据源：akshare (上交所/深交所)
"""

import sqlite3
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

import akshare as ak

PROJECT_ROOT = Path(__file__).resolve().parents[3]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# 使用公共数据库模块
from src.database.connection import get_connection, STOCKS_DB_PATH


def log(msg: str):
    """格式化输出日志信息。"""
    ts = datetime.now().strftime("%H:%M:%S")
    print(f"[{ts}] {msg}", flush=True)


def init_margin_table():
    """初始化融资融券表"""
    conn = get_connection()
    
    # 融资融券个股明细
    conn.execute("""
        CREATE TABLE IF NOT EXISTS margin_trading (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            stock_code TEXT NOT NULL,
            stock_name TEXT,
            date TEXT NOT NULL,
            market TEXT,                 -- 沪市/深市
            
            -- 融资数据
            margin_balance REAL,         -- 融资余额（元）
            margin_buy REAL,             -- 融资买入额（元）
            margin_repay REAL,           -- 融资偿还额（元）
            
            -- 融券数据
            short_balance REAL,          -- 融券余量（股）
            short_sell REAL,             -- 融券卖出量（股）
            short_repay REAL,            -- 融券偿还量（股）
            
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(stock_code, date)
        )
    """)
    
    # 融资融券市场汇总
    conn.execute("""
        CREATE TABLE IF NOT EXISTS margin_market_summary (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT NOT NULL,
            market TEXT NOT NULL,        -- 沪市/深市
            
            margin_balance REAL,         -- 融资余额
            margin_buy REAL,             -- 融资买入额
            short_balance_shares REAL,   -- 融券余量（股）
            short_balance_value REAL,    -- 融券余量金额
            short_sell REAL,             -- 融券卖出量
            total_balance REAL,          -- 融资融券余额
            
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(date, market)
        )
    """)
    
    conn.execute("CREATE INDEX IF NOT EXISTS idx_margin_code ON margin_trading(stock_code)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_margin_date ON margin_trading(date)")
    conn.commit()
    conn.close()
    log("融资融券表初始化完成")


def fetch_margin_detail_sse(date: str):
    """获取沪市融资融券明细"""
    try:
        df = ak.stock_margin_detail_sse(date=date)
        if df.empty:
            return []
        
        results = []
        for _, row in df.iterrows():
            code = str(row.get("标的证券代码", "")).zfill(6)
            # 跳过ETF等非股票
            if not code.startswith(("6", "0", "3")):
                continue
            
            results.append({
                "stock_code": code,
                "stock_name": row.get("标的证券简称"),
                "date": f"{date[:4]}-{date[4:6]}-{date[6:8]}",
                "market": "沪市",
                "margin_balance": row.get("融资余额"),
                "margin_buy": row.get("融资买入额"),
                "margin_repay": row.get("融资偿还额"),
                "short_balance": row.get("融券余量"),
                "short_sell": row.get("融券卖出量"),
                "short_repay": row.get("融券偿还量"),
            })
        return results
    except Exception as e:
        log(f"   沪市明细获取失败: {e}")
        return []


def fetch_margin_detail_szse(date: str):
    """获取深市融资融券明细"""
    try:
        df = ak.stock_margin_detail_szse(date=date)
        if df.empty:
            return []
        
        results = []
        for _, row in df.iterrows():
            code = str(row.get("证券代码", "")).zfill(6)
            # 跳过ETF等非股票
            if not code.startswith(("6", "0", "3")):
                continue
            
            results.append({
                "stock_code": code,
                "stock_name": row.get("证券简称"),
                "date": f"{date[:4]}-{date[4:6]}-{date[6:8]}",
                "market": "深市",
                "margin_balance": row.get("融资余额"),
                "margin_buy": row.get("融资买入额"),
                "margin_repay": row.get("融资偿还额"),
                "short_balance": row.get("融券余量"),
                "short_sell": row.get("融券卖出量"),
                "short_repay": row.get("融券偿还量"),
            })
        return results
    except Exception as e:
        log(f"   深市明细获取失败: {e}")
        return []


def fetch_market_summary(start_date: str, end_date: str):
    """获取市场融资融券汇总"""
    results = []
    
    # 沪市
    try:
        df = ak.stock_margin_sse(start_date=start_date, end_date=end_date)
        for _, row in df.iterrows():
            date_str = str(row.get("信用交易日期", ""))
            results.append({
                "date": f"{date_str[:4]}-{date_str[4:6]}-{date_str[6:8]}",
                "market": "沪市",
                "margin_balance": row.get("融资余额"),
                "margin_buy": row.get("融资买入额"),
                "short_balance_shares": row.get("融券余量"),
                "short_balance_value": row.get("融券余量金额"),
                "short_sell": row.get("融券卖出量"),
                "total_balance": row.get("融资融券余额"),
            })
        log(f"   沪市汇总: {len(df)} 天")
    except Exception as e:
        log(f"   沪市汇总获取失败: {e}")
    
    # 深市
    try:
        df = ak.stock_margin_szse(start_date=start_date, end_date=end_date)
        for _, row in df.iterrows():
            date_str = str(row.get("信用交易日期", ""))
            results.append({
                "date": f"{date_str[:4]}-{date_str[4:6]}-{date_str[6:8]}",
                "market": "深市",
                "margin_balance": row.get("融资余额"),
                "margin_buy": row.get("融资买入额"),
                "short_balance_shares": row.get("融券余量"),
                "short_balance_value": row.get("融券余量金额"),
                "short_sell": row.get("融券卖出量"),
                "total_balance": row.get("融资融券余额"),
            })
        log(f"   深市汇总: {len(df)} 天")
    except Exception as e:
        log(f"   深市汇总获取失败: {e}")
    
    return results


def save_margin_data(records: list):
    """保存融资融券数据（带验证）"""
    if not records:
        return 0
    
    from src.data_ingestion.akshare.models import MarginTrading
    from src.database.connection import validate_and_create, insert_validated
    
    conn = get_connection()
    count = 0
    for r in records:
        validated = validate_and_create(MarginTrading, r)
        if validated and insert_validated(conn, "margin_trading", validated, 
                                          ["stock_code", "date"]):
            count += 1
    conn.commit()
    conn.close()
    return count


def save_market_summary(records: list):
    """保存市场汇总数据"""
    if not records:
        return 0
    
    conn = get_connection()
    count = 0
    for r in records:
        try:
            conn.execute("""
                INSERT OR REPLACE INTO margin_market_summary
                (date, market, margin_balance, margin_buy, short_balance_shares,
                 short_balance_value, short_sell, total_balance, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                r["date"],
                r["market"],
                r.get("margin_balance"),
                r.get("margin_buy"),
                r.get("short_balance_shares"),
                r.get("short_balance_value"),
                r.get("short_sell"),
                r.get("total_balance"),
                datetime.now().isoformat()
            ))
            count += 1
        except Exception:
            pass
    conn.commit()
    conn.close()
    return count


def fetch_margin_trading(days: int = 1):
    """获取融资融券数据"""
    log(f"📊 获取融资融券数据（最近{days}天）...")
    
    total_detail = 0
    total_summary = 0
    
    # 获取日期范围
    end_date = datetime.now()
    
    # 获取市场汇总（历史）
    if days > 1:
        start_date = (end_date - timedelta(days=days)).strftime("%Y%m%d")
        end_date_str = end_date.strftime("%Y%m%d")
        log("   获取市场汇总...")
        summary = fetch_market_summary(start_date, end_date_str)
        total_summary = save_market_summary(summary)
        log(f"   市场汇总: {total_summary} 条")
    
    # 获取每日明细
    for i in range(days):
        date = (end_date - timedelta(days=i))
        # 跳过周末
        if date.weekday() >= 5:
            continue
        date_str = date.strftime("%Y%m%d")
        log(f"   获取 {date_str} 明细...")
        
        # 沪市
        sse_data = fetch_margin_detail_sse(date_str)
        sse_count = save_margin_data(sse_data)
        
        # 深市
        szse_data = fetch_margin_detail_szse(date_str)
        szse_count = save_margin_data(szse_data)
        
        total_detail += sse_count + szse_count
        log(f"   {date_str}: 沪市 {sse_count} + 深市 {szse_count} = {sse_count + szse_count} 条")
        
        time.sleep(0.5)  # 避免请求过快
    
    log(f"   ✅ 融资融券: 明细 {total_detail} 条，汇总 {total_summary} 条")
    return total_detail, total_summary


def main():
    import argparse
    parser = argparse.ArgumentParser(description="融资融券数据获取")
    parser.add_argument("--days", type=int, default=1, help="获取最近N天数据（默认1天）")
    args = parser.parse_args()
    
    log("=" * 50)
    log(f"融资融券数据获取（{args.days}天）")
    log(f"数据库: {STOCKS_DB_PATH}")
    log("=" * 50)
    
    init_margin_table()
    fetch_margin_trading(args.days)
    
    # 统计
    conn = get_connection()
    cursor = conn.execute("""
        SELECT COUNT(*), COUNT(DISTINCT date), MIN(date), MAX(date)
        FROM margin_trading
    """)
    count, days_count, min_date, max_date = cursor.fetchone()
    conn.close()
    
    log(f"📊 融资融券: {count} 条记录，覆盖 {days_count} 个交易日")
    if min_date and max_date:
        log(f"   日期范围: {min_date} ~ {max_date}")
    log("✅ 完成!")


if __name__ == "__main__":
    main()
