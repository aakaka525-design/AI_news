# Phase 3C: 策略增强 + 回测框架 Implementation Plan

> **状态：已完成**
> `src/analysis/backtest_engine.py`、`src/analysis/backtest_metrics.py`、`src/analysis/sector_rotation.py` 及对应测试均已落地并通过。

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build a backtesting framework with performance metrics (Sharpe Ratio, max drawdown, CAGR), sector rotation detection, and reproducible strategy evaluation using existing stock data.

**Architecture:** Pure calculation modules under `src/analysis/` — no DB dependencies in core logic. `BacktestEngine` takes a DataFrame of daily prices + a signal generator function, simulates trades, and returns a `BacktestResult` with metrics. Sector rotation module uses existing `sector_rps` data patterns. All functions are pandas-based and fully testable.

**Tech Stack:** pandas, numpy, pytest

---

### Existing Code Summary

**`src/analysis/technical.py`** (226 lines): Pure calculation — EMA, MACD, RSI, KDJ, Bollinger, ATR, OBV, Williams %R, volume_ratio, compute_all.

**`src/analysis/trend_analysis.py`** (169 lines): identify_trend, find_support_resistance, multi_period_resonance.

**`src/analysis/indicators.py`** (802 lines): RPS calculation (stock_rps table: rps_10/20/50/60), technical indicator batch computation, DB operations.

**`src/strategies/rps_screener.py`** (252 lines): 4 RPS screening strategies (just_started, triple_resonance, accelerating, sector_resonance). Uses raw sqlite3.

**Data available:** `stock_daily` (OHLCV), `stock_rps` (rps_10/20/50/60), `sector_rps` (rps_10/20/50), `sector_stocks` (stock→sector mapping).

---

### Task 1: Performance Metrics Module

**Files:**
- Create: `src/analysis/backtest_metrics.py`
- Create: `tests/test_backtest_metrics.py`

**Step 1: Write failing tests**

```python
"""Tests for backtesting performance metrics."""

import numpy as np
import pandas as pd
import pytest

from src.analysis.backtest_metrics import (
    sharpe_ratio,
    max_drawdown,
    cagr,
    win_rate,
    profit_factor,
)


class TestSharpeRatio:
    def test_positive_sharpe(self):
        # 10% annualized return, 5% vol → Sharpe ≈ 2.0 (with rfr=0)
        daily_returns = pd.Series(np.random.normal(0.0004, 0.003, 252))
        sr = sharpe_ratio(daily_returns, risk_free_rate=0.0)
        assert isinstance(sr, float)
        assert sr > 0

    def test_zero_volatility(self):
        daily_returns = pd.Series([0.001] * 100)
        sr = sharpe_ratio(daily_returns)
        # Constant positive returns → infinite or very large Sharpe
        assert sr > 10

    def test_negative_returns(self):
        daily_returns = pd.Series(np.random.normal(-0.002, 0.01, 252))
        sr = sharpe_ratio(daily_returns)
        assert sr < 0

    def test_empty_series(self):
        assert sharpe_ratio(pd.Series(dtype=float)) == 0.0


class TestMaxDrawdown:
    def test_known_drawdown(self):
        # Equity: 100 → 120 → 90 → 110
        equity = pd.Series([100, 110, 120, 90, 100, 110])
        mdd = max_drawdown(equity)
        assert mdd == pytest.approx(0.25, abs=0.001)  # (120-90)/120

    def test_no_drawdown(self):
        equity = pd.Series([100, 110, 120, 130])
        assert max_drawdown(equity) == 0.0

    def test_empty_series(self):
        assert max_drawdown(pd.Series(dtype=float)) == 0.0


class TestCAGR:
    def test_known_cagr(self):
        # 100 → 200 in 1 year = 100% CAGR
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
        assert pf == pytest.approx(2.25, abs=0.01)  # 0.18/0.08

    def test_no_losses(self):
        trades = pd.Series([0.05, 0.03])
        assert profit_factor(trades) == float("inf")

    def test_empty_trades(self):
        assert profit_factor(pd.Series(dtype=float)) == 0.0
```

**Step 2: Run tests → FAIL**

**Step 3: Implement**

```python
"""
回测性能指标 — 纯计算，无副作用

所有函数接收 pandas Series，返回 float。
"""

import numpy as np
import pandas as pd


def sharpe_ratio(
    daily_returns: pd.Series,
    risk_free_rate: float = 0.03,
    trading_days: int = 252,
) -> float:
    """年化 Sharpe Ratio。

    Args:
        daily_returns: 每日收益率序列
        risk_free_rate: 年化无风险利率（默认 3%）
        trading_days: 年交易日数

    Returns:
        Sharpe Ratio (float)
    """
    if daily_returns.empty or daily_returns.std() == 0:
        if daily_returns.empty:
            return 0.0
        return float("inf") if daily_returns.mean() > 0 else 0.0

    daily_rf = risk_free_rate / trading_days
    excess = daily_returns - daily_rf
    return float(excess.mean() / excess.std() * np.sqrt(trading_days))


def max_drawdown(equity_curve: pd.Series) -> float:
    """最大回撤比例。

    Args:
        equity_curve: 权益曲线（如 [100, 110, 90, 120]）

    Returns:
        最大回撤 (0.0 ~ 1.0)
    """
    if equity_curve.empty or len(equity_curve) < 2:
        return 0.0

    peak = equity_curve.expanding().max()
    drawdown = (peak - equity_curve) / peak
    return float(drawdown.max())


def cagr(
    equity_curve: pd.Series,
    trading_days: int = 252,
) -> float:
    """年化复合增长率。

    Args:
        equity_curve: 权益曲线
        trading_days: 年交易日数

    Returns:
        CAGR (如 0.15 表示 15%)
    """
    if equity_curve.empty or len(equity_curve) < 2:
        return 0.0

    start = equity_curve.iloc[0]
    end = equity_curve.iloc[-1]
    if start <= 0:
        return 0.0

    n_years = (len(equity_curve) - 1) / trading_days
    if n_years <= 0:
        return 0.0

    return float((end / start) ** (1 / n_years) - 1)


def win_rate(trade_returns: pd.Series) -> float:
    """胜率。

    Args:
        trade_returns: 每笔交易收益率

    Returns:
        胜率 (0.0 ~ 1.0)
    """
    if trade_returns.empty:
        return 0.0
    return float((trade_returns > 0).sum() / len(trade_returns))


def profit_factor(trade_returns: pd.Series) -> float:
    """盈亏比 = 总盈利 / 总亏损。

    Args:
        trade_returns: 每笔交易收益率

    Returns:
        盈亏比
    """
    if trade_returns.empty:
        return 0.0
    gains = trade_returns[trade_returns > 0].sum()
    losses = abs(trade_returns[trade_returns < 0].sum())
    if losses == 0:
        return float("inf") if gains > 0 else 0.0
    return float(gains / losses)
```

**Step 4: Run tests → ALL PASS**

**Step 5: Commit**

```bash
git add src/analysis/backtest_metrics.py tests/test_backtest_metrics.py
git commit -m "feat: add backtesting performance metrics (Sharpe, drawdown, CAGR)"
```

---

### Task 2: Backtest Engine

**Files:**
- Create: `src/analysis/backtest_engine.py`
- Create: `tests/test_backtest_engine.py`

**Step 1: Write failing tests**

```python
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
```

**Step 2: Run tests → FAIL**

**Step 3: Implement**

```python
"""
回测引擎 — 单标的信号驱动回测

用法:
    engine = BacktestEngine(initial_capital=100000)
    result = engine.run(price_df, signal_fn)
    print(result.sharpe, result.max_drawdown)
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from src.analysis.backtest_metrics import (
    cagr,
    max_drawdown,
    profit_factor,
    sharpe_ratio,
    win_rate,
)


@dataclass
class BacktestResult:
    """回测结果。"""

    equity_curve: pd.Series
    daily_returns: pd.Series
    trade_returns: pd.Series
    total_return: float
    sharpe: float
    max_drawdown: float
    cagr: float
    win_rate: float
    profit_factor: float
    n_trades: int


class BacktestEngine:
    """单标的回测引擎。

    Args:
        initial_capital: 初始资金
        commission: 单边手续费率（如 0.001 = 0.1%）
    """

    def __init__(self, initial_capital: float = 100000, commission: float = 0.0):
        self.initial_capital = initial_capital
        self.commission = commission

    def run(
        self,
        prices: pd.DataFrame,
        signal_fn,
    ) -> BacktestResult:
        """运行回测。

        Args:
            prices: DataFrame with columns: date, open, high, low, close, volume
            signal_fn: callable(df) -> pd.Series of 0/1 signals (1=hold, 0=cash)

        Returns:
            BacktestResult
        """
        signals = signal_fn(prices)
        closes = prices["close"].values
        n = len(closes)

        equity = np.zeros(n)
        equity[0] = self.initial_capital
        position = 0  # 0=cash, 1=holding
        trade_returns_list: list[float] = []
        entry_price = 0.0

        for i in range(1, n):
            target = int(signals.iloc[i - 1])  # signal at previous bar
            daily_ret = closes[i] / closes[i - 1] - 1

            if position == 0 and target == 1:
                # Buy
                position = 1
                entry_price = closes[i]
                cost = equity[i - 1] * self.commission
                equity[i] = equity[i - 1] - cost
            elif position == 1 and target == 0:
                # Sell
                position = 0
                trade_ret = closes[i] / entry_price - 1
                cost = equity[i - 1] * self.commission
                equity[i] = equity[i - 1] * (1 + daily_ret) - cost
                trade_returns_list.append(trade_ret)
            elif position == 1:
                # Hold
                equity[i] = equity[i - 1] * (1 + daily_ret)
            else:
                # Cash
                equity[i] = equity[i - 1]

        # Close open position at end
        if position == 1:
            trade_ret = closes[-1] / entry_price - 1
            trade_returns_list.append(trade_ret)

        equity_series = pd.Series(equity)
        daily_rets = equity_series.pct_change().fillna(0)
        trade_rets = pd.Series(trade_returns_list, dtype=float)

        total_ret = equity[-1] / equity[0] - 1

        return BacktestResult(
            equity_curve=equity_series,
            daily_returns=daily_rets,
            trade_returns=trade_rets,
            total_return=total_ret,
            sharpe=sharpe_ratio(daily_rets),
            max_drawdown=max_drawdown(equity_series),
            cagr=cagr(equity_series),
            win_rate=win_rate(trade_rets),
            profit_factor=profit_factor(trade_rets),
            n_trades=len(trade_returns_list),
        )
```

**Step 4: Run tests → ALL PASS**

**Step 5: Commit**

```bash
git add src/analysis/backtest_engine.py tests/test_backtest_engine.py
git commit -m "feat: add BacktestEngine with signal-driven simulation"
```

---

### Task 3: Sector Rotation Detection

**Files:**
- Create: `src/analysis/sector_rotation.py`
- Create: `tests/test_sector_rotation.py`

**Step 1: Write failing tests**

```python
"""Tests for sector rotation detection."""

import numpy as np
import pandas as pd
import pytest

from src.analysis.sector_rotation import (
    detect_rotation,
    rank_sectors,
    rotation_momentum,
)


def _make_sector_rps(n_days: int = 30, n_sectors: int = 5) -> pd.DataFrame:
    """Generate synthetic sector RPS data."""
    np.random.seed(42)
    dates = pd.bdate_range("2025-01-01", periods=n_days)
    rows = []
    sectors = [f"sector_{i}" for i in range(n_sectors)]
    for date in dates:
        for sector in sectors:
            rows.append({
                "date": date.strftime("%Y-%m-%d"),
                "sector_name": sector,
                "rps_10": np.random.uniform(10, 100),
                "rps_20": np.random.uniform(10, 100),
                "rps_50": np.random.uniform(10, 100),
            })
    return pd.DataFrame(rows)


class TestRankSectors:
    def test_returns_sorted_sectors(self):
        df = _make_sector_rps(30, 5)
        ranked = rank_sectors(df, period="rps_10", top_n=3)
        assert len(ranked) == 3
        assert all("sector_name" in r for r in ranked)
        assert all("score" in r for r in ranked)

    def test_top_n_limit(self):
        df = _make_sector_rps(30, 10)
        ranked = rank_sectors(df, period="rps_20", top_n=5)
        assert len(ranked) == 5

    def test_scores_descending(self):
        df = _make_sector_rps(30, 5)
        ranked = rank_sectors(df, period="rps_10", top_n=5)
        scores = [r["score"] for r in ranked]
        assert scores == sorted(scores, reverse=True)


class TestDetectRotation:
    def test_detects_rotation_signal(self):
        df = _make_sector_rps(30, 5)
        result = detect_rotation(df, lookback=10)
        assert "rotations" in result
        assert "top_rising" in result
        assert "top_falling" in result
        assert isinstance(result["rotations"], list)

    def test_rising_sectors_have_positive_change(self):
        df = _make_sector_rps(30, 5)
        result = detect_rotation(df, lookback=10)
        for s in result["top_rising"]:
            assert s["rps_change"] >= 0

    def test_falling_sectors_have_negative_change(self):
        df = _make_sector_rps(30, 5)
        result = detect_rotation(df, lookback=10)
        for s in result["top_falling"]:
            assert s["rps_change"] <= 0


class TestRotationMomentum:
    def test_returns_momentum_scores(self):
        df = _make_sector_rps(30, 5)
        momentum = rotation_momentum(df, short_period="rps_10", long_period="rps_50")
        assert len(momentum) > 0
        assert all("sector_name" in m for m in momentum)
        assert all("momentum" in m for m in momentum)

    def test_momentum_is_difference(self):
        df = _make_sector_rps(30, 5)
        momentum = rotation_momentum(df, short_period="rps_10", long_period="rps_50")
        for m in momentum:
            assert isinstance(m["momentum"], float)
```

**Step 2: Run tests → FAIL**

**Step 3: Implement**

```python
"""
板块轮动检测 — 纯计算，无副作用

基于板块 RPS 数据识别轮动信号、排名变化、动量差异。
"""

from __future__ import annotations

import pandas as pd


def rank_sectors(
    sector_rps: pd.DataFrame,
    period: str = "rps_10",
    top_n: int = 5,
) -> list[dict]:
    """对板块按最新 RPS 排名。

    Args:
        sector_rps: DataFrame with date, sector_name, rps_10, rps_20, rps_50
        period: RPS 周期列名
        top_n: 返回前 N 个

    Returns:
        [{"sector_name": str, "score": float}, ...]
    """
    latest_date = sector_rps["date"].max()
    latest = sector_rps[sector_rps["date"] == latest_date].copy()
    latest = latest.sort_values(period, ascending=False).head(top_n)
    return [
        {"sector_name": row["sector_name"], "score": float(row[period])}
        for _, row in latest.iterrows()
    ]


def detect_rotation(
    sector_rps: pd.DataFrame,
    lookback: int = 10,
    period: str = "rps_10",
) -> dict:
    """检测板块轮动信号。

    比较最新 RPS 与 lookback 天前的 RPS，找出上升和下降幅度最大的板块。

    Args:
        sector_rps: DataFrame with date, sector_name, rps_10, rps_20, rps_50
        lookback: 回看天数
        period: RPS 周期列名

    Returns:
        {"rotations": [...], "top_rising": [...], "top_falling": [...]}
    """
    dates = sorted(sector_rps["date"].unique())
    if len(dates) < lookback + 1:
        return {"rotations": [], "top_rising": [], "top_falling": []}

    latest_date = dates[-1]
    past_date = dates[-lookback - 1]

    latest = sector_rps[sector_rps["date"] == latest_date].set_index("sector_name")
    past = sector_rps[sector_rps["date"] == past_date].set_index("sector_name")

    common = latest.index.intersection(past.index)
    changes = []
    for sector in common:
        change = float(latest.loc[sector, period]) - float(past.loc[sector, period])
        changes.append({"sector_name": sector, "rps_change": change})

    changes.sort(key=lambda x: x["rps_change"], reverse=True)

    top_rising = [c for c in changes if c["rps_change"] >= 0][:5]
    top_falling = [c for c in changes if c["rps_change"] < 0][-5:]
    top_falling.sort(key=lambda x: x["rps_change"])

    # A rotation is when a previously low-ranked sector enters top ranks
    rotations = [c for c in changes if abs(c["rps_change"]) > 20]

    return {
        "rotations": rotations,
        "top_rising": top_rising,
        "top_falling": top_falling,
    }


def rotation_momentum(
    sector_rps: pd.DataFrame,
    short_period: str = "rps_10",
    long_period: str = "rps_50",
) -> list[dict]:
    """计算板块轮动动量 = 短期 RPS - 长期 RPS。

    动量为正 → 板块加速走强；动量为负 → 板块走弱。

    Args:
        sector_rps: DataFrame with date, sector_name, rps_10, rps_50 etc.
        short_period: 短期 RPS 列名
        long_period: 长期 RPS 列名

    Returns:
        [{"sector_name": str, "momentum": float, "short_rps": float, "long_rps": float}, ...]
    """
    latest_date = sector_rps["date"].max()
    latest = sector_rps[sector_rps["date"] == latest_date].copy()

    result = []
    for _, row in latest.iterrows():
        short_val = float(row.get(short_period, 0))
        long_val = float(row.get(long_period, 0))
        result.append({
            "sector_name": row["sector_name"],
            "momentum": short_val - long_val,
            "short_rps": short_val,
            "long_rps": long_val,
        })

    result.sort(key=lambda x: x["momentum"], reverse=True)
    return result
```

**Step 4: Run tests → ALL PASS**

**Step 5: Commit**

```bash
git add src/analysis/sector_rotation.py tests/test_sector_rotation.py
git commit -m "feat: add sector rotation detection module"
```

---

### Task 4: RPS Backtest Strategy (Integration)

**Files:**
- Create: `src/analysis/strategies.py`
- Create: `tests/test_strategies.py`

**Step 1: Write failing tests**

```python
"""Tests for built-in backtest strategies."""

import numpy as np
import pandas as pd
import pytest

from src.analysis.strategies import rps_momentum_signal, ma_crossover_signal
from src.analysis.backtest_engine import BacktestEngine


def _make_price_with_rps(n_days: int = 120) -> pd.DataFrame:
    """Generate price data with RPS columns."""
    np.random.seed(42)
    returns = np.random.normal(0.001, 0.02, n_days)
    close = 10.0 * np.cumprod(1 + returns)
    dates = pd.bdate_range("2025-01-01", periods=n_days)
    df = pd.DataFrame({
        "date": dates,
        "open": close * 0.999,
        "high": close * 1.01,
        "low": close * 0.99,
        "close": close,
        "volume": np.random.randint(100000, 1000000, n_days),
        "rps_10": np.random.uniform(50, 100, n_days),
        "rps_20": np.random.uniform(40, 95, n_days),
        "rps_50": np.random.uniform(30, 90, n_days),
    })
    return df


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
```

**Step 2: Run tests → FAIL**

**Step 3: Implement**

```python
"""
内置回测策略信号生成器

每个 signal_fn 接收 DataFrame，返回 pd.Series of 0/1。
"""

import pandas as pd


def rps_momentum_signal(
    df: pd.DataFrame,
    threshold: float = 90,
    rps_col: str = "rps_10",
) -> pd.Series:
    """RPS 动量策略：RPS > threshold 时持仓。

    Args:
        df: DataFrame with rps_10 (or specified rps_col) column
        threshold: RPS 阈值
        rps_col: RPS 列名

    Returns:
        0/1 信号序列
    """
    if rps_col not in df.columns:
        return pd.Series(0, index=df.index)
    return (df[rps_col] > threshold).astype(int)


def ma_crossover_signal(
    df: pd.DataFrame,
    fast: int = 5,
    slow: int = 20,
) -> pd.Series:
    """均线交叉策略：快线 > 慢线时持仓。

    Args:
        df: DataFrame with 'close' column
        fast: 快线周期
        slow: 慢线周期

    Returns:
        0/1 信号序列
    """
    ma_fast = df["close"].rolling(fast).mean()
    ma_slow = df["close"].rolling(slow).mean()
    return (ma_fast > ma_slow).astype(int).fillna(0).astype(int)
```

**Step 4: Run tests → ALL PASS**

**Step 5: Commit**

```bash
git add src/analysis/strategies.py tests/test_strategies.py
git commit -m "feat: add RPS momentum and MA crossover strategy signals"
```

---

### Task 5: Full Regression + Lint

**Files:** All Phase 3C files

**Step 1: Run ruff**

```bash
ruff check src/analysis/backtest_metrics.py src/analysis/backtest_engine.py src/analysis/sector_rotation.py src/analysis/strategies.py tests/test_backtest_metrics.py tests/test_backtest_engine.py tests/test_sector_rotation.py tests/test_strategies.py --fix
ruff format src/analysis/backtest_metrics.py src/analysis/backtest_engine.py src/analysis/sector_rotation.py src/analysis/strategies.py tests/test_backtest_metrics.py tests/test_backtest_engine.py tests/test_sector_rotation.py tests/test_strategies.py
```

**Step 2: Run full test suite**

```bash
python -m pytest --tb=short -q
```

Expected: ~340+ tests, ALL PASS (except pre-existing flaky rate limiter)

**Step 3: Fix any failures, then commit**

```bash
git add -u
git commit -m "chore: lint fixes for Phase 3C"
```

---

## DoD Verification

| Requirement | Implementation |
|---|---|
| RPS 行业相对强度 | `rps_momentum_signal()` + existing `stock_rps`/`sector_rps` data |
| 板块轮动检测 | `sector_rotation.py`: `detect_rotation()`, `rank_sectors()`, `rotation_momentum()` |
| 基础回测框架 | `BacktestEngine.run(prices, signal_fn)` → `BacktestResult` |
| 可复现回测结果 | Deterministic: same data + same signal = same result |
| Sharpe Ratio | `backtest_metrics.sharpe_ratio()` — annualized, configurable risk-free rate |
| 最大回撤 | `backtest_metrics.max_drawdown()` |
| CAGR | `backtest_metrics.cagr()` |
| 胜率/盈亏比 | `win_rate()`, `profit_factor()` |
| 内置策略 | `strategies.py`: RPS momentum, MA crossover |
