"""技术指标纯计算函数测试。"""

import numpy as np
import pandas as pd

from src.analysis.technical import (
    atr,
    bollinger_bands,
    ema,
    kdj,
    macd,
    obv,
    rsi,
    volume_ratio,
    williams_r,
)


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


class TestRSI:
    def test_rsi_range_0_to_100(self):
        closes = pd.Series(np.random.uniform(10, 20, 50))
        result = rsi(closes, period=14)
        valid = result.dropna()
        assert (valid >= 0).all()
        assert (valid <= 100).all()

    def test_rsi_all_up_near_100(self):
        closes = pd.Series(range(1, 32), dtype=float)
        result = rsi(closes, period=14)
        assert result.iloc[-1] > 90

    def test_rsi_all_down_near_0(self):
        closes = pd.Series(range(30, 0, -1), dtype=float)
        result = rsi(closes, period=14)
        assert result.iloc[-1] < 10

    def test_rsi_default_period_14(self):
        closes = pd.Series(np.random.uniform(10, 20, 30))
        result = rsi(closes)
        assert len(result) == 30


class TestKDJ:
    def test_kdj_returns_three_series(self):
        df = pd.DataFrame(
            {
                "high": np.random.uniform(11, 15, 30),
                "low": np.random.uniform(8, 10, 30),
                "close": np.random.uniform(9, 14, 30),
            }
        )
        k, d, j = kdj(df["high"], df["low"], df["close"])
        assert len(k) == 30
        assert len(d) == 30
        assert len(j) == 30

    def test_kdj_k_range(self):
        df = pd.DataFrame(
            {
                "high": np.random.uniform(11, 15, 50),
                "low": np.random.uniform(8, 10, 50),
                "close": np.random.uniform(9, 14, 50),
            }
        )
        k, d, j = kdj(df["high"], df["low"], df["close"])
        valid_k = k.dropna()
        assert (valid_k >= 0).all()
        assert (valid_k <= 100).all()

    def test_kdj_j_can_exceed_100(self):
        highs = pd.Series([10.0] * 9 + [20.0] * 5)
        lows = pd.Series([9.0] * 9 + [9.5] * 5)
        closes = pd.Series([9.5] * 9 + [19.0] * 5)
        k, d, j = kdj(highs, lows, closes)
        assert j.iloc[-1] > 100


class TestBollingerBands:
    def test_returns_three_series(self):
        closes = pd.Series(np.random.uniform(10, 20, 30))
        upper, mid, lower = bollinger_bands(closes)
        assert len(upper) == 30

    def test_upper_above_mid_above_lower(self):
        closes = pd.Series(np.random.uniform(10, 20, 30))
        upper, mid, lower = bollinger_bands(closes)
        valid = ~(np.isnan(upper) | np.isnan(lower))
        assert (upper[valid] >= mid[valid]).all()
        assert (mid[valid] >= lower[valid]).all()

    def test_mid_equals_sma(self):
        closes = pd.Series(np.random.uniform(10, 20, 30))
        upper, mid, lower = bollinger_bands(closes, period=20)
        sma = closes.rolling(20).mean()
        pd.testing.assert_series_equal(mid, sma, check_names=False)


class TestATR:
    def test_atr_positive(self):
        highs = pd.Series(np.random.uniform(11, 15, 30))
        lows = pd.Series(np.random.uniform(8, 10, 30))
        closes = pd.Series(np.random.uniform(9, 14, 30))
        result = atr(highs, lows, closes)
        valid = result.dropna()
        assert (valid > 0).all()

    def test_atr_length_matches(self):
        highs = pd.Series(np.random.uniform(11, 15, 30))
        lows = pd.Series(np.random.uniform(8, 10, 30))
        closes = pd.Series(np.random.uniform(9, 14, 30))
        result = atr(highs, lows, closes, period=14)
        assert len(result) == 30


class TestOBV:
    def test_obv_increases_on_up_close(self):
        closes = pd.Series([10.0, 11.0, 12.0, 13.0])
        volumes = pd.Series([100.0, 200.0, 300.0, 400.0])
        result = obv(closes, volumes)
        assert result.iloc[-1] > result.iloc[0]

    def test_obv_length_matches(self):
        closes = pd.Series([10.0, 11.0, 9.0, 12.0])
        volumes = pd.Series([100.0, 200.0, 300.0, 400.0])
        result = obv(closes, volumes)
        assert len(result) == 4


class TestWilliamsR:
    def test_range_negative_100_to_0(self):
        highs = pd.Series(np.random.uniform(11, 15, 30))
        lows = pd.Series(np.random.uniform(8, 10, 30))
        closes = pd.Series(np.random.uniform(9, 14, 30))
        result = williams_r(highs, lows, closes)
        valid = result.dropna()
        assert (valid >= -100).all()
        assert (valid <= 0).all()

    def test_close_at_high_gives_0(self):
        highs = pd.Series([15.0] * 20)
        lows = pd.Series([10.0] * 20)
        closes = pd.Series([15.0] * 20)
        result = williams_r(highs, lows, closes, period=14)
        assert result.iloc[-1] == 0.0


class TestVolumeRatio:
    def test_volume_ratio_returns_series(self):
        volumes = pd.Series([100.0] * 20)
        result = volume_ratio(volumes, period=5)
        assert len(result) == 20

    def test_constant_volume_gives_ratio_1(self):
        volumes = pd.Series([100.0] * 20)
        result = volume_ratio(volumes, period=5)
        valid = result.dropna()
        np.testing.assert_array_almost_equal(valid.values, 1.0)
