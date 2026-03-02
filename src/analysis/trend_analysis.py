"""趋势分析增强模块：趋势识别、支撑阻力、强度评分、多周期共振。"""

import pandas as pd


def identify_trend(
    closes: pd.Series,
    ma_periods: tuple[int, ...] = (5, 10, 20, 60),
) -> dict:
    """基于均线排列识别趋势。

    判断逻辑：
    - 上升：短期均线 > 长期均线（多头排列）
    - 下降：短期均线 < 长期均线（空头排列）
    - 盘整：其他

    强度评分 (0-100)：
    - 均线排列一致性 (+40)
    - 价格在均线上方的比例 (+30)
    - 均线斜率方向一致性 (+30)
    """
    if len(closes) < max(ma_periods):
        return {"trend": "unknown", "strength": 0, "ma_alignment": "insufficient_data"}

    mas = {p: closes.rolling(p).mean() for p in ma_periods}
    latest_mas = {p: mas[p].iloc[-1] for p in ma_periods}

    # 判断排列（短期 > 长期 = 多头）
    sorted_asc = all(
        latest_mas[ma_periods[i]] >= latest_mas[ma_periods[i + 1]]
        for i in range(len(ma_periods) - 1)
    )
    sorted_desc = all(
        latest_mas[ma_periods[i]] <= latest_mas[ma_periods[i + 1]]
        for i in range(len(ma_periods) - 1)
    )

    if sorted_asc:
        trend = "uptrend"
        alignment = "bullish"
    elif sorted_desc:
        trend = "downtrend"
        alignment = "bearish"
    else:
        trend = "sideways"
        alignment = "mixed"

    # 强度评分
    score = 0
    pairs = len(ma_periods) - 1

    # 1. 均线排列一致性 (0-40)
    if trend == "uptrend":
        aligned = sum(
            1 for i in range(pairs) if latest_mas[ma_periods[i]] > latest_mas[ma_periods[i + 1]]
        )
    elif trend == "downtrend":
        aligned = sum(
            1 for i in range(pairs) if latest_mas[ma_periods[i]] < latest_mas[ma_periods[i + 1]]
        )
    else:
        aligned = 0
    score += int(aligned / pairs * 40)

    # 2. 价格在均线上方比例 (0-30)
    above_count = sum(1 for p in ma_periods if closes.iloc[-1] > latest_mas[p])
    if trend == "downtrend":
        above_count = len(ma_periods) - above_count
    score += int(above_count / len(ma_periods) * 30)

    # 3. 均线斜率方向一致性 (0-30)
    slope_window = min(5, len(closes) - max(ma_periods))
    if slope_window > 0:
        slope_aligned = 0
        for p in ma_periods:
            slope = mas[p].iloc[-1] - mas[p].iloc[-1 - slope_window]
            if (trend == "uptrend" and slope > 0) or (trend == "downtrend" and slope < 0):
                slope_aligned += 1
        score += int(slope_aligned / len(ma_periods) * 30)

    return {
        "trend": trend,
        "strength": min(100, max(0, score)),
        "ma_alignment": alignment,
    }


def find_support_resistance(
    highs: pd.Series,
    lows: pd.Series,
    closes: pd.Series,
    window: int = 5,
    max_levels: int = 3,
) -> dict:
    """基于局部极值计算支撑位和阻力位。

    Returns:
        {"support": [float, ...], "resistance": [float, ...]}
    """
    current_price = closes.iloc[-1]

    # 找局部极值
    local_highs = []
    local_lows = []
    for i in range(window, len(highs) - window):
        if highs.iloc[i] == highs.iloc[i - window : i + window + 1].max():
            local_highs.append(float(highs.iloc[i]))
        if lows.iloc[i] == lows.iloc[i - window : i + window + 1].min():
            local_lows.append(float(lows.iloc[i]))

    # 简单聚类：相邻 <1% 差异的合并取均值
    def cluster(levels: list[float], threshold: float = 0.01) -> list[float]:
        if not levels:
            return []
        levels = sorted(levels)
        clusters: list[list[float]] = [[levels[0]]]
        for lv in levels[1:]:
            if (lv - clusters[-1][-1]) / clusters[-1][-1] < threshold:
                clusters[-1].append(lv)
            else:
                clusters.append([lv])
        result = [(len(c), sum(c) / len(c)) for c in clusters]
        result.sort(key=lambda x: x[0], reverse=True)
        return [round(v, 2) for _, v in result]

    all_highs = cluster(local_highs)
    all_lows = cluster(local_lows)

    resistance = [h for h in all_highs if h > current_price][:max_levels]
    support = [lv for lv in all_lows if lv < current_price][:max_levels]

    return {"support": support, "resistance": resistance}


def multi_period_resonance(
    daily_closes: pd.Series,
) -> dict:
    """多周期趋势共振分析（日线 + 周线）。

    将日线数据按每 5 根 K 线聚合为模拟周线，
    分别做趋势识别，方向一致即为「共振」。

    Returns:
        {"resonance": bool, "daily_trend": str, "weekly_trend": str,
         "daily_strength": int, "weekly_strength": int, "signal": str}
    """
    daily_result = identify_trend(daily_closes)

    # 模拟周线：每 5 根日线取最后一根
    weekly_closes = daily_closes.iloc[::5].reset_index(drop=True)
    weekly_result = identify_trend(weekly_closes, ma_periods=(5, 10, 20))

    resonance = daily_result["trend"] == weekly_result["trend"]

    if resonance and daily_result["trend"] == "uptrend":
        signal = "strong_buy"
    elif resonance and daily_result["trend"] == "downtrend":
        signal = "strong_sell"
    else:
        signal = "neutral"

    return {
        "resonance": resonance,
        "daily_trend": daily_result["trend"],
        "weekly_trend": weekly_result["trend"],
        "daily_strength": daily_result["strength"],
        "weekly_strength": weekly_result["strength"],
        "signal": signal,
    }
