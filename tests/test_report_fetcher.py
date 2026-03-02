"""Tests for research report fetcher."""

import pandas as pd

from fetchers.research_report import parse_eastmoney_reports


class TestParseEastmoneyReports:
    def test_parse_valid_dataframe(self):
        df = pd.DataFrame(
            {
                "股票简称": ["平安银行"],
                "报告名称": ["业绩超预期"],
                "东财评级": ["买入"],
                "机构": ["中信证券"],
                "行业": ["银行"],
                "日期": ["2026-03-01"],
            }
        )
        reports = parse_eastmoney_reports("000001", df)
        assert len(reports) == 1
        assert reports[0]["ts_code"] == "000001.SZ"
        assert reports[0]["title"] == "业绩超预期"
        assert reports[0]["rating"] == "买入"
        assert reports[0]["institution"] == "中信证券"
        assert reports[0]["publish_date"] == "20260301"

    def test_parse_empty_dataframe(self):
        df = pd.DataFrame()
        assert parse_eastmoney_reports("000001", df) == []

    def test_parse_none_dataframe(self):
        assert parse_eastmoney_reports("000001", None) == []

    def test_parse_handles_missing_columns(self):
        df = pd.DataFrame({"报告名称": ["test"]})
        reports = parse_eastmoney_reports("000001", df)
        assert len(reports) == 1
        assert reports[0]["title"] == "test"

    def test_code_suffix_sh(self):
        df = pd.DataFrame(
            {
                "报告名称": ["test"],
                "日期": ["2026-03-01"],
            }
        )
        reports = parse_eastmoney_reports("600519", df)
        assert reports[0]["ts_code"] == "600519.SH"

    def test_code_suffix_sz(self):
        df = pd.DataFrame(
            {
                "报告名称": ["test"],
                "日期": ["2026-03-01"],
            }
        )
        reports = parse_eastmoney_reports("000001", df)
        assert reports[0]["ts_code"] == "000001.SZ"

    def test_date_normalization(self):
        df = pd.DataFrame(
            {
                "报告名称": ["test"],
                "日期": ["2026-03-01"],
            }
        )
        reports = parse_eastmoney_reports("000001", df)
        assert reports[0]["publish_date"] == "20260301"

    def test_date_normalization_no_dash(self):
        df = pd.DataFrame(
            {
                "报告名称": ["test"],
                "日期": ["20260301"],
            }
        )
        reports = parse_eastmoney_reports("000001", df)
        assert reports[0]["publish_date"] == "20260301"
