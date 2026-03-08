"""Freshness Decay 引擎

三类衰减规则，根据因子数据类型决定 staleness 对权重的衰减系数。
"""


FRESHNESS_RULES: dict[str, list[tuple[int, int, float]]] = {
    # (min_days, max_days, decay_factor)
    "daily_market": [
        (0, 0, 1.0),
        (1, 1, 0.75),
        (2, 2, 0.40),
        # >=3 → 0
    ],
    "event_short": [
        (0, 2, 1.0),
        (3, 5, 0.75),
        (6, 10, 0.40),
        # >10 → 0
    ],
    "periodic_fundamental": [
        (0, 20, 1.0),
        (21, 60, 0.70),
        (61, 120, 0.40),
        # >120 → 0
    ],
}

# 因子 → freshness_class 映射
FACTOR_FRESHNESS_CLASS: dict[str, str] = {
    "rps_composite": "daily_market",
    "tech_confirm": "daily_market",
    "northbound_flow": "daily_market",
    "main_money_flow": "daily_market",
    "valuation": "daily_market",
    "roe_quality": "periodic_fundamental",
}


def compute_decay(freshness_class: str, staleness_days: int) -> float:
    """根据 freshness_class 和 staleness_days 返回 0-1 的衰减系数。

    Args:
        freshness_class: 衰减规则类别 (daily_market / event_short / periodic_fundamental)
        staleness_days: 数据过期的交易日数

    Returns:
        衰减系数 (0.0 表示完全过期, 1.0 表示完全新鲜)
    """
    rules = FRESHNESS_RULES.get(freshness_class)
    if not rules:
        return 0.0

    for min_d, max_d, factor in rules:
        if min_d <= staleness_days <= max_d:
            return factor

    return 0.0
