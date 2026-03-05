"""Tests for holder number (股东人数) fetcher."""

import sqlite3
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from src.data_ingestion.tushare.holder_number import (
    fetch_holder_number,
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
    def test_init_tables_creates_holder_number(self, mem_conn):
        """init_tables should create ts_holder_number table in the given connection."""
        init_tables(conn=mem_conn)

        cursor = mem_conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='ts_holder_number'"
        )
        tables = [row["name"] for row in cursor.fetchall()]
        assert "ts_holder_number" in tables


class TestFetchHolderNumber:
    def test_fetch_holder_number_inserts_data(self, mem_conn):
        """fetch_holder_number should insert rows returned by the API client."""
        init_tables(conn=mem_conn)

        mock_client = MagicMock()
        mock_client.stk_holdernumber.return_value = pd.DataFrame(
            {
                "ts_code": ["000001.SZ", "000001.SZ"],
                "ann_date": ["20240315", "20240115"],
                "end_date": ["20231231", "20230930"],
                "holder_num": [150000, 160000],
            }
        )

        fetch_holder_number("000001.SZ", client=mock_client, conn=mem_conn)

        rows = mem_conn.execute("SELECT * FROM ts_holder_number").fetchall()
        assert len(rows) == 2

    def test_holder_num_change_calculated(self, mem_conn):
        """holder_num_change should be (current - previous) / previous * 100."""
        init_tables(conn=mem_conn)

        mock_client = MagicMock()
        # Three periods, sorted by end_date ascending: Q1, Q2, Q3
        mock_client.stk_holdernumber.return_value = pd.DataFrame(
            {
                "ts_code": ["000001.SZ", "000001.SZ", "000001.SZ"],
                "ann_date": ["20240415", "20240715", "20241015"],
                "end_date": ["20240331", "20240630", "20240930"],
                "holder_num": [100000, 120000, 90000],
            }
        )

        fetch_holder_number("000001.SZ", client=mock_client, conn=mem_conn)

        rows = mem_conn.execute(
            "SELECT holder_num, holder_num_change FROM ts_holder_number ORDER BY end_date"
        ).fetchall()

        assert len(rows) == 3

        # First period: no previous data, change should be None
        assert rows[0]["holder_num_change"] is None

        # Second period: (120000 - 100000) / 100000 * 100 = 20.0
        assert rows[1]["holder_num_change"] == pytest.approx(20.0)

        # Third period: (90000 - 120000) / 120000 * 100 = -25.0
        assert rows[2]["holder_num_change"] == pytest.approx(-25.0)
