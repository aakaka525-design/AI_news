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
