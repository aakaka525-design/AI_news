"""
技术指标纯计算模块

所有函数接收 pandas Series / DataFrame，返回 pandas Series。
不依赖数据库、不依赖网络。纯数学计算。
"""

import pandas as pd

# ===================================================================
# 均线类
# ===================================================================


def ema(series: pd.Series, period: int) -> pd.Series:
    """指数移动平均线 (EMA)。

    Args:
        series: 价格序列
        period: 周期

    Returns:
        EMA 序列（前 period-1 个值为 NaN）
    """
    return series.ewm(span=period, adjust=False, min_periods=period).mean()


# ===================================================================
# MACD
# ===================================================================


def macd(
    closes: pd.Series,
    fast: int = 12,
    slow: int = 26,
    signal: int = 9,
) -> tuple[pd.Series, pd.Series, pd.Series]:
    """MACD 指标。

    Returns:
        (DIF, DEA, MACD柱) — MACD柱 = (DIF - DEA) * 2
    """
    ema_fast = ema(closes, fast)
    ema_slow = ema(closes, slow)
    dif = ema_fast - ema_slow
    dea = ema(dif, signal)
    hist = (dif - dea) * 2
    return dif, dea, hist
