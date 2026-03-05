"""Tests for screener edge cases: NULL list_status and non-margin stock scoring."""

import math
import sqlite3

import numpy as np
import pandas as pd
import pytest


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def conn_null_list_status():
    """In-memory DB with stocks having various list_status values.

    Stock A (000001.SZ): list_status='L', has recent trades  -> should be included
    Stock B (000002.SZ): list_status=NULL, has recent trades  -> should be included (#14)
    Stock C (000003.SZ): list_status='D', has recent trades   -> should be excluded (delisted)
    Stock D (000004.SZ): list_status=NULL, NO recent trades   -> should be excluded (no liquidity)
    """
    conn = sqlite3.connect(":memory:")

    conn.execute("""
        CREATE TABLE ts_stock_basic (
            ts_code TEXT PRIMARY KEY,
            name TEXT,
            industry TEXT,
            list_status TEXT,
            list_date TEXT
        )
    """)
    conn.execute("INSERT INTO ts_stock_basic VALUES ('000001.SZ', '平安银行', '银行', 'L', '20200101')")
    conn.execute("INSERT INTO ts_stock_basic VALUES ('000002.SZ', '万科A', '科技', NULL, '20200101')")
    conn.execute("INSERT INTO ts_stock_basic VALUES ('000003.SZ', '恒瑞医药', '医药', 'D', '20200101')")
    conn.execute("INSERT INTO ts_stock_basic VALUES ('000004.SZ', '金地集团', '地产', NULL, '20200101')")

    # ts_daily: provide 20+ trading days of data for liquidity filter
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

    # Generate 25 distinct trading days
    trade_dates = [f"2026{str(m).zfill(2)}{str(d).zfill(2)}"
                   for m, d in [(1, dd) for dd in range(5, 30)] + [(2, 3)]]
    trade_dates = sorted(trade_dates)[:25]

    # Stocks A, B, C get high-volume trades (amount=60000 > 50000 threshold)
    for ts_code in ["000001.SZ", "000002.SZ", "000003.SZ"]:
        for td in trade_dates:
            conn.execute(
                "INSERT INTO ts_daily VALUES (?, ?, 10, 11, 9, 10, 10, 0, 0, 1000, 60000)",
                (ts_code, td),
            )

    # Stock D gets low-volume trades (amount=100 < 50000 threshold) -> excluded by liquidity
    for td in trade_dates:
        conn.execute(
            "INSERT INTO ts_daily VALUES (?, ?, 10, 11, 9, 10, 10, 0, 0, 10, 100)",
            ("000004.SZ", td),
        )

    conn.commit()
    yield conn
    conn.close()


@pytest.fixture
def conn_non_margin():
    """In-memory DB for testing capital_margin NaN for non-margin stocks.

    Stock A (000001.SZ): has moneyflow data AND margin_trading data
    Stock B (000002.SZ): has moneyflow data but NO margin_trading data -> capital_margin should be NaN
    """
    conn = sqlite3.connect(":memory:")

    # ts_moneyflow: both stocks have data
    conn.execute("""
        CREATE TABLE ts_moneyflow (
            ts_code TEXT NOT NULL,
            trade_date TEXT NOT NULL,
            buy_lg_amount REAL, sell_lg_amount REAL,
            buy_elg_amount REAL, sell_elg_amount REAL,
            buy_md_amount REAL, sell_md_amount REAL,
            buy_sm_amount REAL, sell_sm_amount REAL,
            UNIQUE(ts_code, trade_date)
        )
    """)
    # 5 trading days of moneyflow
    for td in ["20260301", "20260302", "20260303", "20260304", "20260305"]:
        for ts_code in ["000001.SZ", "000002.SZ"]:
            conn.execute(
                "INSERT INTO ts_moneyflow VALUES (?, ?, 100, 50, 200, 80, 50, 30, 20, 10)",
                (ts_code, td),
            )

    # margin_trading: ONLY Stock A has data
    conn.execute("""
        CREATE TABLE margin_trading (
            stock_code TEXT NOT NULL,
            date TEXT NOT NULL,
            margin_balance REAL,
            UNIQUE(stock_code, date)
        )
    """)
    # Generate 20 distinct dates for margin_trading
    margin_dates = [f"2026-02-{str(d).zfill(2)}" for d in range(1, 21)]
    for md in margin_dates:
        conn.execute(
            "INSERT INTO margin_trading VALUES ('000001', ?, 100000.0)",
            (md,),
        )
    # Latest date with slightly higher balance to create growth
    conn.execute(
        "INSERT INTO margin_trading VALUES ('000001', '2026-02-28', 120000.0)"
    )

    # ts_hsgt_top10: empty (not relevant for this test)
    conn.execute("""
        CREATE TABLE ts_hsgt_top10 (
            ts_code TEXT NOT NULL,
            trade_date TEXT NOT NULL,
            net_amount REAL,
            side TEXT
        )
    """)

    conn.commit()
    yield conn
    conn.close()


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_null_list_status_with_recent_trading(conn_null_list_status):
    """#14: Stock with NULL list_status but recent trades should be included in candidate pool."""
    from src.strategies.potential_screener import get_candidate_pool

    latest_date = "20260203"
    pool = get_candidate_pool(conn_null_list_status, latest_date)

    ts_codes_in_pool = set(pool["ts_code"].tolist())

    # Stock A (list_status='L') should be included
    assert "000001.SZ" in ts_codes_in_pool, (
        "Stock A with list_status='L' should be in the candidate pool"
    )

    # Stock B (list_status=NULL, high volume) should be included
    assert "000002.SZ" in ts_codes_in_pool, (
        "Stock B with list_status=NULL but recent high-volume trades should be in the candidate pool"
    )

    # Stock C (list_status='D', delisted) should be excluded
    assert "000003.SZ" not in ts_codes_in_pool, (
        "Stock C with list_status='D' (delisted) should NOT be in the candidate pool"
    )

    # Stock D (list_status=NULL, low volume) should be excluded by liquidity filter
    assert "000004.SZ" not in ts_codes_in_pool, (
        "Stock D with NULL list_status and low volume should NOT be in the candidate pool"
    )


def test_score_capital_margin_na_for_non_margin_stock(conn_non_margin):
    """#10: Stock not in margin_trading should get NaN capital_margin (not 0)."""
    from src.strategies.potential_screener import score_capital_flow

    candidates = pd.Series(["000001.SZ", "000002.SZ"])
    result = score_capital_flow(conn_non_margin, candidates)

    row_a = result[result["ts_code"] == "000001.SZ"].iloc[0]
    row_b = result[result["ts_code"] == "000002.SZ"].iloc[0]

    # Stock A has margin_trading data -> capital_margin should be a number (not NaN)
    assert not math.isnan(row_a["capital_margin"]), (
        f"Stock A (in margin_trading) should have numeric capital_margin, got NaN"
    )

    # Stock B has NO margin_trading data -> capital_margin should be NaN
    assert math.isnan(row_b["capital_margin"]), (
        f"Stock B (not in margin_trading) should have NaN capital_margin, got {row_b['capital_margin']}"
    )

    # Total score_capital should still work (NaN capital_margin -> treated as 0 in sum)
    assert not math.isnan(row_b["score_capital"]), (
        f"score_capital should not be NaN even when capital_margin is NaN, got {row_b['score_capital']}"
    )
