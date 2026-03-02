"""Database connection module tests (P0)."""
import sqlite3
from pathlib import Path
from unittest.mock import patch

import pytest
from pydantic import BaseModel

from src.database.connection import (
    get_connection,
    insert_validated,
    batch_insert_validated,
    validate_and_create,
    _object_type,
    _table_exists,
    _create_or_replace_view,
    _ensure_compat_views,
)


class StockRecord(BaseModel):
    ts_code: str
    trade_date: str
    close: float
    vol: float


@pytest.fixture
def mem_db():
    """In-memory SQLite database with test table."""
    conn = sqlite3.connect(":memory:")
    conn.execute(
        """
        CREATE TABLE ts_daily (
            ts_code TEXT NOT NULL,
            trade_date TEXT NOT NULL,
            close REAL,
            vol REAL,
            UNIQUE(ts_code, trade_date)
        )
        """
    )
    yield conn
    conn.close()


class TestInsertValidated:
    def test_insert_new_record(self, mem_db):
        record = StockRecord(ts_code="000001.SZ", trade_date="20260301", close=10.5, vol=1000.0)
        result = insert_validated(mem_db, "ts_daily", record, ["ts_code", "trade_date"])
        assert result is True
        row = mem_db.execute("SELECT close FROM ts_daily WHERE ts_code='000001.SZ'").fetchone()
        assert row[0] == 10.5

    def test_upsert_updates_existing(self, mem_db):
        r1 = StockRecord(ts_code="000001.SZ", trade_date="20260301", close=10.0, vol=800.0)
        r2 = StockRecord(ts_code="000001.SZ", trade_date="20260301", close=11.0, vol=900.0)
        insert_validated(mem_db, "ts_daily", r1, ["ts_code", "trade_date"])
        insert_validated(mem_db, "ts_daily", r2, ["ts_code", "trade_date"])
        mem_db.commit()
        row = mem_db.execute("SELECT close, vol FROM ts_daily").fetchone()
        assert row[0] == 11.0
        assert row[1] == 900.0

    def test_upsert_keeps_single_row(self, mem_db):
        """Upsert with same unique keys should not create duplicate rows."""
        r1 = StockRecord(ts_code="000001.SZ", trade_date="20260301", close=10.0, vol=800.0)
        r2 = StockRecord(ts_code="000001.SZ", trade_date="20260301", close=11.0, vol=900.0)
        insert_validated(mem_db, "ts_daily", r1, ["ts_code", "trade_date"])
        insert_validated(mem_db, "ts_daily", r2, ["ts_code", "trade_date"])
        mem_db.commit()
        count = mem_db.execute("SELECT COUNT(*) FROM ts_daily").fetchone()[0]
        assert count == 1

    def test_insert_without_unique_keys(self, mem_db):
        mem_db.execute("CREATE TABLE simple (ts_code TEXT, trade_date TEXT, close REAL, vol REAL)")
        record = StockRecord(ts_code="test", trade_date="20260301", close=1.0, vol=1.0)
        result = insert_validated(mem_db, "simple", record, [])
        assert result is True

    def test_insert_to_nonexistent_table_returns_false(self, mem_db):
        """Inserting into a table that doesn't exist should return False."""
        record = StockRecord(ts_code="000001.SZ", trade_date="20260301", close=10.0, vol=100.0)
        result = insert_validated(mem_db, "nonexistent_table", record, ["ts_code"])
        assert result is False


class TestBatchInsertValidated:
    def test_batch_insert_multiple(self, mem_db):
        records = [
            StockRecord(ts_code="000001.SZ", trade_date=f"2026030{i}", close=10.0 + i, vol=100.0)
            for i in range(1, 6)
        ]
        count = batch_insert_validated(mem_db, "ts_daily", records, ["ts_code", "trade_date"])
        assert count == 5
        total = mem_db.execute("SELECT COUNT(*) FROM ts_daily").fetchone()[0]
        assert total == 5

    def test_batch_insert_with_duplicates(self, mem_db):
        records = [
            StockRecord(ts_code="000001.SZ", trade_date="20260301", close=10.0, vol=100.0),
            StockRecord(ts_code="000001.SZ", trade_date="20260301", close=11.0, vol=200.0),
        ]
        count = batch_insert_validated(mem_db, "ts_daily", records, ["ts_code", "trade_date"])
        assert count == 2
        row = mem_db.execute("SELECT close FROM ts_daily").fetchone()
        assert row[0] == 11.0

    def test_batch_insert_empty_list(self, mem_db):
        """Batch insert with no records should return 0."""
        count = batch_insert_validated(mem_db, "ts_daily", [], ["ts_code", "trade_date"])
        assert count == 0

    def test_batch_insert_commits_periodically(self, mem_db):
        """Batch insert with commit_every should commit in chunks and return full count."""
        records = [
            StockRecord(ts_code=f"{i:06d}.SZ", trade_date="20260301", close=10.0, vol=100.0)
            for i in range(5)
        ]
        count = batch_insert_validated(
            mem_db, "ts_daily", records, ["ts_code", "trade_date"], commit_every=2
        )
        assert count == 5
        total = mem_db.execute("SELECT COUNT(*) FROM ts_daily").fetchone()[0]
        assert total == 5


class TestValidateAndCreate:
    def test_valid_data(self):
        data = {"ts_code": "000001.SZ", "trade_date": "20260301", "close": 10.5, "vol": 1000.0}
        result = validate_and_create(StockRecord, data)
        assert result is not None
        assert result.ts_code == "000001.SZ"
        assert result.close == 10.5

    def test_invalid_data_returns_none(self):
        data = {"ts_code": "000001.SZ"}  # missing required fields
        result = validate_and_create(StockRecord, data)
        assert result is None

    def test_invalid_data_strict_raises(self):
        data = {"ts_code": "000001.SZ"}
        with pytest.raises(Exception):
            validate_and_create(StockRecord, data, strict=True)

    def test_type_coercion(self):
        """Pydantic should coerce string numbers to float."""
        data = {"ts_code": "000001.SZ", "trade_date": "20260301", "close": "10.5", "vol": "1000"}
        result = validate_and_create(StockRecord, data)
        assert result is not None
        assert isinstance(result.close, float)
        assert result.close == 10.5


class TestGetConnection:
    def test_returns_connection_with_row_factory(self, tmp_path):
        db_path = tmp_path / "test.db"
        with patch("src.database.connection.STOCKS_DB_PATH", str(db_path)):
            conn = get_connection()
            assert conn.row_factory == sqlite3.Row
            conn.close()

    def test_wal_mode_enabled(self, tmp_path):
        db_path = tmp_path / "test.db"
        with patch("src.database.connection.STOCKS_DB_PATH", str(db_path)):
            conn = get_connection()
            mode = conn.execute("PRAGMA journal_mode").fetchone()
            assert mode[0] == "wal"
            conn.close()

    def test_custom_timeout(self, tmp_path):
        db_path = tmp_path / "test.db"
        with patch("src.database.connection.STOCKS_DB_PATH", str(db_path)):
            conn = get_connection(timeout=10)
            # Connection should be usable
            assert conn is not None
            conn.close()


class TestObjectType:
    def test_returns_table_for_table(self):
        conn = sqlite3.connect(":memory:")
        conn.execute("CREATE TABLE foo (id INTEGER)")
        assert _object_type(conn, "foo") == "table"
        conn.close()

    def test_returns_view_for_view(self):
        conn = sqlite3.connect(":memory:")
        conn.execute("CREATE TABLE foo (id INTEGER)")
        conn.execute("CREATE VIEW bar AS SELECT id FROM foo")
        assert _object_type(conn, "bar") == "view"
        conn.close()

    def test_returns_none_for_missing(self):
        conn = sqlite3.connect(":memory:")
        assert _object_type(conn, "nonexistent") is None
        conn.close()


class TestTableExists:
    def test_true_for_table(self):
        conn = sqlite3.connect(":memory:")
        conn.execute("CREATE TABLE t1 (id INTEGER)")
        assert _table_exists(conn, "t1") is True
        conn.close()

    def test_false_for_view(self):
        conn = sqlite3.connect(":memory:")
        conn.execute("CREATE TABLE t1 (id INTEGER)")
        conn.execute("CREATE VIEW v1 AS SELECT id FROM t1")
        assert _table_exists(conn, "v1") is False
        conn.close()

    def test_false_for_missing(self):
        conn = sqlite3.connect(":memory:")
        assert _table_exists(conn, "nope") is False
        conn.close()


class TestCreateOrReplaceView:
    def test_creates_new_view(self):
        conn = sqlite3.connect(":memory:")
        conn.execute("CREATE TABLE src (id INTEGER)")
        _create_or_replace_view(conn, "my_view", "SELECT id FROM src")
        assert _object_type(conn, "my_view") == "view"
        conn.close()

    def test_replaces_existing_view(self):
        conn = sqlite3.connect(":memory:")
        conn.execute("CREATE TABLE src (id INTEGER, name TEXT)")
        conn.execute("CREATE VIEW my_view AS SELECT id FROM src")
        # Replace with a different view definition
        _create_or_replace_view(conn, "my_view", "SELECT id, name FROM src")
        assert _object_type(conn, "my_view") == "view"
        # Verify the view now has two columns
        cols = conn.execute("PRAGMA table_info(my_view)").fetchall()
        assert len(cols) == 2
        conn.close()

    def test_skips_if_table_exists_with_same_name(self):
        """If a real table exists with the same name, do NOT replace it."""
        conn = sqlite3.connect(":memory:")
        conn.execute("CREATE TABLE my_view (id INTEGER)")
        conn.execute("INSERT INTO my_view VALUES (1)")
        _create_or_replace_view(conn, "my_view", "SELECT 999 AS id")
        # Should still be a table, not replaced
        assert _object_type(conn, "my_view") == "table"
        row = conn.execute("SELECT id FROM my_view").fetchone()
        assert row[0] == 1
        conn.close()


class TestEnsureCompatViews:
    """Test _ensure_compat_views with various source table configurations."""

    def _make_conn(self):
        return sqlite3.connect(":memory:")

    def test_creates_ts_weekly_view_from_ts_daily(self):
        conn = self._make_conn()
        conn.execute(
            "CREATE TABLE ts_daily ("
            "  id INTEGER, ts_code TEXT, trade_date TEXT, open REAL, high REAL,"
            "  low REAL, close REAL, pre_close REAL, change REAL, pct_chg REAL,"
            "  vol REAL, amount REAL, updated_at TEXT"
            ")"
        )
        _ensure_compat_views(conn)
        assert _object_type(conn, "ts_weekly") == "view"
        conn.close()

    def test_skips_ts_weekly_if_table_already_exists(self):
        conn = self._make_conn()
        conn.execute("CREATE TABLE ts_daily (id INTEGER)")
        conn.execute("CREATE TABLE ts_weekly (id INTEGER)")
        _ensure_compat_views(conn)
        # ts_weekly should still be a table, not overwritten
        assert _object_type(conn, "ts_weekly") == "table"
        conn.close()

    def test_creates_ts_weekly_valuation_from_ts_daily_basic(self):
        conn = self._make_conn()
        conn.execute(
            "CREATE TABLE ts_daily_basic ("
            "  id INTEGER, ts_code TEXT, trade_date TEXT, pe REAL, pe_ttm REAL,"
            "  pb REAL, ps REAL, ps_ttm REAL, total_mv REAL, circ_mv REAL,"
            "  updated_at TEXT, turnover_rate REAL, volume_ratio REAL, dv_ttm REAL"
            ")"
        )
        _ensure_compat_views(conn)
        assert _object_type(conn, "ts_weekly_valuation") == "view"
        conn.close()

    def test_creates_stocks_view_from_ts_stock_basic(self):
        conn = self._make_conn()
        conn.execute(
            "CREATE TABLE ts_stock_basic (symbol TEXT, name TEXT, updated_at TEXT)"
        )
        _ensure_compat_views(conn)
        assert _object_type(conn, "stocks") == "view"
        conn.close()

    def test_creates_stock_daily_view_from_ts_daily_and_ts_daily_basic(self):
        conn = self._make_conn()
        conn.execute(
            "CREATE TABLE ts_daily ("
            "  id INTEGER, ts_code TEXT, trade_date TEXT, open REAL, high REAL,"
            "  low REAL, close REAL, pre_close REAL, change REAL, pct_chg REAL,"
            "  vol REAL, amount REAL, updated_at TEXT"
            ")"
        )
        conn.execute(
            "CREATE TABLE ts_daily_basic ("
            "  id INTEGER, ts_code TEXT, trade_date TEXT, pe REAL, pe_ttm REAL,"
            "  pb REAL, ps REAL, ps_ttm REAL, total_mv REAL, circ_mv REAL,"
            "  updated_at TEXT, turnover_rate REAL, volume_ratio REAL, dv_ttm REAL"
            ")"
        )
        _ensure_compat_views(conn)
        assert _object_type(conn, "stock_daily") == "view"
        conn.close()

    def test_creates_stock_valuation_from_ts_daily_basic(self):
        conn = self._make_conn()
        conn.execute(
            "CREATE TABLE ts_daily_basic ("
            "  id INTEGER, ts_code TEXT, trade_date TEXT, pe REAL, pe_ttm REAL,"
            "  pb REAL, ps REAL, ps_ttm REAL, total_mv REAL, circ_mv REAL,"
            "  updated_at TEXT, turnover_rate REAL, volume_ratio REAL, dv_ttm REAL"
            ")"
        )
        _ensure_compat_views(conn)
        assert _object_type(conn, "stock_valuation") == "view"
        conn.close()

    def test_creates_stock_valuation_from_ts_weekly_valuation_fallback(self):
        """When ts_daily_basic is absent, fall back to ts_weekly_valuation."""
        conn = self._make_conn()
        conn.execute(
            "CREATE TABLE ts_weekly_valuation ("
            "  id INTEGER, ts_code TEXT, trade_date TEXT, pe REAL, pe_ttm REAL,"
            "  pb REAL, ps REAL, ps_ttm REAL, total_mv REAL, circ_mv REAL,"
            "  updated_at TEXT"
            ")"
        )
        _ensure_compat_views(conn)
        assert _object_type(conn, "stock_valuation") == "view"
        conn.close()

    def test_creates_main_money_flow_from_ts_moneyflow(self):
        conn = self._make_conn()
        conn.execute(
            "CREATE TABLE ts_moneyflow ("
            "  ts_code TEXT, trade_date TEXT, net_mf_amount REAL,"
            "  buy_elg_amount REAL, buy_lg_amount REAL, updated_at TEXT"
            ")"
        )
        _ensure_compat_views(conn)
        assert _object_type(conn, "main_money_flow") == "view"
        conn.close()

    def test_creates_main_money_flow_from_money_flow_fallback(self):
        """When ts_moneyflow is absent, fall back to money_flow table."""
        conn = self._make_conn()
        conn.execute(
            "CREATE TABLE money_flow ("
            "  ts_code TEXT, trade_date TEXT, net_mf_amount REAL,"
            "  buy_elg_amount REAL, buy_lg_amount REAL, updated_at TEXT"
            ")"
        )
        _ensure_compat_views(conn)
        assert _object_type(conn, "main_money_flow") == "view"
        conn.close()

    def test_creates_north_money_holding_from_ts_hsgt_top10(self):
        conn = self._make_conn()
        conn.execute(
            "CREATE TABLE ts_hsgt_top10 ("
            "  ts_code TEXT, trade_date TEXT, net_amount REAL,"
            "  buy REAL, sell REAL, market_type TEXT, updated_at TEXT"
            ")"
        )
        _ensure_compat_views(conn)
        assert _object_type(conn, "north_money_holding") == "view"
        conn.close()

    def test_creates_dragon_tiger_stock_from_ts_top_list(self):
        conn = self._make_conn()
        conn.execute(
            "CREATE TABLE ts_top_list ("
            "  ts_code TEXT, trade_date TEXT, name TEXT, close REAL,"
            "  pct_change REAL, amount REAL, reason TEXT, updated_at TEXT"
            ")"
        )
        _ensure_compat_views(conn)
        assert _object_type(conn, "dragon_tiger_stock") == "view"
        conn.close()

    def test_creates_dragon_tiger_stock_from_dragon_tiger_fallback(self):
        conn = self._make_conn()
        conn.execute(
            "CREATE TABLE dragon_tiger ("
            "  ts_code TEXT, trade_date TEXT, name TEXT, close REAL,"
            "  pct_chg REAL, amount REAL, reason TEXT, updated_at TEXT,"
            "  turnover_rate REAL, net_amount REAL"
            ")"
        )
        _ensure_compat_views(conn)
        assert _object_type(conn, "dragon_tiger_stock") == "view"
        conn.close()

    def test_creates_sectors_from_ts_ths_index(self):
        conn = self._make_conn()
        conn.execute(
            "CREATE TABLE ts_ths_index ("
            "  ts_code TEXT, name TEXT, type TEXT, updated_at TEXT"
            ")"
        )
        _ensure_compat_views(conn)
        assert _object_type(conn, "sectors") == "view"
        conn.close()

    def test_creates_sector_stocks_from_ths_member_and_index(self):
        conn = self._make_conn()
        conn.execute(
            "CREATE TABLE ts_ths_index (ts_code TEXT, name TEXT, type TEXT, updated_at TEXT)"
        )
        conn.execute(
            "CREATE TABLE ts_ths_member (ts_code TEXT, con_code TEXT)"
        )
        _ensure_compat_views(conn)
        assert _object_type(conn, "sector_stocks") == "view"
        conn.close()

    def test_creates_sector_daily_rank_from_ts_ths_daily(self):
        conn = self._make_conn()
        conn.execute(
            "CREATE TABLE ts_ths_daily ("
            "  ts_code TEXT, trade_date TEXT, pct_change REAL"
            ")"
        )
        # Also need ts_ths_index for the LEFT JOIN in the view
        conn.execute(
            "CREATE TABLE ts_ths_index (ts_code TEXT, name TEXT, type TEXT, updated_at TEXT)"
        )
        _ensure_compat_views(conn)
        assert _object_type(conn, "sector_daily_rank") == "view"
        conn.close()

    def test_creates_limit_up_pool_from_dragon_tiger(self):
        conn = self._make_conn()
        conn.execute(
            "CREATE TABLE dragon_tiger ("
            "  ts_code TEXT, name TEXT, trade_date TEXT,"
            "  reason TEXT, turnover_rate REAL, net_amount REAL, pct_chg REAL"
            ")"
        )
        _ensure_compat_views(conn)
        assert _object_type(conn, "limit_up_pool") == "view"
        conn.close()

    def test_no_views_created_on_empty_database(self):
        """On a completely empty database, no views should be created."""
        conn = self._make_conn()
        _ensure_compat_views(conn)
        rows = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='view'"
        ).fetchall()
        assert len(rows) == 0
        conn.close()

    def test_does_not_overwrite_existing_target_tables(self):
        """If the target table already exists as a real table, the view is not created."""
        conn = self._make_conn()
        conn.execute("CREATE TABLE ts_daily (id INTEGER)")
        conn.execute("CREATE TABLE ts_weekly (id INTEGER)")
        conn.execute(
            "CREATE TABLE ts_stock_basic (symbol TEXT, name TEXT, updated_at TEXT)"
        )
        conn.execute("CREATE TABLE stocks (code TEXT, name TEXT)")
        _ensure_compat_views(conn)
        assert _object_type(conn, "ts_weekly") == "table"
        assert _object_type(conn, "stocks") == "table"
        conn.close()
