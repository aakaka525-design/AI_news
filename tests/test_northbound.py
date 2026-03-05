"""Tests for northbound holdings (北向持股) fetcher."""

import sqlite3
from unittest.mock import MagicMock

import pandas as pd
import pytest

from src.data_ingestion.tushare.northbound import (
    fetch_northbound_by_date,
    init_tables,
)


@pytest.fixture
def mem_conn():
    """Provide an in-memory SQLite connection for isolated testing."""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    yield conn
    conn.close()


class TestInitTables:
    def test_init_tables_creates_hk_hold(self, mem_conn):
        """init_tables should create ts_hk_hold table in the given connection."""
        init_tables(conn=mem_conn)

        cursor = mem_conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='ts_hk_hold'"
        )
        tables = [row["name"] for row in cursor.fetchall()]
        assert "ts_hk_hold" in tables


class TestFetchNorthboundByDate:
    def test_fetch_northbound_by_date(self, mem_conn):
        """fetch_northbound_by_date should insert rows returned by the API client."""
        init_tables(conn=mem_conn)

        mock_client = MagicMock()
        mock_client.hk_hold.return_value = pd.DataFrame(
            {
                "ts_code": ["000001.SZ", "000002.SZ", "600000.SH"],
                "trade_date": ["20260303", "20260303", "20260303"],
                "vol": [50000000, 30000000, 20000000],
                "ratio": [1.25, 0.88, 2.10],
                "exchange": ["SZ", "SZ", "SH"],
            }
        )

        count = fetch_northbound_by_date(
            "20260303", client=mock_client, conn=mem_conn
        )

        assert count == 3
        rows = mem_conn.execute("SELECT * FROM ts_hk_hold").fetchall()
        assert len(rows) == 3

    def test_fetch_northbound_upsert(self, mem_conn):
        """Inserting the same (ts_code, trade_date) twice should upsert; second value wins."""
        init_tables(conn=mem_conn)

        mock_client = MagicMock()

        # First insert: vol = 50000000
        mock_client.hk_hold.return_value = pd.DataFrame(
            {
                "ts_code": ["000001.SZ"],
                "trade_date": ["20260303"],
                "vol": [50000000],
                "ratio": [1.25],
                "exchange": ["SZ"],
            }
        )
        fetch_northbound_by_date("20260303", client=mock_client, conn=mem_conn)

        # Second insert: vol = 60000000 (updated)
        mock_client.hk_hold.return_value = pd.DataFrame(
            {
                "ts_code": ["000001.SZ"],
                "trade_date": ["20260303"],
                "vol": [60000000],
                "ratio": [1.50],
                "exchange": ["SZ"],
            }
        )
        fetch_northbound_by_date("20260303", client=mock_client, conn=mem_conn)

        rows = mem_conn.execute("SELECT * FROM ts_hk_hold").fetchall()
        assert len(rows) == 1, "Upsert should keep only 1 row for same (ts_code, trade_date)"
        assert rows[0]["vol"] == 60000000, "Second insert value should win"
        assert rows[0]["ratio"] == pytest.approx(1.50)
