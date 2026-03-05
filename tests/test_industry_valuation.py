"""Tests for industry valuation median computation script."""

import sqlite3
import pytest

from scripts.compute_industry_valuation import init_table, compute_for_date


@pytest.fixture
def mem_conn():
    """Create an in-memory SQLite database with required dependency tables and test data."""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row

    # Create dependency tables
    conn.execute("""
        CREATE TABLE ts_stock_basic (
            ts_code TEXT PRIMARY KEY,
            name TEXT,
            industry TEXT
        )
    """)
    conn.execute("""
        CREATE TABLE ts_daily_basic (
            ts_code TEXT NOT NULL,
            trade_date TEXT NOT NULL,
            pe_ttm REAL,
            pb REAL,
            UNIQUE(ts_code, trade_date)
        )
    """)

    # Insert test stocks -- 3 stocks in "银行" industry
    conn.execute("INSERT INTO ts_stock_basic VALUES ('A.SZ', 'StockA', '银行')")
    conn.execute("INSERT INTO ts_stock_basic VALUES ('B.SZ', 'StockB', '银行')")
    conn.execute("INSERT INTO ts_stock_basic VALUES ('C.SZ', 'StockC', '银行')")

    # Insert daily basic data for trade_date = '20260305'
    # A: PE=5, PB=1.0
    # B: PE=10, PB=2.0
    # C: PE=600, PB=3.0  (extreme PE, should be excluded from PE stats)
    conn.execute("INSERT INTO ts_daily_basic VALUES ('A.SZ', '20260305', 5.0, 1.0)")
    conn.execute("INSERT INTO ts_daily_basic VALUES ('B.SZ', '20260305', 10.0, 2.0)")
    conn.execute("INSERT INTO ts_daily_basic VALUES ('C.SZ', '20260305', 600.0, 3.0)")

    conn.commit()
    yield conn
    conn.close()


def test_init_table(mem_conn):
    """Verify that init_table creates the industry_valuation table."""
    init_table(conn=mem_conn)

    row = mem_conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='industry_valuation'"
    ).fetchone()
    assert row is not None
    assert row[0] == "industry_valuation"


def test_compute_filters_extreme_pe(mem_conn):
    """PE=600 should be excluded (>500). Median of (5,10) = 7.5. valid_pe_count=2, stock_count=3."""
    init_table(conn=mem_conn)
    compute_for_date("20260305", conn=mem_conn)

    row = mem_conn.execute(
        "SELECT * FROM industry_valuation WHERE trade_date='20260305' AND industry='银行'"
    ).fetchone()
    assert row is not None

    assert row["stock_count"] == 3
    assert row["valid_pe_count"] == 2
    assert row["pe_median"] == pytest.approx(7.5)
    # p25 and p75 for [5, 10]: p25=5+(10-5)*0.25=6.25, p75=5+(10-5)*0.75=8.75
    # But with only 2 data points, exact values depend on interpolation method.
    # We simply check they are reasonable: p25 <= median <= p75
    assert row["pe_p25"] <= row["pe_median"]
    assert row["pe_p75"] >= row["pe_median"]
    # PB median of (1.0, 2.0, 3.0) = 2.0 (all PB > 0)
    assert row["pb_median"] == pytest.approx(2.0)


def test_compute_negative_pe_excluded(mem_conn):
    """Add stock with PE=-5, verify it's excluded from PE stats, valid_pe_count still 2."""
    # Add a fourth stock with negative PE
    mem_conn.execute("INSERT INTO ts_stock_basic VALUES ('D.SZ', 'StockD', '银行')")
    mem_conn.execute("INSERT INTO ts_daily_basic VALUES ('D.SZ', '20260305', -5.0, 0.5)")
    mem_conn.commit()

    init_table(conn=mem_conn)
    compute_for_date("20260305", conn=mem_conn)

    row = mem_conn.execute(
        "SELECT * FROM industry_valuation WHERE trade_date='20260305' AND industry='银行'"
    ).fetchone()
    assert row is not None

    # stock_count should now be 4 (total stocks in the industry)
    assert row["stock_count"] == 4
    # valid_pe_count should still be 2 (PE=-5 excluded, PE=600 excluded)
    assert row["valid_pe_count"] == 2
    # Median of valid PEs [5, 10] = 7.5
    assert row["pe_median"] == pytest.approx(7.5)
    # PB: D has PB=0.5 which is > 0, so PB values are [0.5, 1.0, 2.0, 3.0], median = 1.5
    assert row["pb_median"] == pytest.approx(1.5)
