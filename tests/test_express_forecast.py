"""Tests for express (业绩快报) and forecast (业绩预告) fetchers."""

import sqlite3
from unittest.mock import MagicMock

import pandas as pd
import pytest

from src.data_ingestion.tushare.express_forecast import (
    fetch_express,
    fetch_forecast,
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
    def test_init_tables_creates_both_tables(self, mem_conn):
        """init_tables should create both ts_express and ts_forecast tables."""
        init_tables(conn=mem_conn)

        cursor = mem_conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        )
        tables = [row["name"] for row in cursor.fetchall()]
        assert "ts_express" in tables
        assert "ts_forecast" in tables


class TestFetchExpress:
    def test_fetch_express_inserts_data(self, mem_conn):
        """fetch_express should insert rows returned by the API client."""
        init_tables(conn=mem_conn)

        mock_client = MagicMock()
        mock_client.express.return_value = pd.DataFrame(
            {
                "ts_code": ["000001.SZ"],
                "ann_date": ["20260115"],
                "end_date": ["20251231"],
                "revenue": [50000000000.0],
                "operate_profit": [20000000000.0],
                "total_profit": [18000000000.0],
                "n_income": [15000000000.0],
                "total_assets": [100000000000.0],
                "yoy_net_profit": [12.5],
            }
        )

        count = fetch_express("000001.SZ", client=mock_client, conn=mem_conn)

        assert count == 1
        rows = mem_conn.execute("SELECT * FROM ts_express").fetchall()
        assert len(rows) == 1
        assert rows[0]["ts_code"] == "000001.SZ"
        assert rows[0]["revenue"] == 50000000000.0
        assert rows[0]["yoy_net_profit"] == 12.5


class TestFetchForecast:
    def test_fetch_forecast_inserts_data(self, mem_conn):
        """fetch_forecast should insert rows returned by the API client."""
        init_tables(conn=mem_conn)

        mock_client = MagicMock()
        mock_client.forecast.return_value = pd.DataFrame(
            {
                "ts_code": ["000001.SZ"],
                "ann_date": ["20260115"],
                "end_date": ["20251231"],
                "type": ["\u9884\u589e"],
                "p_change_min": [30.0],
                "p_change_max": [50.0],
                "net_profit_min": [1000000000.0],
                "net_profit_max": [1500000000.0],
            }
        )

        count = fetch_forecast("000001.SZ", client=mock_client, conn=mem_conn)

        assert count == 1
        rows = mem_conn.execute("SELECT * FROM ts_forecast").fetchall()
        assert len(rows) == 1
        assert rows[0]["ts_code"] == "000001.SZ"
        assert rows[0]["type"] == "\u9884\u589e"
        assert rows[0]["p_change_min"] == 30.0
        assert rows[0]["net_profit_max"] == 1500000000.0
