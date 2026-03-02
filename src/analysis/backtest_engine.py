"""
回测引擎 -- 单标的信号驱动回测

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
            target = int(signals.iloc[i - 1])  # signal from previous bar
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
