"""技术指标纯计算函数测试。"""

import numpy as np
import pandas as pd

from src.analysis.technical import ema, macd


class TestEMA:
    def test_ema_length_matches_input(self):
        closes = pd.Series([10.0, 11.0, 12.0, 11.5, 13.0])
        result = ema(closes, period=3)
        assert len(result) == len(closes)

    def test_ema_first_values_are_nan(self):
        closes = pd.Series([10.0, 11.0, 12.0, 11.5, 13.0])
        result = ema(closes, period=3)
        assert np.isnan(result.iloc[0])
        assert np.isnan(result.iloc[1])

    def test_ema_responds_to_price_changes(self):
        closes = pd.Series([10.0] * 10 + [20.0] * 5)
        result = ema(closes, period=5)
        assert result.iloc[-1] > result.iloc[9]

    def test_ema_period_1_equals_close(self):
        closes = pd.Series([10.0, 11.0, 12.0])
        result = ema(closes, period=1)
        pd.testing.assert_series_equal(result, closes)


class TestMACD:
    def test_macd_returns_three_series(self):
        closes = pd.Series(np.random.uniform(10, 20, 50))
        dif, dea, hist = macd(closes)
        assert len(dif) == 50
        assert len(dea) == 50
        assert len(hist) == 50

    def test_macd_hist_equals_dif_minus_dea_times_2(self):
        closes = pd.Series(np.random.uniform(10, 20, 50))
        dif, dea, hist = macd(closes)
        valid = ~(np.isnan(dif) | np.isnan(dea))
        np.testing.assert_array_almost_equal(hist[valid], (dif[valid] - dea[valid]) * 2)

    def test_macd_default_params(self):
        closes = pd.Series(np.random.uniform(10, 20, 50))
        dif, dea, hist = macd(closes)
        assert np.isnan(dif.iloc[0])
