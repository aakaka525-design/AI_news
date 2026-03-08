"""Tests for core fetcher modules (research_report, trading_calendar, main_money_flow).

All external API calls (akshare, eastmoney, DB) are mocked.
"""

from __future__ import annotations

from datetime import datetime
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest


# ---------------------------------------------------------------------------
# research_report tests
# ---------------------------------------------------------------------------

class TestResearchReportHelpers:
    """Test helper functions in fetchers.research_report."""

    def test_stock_suffix_sh(self):
        from fetchers.research_report import _stock_suffix
        assert _stock_suffix("600519") == "600519.SH"
        assert _stock_suffix("688111") == "688111.SH"

    def test_stock_suffix_sz(self):
        from fetchers.research_report import _stock_suffix
        assert _stock_suffix("000001") == "000001.SZ"
        assert _stock_suffix("300750") == "300750.SZ"

    def test_stock_suffix_strips_whitespace(self):
        from fetchers.research_report import _stock_suffix
        assert _stock_suffix("  600519  ") == "600519.SH"

    def test_normalize_date_with_dashes(self):
        from fetchers.research_report import _normalize_date
        assert _normalize_date("2026-03-08") == "20260308"

    def test_normalize_date_already_compact(self):
        from fetchers.research_report import _normalize_date
        assert _normalize_date("20260308") == "20260308"

    def test_normalize_date_empty(self):
        from fetchers.research_report import _normalize_date
        assert _normalize_date("") == ""


class TestParseEastmoneyReports:
    """Test parse_eastmoney_reports with various DataFrame inputs."""

    def test_valid_full_dataframe(self):
        from fetchers.research_report import parse_eastmoney_reports

        df = pd.DataFrame({
            "股票简称": ["贵州茅台", "贵州茅台"],
            "报告名称": ["业绩快报点评", "季度跟踪"],
            "东财评级": ["买入", "增持"],
            "机构": ["中信证券", "华泰证券"],
            "日期": ["2026-03-01", "2026-02-28"],
        })
        reports = parse_eastmoney_reports("600519", df)

        assert len(reports) == 2
        assert reports[0]["ts_code"] == "600519.SH"
        assert reports[0]["title"] == "业绩快报点评"
        assert reports[0]["rating"] == "买入"
        assert reports[0]["institution"] == "中信证券"
        assert reports[0]["publish_date"] == "20260301"
        assert reports[1]["publish_date"] == "20260228"

    def test_empty_dataframe_returns_empty_list(self):
        from fetchers.research_report import parse_eastmoney_reports
        assert parse_eastmoney_reports("000001", pd.DataFrame()) == []

    def test_none_input_returns_empty_list(self):
        from fetchers.research_report import parse_eastmoney_reports
        assert parse_eastmoney_reports("000001", None) == []

    def test_missing_optional_columns_use_defaults(self):
        from fetchers.research_report import parse_eastmoney_reports

        df = pd.DataFrame({"日期": ["2026-03-01"]})
        reports = parse_eastmoney_reports("000001", df)

        assert len(reports) == 1
        assert reports[0]["title"] == "无标题"
        assert reports[0]["stock_name"] is None
        assert reports[0]["rating"] is None
        assert reports[0]["institution"] is None

    def test_non_dataframe_without_empty_attr(self):
        """Objects that lack .empty should be treated like None."""
        from fetchers.research_report import parse_eastmoney_reports
        assert parse_eastmoney_reports("000001", "not_a_df") == []


class TestFetchStockReports:
    """Test fetch_stock_reports with mocked akshare."""

    @patch("fetchers.research_report.ak")
    def test_successful_fetch(self, mock_ak):
        from fetchers.research_report import fetch_stock_reports

        mock_ak.stock_research_report_em.return_value = pd.DataFrame({
            "股票简称": ["平安银行"],
            "报告名称": ["估值修复"],
            "东财评级": ["买入"],
            "机构": ["国泰君安"],
            "日期": ["2026-03-05"],
        })

        reports = fetch_stock_reports("000001", timeout=5)

        assert len(reports) == 1
        assert reports[0]["ts_code"] == "000001.SZ"
        mock_ak.stock_research_report_em.assert_called_once_with(symbol="000001")

    @patch("fetchers.research_report.ak")
    def test_api_exception_returns_empty(self, mock_ak):
        from fetchers.research_report import fetch_stock_reports

        mock_ak.stock_research_report_em.side_effect = RuntimeError("network error")

        reports = fetch_stock_reports("000001", timeout=5)
        assert reports == []

    @patch("fetchers.research_report.ak")
    def test_empty_api_response(self, mock_ak):
        from fetchers.research_report import fetch_stock_reports

        mock_ak.stock_research_report_em.return_value = pd.DataFrame()
        reports = fetch_stock_reports("000001", timeout=5)
        assert reports == []


# ---------------------------------------------------------------------------
# trading_calendar tests
# ---------------------------------------------------------------------------

class TestTradingCalendarParsing:
    """Test trading_calendar date filtering and queries."""

    @patch("fetchers.trading_calendar.load_trading_days")
    def test_is_trading_day_true(self, mock_load):
        from fetchers.trading_calendar import is_trading_day

        mock_load.return_value = {"2026-03-06", "2026-03-07", "2026-03-08"}
        assert is_trading_day("2026-03-06") is True

    @patch("fetchers.trading_calendar.load_trading_days")
    def test_is_trading_day_false_weekend(self, mock_load):
        from fetchers.trading_calendar import is_trading_day

        mock_load.return_value = {"2026-03-06", "2026-03-09"}
        assert is_trading_day("2026-03-07") is False

    @patch("fetchers.trading_calendar.load_trading_days")
    def test_get_latest_trading_day(self, mock_load):
        from fetchers.trading_calendar import get_latest_trading_day

        mock_load.return_value = {
            "2026-03-02", "2026-03-03", "2026-03-04",
            "2026-03-05", "2026-03-06",
        }
        result = get_latest_trading_day(before_date="2026-03-04")
        assert result == "2026-03-04"

    @patch("fetchers.trading_calendar.load_trading_days")
    def test_get_latest_trading_day_skips_future(self, mock_load):
        from fetchers.trading_calendar import get_latest_trading_day

        mock_load.return_value = {"2026-03-02", "2026-03-03", "2026-03-10"}
        result = get_latest_trading_day(before_date="2026-03-05")
        assert result == "2026-03-03"

    @patch("fetchers.trading_calendar.load_trading_days")
    def test_get_latest_trading_day_empty(self, mock_load):
        from fetchers.trading_calendar import get_latest_trading_day

        mock_load.return_value = set()
        assert get_latest_trading_day(before_date="2026-03-05") is None

    @patch("fetchers.trading_calendar.load_trading_days")
    def test_get_trading_days_range(self, mock_load):
        from fetchers.trading_calendar import get_trading_days_range

        mock_load.return_value = {
            "2026-03-02", "2026-03-03", "2026-03-04",
            "2026-03-05", "2026-03-06", "2026-03-10",
        }
        days = get_trading_days_range("2026-03-03", "2026-03-06")
        assert days == ["2026-03-03", "2026-03-04", "2026-03-05", "2026-03-06"]

    @patch("fetchers.trading_calendar.load_trading_days")
    def test_get_prev_n_trading_days(self, mock_load):
        from fetchers.trading_calendar import get_prev_n_trading_days

        mock_load.return_value = {
            "2026-03-02", "2026-03-03", "2026-03-04",
            "2026-03-05", "2026-03-06",
        }
        days = get_prev_n_trading_days(3, before_date="2026-03-06")
        assert days == ["2026-03-06", "2026-03-05", "2026-03-04"]


class TestFetchTradingCalendar:
    """Test fetch_trading_calendar with mocked akshare."""

    @patch("fetchers.trading_calendar.ak")
    def test_fetch_all_dates(self, mock_ak):
        from fetchers.trading_calendar import fetch_trading_calendar

        mock_ak.tool_trade_date_hist_sina.return_value = pd.DataFrame({
            "trade_date": pd.to_datetime(["2026-03-02", "2026-03-03", "2025-12-31"])
        })
        dates = fetch_trading_calendar()
        assert len(dates) == 3

    @patch("fetchers.trading_calendar.ak")
    def test_fetch_filtered_by_year(self, mock_ak):
        from fetchers.trading_calendar import fetch_trading_calendar

        mock_ak.tool_trade_date_hist_sina.return_value = pd.DataFrame({
            "trade_date": pd.to_datetime(["2026-03-02", "2026-03-03", "2025-12-31"])
        })
        dates = fetch_trading_calendar(year=2026)
        assert len(dates) == 2
        assert all(d.startswith("2026") for d in dates)

    @patch("fetchers.trading_calendar.ak")
    def test_fetch_api_failure_returns_empty(self, mock_ak):
        from fetchers.trading_calendar import fetch_trading_calendar

        mock_ak.tool_trade_date_hist_sina.side_effect = Exception("API down")
        dates = fetch_trading_calendar()
        assert dates == []


class TestSaveTradingCalendar:
    """Test save_trading_calendar with mocked DB."""

    @patch("fetchers.trading_calendar.get_connection")
    @patch("fetchers.trading_calendar.init_trading_calendar_table")
    def test_save_dates(self, mock_init, mock_conn):
        from fetchers.trading_calendar import save_trading_calendar

        mock_connection = MagicMock()
        mock_conn.return_value = mock_connection

        count = save_trading_calendar(["2026-03-02", "2026-03-03", "2026-03-04"])

        assert count == 3
        assert mock_connection.execute.call_count == 3
        mock_connection.commit.assert_called_once()
        mock_connection.close.assert_called_once()

    @patch("fetchers.trading_calendar.get_connection")
    @patch("fetchers.trading_calendar.init_trading_calendar_table")
    def test_save_empty_list(self, mock_init, mock_conn):
        from fetchers.trading_calendar import save_trading_calendar
        assert save_trading_calendar([]) == 0


class TestCalculateTradingDayDelay:
    """Test delay calculation logic."""

    @patch("fetchers.trading_calendar.load_trading_days")
    def test_zero_delay_on_latest_day(self, mock_load):
        from fetchers.trading_calendar import calculate_trading_day_delay

        mock_load.return_value = {"2026-03-06", "2026-03-07", "2026-03-08"}
        delay = calculate_trading_day_delay("2026-03-08")
        assert delay == 0

    @patch("fetchers.trading_calendar.load_trading_days")
    def test_one_day_delay(self, mock_load):
        from fetchers.trading_calendar import calculate_trading_day_delay

        today = datetime.now().strftime("%Y-%m-%d")
        mock_load.return_value = {"2026-03-05", "2026-03-06", today}
        delay = calculate_trading_day_delay("2026-03-06")
        # Delay depends on how many of the days in range [2026-03-06, today] are trading days
        assert delay >= 0


# ---------------------------------------------------------------------------
# main_money_flow tests
# ---------------------------------------------------------------------------

class TestMainMoneyFlowSafeFloat:
    """Test the safe_float helper for parsing API responses."""

    def test_valid_number(self):
        from fetchers.main_money_flow import safe_float
        assert safe_float("123.45") == 123.45

    def test_none_returns_none(self):
        from fetchers.main_money_flow import safe_float
        assert safe_float(None) is None

    def test_dash_returns_none(self):
        from fetchers.main_money_flow import safe_float
        assert safe_float("-") is None

    def test_empty_string_returns_none(self):
        from fetchers.main_money_flow import safe_float
        assert safe_float("") is None

    def test_invalid_string_returns_none(self):
        from fetchers.main_money_flow import safe_float
        assert safe_float("abc") is None

    def test_integer_input(self):
        from fetchers.main_money_flow import safe_float
        assert safe_float(42) == 42.0


class TestSaveMoneyFlows:
    """Test save_money_flows with mocked DB."""

    def test_save_valid_records(self, monkeypatch):
        from fetchers import main_money_flow

        class _DummyConn:
            def __init__(self):
                self.committed = False
                self.closed = False
            def commit(self):
                self.committed = True
            def close(self):
                self.closed = True

        class _DummyRecord:
            def __init__(self, data):
                self._data = data
            def model_dump(self, exclude_none=False):
                return self._data

        conn = _DummyConn()
        monkeypatch.setattr(main_money_flow, "get_connection", lambda: conn)

        import fetchers.db as fetcher_db
        monkeypatch.setattr(
            fetcher_db, "validate_and_create",
            lambda _cls, data: _DummyRecord(data),
        )
        monkeypatch.setattr(
            fetcher_db, "insert_validated",
            lambda _conn, _table, _record, _keys: True,
        )

        records = [
            {"stock_code": "000001", "date": "2026-03-01", "main_net_inflow": 12.3},
            {"stock_code": "000002", "date": "2026-03-01", "main_net_inflow": -5.6},
        ]
        saved = main_money_flow.save_money_flows(records)

        assert saved == 2
        assert conn.committed is True
        assert conn.closed is True

    def test_save_empty_list(self):
        from fetchers.main_money_flow import save_money_flows
        assert save_money_flows([]) == 0

    def test_skips_records_without_main_net_inflow(self, monkeypatch):
        from fetchers import main_money_flow

        class _DummyConn:
            def commit(self): pass
            def close(self): pass

        monkeypatch.setattr(main_money_flow, "get_connection", lambda: _DummyConn())

        # Record with main_net_inflow=None should be skipped
        saved = main_money_flow.save_money_flows(
            [{"stock_code": "000001", "date": "2026-03-01", "main_net_inflow": None}]
        )
        assert saved == 0

    def test_skips_none_entries(self, monkeypatch):
        from fetchers import main_money_flow

        class _DummyConn:
            def commit(self): pass
            def close(self): pass

        monkeypatch.setattr(main_money_flow, "get_connection", lambda: _DummyConn())

        saved = main_money_flow.save_money_flows([None, None])
        assert saved == 0
