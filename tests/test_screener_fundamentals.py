"""Tests for score_fundamentals: industry median PE and NULL PE handling."""

import math
import sqlite3

import numpy as np
import pandas as pd
import pytest


@pytest.fixture
def conn_with_data():
    """Create in-memory DB with test data for score_fundamentals.

    Stocks:
      - Stock A (000001.SZ): PE=15, ROE=20, growth=35, industry=银行,
            industry median PE=20 → PE < median → should score well
      - Stock B (000002.SZ): PE=NULL, ROE=12, growth=15, industry=科技
            → pe_missing, fund_pe=NaN, weight redistributed to ROE and growth
    """
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row

    # ts_stock_basic: maps ts_code → industry
    conn.execute("""
        CREATE TABLE ts_stock_basic (
            ts_code TEXT PRIMARY KEY,
            name TEXT,
            industry TEXT
        )
    """)
    conn.execute("INSERT INTO ts_stock_basic VALUES ('000001.SZ', 'StockA', '银行')")
    conn.execute("INSERT INTO ts_stock_basic VALUES ('000002.SZ', 'StockB', '科技')")

    # ts_fina_indicator: ROE and netprofit_yoy
    conn.execute("""
        CREATE TABLE ts_fina_indicator (
            ts_code TEXT NOT NULL,
            end_date TEXT NOT NULL,
            roe REAL,
            netprofit_yoy REAL
        )
    """)
    # Stock A: ROE=20 (>15 → 8pts), growth=35 (>30 → 5pts)
    conn.execute(
        "INSERT INTO ts_fina_indicator VALUES ('000001.SZ', '20251231', 20.0, 35.0)"
    )
    # Stock B: ROE=12 (>10 → 5pts), growth=15 (>10 → 3pts)
    conn.execute(
        "INSERT INTO ts_fina_indicator VALUES ('000002.SZ', '20251231', 12.0, 15.0)"
    )

    # ts_daily_basic: PE_TTM data
    conn.execute("""
        CREATE TABLE ts_daily_basic (
            ts_code TEXT NOT NULL,
            trade_date TEXT NOT NULL,
            pe_ttm REAL,
            UNIQUE(ts_code, trade_date)
        )
    """)
    # Stock A: PE=15 (in 银行, median=20 → PE <= median → 5pts at least)
    conn.execute(
        "INSERT INTO ts_daily_basic VALUES ('000001.SZ', '20260305', 15.0)"
    )
    # Stock B: PE=NULL (missing)
    conn.execute(
        "INSERT INTO ts_daily_basic VALUES ('000002.SZ', '20260305', NULL)"
    )

    # industry_valuation: pre-computed industry PE median/percentiles
    conn.execute("""
        CREATE TABLE industry_valuation (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            trade_date TEXT NOT NULL,
            industry TEXT NOT NULL,
            pe_median REAL,
            pe_p25 REAL,
            pe_p75 REAL,
            pb_median REAL,
            stock_count INTEGER,
            valid_pe_count INTEGER,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(trade_date, industry)
        )
    """)
    # 银行 industry: median=20, p25=12, p75=30
    conn.execute("""
        INSERT INTO industry_valuation (trade_date, industry, pe_median, pe_p25, pe_p75, stock_count, valid_pe_count)
        VALUES ('20260305', '银行', 20.0, 12.0, 30.0, 10, 8)
    """)
    # 科技 industry: median=40, p25=25, p75=60
    conn.execute("""
        INSERT INTO industry_valuation (trade_date, industry, pe_median, pe_p25, pe_p75, stock_count, valid_pe_count)
        VALUES ('20260305', '科技', 40.0, 25.0, 60.0, 15, 12)
    """)

    conn.commit()
    yield conn
    conn.close()


def test_null_pe_not_zero_score(conn_with_data):
    """PE 为 NULL 的股票, fund_pe 应为 NaN (not 0), weight redistributed."""
    from src.strategies.potential_screener import score_fundamentals

    candidates = pd.Series(["000001.SZ", "000002.SZ"])
    result = score_fundamentals(conn_with_data, candidates)

    # Stock B (000002.SZ) has NULL PE
    row_b = result[result["ts_code"] == "000002.SZ"].iloc[0]

    # fund_pe must be NaN, NOT 0
    assert math.isnan(row_b["fund_pe"]), (
        f"Expected fund_pe to be NaN for NULL PE stock, got {row_b['fund_pe']}"
    )

    # With pe_missing, ROE weight gets +3: ROE=12 (>10 → base 5) + 3 = 8
    # Growth weight gets +4: growth=15 (>10 → base 3) + 4 = 7
    # score_fundamental should be sum of redistributed ROE + redistributed growth (no PE)
    # ROE bonus: 5 + 3 = 8, Growth bonus: 3 + 4 = 7 → total = 15
    assert row_b["fund_roe"] == 8.0, f"Expected redistributed ROE=8, got {row_b['fund_roe']}"
    assert row_b["fund_growth"] == 7.0, f"Expected redistributed growth=7, got {row_b['fund_growth']}"

    # score_fundamental = fund_roe + fund_growth (fund_pe excluded as NaN)
    expected_score = 8.0 + 7.0
    assert row_b["score_fundamental"] == pytest.approx(expected_score), (
        f"Expected score_fundamental={expected_score}, got {row_b['score_fundamental']}"
    )


def test_pe_uses_industry_median(conn_with_data):
    """PE=15 < industry median 20 → should get >= 5 points (PE <= median tier)."""
    from src.strategies.potential_screener import score_fundamentals

    candidates = pd.Series(["000001.SZ", "000002.SZ"])
    result = score_fundamentals(conn_with_data, candidates)

    row_a = result[result["ts_code"] == "000001.SZ"].iloc[0]

    # Stock A: PE=15, 银行 industry p25=12, median=20, p75=30
    # PE=15 > p25(12) but <= median(20) → 5pts
    assert row_a["fund_pe"] >= 5.0, (
        f"PE=15 < industry median 20, expected fund_pe >= 5, got {row_a['fund_pe']}"
    )

    # ROE=20 (>15) → 8pts, growth=35 (>30) → 5pts, PE → 5pts
    # Total = 8 + 5 + 5 = 18
    assert row_a["fund_roe"] == 8.0
    assert row_a["fund_growth"] == 5.0
    assert row_a["score_fundamental"] == pytest.approx(18.0)


def test_data_completeness_field(conn_with_data):
    """Output should have data_completeness column: 'full' or 'pe_missing'."""
    from src.strategies.potential_screener import score_fundamentals

    candidates = pd.Series(["000001.SZ", "000002.SZ"])
    result = score_fundamentals(conn_with_data, candidates)

    # Column must exist
    assert "data_completeness" in result.columns, (
        "data_completeness column missing from output"
    )

    row_a = result[result["ts_code"] == "000001.SZ"].iloc[0]
    row_b = result[result["ts_code"] == "000002.SZ"].iloc[0]

    # Stock A has PE data → "full"
    assert row_a["data_completeness"] == "full", (
        f"Expected 'full' for stock with PE, got '{row_a['data_completeness']}'"
    )

    # Stock B has NULL PE → "pe_missing"
    assert row_b["data_completeness"] == "pe_missing", (
        f"Expected 'pe_missing' for stock without PE, got '{row_b['data_completeness']}'"
    )


def test_fallback_without_industry_valuation():
    """When industry_valuation table doesn't exist, fallback to absolute PE ranges."""
    from src.strategies.potential_screener import score_fundamentals

    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row

    # Create required tables but NOT industry_valuation
    conn.execute("""
        CREATE TABLE ts_stock_basic (
            ts_code TEXT PRIMARY KEY, name TEXT, industry TEXT
        )
    """)
    conn.execute("INSERT INTO ts_stock_basic VALUES ('000001.SZ', 'StockA', '银行')")

    conn.execute("""
        CREATE TABLE ts_fina_indicator (
            ts_code TEXT NOT NULL, end_date TEXT NOT NULL, roe REAL, netprofit_yoy REAL
        )
    """)
    conn.execute(
        "INSERT INTO ts_fina_indicator VALUES ('000001.SZ', '20251231', 20.0, 35.0)"
    )

    conn.execute("""
        CREATE TABLE ts_daily_basic (
            ts_code TEXT NOT NULL, trade_date TEXT NOT NULL, pe_ttm REAL,
            UNIQUE(ts_code, trade_date)
        )
    """)
    # PE=15 → in absolute range 10-30 → 7pts
    conn.execute(
        "INSERT INTO ts_daily_basic VALUES ('000001.SZ', '20260305', 15.0)"
    )
    conn.commit()

    candidates = pd.Series(["000001.SZ"])
    result = score_fundamentals(conn, candidates)

    row = result[result["ts_code"] == "000001.SZ"].iloc[0]
    # Fallback absolute range: 10-30 → 7pts
    assert row["fund_pe"] == 7.0, f"Expected fallback PE score=7, got {row['fund_pe']}"
    assert row["data_completeness"] == "full"

    conn.close()
