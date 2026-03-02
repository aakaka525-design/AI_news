"""Tests for BacktestEngine."""

import numpy as np
import pandas as pd
import pytest

from src.analysis.backtest_engine import BacktestEngine, BacktestResult


def _make_price_data(n_days: int = 100, start_price: float = 10.0) -> pd.DataFrame:
    """Generate synthetic daily OHLCV data."""
    np.random.seed(42)
    returns = np.random.normal(0.001, 0.02, n_days)
    close = start_price * np.cumprod(1 + returns)
    dates = pd.bdate_range("2025-01-01", periods=n_days)
    return pd.DataFrame({
        "date": dates,
        "open": close * (1 + np.random.uniform(-0.005, 0.005, n_days)),
        "high": close * (1 + np.abs(np.random.normal(0, 0.01, n_days))),
        "low": close * (1 - np.abs(np.random.normal(0, 0.01, n_days))),
        "close": close,
        "volume": np.random.randint(100000, 1000000, n_days),
    })


def _always_hold_signal(df: pd.DataFrame) -> pd.Series:
    """Signal: always hold (1 every day)."""
    return pd.Series(1, index=df.index)


def _never_hold_signal(df: pd.DataFrame) -> pd.Series:
    """Signal: never hold (0 every day)."""
    return pd.Series(0, index=df.index)


def _simple_ma_signal(df: pd.DataFrame) -> pd.Series:
    """Signal: hold when close > MA20."""
    ma20 = df["close"].rolling(20).mean()
    return (df["close"] > ma20).astype(int)


class TestBacktestEngine:
    def test_always_hold_returns_market_return(self):
        prices = _make_price_data(100)
        engine = BacktestEngine(initial_capital=100000)
        result = engine.run(prices, _always_hold_signal)
        assert isinstance(result, BacktestResult)
        assert result.total_return != 0.0
        assert len(result.equity_curve) == 100

    def test_never_hold_returns_zero(self):
        prices = _make_price_data(100)
        engine = BacktestEngine(initial_capital=100000)
        result = engine.run(prices, _never_hold_signal)
        assert result.total_return == pytest.approx(0.0, abs=0.001)

    def test_result_has_metrics(self):
        prices = _make_price_data(252)
        engine = BacktestEngine(initial_capital=100000)
        result = engine.run(prices, _always_hold_signal)
        assert hasattr(result, "sharpe")
        assert hasattr(result, "max_drawdown")
        assert hasattr(result, "cagr")
        assert hasattr(result, "total_return")
        assert hasattr(result, "n_trades")

    def test_commission_reduces_return(self):
        prices = _make_price_data(100)
        result_no_comm = BacktestEngine(initial_capital=100000, commission=0.0).run(
            prices, _simple_ma_signal
        )
        result_with_comm = BacktestEngine(initial_capital=100000, commission=0.001).run(
            prices, _simple_ma_signal
        )
        assert result_with_comm.total_return < result_no_comm.total_return

    def test_equity_curve_starts_at_initial(self):
        prices = _make_price_data(50)
        engine = BacktestEngine(initial_capital=50000)
        result = engine.run(prices, _always_hold_signal)
        assert result.equity_curve.iloc[0] == pytest.approx(50000, rel=0.01)

    def test_trade_log_records_entries_and_exits(self):
        prices = _make_price_data(100)
        engine = BacktestEngine(initial_capital=100000)
        result = engine.run(prices, _simple_ma_signal)
        assert result.n_trades >= 0
        assert len(result.trade_returns) == result.n_trades
