"""Tests for staleness-weighted scoring in score_fundamentals."""

import sqlite3

import pandas as pd
import pytest


@pytest.fixture
def conn_staleness():
    """Create in-memory DB with two stocks: one stale, one fresh.

    Stock A (000001.SZ): fina end_date=20250331 (stale, ~4 quarters behind)
    Stock B (000002.SZ): fina end_date=20251231 (fresh, ~1 quarter behind)
    Both: same ROE=15, netprofit_yoy=20, pe_ttm=15, industry='银行'
    ts_daily_basic latest trade_date=20260305
    """
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row

    # ts_stock_basic
    conn.execute("""
        CREATE TABLE ts_stock_basic (
            ts_code TEXT PRIMARY KEY,
            name TEXT,
            industry TEXT
        )
    """)
    conn.execute("INSERT INTO ts_stock_basic VALUES ('000001.SZ', 'StaleStock', '银行')")
    conn.execute("INSERT INTO ts_stock_basic VALUES ('000002.SZ', 'FreshStock', '银行')")

    # ts_fina_indicator
    conn.execute("""
        CREATE TABLE ts_fina_indicator (
            ts_code TEXT NOT NULL,
            end_date TEXT NOT NULL,
            roe REAL,
            netprofit_yoy REAL
        )
    """)
    # Stock A: stale financials (2025-03-31, about 4 quarters behind 2026-03-05)
    conn.execute(
        "INSERT INTO ts_fina_indicator VALUES ('000001.SZ', '20250331', 15.0, 20.0)"
    )
    # Stock B: fresh financials (2025-12-31, about 1 quarter behind 2026-03-05)
    conn.execute(
        "INSERT INTO ts_fina_indicator VALUES ('000002.SZ', '20251231', 15.0, 20.0)"
    )

    # ts_daily_basic (provides PE and ref_date)
    conn.execute("""
        CREATE TABLE ts_daily_basic (
            ts_code TEXT NOT NULL,
            trade_date TEXT NOT NULL,
            pe_ttm REAL,
            UNIQUE(ts_code, trade_date)
        )
    """)
    conn.execute("INSERT INTO ts_daily_basic VALUES ('000001.SZ', '20260305', 15.0)")
    conn.execute("INSERT INTO ts_daily_basic VALUES ('000002.SZ', '20260305', 15.0)")

    # ts_daily (needed for ts_daily existence; minimal data)
    conn.execute("""
        CREATE TABLE ts_daily (
            ts_code TEXT NOT NULL,
            trade_date TEXT NOT NULL,
            open REAL, high REAL, low REAL, close REAL,
            pre_close REAL, change REAL, pct_chg REAL,
            vol REAL, amount REAL,
            UNIQUE(ts_code, trade_date)
        )
    """)
    conn.execute(
        "INSERT INTO ts_daily VALUES ('000001.SZ', '20260305', 10, 11, 9, 10, 10, 0, 0, 1000, 10000)"
    )
    conn.execute(
        "INSERT INTO ts_daily VALUES ('000002.SZ', '20260305', 10, 11, 9, 10, 10, 0, 0, 1000, 10000)"
    )

    # industry_valuation so PE scoring uses industry-relative path
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
    conn.execute("""
        INSERT INTO industry_valuation (trade_date, industry, pe_median, pe_p25, pe_p75, stock_count, valid_pe_count)
        VALUES ('20260305', '银行', 20.0, 12.0, 30.0, 10, 8)
    """)

    conn.commit()
    yield conn
    conn.close()


def test_stale_stock_gets_lower_fundamental_weight(conn_staleness):
    """Stock A: end_date=20250331 (stale), Stock B: end_date=20251231 (fresh).
    Same ROE/PE/growth. A should score lower due to staleness discount."""
    from src.strategies.potential_screener import score_fundamentals

    candidates = pd.Series(["000001.SZ", "000002.SZ"])
    result = score_fundamentals(conn_staleness, candidates)

    row_a = result[result["ts_code"] == "000001.SZ"].iloc[0]
    row_b = result[result["ts_code"] == "000002.SZ"].iloc[0]

    # Stock A is stale (lag >= 3 quarters) -> score_fundamental should be halved
    # Stock B is fresh (lag < 3 quarters) -> score_fundamental unchanged
    assert row_a["score_fundamental"] < row_b["score_fundamental"], (
        f"Stale stock A ({row_a['score_fundamental']}) should score lower "
        f"than fresh stock B ({row_b['score_fundamental']})"
    )

    # Specifically: Stock A's score should be exactly half of Stock B's score
    # (same base scores, but A gets 0.5x discount)
    expected_a = round(row_b["score_fundamental"] * 0.5, 2)
    assert row_a["score_fundamental"] == pytest.approx(expected_a), (
        f"Expected stale score={expected_a}, got {row_a['score_fundamental']}"
    )


def test_staleness_flag_in_output(conn_staleness):
    """Output should have financial_lag_quarters column."""
    from src.strategies.potential_screener import score_fundamentals

    candidates = pd.Series(["000001.SZ", "000002.SZ"])
    result = score_fundamentals(conn_staleness, candidates)

    assert "financial_lag_quarters" in result.columns, (
        "financial_lag_quarters column missing from output"
    )

    row_a = result[result["ts_code"] == "000001.SZ"].iloc[0]
    row_b = result[result["ts_code"] == "000002.SZ"].iloc[0]

    # Stock A: end_date=20250331, ref_date=20260305 -> ~12 months -> ~4 quarters
    assert row_a["financial_lag_quarters"] >= 3, (
        f"Expected stale stock lag >= 3, got {row_a['financial_lag_quarters']}"
    )

    # Stock B: end_date=20251231, ref_date=20260305 -> ~2 months -> ~0-1 quarters
    assert row_b["financial_lag_quarters"] < 3, (
        f"Expected fresh stock lag < 3, got {row_b['financial_lag_quarters']}"
    )
