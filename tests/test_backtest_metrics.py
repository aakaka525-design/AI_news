"""Tests for backtesting performance metrics."""

import numpy as np
import pandas as pd
import pytest

from src.analysis.backtest_metrics import (
    cagr,
    max_drawdown,
    profit_factor,
    sharpe_ratio,
    win_rate,
)


class TestSharpeRatio:
    def test_positive_sharpe(self):
        np.random.seed(42)
        daily_returns = pd.Series(np.random.normal(0.0004, 0.003, 252))
        sr = sharpe_ratio(daily_returns, risk_free_rate=0.0)
        assert isinstance(sr, float)
        assert sr > 0

    def test_zero_volatility(self):
        daily_returns = pd.Series([0.001] * 100)
        sr = sharpe_ratio(daily_returns)
        assert sr > 10

    def test_negative_returns(self):
        np.random.seed(42)
        daily_returns = pd.Series(np.random.normal(-0.002, 0.01, 252))
        sr = sharpe_ratio(daily_returns)
        assert sr < 0

    def test_empty_series(self):
        assert sharpe_ratio(pd.Series(dtype=float)) == 0.0


class TestMaxDrawdown:
    def test_known_drawdown(self):
        equity = pd.Series([100, 110, 120, 90, 100, 110])
        mdd = max_drawdown(equity)
        assert mdd == pytest.approx(0.25, abs=0.001)

    def test_no_drawdown(self):
        equity = pd.Series([100, 110, 120, 130])
        assert max_drawdown(equity) == 0.0

    def test_empty_series(self):
        assert max_drawdown(pd.Series(dtype=float)) == 0.0


class TestCAGR:
    def test_known_cagr(self):
        equity = pd.Series([100] + [0] * 250 + [200])
        c = cagr(equity, trading_days=252)
        assert c == pytest.approx(1.0, abs=0.05)

    def test_flat_returns(self):
        equity = pd.Series([100] * 252)
        assert cagr(equity, trading_days=252) == pytest.approx(0.0, abs=0.01)

    def test_empty_series(self):
        assert cagr(pd.Series(dtype=float)) == 0.0


class TestWinRate:
    def test_known_win_rate(self):
        trades = pd.Series([0.05, -0.02, 0.03, -0.01, 0.04])
        assert win_rate(trades) == pytest.approx(0.6, abs=0.01)

    def test_all_winners(self):
        trades = pd.Series([0.05, 0.03, 0.04])
        assert win_rate(trades) == pytest.approx(1.0)

    def test_empty_trades(self):
        assert win_rate(pd.Series(dtype=float)) == 0.0


class TestProfitFactor:
    def test_known_profit_factor(self):
        trades = pd.Series([0.10, -0.05, 0.08, -0.03])
        pf = profit_factor(trades)
        assert pf == pytest.approx(2.25, abs=0.01)

    def test_no_losses(self):
        trades = pd.Series([0.05, 0.03])
        assert profit_factor(trades) == float("inf")

    def test_empty_trades(self):
        assert profit_factor(pd.Series(dtype=float)) == 0.0
