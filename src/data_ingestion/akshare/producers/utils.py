"""AkShare producer 公共工具"""

import logging

import pandas as pd

from src.database.connection import get_connection
from src.utils.rate_limiter import create_rate_limiter

logger = logging.getLogger(__name__)

# 全局 AkShare 限流器（300 req/min）
akshare_limiter = create_rate_limiter(requests_per_minute=300, burst_capacity=10)


def ensure_tables_exist():
    """确保所有 ts_* 目标表已创建（复用 Tushare 模块的 DDL）"""
    from src.data_ingestion.tushare.daily import init_tables as init_daily_tables
    from src.data_ingestion.tushare.moneyflow import init_tables as init_moneyflow_tables
    from src.data_ingestion.tushare.northbound import init_tables as init_northbound_tables
    from src.data_ingestion.tushare.financials import init_tables as init_fina_tables
    init_daily_tables()
    init_moneyflow_tables()
    init_northbound_tables()
    init_fina_tables()


def safe_float(val) -> float | None:
    """安全转换为 float，NaN/None → None"""
    if val is None or (isinstance(val, float) and pd.isna(val)):
        return None
    try:
        return float(val)
    except (ValueError, TypeError):
        return None


def safe_str(val) -> str | None:
    """安全转换为 str，NaN/None → None"""
    if val is None or (isinstance(val, float) and pd.isna(val)):
        return None
    return str(val).strip() or None


def ts_code_from_symbol(symbol: str) -> str:
    """将 6 位代码转换为 ts_code 格式（000001 → 000001.SZ）

    与 src/data_ingestion/compat.py:to_ts_code() 保持一致。
    """
    s = str(symbol).strip()
    if "." in s:
        return s
    if s.startswith(("6", "5")):
        return f"{s}.SH"
    if s.startswith(("4", "8")):
        return f"{s}.BJ"
    return f"{s}.SZ"
