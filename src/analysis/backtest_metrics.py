"""
回测性能指标 -- 纯计算，无副作用

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
