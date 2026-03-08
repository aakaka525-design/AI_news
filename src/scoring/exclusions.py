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


def _add_new_listing_exclusions(
    conn: sqlite3.Connection, exclusions: dict[str, str]
) -> None:
    """检查上市未满 60 个交易日的股票。"""
    today = datetime.now().strftime("%Y-%m-%d")

    # 获取交易日历
    try:
        cal_rows = conn.execute(
            "SELECT cal_date FROM trading_calendar WHERE is_open=1 AND cal_date <= ? ORDER BY cal_date DESC LIMIT 61",
            (today,),
        ).fetchall()
    except Exception:
        # trading_calendar 可能不在 stocks.db 中，尝试其他方式
        from fetchers.trading_calendar import get_recent_trading_days
        cal_rows = None
        recent_days = get_recent_trading_days(61)
        if len(recent_days) >= 61:
            cutoff_date = recent_days[-1]  # 60 个交易日前的日期
        else:
            return

    if cal_rows is not None:
        if len(cal_rows) < 61:
            return
        cutoff_date = cal_rows[-1]["cal_date"]

    # 将 cutoff_date 转换为 YYYYMMDD 格式以匹配 list_date
    cutoff_yyyymmdd = cutoff_date.replace("-", "")

    rows = conn.execute(
        "SELECT ts_code FROM ts_stock_basic WHERE (list_status = 'L' OR list_status IS NULL) AND list_date > ?",
        (cutoff_yyyymmdd,),
    ).fetchall()
    for row in rows:
        if row["ts_code"] not in exclusions:
            exclusions[row["ts_code"]] = "new_listing"
