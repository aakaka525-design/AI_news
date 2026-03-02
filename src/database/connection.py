#!/usr/bin/env python3
"""
AI News - 数据库连接公共模块

提供统一的数据库连接管理和数据验证入库功能。
"""
import sqlite3
from pathlib import Path
from datetime import datetime
from typing import TypeVar, Type, Optional, Any
from pydantic import BaseModel, ValidationError

# 使用统一配置路径 (修正为项目根目录)
STOCKS_DB_PATH = Path(__file__).resolve().parent.parent.parent / "data" / "stocks.db"

# 泛型类型变量
T = TypeVar('T', bound=BaseModel)


def _is_sqlite(conn) -> bool:
    """Detect whether *conn* is a SQLite connection."""
    return "sqlite" in type(conn).__module__


def _object_type(conn: sqlite3.Connection, name: str) -> Optional[str]:
    """Get object type. Works with SQLite only (backwards compat)."""
    try:
        row = conn.execute(
            "SELECT type FROM sqlite_master WHERE name=?",
            (name,),
        ).fetchone()
        return row[0] if row else None
    except Exception:
        return None  # Not SQLite, or table doesn't exist


def _table_exists(conn: sqlite3.Connection, name: str) -> bool:
    return _object_type(conn, name) == "table"


def _create_or_replace_view(conn: sqlite3.Connection, view_name: str, select_sql: str) -> None:
    existing = _object_type(conn, view_name)
    if existing == "table":
        return
    if existing == "view":
        conn.execute(f"DROP VIEW IF EXISTS {view_name}")
    conn.execute(f"CREATE VIEW {view_name} AS {select_sql}")


def _ensure_compat_views(conn: sqlite3.Connection) -> None:
    """Create compatibility views for legacy queries when source tables exist."""
    try:
        if not _table_exists(conn, "ts_weekly") and _table_exists(conn, "ts_daily"):
            _create_or_replace_view(
                conn,
                "ts_weekly",
                """
                SELECT
                    id,
                    ts_code,
                    trade_date,
                    open,
                    high,
                    low,
                    close,
                    pre_close,
                    change,
                    pct_chg,
                    vol,
                    amount,
                    updated_at
                FROM ts_daily
                """,
            )
    except (sqlite3.OperationalError, sqlite3.DatabaseError):
        pass  # View creation is best-effort for backwards compatibility

    try:
        if not _table_exists(conn, "ts_weekly_valuation") and _table_exists(conn, "ts_daily_basic"):
            _create_or_replace_view(
                conn,
                "ts_weekly_valuation",
                """
                SELECT
                    id,
                    ts_code,
                    trade_date,
                    pe,
                    pe_ttm,
                    pb,
                    ps,
                    ps_ttm,
                    total_mv,
                    circ_mv,
                    updated_at
                FROM ts_daily_basic
                """,
            )
    except (sqlite3.OperationalError, sqlite3.DatabaseError):
        pass  # View creation is best-effort for backwards compatibility

    try:
        if not _table_exists(conn, "stocks") and _table_exists(conn, "ts_stock_basic"):
            _create_or_replace_view(
                conn,
                "stocks",
                """
                SELECT
                    symbol AS code,
                    name,
                    updated_at
                FROM ts_stock_basic
                """,
            )
    except (sqlite3.OperationalError, sqlite3.DatabaseError):
        pass  # View creation is best-effort for backwards compatibility

    try:
        if not _table_exists(conn, "stock_daily") and _table_exists(conn, "ts_daily"):
            _create_or_replace_view(
                conn,
                "stock_daily",
                """
                SELECT
                    substr(d.ts_code, 1, 6) AS stock_code,
                    substr(d.trade_date, 1, 4) || '-' || substr(d.trade_date, 5, 2) || '-' || substr(d.trade_date, 7, 2) AS date,
                    d.open,
                    d.close,
                    d.high,
                    d.low,
                    d.vol AS volume,
                    d.amount,
                    d.pct_chg AS change_pct,
                    db.turnover_rate,
                    db.volume_ratio,
                    d.updated_at
                FROM ts_daily d
                LEFT JOIN ts_daily_basic db
                    ON d.ts_code = db.ts_code AND d.trade_date = db.trade_date
                """,
            )
    except (sqlite3.OperationalError, sqlite3.DatabaseError):
        pass  # View creation is best-effort for backwards compatibility

    try:
        if not _table_exists(conn, "stock_valuation"):
            if _table_exists(conn, "ts_daily_basic"):
                _create_or_replace_view(
                    conn,
                    "stock_valuation",
                    """
                    SELECT
                        substr(ts_code, 1, 6) AS stock_code,
                        substr(trade_date, 1, 4) || '-' || substr(trade_date, 5, 2) || '-' || substr(trade_date, 7, 2) AS date,
                        pe_ttm,
                        pb,
                        total_mv,
                        circ_mv,
                        dv_ttm,
                        turnover_rate,
                        volume_ratio,
                        updated_at
                    FROM ts_daily_basic
                    """,
                )
            elif _table_exists(conn, "ts_weekly_valuation"):
                _create_or_replace_view(
                    conn,
                    "stock_valuation",
                    """
                    SELECT
                        substr(ts_code, 1, 6) AS stock_code,
                        substr(trade_date, 1, 4) || '-' || substr(trade_date, 5, 2) || '-' || substr(trade_date, 7, 2) AS date,
                        pe_ttm,
                        pb,
                        total_mv,
                        circ_mv,
                        NULL AS dv_ttm,
                        NULL AS turnover_rate,
                        NULL AS volume_ratio,
                        updated_at
                    FROM ts_weekly_valuation
                    """,
                )
    except (sqlite3.OperationalError, sqlite3.DatabaseError):
        pass  # View creation is best-effort for backwards compatibility

    try:
        if not _table_exists(conn, "main_money_flow"):
            source_table = None
            if _table_exists(conn, "ts_moneyflow"):
                source_table = "ts_moneyflow"
            elif _table_exists(conn, "money_flow"):
                source_table = "money_flow"
            if source_table:
                _create_or_replace_view(
                    conn,
                    "main_money_flow",
                    f"""
                    SELECT
                        substr(ts_code, 1, 6) AS stock_code,
                        substr(trade_date, 1, 4) || '-' || substr(trade_date, 5, 2) || '-' || substr(trade_date, 7, 2) AS date,
                        net_mf_amount AS main_net_inflow,
                        buy_elg_amount AS super_large_net,
                        buy_lg_amount AS large_net,
                        NULL AS change_pct,
                        updated_at
                    FROM {source_table}
                    """,
                )
    except (sqlite3.OperationalError, sqlite3.DatabaseError):
        pass  # View creation is best-effort for backwards compatibility

    try:
        if not _table_exists(conn, "north_money_holding") and _table_exists(conn, "ts_hsgt_top10"):
            _create_or_replace_view(
                conn,
                "north_money_holding",
                """
                SELECT
                    substr(ts_code, 1, 6) AS stock_code,
                    substr(trade_date, 1, 4) || '-' || substr(trade_date, 5, 2) || '-' || substr(trade_date, 7, 2) AS date,
                    net_amount AS net_buy,
                    net_amount AS net_buy_value,
                    buy,
                    sell,
                    market_type AS market,
                    updated_at
                FROM ts_hsgt_top10
                """,
            )
    except (sqlite3.OperationalError, sqlite3.DatabaseError):
        pass  # View creation is best-effort for backwards compatibility

    try:
        if not _table_exists(conn, "dragon_tiger_stock"):
            if _table_exists(conn, "ts_top_list"):
                _create_or_replace_view(
                    conn,
                    "dragon_tiger_stock",
                    """
                    SELECT
                        substr(ts_code, 1, 6) AS stock_code,
                        substr(trade_date, 1, 4) || '-' || substr(trade_date, 5, 2) || '-' || substr(trade_date, 7, 2) AS date,
                        name AS stock_name,
                        close,
                        pct_change AS change_pct,
                        amount,
                        reason,
                        updated_at
                    FROM ts_top_list
                    """,
                )
            elif _table_exists(conn, "dragon_tiger"):
                _create_or_replace_view(
                    conn,
                    "dragon_tiger_stock",
                    """
                    SELECT
                        substr(ts_code, 1, 6) AS stock_code,
                        substr(trade_date, 1, 4) || '-' || substr(trade_date, 5, 2) || '-' || substr(trade_date, 7, 2) AS date,
                        name AS stock_name,
                        close,
                        pct_chg AS change_pct,
                        amount,
                        reason,
                        updated_at
                    FROM dragon_tiger
                    """,
                )
    except (sqlite3.OperationalError, sqlite3.DatabaseError):
        pass  # View creation is best-effort for backwards compatibility

    try:
        if not _table_exists(conn, "sectors") and _table_exists(conn, "ts_ths_index"):
            _create_or_replace_view(
                conn,
                "sectors",
                """
                SELECT
                    ts_code AS code,
                    name,
                    type AS sector_type,
                    updated_at
                FROM ts_ths_index
                """,
            )
    except (sqlite3.OperationalError, sqlite3.DatabaseError):
        pass  # View creation is best-effort for backwards compatibility

    try:
        if (
            not _table_exists(conn, "sector_stocks")
            and _table_exists(conn, "ts_ths_member")
            and _table_exists(conn, "ts_ths_index")
        ):
            _create_or_replace_view(
                conn,
                "sector_stocks",
                """
                SELECT
                    i.name AS sector_name,
                    i.type AS sector_type,
                    substr(m.con_code, 1, 6) AS stock_code
                FROM ts_ths_member m
                JOIN ts_ths_index i
                    ON m.ts_code = i.ts_code
                """,
            )
    except (sqlite3.OperationalError, sqlite3.DatabaseError):
        pass  # View creation is best-effort for backwards compatibility

    try:
        if not _table_exists(conn, "sector_daily_rank") and _table_exists(conn, "ts_ths_daily"):
            _create_or_replace_view(
                conn,
                "sector_daily_rank",
                """
                SELECT
                    substr(d.trade_date, 1, 4) || '-' || substr(d.trade_date, 5, 2) || '-' || substr(d.trade_date, 7, 2) AS date,
                    COALESCE(i.name, d.ts_code) AS sector_name,
                    d.pct_change AS change_pct,
                    NULL AS rank_by_change,
                    NULL AS main_net_inflow,
                    NULL AS leading_stock_name
                FROM ts_ths_daily d
                LEFT JOIN ts_ths_index i
                    ON d.ts_code = i.ts_code
                """,
            )
    except (sqlite3.OperationalError, sqlite3.DatabaseError):
        pass  # View creation is best-effort for backwards compatibility

    try:
        if not _table_exists(conn, "limit_up_pool") and _table_exists(conn, "dragon_tiger"):
            _create_or_replace_view(
                conn,
                "limit_up_pool",
                """
                SELECT
                    substr(ts_code, 1, 6) AS stock_code,
                    name AS stock_name,
                    substr(trade_date, 1, 4) || '-' || substr(trade_date, 5, 2) || '-' || substr(trade_date, 7, 2) AS date,
                    1 AS continuous_days,
                    reason AS limit_up_reason,
                    turnover_rate AS turnover_ratio,
                    net_amount AS buy_lock_amount
                FROM dragon_tiger
                WHERE pct_chg >= 9.5
                """,
            )
    except (sqlite3.OperationalError, sqlite3.DatabaseError):
        pass  # View creation is best-effort for backwards compatibility


def get_connection(timeout: int = 30) -> sqlite3.Connection:
    """
    获取统一的数据库连接。

    Args:
        timeout: 连接超时时间（秒），默认 30 秒

    Returns:
        sqlite3.Connection: 数据库连接对象
    """
    conn = sqlite3.connect(STOCKS_DB_PATH, timeout=timeout)
    # Use Row so callers can safely use both row[0] and row["col"] styles.
    conn.row_factory = sqlite3.Row
    # Only apply SQLite-specific PRAGMAs
    if _is_sqlite(conn):
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA busy_timeout=30000;")
    _ensure_compat_views(conn)
    return conn


def validate_and_create(
    model_class: Type[T],
    data: dict[str, Any],
    strict: bool = False
) -> Optional[T]:
    """
    验证数据并创建模型实例。

    Args:
        model_class: Pydantic 模型类
        data: 原始数据字典
        strict: 严格模式（失败抛异常）

    Returns:
        模型实例，或 None（非严格模式下验证失败）
    """
    try:
        return model_class(**data)
    except ValidationError as e:
        if strict:
            raise
        # 非严格模式：记录警告但不中断
        return None


def insert_validated(
    conn: sqlite3.Connection,
    table: str,
    record: BaseModel,
    unique_keys: list[str]
) -> bool:
    """
    将验证后的记录插入数据库。

    Args:
        conn: 数据库连接
        table: 表名
        record: Pydantic 模型实例
        unique_keys: 唯一键字段列表（用于 REPLACE）

    Returns:
        是否成功
    """
    try:
        data = record.model_dump(exclude_none=False)
        columns = list(data.keys())
        placeholders = ["?" for _ in columns]
        values = [
            data[c] if not isinstance(data[c], datetime) else data[c].isoformat()
            for c in columns
        ]

        if unique_keys:
            conflict_cols = ", ".join(unique_keys)
            update_cols = [c for c in columns if c not in unique_keys]
            if update_cols:
                set_clause = ", ".join(f"{c}=excluded.{c}" for c in update_cols)
                sql = (
                    f"INSERT INTO {table} ({', '.join(columns)}) "
                    f"VALUES ({', '.join(placeholders)}) "
                    f"ON CONFLICT ({conflict_cols}) DO UPDATE SET {set_clause}"
                )
            else:
                sql = (
                    f"INSERT INTO {table} ({', '.join(columns)}) "
                    f"VALUES ({', '.join(placeholders)}) "
                    f"ON CONFLICT ({conflict_cols}) DO NOTHING"
                )
        else:
            sql = (
                f"INSERT INTO {table} ({', '.join(columns)}) "
                f"VALUES ({', '.join(placeholders)})"
            )

        conn.execute(sql, values)
        return True
    except Exception:  # noqa: BLE001
        return False


def batch_insert_validated(
    conn: sqlite3.Connection,
    table: str,
    records: list[BaseModel],
    unique_keys: list[str],
    commit_every: int = 100
) -> int:
    """
    批量插入验证后的记录。

    Args:
        conn: 数据库连接
        table: 表名
        records: Pydantic 模型实例列表
        unique_keys: 唯一键字段列表
        commit_every: 每 N 条提交一次

    Returns:
        成功插入的记录数
    """
    count = 0
    for i, record in enumerate(records):
        if insert_validated(conn, table, record, unique_keys):
            count += 1
        if (i + 1) % commit_every == 0:
            conn.commit()
    conn.commit()  # 最后一批
    return count
