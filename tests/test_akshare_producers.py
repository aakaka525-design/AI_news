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


class TestDailyBasicProducer:
    """daily_basic producer 测试"""

    @patch("src.data_ingestion.akshare.producers.daily_basic.ak")
    def test_fetch_spot_em(self, mock_ak):
        mock_ak.stock_zh_a_spot_em.return_value = pd.DataFrame({
            "代码": ["000001", "600036"],
            "名称": ["平安银行", "招商银行"],
            "市盈率-动态": [8.5, 6.2],
            "市净率": [0.9, 1.1],
            "总市值": [300000000000, 500000000000],
            "流通市值": [280000000000, 450000000000],
            "换手率": [1.5, 0.8],
            "量比": [1.2, 0.9],
        })
        from src.data_ingestion.akshare.producers.daily_basic import _fetch_spot_data
        result = _fetch_spot_data()
        assert len(result) == 2
        assert "pe_ttm" in result.columns
        # 市值应已转换为万元
        assert result.iloc[0]["total_mv"] == 300000000000 / 10000.0

    def test_write_daily_basic_to_db(self, tmp_path):
        db = tmp_path / "test.db"
        conn = sqlite3.connect(str(db))
        conn.execute("""
            CREATE TABLE ts_daily_basic (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ts_code TEXT, trade_date TEXT, volume_ratio REAL,
                pe REAL, pe_ttm REAL, pb REAL,
                ps REAL, ps_ttm REAL, dv_ratio REAL, dv_ttm REAL,
                total_mv REAL, circ_mv REAL,
                total_share REAL, float_share REAL, free_share REAL,
                turnover_rate REAL, turnover_rate_f REAL,
                updated_at TIMESTAMP, UNIQUE(ts_code, trade_date)
            )
        """)
        from src.data_ingestion.akshare.producers.daily_basic import _write_daily_basic
        df = pd.DataFrame({
            "ts_code": ["000001.SZ"],
            "pe_ttm": [8.5], "pb": [0.9],
            "total_mv": [30000000.0], "circ_mv": [28000000.0],
            "turnover_rate": [1.5], "volume_ratio": [1.2],
        })
        count = _write_daily_basic(conn, df, "20260309")
        assert count == 1
        rows = conn.execute("SELECT * FROM ts_daily_basic").fetchall()
        assert len(rows) == 1
        conn.close()


class TestMoneyflowProducer:
    """moneyflow producer 测试"""

    def test_market_for_symbol(self):
        from src.data_ingestion.akshare.producers.moneyflow import _market_for_symbol
        assert _market_for_symbol("600036") == "sh"
        assert _market_for_symbol("000001") == "sz"
        assert _market_for_symbol("300750") == "sz"

    def test_write_moneyflow_to_db(self, tmp_path):
        db = tmp_path / "test.db"
        conn = sqlite3.connect(str(db))
        conn.execute("""
            CREATE TABLE ts_moneyflow (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ts_code TEXT, trade_date TEXT,
                buy_sm_vol REAL, buy_md_vol REAL, buy_lg_vol REAL, buy_elg_vol REAL,
                sell_sm_vol REAL, sell_md_vol REAL, sell_lg_vol REAL, sell_elg_vol REAL,
                buy_sm_amount REAL, buy_md_amount REAL, buy_lg_amount REAL, buy_elg_amount REAL,
                sell_sm_amount REAL, sell_md_amount REAL, sell_lg_amount REAL, sell_elg_amount REAL,
                net_mf_vol REAL, net_mf_amount REAL,
                updated_at TIMESTAMP, UNIQUE(ts_code, trade_date)
            )
        """)
        from src.data_ingestion.akshare.producers.moneyflow import _write_moneyflow
        row = pd.Series({"主力净流入-净额": 50000000.0})
        result = _write_moneyflow(conn, "000001.SZ", "20260309", row)
        assert result is True
        conn.commit()
        rows = conn.execute("SELECT * FROM ts_moneyflow").fetchall()
        assert len(rows) == 1
        conn.close()


class TestHkHoldProducer:
    """hk_hold producer 测试"""

    @patch("src.data_ingestion.akshare.producers.hk_hold.ak")
    def test_fetch_hk_hold_data(self, mock_ak):
        mock_ak.stock_hsgt_hold_stock_em.return_value = pd.DataFrame({
            "代码": ["000001", "600036"],
            "名称": ["平安银行", "招商银行"],
            "今日持股-股数": [1000000, 2000000],
            "今日持股-占流通股比": [0.5, 0.3],
        })
        from src.data_ingestion.akshare.producers.hk_hold import _fetch_hk_hold_data
        result = _fetch_hk_hold_data()
        assert len(result) == 2

    def test_write_hk_hold_to_db(self, tmp_path):
        db = tmp_path / "test.db"
        conn = sqlite3.connect(str(db))
        conn.execute("""
            CREATE TABLE ts_hk_hold (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ts_code TEXT, trade_date TEXT,
                vol INTEGER, ratio REAL, exchange TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(ts_code, trade_date)
            )
        """)
        from src.data_ingestion.akshare.producers.hk_hold import _write_hk_hold
        df = pd.DataFrame({
            "代码": ["000001", "600036"],
            "今日持股-股数": [1000000, 2000000],
            "今日持股-占流通股比": [0.5, 0.3],
        })
        count = _write_hk_hold(conn, df, "20260309")
        assert count == 2
        rows = conn.execute("SELECT * FROM ts_hk_hold").fetchall()
        assert len(rows) == 2
        conn.close()


class TestFinaIndicatorProducer:
    """fina_indicator producer 测试"""

    def test_write_fina_indicator_to_db(self, tmp_path):
        db = tmp_path / "test.db"
        conn = sqlite3.connect(str(db))
        conn.execute("""
            CREATE TABLE ts_fina_indicator (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ts_code TEXT NOT NULL, ann_date TEXT, end_date TEXT NOT NULL,
                eps REAL, dt_eps REAL, bps REAL, ocfps REAL, grps REAL,
                roe REAL, roe_waa REAL, roe_dt REAL, roa REAL, npta REAL, roic REAL,
                grossprofit_margin REAL, netprofit_margin REAL, op_of_gr REAL,
                or_yoy REAL, op_yoy REAL, tp_yoy REAL, netprofit_yoy REAL, dt_netprofit_yoy REAL,
                debt_to_assets REAL, current_ratio REAL, quick_ratio REAL,
                ar_turn REAL, inv_turn REAL, fa_turn REAL, assets_turn REAL,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(ts_code, end_date)
            )
        """)
        from src.data_ingestion.akshare.producers.fina_indicator import _write_fina_indicator
        df = pd.DataFrame({
            "日期": ["2025-12-31"],
            "摊薄每股收益": [1.5],
            "每股净资产": [10.2],
            "净资产收益率": [15.0],
            "销售毛利率": [30.0],
        })
        count = _write_fina_indicator(conn, "000001.SZ", df)
        assert count == 1
        rows = conn.execute("SELECT * FROM ts_fina_indicator").fetchall()
        assert len(rows) == 1
        conn.close()

    def test_write_fina_indicator_idempotent(self, tmp_path):
        db = tmp_path / "test.db"
        conn = sqlite3.connect(str(db))
        conn.execute("""
            CREATE TABLE ts_fina_indicator (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ts_code TEXT NOT NULL, ann_date TEXT, end_date TEXT NOT NULL,
                eps REAL, dt_eps REAL, bps REAL, ocfps REAL, grps REAL,
                roe REAL, roe_waa REAL, roe_dt REAL, roa REAL, npta REAL, roic REAL,
                grossprofit_margin REAL, netprofit_margin REAL, op_of_gr REAL,
                or_yoy REAL, op_yoy REAL, tp_yoy REAL, netprofit_yoy REAL, dt_netprofit_yoy REAL,
                debt_to_assets REAL, current_ratio REAL, quick_ratio REAL,
                ar_turn REAL, inv_turn REAL, fa_turn REAL, assets_turn REAL,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(ts_code, end_date)
            )
        """)
        from src.data_ingestion.akshare.producers.fina_indicator import _write_fina_indicator
        df = pd.DataFrame({
            "日期": ["2025-12-31"],
            "摊薄每股收益": [1.5],
            "每股净资产": [10.2],
            "净资产收益率": [15.0],
        })
        _write_fina_indicator(conn, "000001.SZ", df)
        _write_fina_indicator(conn, "000001.SZ", df)
        rows = conn.execute("SELECT * FROM ts_fina_indicator").fetchall()
        assert len(rows) == 1
        conn.close()
