"""AkShare producers 单元测试"""
import sqlite3

import pytest
import pandas as pd
from unittest.mock import patch, MagicMock


class TestUtils:
    """公共工具测试"""

    def test_ts_code_from_symbol(self):
        from src.data_ingestion.akshare.producers.utils import ts_code_from_symbol
        assert ts_code_from_symbol("000001") == "000001.SZ"
        assert ts_code_from_symbol("600036") == "600036.SH"
        assert ts_code_from_symbol("300750") == "300750.SZ"
        assert ts_code_from_symbol("688001") == "688001.SH"
        assert ts_code_from_symbol("000001.SZ") == "000001.SZ"

    def test_safe_float(self):
        from src.data_ingestion.akshare.producers.utils import safe_float
        assert safe_float(3.14) == 3.14
        assert safe_float("2.5") == 2.5
        assert safe_float(None) is None
        assert safe_float(float("nan")) is None
        assert safe_float("abc") is None

    def test_safe_str(self):
        from src.data_ingestion.akshare.producers.utils import safe_str
        assert safe_str("hello") == "hello"
        assert safe_str(None) is None
        assert safe_str(float("nan")) is None
        assert safe_str("  ") is None
        assert safe_str("  abc  ") == "abc"


class TestStockBasicProducer:
    """stock_basic producer 测试"""

    def test_market_from_symbol(self):
        from src.data_ingestion.akshare.producers.stock_basic import _market_from_symbol
        assert _market_from_symbol("600036") == "主板"
        assert _market_from_symbol("000001") == "主板"
        assert _market_from_symbol("300750") == "创业板"
        assert _market_from_symbol("688001") == "科创板"

    def test_exchange_from_symbol(self):
        from src.data_ingestion.akshare.producers.stock_basic import _exchange_from_symbol
        assert _exchange_from_symbol("600036") == "SSE"
        assert _exchange_from_symbol("000001") == "SZSE"
        assert _exchange_from_symbol("300750") == "SZSE"

    @patch("src.data_ingestion.akshare.producers.stock_basic.ak")
    def test_fetch_stock_list_basic(self, mock_ak):
        mock_ak.stock_info_a_code_name.return_value = pd.DataFrame({
            "code": ["000001", "600036"],
            "name": ["平安银行", "招商银行"],
        })
        from src.data_ingestion.akshare.producers.stock_basic import _fetch_stock_list
        result = _fetch_stock_list()
        assert len(result) == 2
        assert result.iloc[0]["ts_code"] == "000001.SZ"

    def test_write_stock_basic_to_db(self, tmp_path):
        db = tmp_path / "test.db"
        conn = sqlite3.connect(str(db))
        conn.execute("""
            CREATE TABLE ts_stock_basic (
                ts_code TEXT PRIMARY KEY, symbol TEXT, name TEXT,
                area TEXT, industry TEXT, fullname TEXT, market TEXT,
                exchange TEXT, list_status TEXT, list_date TEXT,
                delist_date TEXT, is_hs TEXT, updated_at TIMESTAMP
            )
        """)
        from src.data_ingestion.akshare.producers.stock_basic import _write_stock_basic
        df = pd.DataFrame({
            "ts_code": ["000001.SZ"], "symbol": ["000001"], "name": ["平安银行"],
            "industry": ["银行"], "market": ["主板"], "exchange": ["SZSE"],
            "list_status": ["L"], "list_date": ["20001219"],
        })
        count = _write_stock_basic(conn, df)
        assert count == 1
        rows = conn.execute("SELECT * FROM ts_stock_basic").fetchall()
        assert len(rows) == 1
        conn.close()

    def test_write_stock_basic_idempotent(self, tmp_path):
        """INSERT OR REPLACE 幂等性"""
        db = tmp_path / "test.db"
        conn = sqlite3.connect(str(db))
        conn.execute("""
            CREATE TABLE ts_stock_basic (
                ts_code TEXT PRIMARY KEY, symbol TEXT, name TEXT,
                area TEXT, industry TEXT, fullname TEXT, market TEXT,
                exchange TEXT, list_status TEXT, list_date TEXT,
                delist_date TEXT, is_hs TEXT, updated_at TIMESTAMP
            )
        """)
        from src.data_ingestion.akshare.producers.stock_basic import _write_stock_basic
        df = pd.DataFrame({
            "ts_code": ["000001.SZ"], "symbol": ["000001"], "name": ["平安银行"],
            "industry": ["银行"], "market": ["主板"], "exchange": ["SZSE"],
            "list_status": ["L"], "list_date": ["20001219"],
        })
        _write_stock_basic(conn, df)
        _write_stock_basic(conn, df)  # 再写一次不报错
        rows = conn.execute("SELECT * FROM ts_stock_basic").fetchall()
        assert len(rows) == 1
        conn.close()


class TestDailyProducer:
    """daily producer 测试"""

    @patch("src.data_ingestion.akshare.producers.daily.ak")
    def test_fetch_daily_single_stock(self, mock_ak):
        mock_ak.stock_zh_a_hist.return_value = pd.DataFrame({
            "日期": ["2026-03-09"],
            "开盘": [10.0], "收盘": [10.5], "最高": [10.8], "最低": [9.9],
            "成交量": [100000], "成交额": [1050000000],
            "涨跌幅": [5.0], "涨跌额": [0.5], "换手率": [2.5],
        })
        from src.data_ingestion.akshare.producers.daily import _fetch_daily_one
        result = _fetch_daily_one("000001", "20260309", "20260309")
        assert len(result) == 1
        assert result.iloc[0]["close"] == 10.5

    def test_write_daily_to_db(self, tmp_path):
        db = tmp_path / "test.db"
        conn = sqlite3.connect(str(db))
        conn.execute("""
            CREATE TABLE ts_daily (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ts_code TEXT, trade_date TEXT, open REAL, high REAL,
                low REAL, close REAL, pre_close REAL, change REAL,
                pct_chg REAL, vol REAL, amount REAL, adj_factor REAL,
                updated_at TIMESTAMP, UNIQUE(ts_code, trade_date)
            )
        """)
        from src.data_ingestion.akshare.producers.daily import _write_daily
        df = pd.DataFrame({
            "ts_code": ["000001.SZ"], "trade_date": ["20260309"],
            "open": [10.0], "high": [10.8], "low": [9.9], "close": [10.5],
            "pre_close": [10.0], "change": [0.5], "pct_chg": [5.0],
            "vol": [100000], "amount": [1050000.0], "adj_factor": [1.0],
        })
        count = _write_daily(conn, df)
        assert count == 1
        rows = conn.execute("SELECT * FROM ts_daily").fetchall()
        assert len(rows) == 1
        conn.close()

    def test_write_daily_idempotent(self, tmp_path):
        db = tmp_path / "test.db"
        conn = sqlite3.connect(str(db))
        conn.execute("""
            CREATE TABLE ts_daily (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ts_code TEXT, trade_date TEXT, open REAL, high REAL,
                low REAL, close REAL, pre_close REAL, change REAL,
                pct_chg REAL, vol REAL, amount REAL, adj_factor REAL,
                updated_at TIMESTAMP, UNIQUE(ts_code, trade_date)
            )
        """)
        from src.data_ingestion.akshare.producers.daily import _write_daily
        df = pd.DataFrame({
            "ts_code": ["000001.SZ"], "trade_date": ["20260309"],
            "open": [10.0], "high": [10.8], "low": [9.9], "close": [10.5],
            "pre_close": [10.0], "change": [0.5], "pct_chg": [5.0],
            "vol": [100000], "amount": [1050000.0], "adj_factor": [1.0],
        })
        _write_daily(conn, df)
        _write_daily(conn, df)
        rows = conn.execute("SELECT * FROM ts_daily").fetchall()
        assert len(rows) == 1
        conn.close()
