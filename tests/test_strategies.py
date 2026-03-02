"""Tests for built-in backtest strategies."""

import numpy as np
import pandas as pd

from src.analysis.backtest_engine import BacktestEngine
from src.analysis.strategies import ma_crossover_signal, rps_momentum_signal


def _make_price_with_rps(n_days: int = 120) -> pd.DataFrame:
    """Generate price data with RPS columns."""
    np.random.seed(42)
    returns = np.random.normal(0.001, 0.02, n_days)
    close = 10.0 * np.cumprod(1 + returns)
    dates = pd.bdate_range("2025-01-01", periods=n_days)
    return pd.DataFrame(
        {
            "date": dates,
            "open": close * 0.999,
            "high": close * 1.01,
            "low": close * 0.99,
            "close": close,
            "volume": np.random.randint(100000, 1000000, n_days),
            "rps_10": np.random.uniform(50, 100, n_days),
            "rps_20": np.random.uniform(40, 95, n_days),
            "rps_50": np.random.uniform(30, 90, n_days),
        }
    )


class TestRpsMomentumSignal:
    def test_generates_binary_signals(self):
        df = _make_price_with_rps()
        signals = rps_momentum_signal(df, threshold=90)
        assert signals.isin([0, 1]).all()

    def test_high_threshold_fewer_signals(self):
        df = _make_price_with_rps()
        signals_high = rps_momentum_signal(df, threshold=95)
        signals_low = rps_momentum_signal(df, threshold=70)
        assert signals_high.sum() <= signals_low.sum()

    def test_runs_in_backtest(self):
        df = _make_price_with_rps(252)
        engine = BacktestEngine(initial_capital=100000)
        result = engine.run(df, lambda d: rps_momentum_signal(d, threshold=80))
        assert result.equity_curve is not None
        assert isinstance(result.sharpe, float)


class TestMaCrossoverSignal:
    def test_generates_binary_signals(self):
        df = _make_price_with_rps(100)
        signals = ma_crossover_signal(df, fast=5, slow=20)
        assert signals.isin([0, 1]).all()

    def test_runs_in_backtest(self):
        df = _make_price_with_rps(252)
        engine = BacktestEngine(initial_capital=100000)
        result = engine.run(df, lambda d: ma_crossover_signal(d, fast=5, slow=20))
        assert isinstance(result.total_return, float)
