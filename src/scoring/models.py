"""评分系统数据表 DDL — stocks.db

Tables:
    stock_composite_score  — 综合评分结果（每股每日一条）
    stock_composite_factor — 因子明细（每股每日每因子一条）
"""

import logging
import sqlite3

logger = logging.getLogger(__name__)

DDL_COMPOSITE_SCORE = """
CREATE TABLE IF NOT EXISTS stock_composite_score (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts_code TEXT NOT NULL,
    trade_date TEXT NOT NULL,
    score REAL,
    score_version TEXT NOT NULL DEFAULT 'v1',
    status TEXT NOT NULL DEFAULT 'scored',
    exclusion_reason TEXT,
    experimental INTEGER DEFAULT 1,
    coverage_ratio REAL,
    low_confidence INTEGER DEFAULT 0,
    price_trend_score REAL,
    flow_score REAL,
    fundamentals_score REAL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(ts_code, trade_date, score_version)
)
"""

DDL_COMPOSITE_FACTOR = """
CREATE TABLE IF NOT EXISTS stock_composite_factor (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts_code TEXT NOT NULL,
    trade_date TEXT NOT NULL,
    score_version TEXT NOT NULL DEFAULT 'v1',
    factor_key TEXT NOT NULL,
    bucket TEXT NOT NULL,
    available INTEGER DEFAULT 0,
    raw_value REAL,
    normalized_value REAL,
    weight_nominal REAL,
    weight_effective REAL,
    staleness_trading_days INTEGER,
    source_key TEXT,
    source_table TEXT,
    data_date TEXT,
    UNIQUE(ts_code, trade_date, score_version, factor_key)
)
"""

IDX_SCORE_DATE = "CREATE INDEX IF NOT EXISTS ix_composite_score_date ON stock_composite_score(trade_date)"
IDX_SCORE_CODE = "CREATE INDEX IF NOT EXISTS ix_composite_score_code ON stock_composite_score(ts_code)"
IDX_FACTOR_CODE_DATE = "CREATE INDEX IF NOT EXISTS ix_composite_factor_code_date ON stock_composite_factor(ts_code, trade_date)"


def ensure_scoring_tables(conn: sqlite3.Connection) -> None:
    """创建评分相关表（幂等）。"""
    conn.execute(DDL_COMPOSITE_SCORE)
    conn.execute(DDL_COMPOSITE_FACTOR)
    conn.execute(IDX_SCORE_DATE)
    conn.execute(IDX_SCORE_CODE)
    conn.execute(IDX_FACTOR_CODE_DATE)
    conn.commit()
    logger.info("评分表已就绪")
