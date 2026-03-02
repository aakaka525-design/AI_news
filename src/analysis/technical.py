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


# ===================================================================
# RSI
# ===================================================================


def rsi(closes: pd.Series, period: int = 14) -> pd.Series:
    """RSI 相对强弱指标。使用 Wilder 平滑法（alpha=1/period）。

    Returns:
        RSI 序列 (0-100)
    """
    delta = closes.diff()
    gain = delta.clip(lower=0)
    loss = (-delta).clip(lower=0)

    avg_gain = gain.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()

    rs = avg_gain / avg_loss
    return 100 - 100 / (1 + rs)


# ===================================================================
# KDJ
# ===================================================================


def kdj(
    highs: pd.Series,
    lows: pd.Series,
    closes: pd.Series,
    n: int = 9,
    m1: int = 3,
    m2: int = 3,
) -> tuple[pd.Series, pd.Series, pd.Series]:
    """KDJ 随机指标。

    Returns:
        (K, D, J) — J = 3K - 2D
    """
    lowest = lows.rolling(window=n, min_periods=n).min()
    highest = highs.rolling(window=n, min_periods=n).max()
    rsv = (closes - lowest) / (highest - lowest) * 100

    k = rsv.ewm(alpha=1 / m1, adjust=False, min_periods=1).mean()
    d = k.ewm(alpha=1 / m2, adjust=False, min_periods=1).mean()
    j = 3 * k - 2 * d
    return k, d, j


# ===================================================================
# 布林带 + ATR
# ===================================================================


def bollinger_bands(
    closes: pd.Series,
    period: int = 20,
    num_std: float = 2.0,
) -> tuple[pd.Series, pd.Series, pd.Series]:
    """布林带。

    Returns:
        (上轨, 中轨, 下轨)
    """
    mid = closes.rolling(window=period).mean()
    std = closes.rolling(window=period).std()
    upper = mid + num_std * std
    lower = mid - num_std * std
    return upper, mid, lower


def atr(
    highs: pd.Series,
    lows: pd.Series,
    closes: pd.Series,
    period: int = 14,
) -> pd.Series:
    """ATR 平均真实波幅。"""
    prev_close = closes.shift(1)
    tr = pd.concat(
        [
            highs - lows,
            (highs - prev_close).abs(),
            (lows - prev_close).abs(),
        ],
        axis=1,
    ).max(axis=1)
    return tr.rolling(window=period, min_periods=period).mean()


# ===================================================================
# OBV + 威廉指标 + 量比
# ===================================================================


def obv(closes: pd.Series, volumes: pd.Series) -> pd.Series:
    """OBV 能量潮指标。"""
    direction = closes.diff().apply(lambda x: 1 if x > 0 else (-1 if x < 0 else 0))
    return (direction * volumes).cumsum()


def williams_r(
    highs: pd.Series,
    lows: pd.Series,
    closes: pd.Series,
    period: int = 14,
) -> pd.Series:
    """威廉指标 (Williams %R)。

    Returns:
        序列 (-100 到 0)
    """
    highest = highs.rolling(window=period, min_periods=period).max()
    lowest = lows.rolling(window=period, min_periods=period).min()
    return (closes - highest) / (highest - lowest) * 100


def volume_ratio(volumes: pd.Series, period: int = 5) -> pd.Series:
    """量比 = 当日成交量 / 过去 N 日平均成交量。"""
    avg = volumes.rolling(window=period, min_periods=period).mean()
    return volumes / avg
