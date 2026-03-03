#!/usr/bin/env python3
"""
Tushare 财务数据抓取模块

功能：
- 获取财务指标 (fina_indicator)
- 获取利润表 (income)
- 获取资产负债表 (balancesheet)
"""

import sqlite3
import sys
from datetime import datetime
from pathlib import Path
from typing import List, Optional

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
    """初始化财务数据表"""
    conn = get_connection()
    
    # 财务指标表
    conn.execute("""
        CREATE TABLE IF NOT EXISTS ts_fina_indicator (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts_code TEXT NOT NULL,
            ann_date TEXT,
            end_date TEXT NOT NULL,
            
            -- 每股指标
            eps REAL,
            dt_eps REAL,
            bps REAL,
            ocfps REAL,
            grps REAL,
            
            -- 盈利能力
            roe REAL,
            roe_waa REAL,
            roe_dt REAL,
            roa REAL,
            npta REAL,
            roic REAL,
            
            -- 利润率
            grossprofit_margin REAL,
            netprofit_margin REAL,
            op_of_gr REAL,
            
            -- 增长率
            or_yoy REAL,
            op_yoy REAL,
            tp_yoy REAL,
            netprofit_yoy REAL,
            dt_netprofit_yoy REAL,
            
            -- 偿债能力
            debt_to_assets REAL,
            current_ratio REAL,
            quick_ratio REAL,
            
            -- 营运能力
            ar_turn REAL,
            inv_turn REAL,
            fa_turn REAL,
            assets_turn REAL,
            
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(ts_code, end_date)
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_ts_fina_code ON ts_fina_indicator(ts_code)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_ts_fina_date ON ts_fina_indicator(end_date)")
    
    conn.commit()
    conn.close()
    log("✅ 财务数据表初始化完成")


# ============================================================
# 财务指标
# ============================================================

def fetch_fina_indicator_by_stock(ts_code: str, client: TushareAdapter = None) -> int:
    """
    获取单只股票的财务指标
    
    Args:
        ts_code: 股票代码
        
    Returns:
        保存的记录数
    """
    if client is None:
        client = get_tushare_client()
    
    conn = get_connection()
    
    try:
        df = client.fina_indicator(ts_code=ts_code)
        
        if df is None or df.empty:
            return 0
        
        count = 0
        for _, row in df.iterrows():
            try:
                conn.execute("""
                    INSERT OR REPLACE INTO ts_fina_indicator
                    (ts_code, ann_date, end_date, eps, dt_eps, bps, ocfps, grps,
                     roe, roe_waa, roe_dt, roa, npta, roic,
                     grossprofit_margin, netprofit_margin, op_of_gr,
                     or_yoy, op_yoy, tp_yoy, netprofit_yoy, dt_netprofit_yoy,
                     debt_to_assets, current_ratio, quick_ratio,
                     ar_turn, inv_turn, fa_turn, assets_turn, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    ts_code,
                    row.get('ann_date'),
                    row.get('end_date'),
                    row.get('eps'),
                    row.get('dt_eps'),
                    row.get('bps'),
                    row.get('ocfps'),
                    row.get('grps'),
                    row.get('roe'),
                    row.get('roe_waa'),
                    row.get('roe_dt'),
                    row.get('roa'),
                    row.get('npta'),
                    row.get('roic'),
                    row.get('grossprofit_margin'),
                    row.get('netprofit_margin'),
                    row.get('op_of_gr'),
                    row.get('or_yoy'),
                    row.get('op_yoy'),
                    row.get('tp_yoy'),
                    row.get('netprofit_yoy'),
                    row.get('dt_netprofit_yoy'),
                    row.get('debt_to_assets'),
                    row.get('current_ratio'),
                    row.get('quick_ratio'),
                    row.get('ar_turn'),
                    row.get('inv_turn'),
                    row.get('fa_turn'),
                    row.get('assets_turn'),
                    datetime.now().isoformat()
                ))
                count += 1
            except Exception as e:
                log(f"   ⚠️ 保存财务指标 {ts_code} {row.get('end_date')} 失败: {e}")
        
        conn.commit()
        return count
        
    finally:
        conn.close()


def fetch_fina_batch(ts_codes: List[str], batch_size: int = 100) -> int:
    """
    批量获取财务指标
    
    Args:
        ts_codes: 股票代码列表
        batch_size: 每批数量
        
    Returns:
        总记录数
    """
    log(f"📊 批量获取 {len(ts_codes)} 只股票财务数据...")
    
    init_tables()
    client = get_tushare_client()
    total = 0
    
    for i in range(0, len(ts_codes), batch_size):
        batch = ts_codes[i:i + batch_size]
        for ts_code in batch:
            count = fetch_fina_indicator_by_stock(ts_code, client)
            total += count

        processed = min(i + batch_size, len(ts_codes))
        stats = client.get_stats()
        log(f"   进度: {processed}/{len(ts_codes)}, 累计: {total} 条, 请求: {stats['total_requests']} 次")
    
    log(f"   ✅ 完成! 共 {total} 条财务记录")
    return total


# ============================================================
# 主函数
# ============================================================

def main():
    log("=" * 50)
    log("Tushare 财务数据抓取")
    log("=" * 50)
    
    from src.data_ingestion.tushare.daily import get_all_ts_codes
    
    init_tables()
    
    # 获取股票列表
    ts_codes = get_all_ts_codes()
    
    if not ts_codes:
        log("⚠️ 请先运行 ts_daily_fetcher 获取股票列表")
        return
    
    log(f"📋 待处理: {len(ts_codes)} 只股票")
    
    fetch_fina_batch(ts_codes)
    
    log("\n✅ 完成!")


if __name__ == "__main__":
    main()
