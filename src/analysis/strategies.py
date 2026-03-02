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
