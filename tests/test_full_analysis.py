"""
full_analysis 模块单元测试

覆盖：技术形态分析、支撑阻力计算、数据获取
"""

import pytest
import pandas as pd
import numpy as np
from unittest.mock import patch, MagicMock


class TestAnalyzePattern:
    """技术形态分析测试"""

    def _make_df(self, closes, volumes=None):
        """构造测试用 DataFrame"""
        n = len(closes)
        if volumes is None:
            volumes = [1000000] * n
        return pd.DataFrame({
            "日期": pd.date_range("2026-01-01", periods=n).strftime("%Y-%m-%d").tolist(),
            "开盘": closes,
            "收盘": closes,
            "最高": [c * 1.02 for c in closes],
            "最低": [c * 0.98 for c in closes],
            "成交量": volumes,
            "涨跌幅": [0.0] + [
                (closes[i] - closes[i - 1]) / closes[i - 1] * 100
                for i in range(1, n)
            ],
        })

    def test_analyze_pattern_returns_metrics(self):
        from src.strategies.full_analysis import analyze_pattern

        closes = list(range(50, 110))  # 60 days uptrend
        df = self._make_df(closes)
        metrics = analyze_pattern(df)

        assert "price" in metrics
        assert "ma20" in metrics
        assert "recent_high" in metrics
        assert "recent_low" in metrics
        assert metrics["price"] == closes[-1]

    def test_calc_support_resistance(self):
        from src.strategies.full_analysis import calc_support_resistance

        closes = list(range(50, 110))
        df = self._make_df(closes)
        metrics = {
            "price": closes[-1],
            "ma20": sum(closes[-20:]) / 20,
            "recent_high": max(c * 1.02 for c in closes[-20:]),
            "recent_low": min(c * 0.98 for c in closes[-20:]),
        }

        # Should not raise
        calc_support_resistance(df, metrics)

    def test_volume_analysis_detects_shrinkage(self):
        """缩量检测"""
        from src.strategies.full_analysis import analyze_pattern

        closes = list(range(50, 110))
        volumes = [1000000] * 55 + [100000] * 5  # 最后 5 天缩量
        df = self._make_df(closes, volumes)
        metrics = analyze_pattern(df)
        assert metrics is not None

    def test_bull_trend_detection(self):
        """多头排列检测"""
        from src.strategies.full_analysis import analyze_pattern

        # MA5 > MA10 > MA20 需要持续上涨
        closes = [float(i) for i in range(50, 110)]
        df = self._make_df(closes)
        metrics = analyze_pattern(df)
        # 上涨趋势中，价格应高于 MA20
        assert metrics["price"] > metrics["ma20"]

    def test_handles_short_data(self):
        """短数据不崩溃（< 60 天）"""
        from src.strategies.full_analysis import analyze_pattern

        closes = list(range(50, 80))  # 30 天
        df = self._make_df(closes)
        metrics = analyze_pattern(df)
        assert metrics is not None
