"""趋势分析增强功能测试。"""

import numpy as np
import pandas as pd

from src.analysis.trend_analysis import (
    find_support_resistance,
    identify_trend,
    multi_period_resonance,
)

# ===================================================================
# identify_trend
# ===================================================================


class TestIdentifyTrend:
    def test_uptrend_on_rising_prices(self):
        closes = pd.Series(np.linspace(10, 30, 60))
        result = identify_trend(closes)
        assert result["trend"] == "uptrend"

    def test_downtrend_on_falling_prices(self):
        closes = pd.Series(np.linspace(30, 10, 60))
        result = identify_trend(closes)
        assert result["trend"] == "downtrend"

    def test_sideways_on_mixed_prices(self):
        # Gradual rise then pullback creates mixed MA ordering (sideways)
        data = np.concatenate(
            [
                np.linspace(19, 21, 40),
                np.linspace(21, 19.5, 20),
            ]
        )
        closes = pd.Series(data)
        result = identify_trend(closes)
        assert result["trend"] == "sideways"

    def test_result_has_required_keys(self):
        closes = pd.Series(np.linspace(10, 30, 60))
        result = identify_trend(closes)
        assert "trend" in result
        assert "strength" in result
        assert "ma_alignment" in result

    def test_strength_range_0_to_100(self):
        closes = pd.Series(np.linspace(10, 30, 60))
        result = identify_trend(closes)
        assert 0 <= result["strength"] <= 100

    def test_insufficient_data(self):
        closes = pd.Series([10.0, 11.0])
        result = identify_trend(closes)
        assert result["trend"] == "unknown"


# ===================================================================
# find_support_resistance
# ===================================================================


class TestSupportResistance:
    def test_returns_support_and_resistance(self):
        highs = pd.Series([12, 11, 13, 10, 14, 11, 12, 15, 13, 11] * 3, dtype=float)
        lows = pd.Series([9, 8, 10, 7, 11, 8, 9, 12, 10, 8] * 3, dtype=float)
        closes = pd.Series([10, 9, 12, 8, 13, 9, 11, 14, 12, 9] * 3, dtype=float)
        result = find_support_resistance(highs, lows, closes)
        assert "support" in result
        assert "resistance" in result
        assert len(result["support"]) > 0 or len(result["resistance"]) > 0

    def test_returns_list_of_floats(self):
        n = 30
        np.random.seed(42)
        highs = pd.Series(np.random.uniform(12, 15, n))
        lows = pd.Series(np.random.uniform(8, 10, n))
        closes = pd.Series(np.random.uniform(9, 14, n))
        result = find_support_resistance(highs, lows, closes)
        for level in result["support"] + result["resistance"]:
            assert isinstance(level, float)

    def test_max_levels_respected(self):
        highs = pd.Series([12, 11, 15, 10, 18, 11, 20, 10, 22, 11] * 3, dtype=float)
        lows = pd.Series([5, 4, 6, 3, 7, 4, 8, 3, 9, 4] * 3, dtype=float)
        closes = pd.Series([10, 9, 12, 8, 13, 9, 14, 8, 15, 9] * 3, dtype=float)
        result = find_support_resistance(highs, lows, closes, max_levels=2)
        assert len(result["support"]) <= 2
        assert len(result["resistance"]) <= 2


# ===================================================================
# multi_period_resonance
# ===================================================================


class TestMultiPeriodResonance:
    def test_full_resonance_on_strong_uptrend(self):
        daily = pd.Series(np.linspace(10, 30, 120))
        result = multi_period_resonance(daily)
        assert result["resonance"] is True
        assert result["daily_trend"] == "uptrend"
        assert result["weekly_trend"] == "uptrend"

    def test_result_keys(self):
        daily = pd.Series(np.linspace(10, 30, 120))
        result = multi_period_resonance(daily)
        assert "resonance" in result
        assert "daily_trend" in result
        assert "weekly_trend" in result
        assert "signal" in result

    def test_strong_buy_signal_on_resonance_uptrend(self):
        daily = pd.Series(np.linspace(10, 30, 120))
        result = multi_period_resonance(daily)
        assert result["signal"] == "strong_buy"

    def test_strong_sell_signal_on_resonance_downtrend(self):
        daily = pd.Series(np.linspace(30, 10, 120))
        result = multi_period_resonance(daily)
        assert result["signal"] == "strong_sell"
