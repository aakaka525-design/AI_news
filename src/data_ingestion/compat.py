#!/usr/bin/env python3
"""
Tushare 兼容层

提供旧代码和新 Tushare 数据的兼容接口，支持平滑过渡。

功能：
1. 股票代码格式转换
2. 日期格式转换
3. 统一查询接口（自动选择新旧表）
"""

import sqlite3
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional, List, Dict, Any

# 添加项目根目录
PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.database.connection import STOCKS_DB_PATH


def get_connection():
    """获取数据库连接（支持字典访问）"""
    import sqlite3
    conn = sqlite3.connect(STOCKS_DB_PATH, timeout=30)
    conn.row_factory = sqlite3.Row
    return conn


# ============================================================
# 代码格式转换
# ============================================================

def to_ts_code(code: str) -> str:
    """
    将 6 位股票代码转换为 Tushare 格式
    
    Args:
        code: 6 位股票代码 (如 "000001") 或已有 ts_code
        
    Returns:
        Tushare 格式代码 (如 "000001.SZ")
    """
    code = str(code).strip()
    
    # 已经是 ts_code 格式
    if '.' in code:
        return code.upper()
    
    # 补齐 6 位
    code = code.zfill(6)
    
    # 判断交易所
    if code.startswith(('6', '5')):
        return f"{code}.SH"  # 上交所
    elif code.startswith(('0', '3', '1', '2')):
        return f"{code}.SZ"  # 深交所
    elif code.startswith(('4', '8', '9')):
        return f"{code}.BJ"  # 北交所
    else:
        return f"{code}.SZ"


def from_ts_code(ts_code: str) -> str:
    """
    从 Tushare 格式提取 6 位股票代码
    
    Args:
        ts_code: Tushare 格式代码 (如 "000001.SZ")
        
    Returns:
        6 位股票代码 (如 "000001")
    """
    if not ts_code:
        return ""
    if '.' in ts_code:
        return ts_code.split('.')[0]
    return ts_code


def normalize_code(code: str) -> str:
    """
    标准化代码（自动识别格式）
    
    Args:
        code: 任意格式的股票代码
        
    Returns:
        6 位股票代码
    """
    return from_ts_code(code) if '.' in str(code) else str(code).zfill(6)


# ============================================================
# 日期格式转换
# ============================================================

def to_trade_date(date_str: str) -> str:
    """
    转换为 Tushare 日期格式 (YYYYMMDD)
    
    支持输入：
    - YYYYMMDD
    - YYYY-MM-DD
    - YYYY/MM/DD
    """
    if not date_str:
        return ""
    date_str = str(date_str).strip()
    return date_str.replace('-', '').replace('/', '')[:8]


def to_legacy_date(trade_date: str) -> str:
    """
    转换为旧日期格式 (YYYY-MM-DD)
    
    Args:
        trade_date: YYYYMMDD 格式
        
    Returns:
        YYYY-MM-DD 格式
    """
    if not trade_date or len(trade_date) != 8:
        return trade_date
    return f"{trade_date[:4]}-{trade_date[4:6]}-{trade_date[6:8]}"


# ============================================================
# 统一查询接口
# ============================================================

def query_daily(
    code: str = None,
    start_date: str = None,
    end_date: str = None,
    limit: int = 100,
    prefer_tushare: bool = True
) -> List[Dict[str, Any]]:
    """
    统一日线查询接口
    
    自动选择 ts_daily（Tushare）或 stock_daily（旧表）
    
    Args:
        code: 股票代码（支持两种格式）
        start_date: 开始日期
        end_date: 结束日期
        limit: 返回数量限制
        prefer_tushare: 优先使用 Tushare 表
        
    Returns:
        统一格式的日线数据列表
    """
    conn = get_connection()
    
    try:
        if prefer_tushare:
            # 使用 Tushare 表
            ts_code = to_ts_code(code) if code else None
            start_d = to_trade_date(start_date) if start_date else None
            end_d = to_trade_date(end_date) if end_date else None
            
            sql = "SELECT * FROM ts_daily WHERE 1=1"
            params = []
            
            if ts_code:
                sql += " AND ts_code = ?"
                params.append(ts_code)
            if start_d:
                sql += " AND trade_date >= ?"
                params.append(start_d)
            if end_d:
                sql += " AND trade_date <= ?"
                params.append(end_d)
            
            sql += " ORDER BY trade_date DESC LIMIT ?"
            params.append(limit)

            cursor = conn.execute(sql, params)
            rows = cursor.fetchall()
            
            # 转换为统一格式
            results = []
            for row in rows:
                results.append({
                    'stock_code': from_ts_code(row['ts_code']),
                    'ts_code': row['ts_code'],
                    'date': to_legacy_date(row['trade_date']),
                    'trade_date': row['trade_date'],
                    'open': row['open'],
                    'high': row['high'],
                    'low': row['low'],
                    'close': row['close'],
                    'volume': row['vol'],
                    'amount': row['amount'],
                    'change_pct': row['pct_chg'],
                    'adj_factor': row['adj_factor'],
                })
            return results
        else:
            # 使用旧表
            stock_code = normalize_code(code) if code else None
            
            sql = "SELECT * FROM stock_daily WHERE 1=1"
            params = []
            
            if stock_code:
                sql += " AND stock_code = ?"
                params.append(stock_code)
            if start_date:
                sql += " AND date >= ?"
                params.append(start_date)
            if end_date:
                sql += " AND date <= ?"
                params.append(end_date)
            
            sql += " ORDER BY date DESC LIMIT ?"
            params.append(limit)

            cursor = conn.execute(sql, params)
            rows = cursor.fetchall()
            
            results = []
            for row in rows:
                results.append({
                    'stock_code': row['stock_code'],
                    'ts_code': to_ts_code(row['stock_code']),
                    'date': row['date'],
                    'trade_date': to_trade_date(row['date']),
                    'open': row['open'],
                    'high': row['high'],
                    'low': row['low'],
                    'close': row['close'],
                    'volume': row['volume'],
                    'amount': row['amount'],
                    'change_pct': row['change_pct'],
                    'adj_factor': None,
                })
            return results
    finally:
        conn.close()


def query_stock_info(code: str) -> Optional[Dict[str, Any]]:
    """
    查询股票基本信息
    
    自动选择 ts_stock_basic 或 stocks 表
    """
    conn = get_connection()
    
    try:
        # 尝试 Tushare 表
        ts_code = to_ts_code(code)
        cursor = conn.execute(
            "SELECT * FROM ts_stock_basic WHERE ts_code = ?",
            (ts_code,)
        )
        row = cursor.fetchone()
        
        if row:
            return {
                'code': row['symbol'],
                'ts_code': row['ts_code'],
                'name': row['name'],
                'industry': row['industry'],
                'area': row['area'],
                'market': row['market'],
                'exchange': row['exchange'],
                'list_date': row['list_date'],
            }
        
        # 回退到旧表（仅在旧表存在时尝试）
        stock_code = normalize_code(code)
        has_stocks_table = conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='stocks'"
        ).fetchone()
        row = None
        if has_stocks_table:
            cursor = conn.execute(
                "SELECT * FROM stocks WHERE code = ?",
                (stock_code,)
            )
            row = cursor.fetchone()
        
        if row:
            return {
                'code': row['code'],
                'ts_code': to_ts_code(row['code']),
                'name': row['name'],
                'industry': None,
                'area': None,
                'market': None,
                'exchange': None,
                'list_date': None,
            }
        
        return None
    finally:
        conn.close()


def query_financials(
    code: str,
    limit: int = 10,
    prefer_tushare: bool = True
) -> List[Dict[str, Any]]:
    """
    查询财务指标
    """
    conn = get_connection()
    
    try:
        if prefer_tushare:
            ts_code = to_ts_code(code)
            cursor = conn.execute("""
                SELECT * FROM ts_fina_indicator 
                WHERE ts_code = ?
                ORDER BY end_date DESC
                LIMIT ?
            """, (ts_code, limit))
            
            results = []
            for row in cursor.fetchall():
                results.append({
                    'stock_code': from_ts_code(row['ts_code']),
                    'ts_code': row['ts_code'],
                    'report_date': to_legacy_date(row['end_date']),
                    'end_date': row['end_date'],
                    'roe': row['roe'],
                    'eps': row['eps'],
                    'net_profit_yoy': row['netprofit_yoy'],
                    'revenue_yoy': row['or_yoy'],
                    'gross_margin': row['grossprofit_margin'],
                    'net_margin': row['netprofit_margin'],
                    'debt_ratio': row['debt_to_assets'],
                })
            return results
        else:
            stock_code = normalize_code(code)
            cursor = conn.execute("""
                SELECT * FROM stock_financials 
                WHERE stock_code = ?
                ORDER BY report_date DESC
                LIMIT ?
            """, (stock_code, limit))
            
            results = []
            for row in cursor.fetchall():
                results.append({
                    'stock_code': row['stock_code'],
                    'ts_code': to_ts_code(row['stock_code']),
                    'report_date': row['report_date'],
                    'end_date': to_trade_date(row['report_date']),
                    'roe': row['roe'],
                    'eps': None,
                    'net_profit_yoy': row['net_profit_yoy'],
                    'revenue_yoy': row['revenue_yoy'],
                    'gross_margin': row['gross_margin'],
                    'net_margin': row['net_margin'],
                    'debt_ratio': row['debt_ratio'],
                })
            return results
    finally:
        conn.close()


# ============================================================
# 快捷函数
# ============================================================

def get_stock_name(code: str) -> Optional[str]:
    """获取股票名称"""
    info = query_stock_info(code)
    return info['name'] if info else None


def get_latest_price(code: str) -> Optional[float]:
    """获取最新收盘价"""
    data = query_daily(code, limit=1)
    return data[0]['close'] if data else None


def is_ts_code(code: str) -> bool:
    """判断是否为 Tushare 格式"""
    return '.' in str(code)


# ============================================================
# 测试
# ============================================================

if __name__ == "__main__":
    print("=" * 50)
    print("Tushare 兼容层测试")
    print("=" * 50)
    
    # 代码转换测试
    print("\n📝 代码转换:")
    print(f"  000001 -> {to_ts_code('000001')}")
    print(f"  600519 -> {to_ts_code('600519')}")
    print(f"  000001.SZ -> {from_ts_code('000001.SZ')}")
    
    # 日期转换测试
    print("\n📅 日期转换:")
    print(f"  2026-01-16 -> {to_trade_date('2026-01-16')}")
    print(f"  20260116 -> {to_legacy_date('20260116')}")
    
    # 查询测试
    print("\n📊 查询测试:")
    info = query_stock_info('600519')
    if info:
        print(f"  股票信息: {info['name']} ({info['ts_code']})")
    
    data = query_daily('600519', limit=3)
    if data:
        print(f"  最新日线: {data[0]['date']} 收盘 {data[0]['close']}")
    
    print("\n✅ 完成!")
