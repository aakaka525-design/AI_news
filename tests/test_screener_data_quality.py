"""测试选股器 data_quality 元数据字段"""
import sqlite3
import pandas as pd


def test_score_fundamentals_has_data_quality_fields():
    """score_fundamentals 输出应包含 data_completeness 和 financial_lag_quarters"""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("CREATE TABLE ts_stock_basic (ts_code TEXT PRIMARY KEY, name TEXT, industry TEXT, list_status TEXT)")
    conn.execute("CREATE TABLE ts_fina_indicator (ts_code TEXT, end_date TEXT, roe REAL, netprofit_yoy REAL)")
    conn.execute("CREATE TABLE ts_daily_basic (ts_code TEXT, trade_date TEXT, pe_ttm REAL, pb REAL)")

    conn.execute("INSERT INTO ts_stock_basic VALUES ('A.SZ','A','银行','L')")
    conn.execute("INSERT INTO ts_fina_indicator VALUES ('A.SZ','20251231',15.0,20.0)")
    conn.execute("INSERT INTO ts_daily_basic VALUES ('A.SZ','20260305',15.0,1.2)")
    conn.commit()

    from src.strategies.potential_screener import score_fundamentals

    result = score_fundamentals(conn, pd.Series(["A.SZ"]))
    assert "data_completeness" in result.columns, "Missing data_completeness column"
    assert "financial_lag_quarters" in result.columns, "Missing financial_lag_quarters column"
    conn.close()
