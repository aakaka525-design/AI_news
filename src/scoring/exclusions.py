"""排除规则 — 识别不应参与评分的股票

三条规则（Codex 锁定）：
1. list_status != 'L' → delisted
2. name LIKE '%ST%' OR name LIKE '%退%' → st
3. 上市未满 60 个交易日 → new_listing
"""

import logging
import sqlite3
from datetime import datetime

logger = logging.getLogger(__name__)


def get_exclusions(conn: sqlite3.Connection) -> dict[str, str]:
    """返回 {ts_code: reason} 映射，包含所有应排除的股票。"""
    exclusions: dict[str, str] = {}

    # 1. 退市 (list_status 明确非 'L' 且非 NULL)
    rows = conn.execute(
        "SELECT ts_code FROM ts_stock_basic WHERE list_status IS NOT NULL AND list_status != 'L'"
    ).fetchall()
    for row in rows:
        exclusions[row["ts_code"]] = "delisted"

    # 2. ST / *退 (name 包含 ST 或 退)
    rows = conn.execute(
        "SELECT ts_code FROM ts_stock_basic WHERE name LIKE '%ST%' OR name LIKE '%退%'"
    ).fetchall()
    for row in rows:
        if row["ts_code"] not in exclusions:
            exclusions[row["ts_code"]] = "st"

    # 3. 上市未满 60 个交易日
    try:
        _add_new_listing_exclusions(conn, exclusions)
    except Exception as e:
        logger.warning(f"新股排除规则计算失败，跳过: {e}")

    logger.info(f"排除股票数: {len(exclusions)}")
    return exclusions


def _get_cutoff_date(conn: sqlite3.Connection) -> str | None:
    """推导 60 个交易日前的 cutoff 日期 (YYYYMMDD)。

    按优先级尝试三种数据源:
    1. trading_calendar 表（可能不存在）
    2. ts_daily 表的 distinct trade_date（真实库中稳定存在）
    3. fetchers.trading_calendar 模块
    """
    # 策略 1: trading_calendar 表
    try:
        rows = conn.execute(
            "SELECT cal_date FROM trading_calendar WHERE is_open=1 "
            "ORDER BY cal_date DESC LIMIT 61"
        ).fetchall()
        if len(rows) >= 61:
            return rows[-1]["cal_date"].replace("-", "")
    except Exception:
        pass

    # 策略 2: 从 ts_daily 推导（真实库中稳定可用）
    try:
        rows = conn.execute(
            "SELECT DISTINCT trade_date FROM ts_daily "
            "ORDER BY trade_date DESC LIMIT 61"
        ).fetchall()
        if len(rows) >= 61:
            return rows[-1]["trade_date"].replace("-", "")
    except Exception:
        pass

    # 策略 3: fetchers 模块（可能也依赖缺失的表，最后兜底）
    try:
        from fetchers.trading_calendar import get_prev_n_trading_days
        recent_days = get_prev_n_trading_days(61)
        if len(recent_days) >= 61:
            return recent_days[-1].replace("-", "")
    except Exception:
        pass

    return None


def _add_new_listing_exclusions(
    conn: sqlite3.Connection, exclusions: dict[str, str]
) -> None:
    """检查上市未满 60 个交易日的股票。"""
    cutoff_yyyymmdd = _get_cutoff_date(conn)
    if not cutoff_yyyymmdd:
        return

    rows = conn.execute(
        "SELECT ts_code FROM ts_stock_basic WHERE (list_status = 'L' OR list_status IS NULL) AND list_date > ?",
        (cutoff_yyyymmdd,),
    ).fetchall()
    for row in rows:
        if row["ts_code"] not in exclusions:
            exclusions[row["ts_code"]] = "new_listing"
