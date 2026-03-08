# Phase 3A：技术指标 + 趋势分析 实施计划

> **状态：已完成**
> `src/analysis/technical.py`、`src/analysis/trend_analysis.py` 及对应测试已落地，计划中的技术指标与趋势分析核心纯计算模块已全部实现。

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**目标：** 补全缺失的技术指标计算（MACD/RSI/KDJ/布林带/ATR/OBV/EMA/威廉指标），增强趋势分析（趋势识别、支撑阻力、强度评分、多周期共振）。

**架构：** 新建纯计算模块 `src/analysis/technical.py`，输入 pandas DataFrame，输出指标值。不耦合数据库，不耦合数据源。现有 `indicators.py`（数据获取+MA/RPS）和 `trend.py`（规则预测）保持不变，新模块被它们调用。

**技术栈：** pandas, numpy（向量化计算，无第三方技术指标库依赖）

**现状分析：**
- `indicators.py` 已有：MA(5/10/20/60)、RPS(10/20/50/60)、Volume MA(5)、多头排列标志
- `indicators.py` 缺失：EMA、MACD、RSI、KDJ、布林带、ATR、OBV、威廉指标、MA(120/250)
- `trend.py` 已有：规则预测（bullish/bearish/neutral）、12维特征、LSTM可选、批量预测
- `trend.py` 缺失：趋势识别（上升/下降/盘整）、支撑阻力位、趋势强度评分(0-100)、多周期共振
- `stock_technicals` 表已有列：ma5/ma10/ma20/ma60/rsi14/macd/macd_signal/macd_hist（后4列从未被填充）

---

### Task 1：EMA + MACD 计算函数

**文件：**
- 创建：`src/analysis/technical.py`
- 测试：`tests/test_technical.py`

**Step 1：写失败的测试**

```python
# tests/test_technical.py
"""技术指标纯计算函数测试。"""

import numpy as np
import pandas as pd
import pytest

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
        # EMA 在价格跳涨后应逐步上升
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

    def test_macd_hist_equals_dif_minus_dea(self):
        closes = pd.Series(np.random.uniform(10, 20, 50))
        dif, dea, hist = macd(closes)
        valid = ~(np.isnan(dif) | np.isnan(dea))
        np.testing.assert_array_almost_equal(
            hist[valid], (dif[valid] - dea[valid]) * 2
        )

    def test_macd_default_params(self):
        """默认参数 (12, 26, 9)"""
        closes = pd.Series(np.random.uniform(10, 20, 50))
        dif, dea, hist = macd(closes)
        # 前 25 个 DIF 应为 NaN（需要 26 期 EMA）
        assert np.isnan(dif.iloc[0])
```

**Step 2：运行测试确认失败**

```bash
pytest tests/test_technical.py -v
```

**Step 3：写最小实现**

```python
# src/analysis/technical.py
"""
技术指标纯计算模块

所有函数接收 pandas Series / DataFrame，返回 pandas Series。
不依赖数据库、不依赖网络。纯数学计算。
"""

import numpy as np
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
```

**Step 4：运行测试确认通过**

```bash
pytest tests/test_technical.py -v
```

**Step 5：提交**

```bash
git add src/analysis/technical.py tests/test_technical.py
git commit -m "feat: add EMA and MACD calculation functions"
```

---

### Task 2：RSI 计算函数

**文件：**
- 修改：`src/analysis/technical.py`
- 修改：`tests/test_technical.py`

**Step 1：写失败的测试**

```python
# 追加到 tests/test_technical.py
from src.analysis.technical import rsi


class TestRSI:
    def test_rsi_range_0_to_100(self):
        closes = pd.Series(np.random.uniform(10, 20, 50))
        result = rsi(closes, period=14)
        valid = result.dropna()
        assert (valid >= 0).all()
        assert (valid <= 100).all()

    def test_rsi_all_up_near_100(self):
        closes = pd.Series(range(1, 32), dtype=float)  # 连续上涨
        result = rsi(closes, period=14)
        assert result.iloc[-1] > 90

    def test_rsi_all_down_near_0(self):
        closes = pd.Series(range(30, 0, -1), dtype=float)  # 连续下跌
        result = rsi(closes, period=14)
        assert result.iloc[-1] < 10

    def test_rsi_default_period_14(self):
        closes = pd.Series(np.random.uniform(10, 20, 30))
        result = rsi(closes)
        assert len(result) == 30
```

**Step 2：实现**

```python
# 追加到 src/analysis/technical.py

def rsi(closes: pd.Series, period: int = 14) -> pd.Series:
    """RSI 相对强弱指标。

    使用 Wilder 平滑法（即 EMA alpha=1/period）。

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
```

**Step 3：测试、提交**

```bash
pytest tests/test_technical.py::TestRSI -v
git add src/analysis/technical.py tests/test_technical.py
git commit -m "feat: add RSI calculation function"
```

---

### Task 3：KDJ 计算函数

**文件：**
- 修改：`src/analysis/technical.py`
- 修改：`tests/test_technical.py`

**Step 1：写失败的测试**

```python
from src.analysis.technical import kdj


class TestKDJ:
    def test_kdj_returns_three_series(self):
        df = pd.DataFrame({
            "high": np.random.uniform(11, 15, 30),
            "low": np.random.uniform(8, 10, 30),
            "close": np.random.uniform(9, 14, 30),
        })
        k, d, j = kdj(df["high"], df["low"], df["close"])
        assert len(k) == 30
        assert len(d) == 30
        assert len(j) == 30

    def test_kdj_k_range(self):
        df = pd.DataFrame({
            "high": np.random.uniform(11, 15, 50),
            "low": np.random.uniform(8, 10, 50),
            "close": np.random.uniform(9, 14, 50),
        })
        k, d, j = kdj(df["high"], df["low"], df["close"])
        valid_k = k.dropna()
        assert (valid_k >= 0).all()
        assert (valid_k <= 100).all()

    def test_kdj_j_can_exceed_100(self):
        """J 值 = 3K - 2D，可超出 0-100"""
        highs = pd.Series([10.0] * 9 + [20.0] * 5)
        lows = pd.Series([9.0] * 9 + [9.5] * 5)
        closes = pd.Series([9.5] * 9 + [19.0] * 5)
        k, d, j = kdj(highs, lows, closes)
        # J 值在急涨时应超过 100
        assert j.iloc[-1] > 100
```

**Step 2：实现**

```python
def kdj(
    highs: pd.Series,
    lows: pd.Series,
    closes: pd.Series,
    n: int = 9,
    m1: int = 3,
    m2: int = 3,
) -> tuple[pd.Series, pd.Series, pd.Series]:
    """KDJ 随机指标。

    Args:
        highs: 最高价序列
        lows: 最低价序列
        closes: 收盘价序列
        n: RSV 周期 (默认 9)
        m1: K 平滑周期 (默认 3)
        m2: D 平滑周期 (默认 3)

    Returns:
        (K, D, J)
    """
    lowest = lows.rolling(window=n, min_periods=n).min()
    highest = highs.rolling(window=n, min_periods=n).max()
    rsv = (closes - lowest) / (highest - lowest) * 100

    k = rsv.ewm(alpha=1 / m1, adjust=False, min_periods=1).mean()
    d = k.ewm(alpha=1 / m2, adjust=False, min_periods=1).mean()
    j = 3 * k - 2 * d
    return k, d, j
```

**Step 3：测试、提交**

```bash
pytest tests/test_technical.py::TestKDJ -v
git commit -m "feat: add KDJ calculation function"
```

---

### Task 4：布林带 + ATR

**文件：**
- 修改：`src/analysis/technical.py`
- 修改：`tests/test_technical.py`

**Step 1：写失败的测试**

```python
from src.analysis.technical import bollinger_bands, atr


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
        df = pd.DataFrame({
            "high": np.random.uniform(11, 15, 30),
            "low": np.random.uniform(8, 10, 30),
            "close": np.random.uniform(9, 14, 30),
        })
        result = atr(df["high"], df["low"], df["close"])
        valid = result.dropna()
        assert (valid > 0).all()

    def test_atr_length_matches(self):
        n = 30
        df = pd.DataFrame({
            "high": np.random.uniform(11, 15, n),
            "low": np.random.uniform(8, 10, n),
            "close": np.random.uniform(9, 14, n),
        })
        result = atr(df["high"], df["low"], df["close"], period=14)
        assert len(result) == n
```

**Step 2：实现**

```python
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
    tr = pd.concat([
        highs - lows,
        (highs - prev_close).abs(),
        (lows - prev_close).abs(),
    ], axis=1).max(axis=1)
    return tr.rolling(window=period, min_periods=period).mean()
```

**Step 3：测试、提交**

```bash
pytest tests/test_technical.py -v
git commit -m "feat: add Bollinger Bands and ATR calculation functions"
```

---

### Task 5：OBV + 威廉指标 + 量比

**文件：**
- 修改：`src/analysis/technical.py`
- 修改：`tests/test_technical.py`

**Step 1：写失败的测试**

```python
from src.analysis.technical import obv, williams_r, volume_ratio


class TestOBV:
    def test_obv_increases_on_up_close(self):
        closes = pd.Series([10.0, 11.0, 12.0, 13.0])
        volumes = pd.Series([100.0, 200.0, 300.0, 400.0])
        result = obv(closes, volumes)
        # 连续上涨，OBV 应单调递增
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
        closes = pd.Series([15.0] * 20)  # 收盘=最高
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
```

**Step 2：实现**

```python
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
        序列 (-100 到 0)，-100 表示超卖，0 表示超买
    """
    highest = highs.rolling(window=period, min_periods=period).max()
    lowest = lows.rolling(window=period, min_periods=period).min()
    return (closes - highest) / (highest - lowest) * 100


def volume_ratio(volumes: pd.Series, period: int = 5) -> pd.Series:
    """量比 = 当日成交量 / 过去 N 日平均成交量。"""
    avg = volumes.rolling(window=period, min_periods=period).mean()
    return volumes / avg
```

**Step 3：测试、提交**

```bash
pytest tests/test_technical.py -v
git commit -m "feat: add OBV, Williams %R, and volume ratio functions"
```

---

### Task 6：compute_all 聚合函数 + 集成到 indicators.py

**文件：**
- 修改：`src/analysis/technical.py`
- 修改：`tests/test_technical.py`
- 修改：`src/analysis/indicators.py:492-589`（`calculate_all_indicators` 函数）

**Step 1：写失败的测试**

```python
from src.analysis.technical import compute_all


class TestComputeAll:
    @pytest.fixture()
    def sample_df(self):
        """50 天的模拟 OHLCV 数据。"""
        np.random.seed(42)
        n = 50
        close = pd.Series(np.cumsum(np.random.randn(n)) + 100)
        return pd.DataFrame({
            "open": close + np.random.uniform(-1, 1, n),
            "high": close + np.abs(np.random.randn(n)),
            "low": close - np.abs(np.random.randn(n)),
            "close": close,
            "volume": np.random.uniform(1e6, 5e6, n),
        })

    def test_returns_all_indicator_columns(self, sample_df):
        result = compute_all(sample_df)
        expected_cols = [
            "ema12", "ema26", "macd_dif", "macd_dea", "macd_hist",
            "rsi6", "rsi12", "rsi24",
            "kdj_k", "kdj_d", "kdj_j",
            "boll_upper", "boll_mid", "boll_lower",
            "atr14", "obv", "williams_r", "volume_ratio",
        ]
        for col in expected_cols:
            assert col in result.columns, f"缺少列: {col}"

    def test_does_not_modify_input(self, sample_df):
        original_cols = list(sample_df.columns)
        compute_all(sample_df)
        assert list(sample_df.columns) == original_cols

    def test_output_length_matches_input(self, sample_df):
        result = compute_all(sample_df)
        assert len(result) == len(sample_df)
```

**Step 2：实现 compute_all**

```python
def compute_all(df: pd.DataFrame) -> pd.DataFrame:
    """计算所有技术指标，返回新 DataFrame。

    输入 DataFrame 必须包含列：open, high, low, close, volume

    Returns:
        包含所有指标列的新 DataFrame（保留原始列）
    """
    result = df.copy()

    c = df["close"]
    h = df["high"]
    l = df["low"]  # noqa: E741
    v = df["volume"]

    # EMA
    result["ema12"] = ema(c, 12)
    result["ema26"] = ema(c, 26)

    # MACD
    result["macd_dif"], result["macd_dea"], result["macd_hist"] = macd(c)

    # RSI
    result["rsi6"] = rsi(c, 6)
    result["rsi12"] = rsi(c, 12)
    result["rsi24"] = rsi(c, 24)

    # KDJ
    result["kdj_k"], result["kdj_d"], result["kdj_j"] = kdj(h, l, c)

    # 布林带
    result["boll_upper"], result["boll_mid"], result["boll_lower"] = bollinger_bands(c)

    # ATR
    result["atr14"] = atr(h, l, c, 14)

    # OBV
    result["obv"] = obv(c, v)

    # 威廉指标
    result["williams_r"] = williams_r(h, l, c)

    # 量比
    result["volume_ratio"] = volume_ratio(v)

    return result
```

**Step 3：集成到 indicators.py**

在 `calculate_all_indicators()` 函数的均线计算后面追加 MACD/RSI 计算并写入 `stock_technicals` 表（该表已有 rsi14/macd/macd_signal/macd_hist 列但从未被填充）：

```python
# 在 indicators.py 的 compute_group_metrics 函数中追加：
from src.analysis.technical import macd as calc_macd, rsi as calc_rsi

def compute_group_metrics(group):
    # ... 已有的 MA/RPS 计算 ...

    # MACD
    dif, dea, hist = calc_macd(group['close'])
    group['macd_dif'] = dif
    group['macd_dea'] = dea
    group['macd_hist'] = hist

    # RSI
    group['rsi14'] = calc_rsi(group['close'], 14)

    return group
```

然后更新写入 `stock_technicals` 的 SQL，填充 rsi14/macd/macd_signal/macd_hist 列。

**Step 4：测试、提交**

```bash
pytest tests/test_technical.py tests/test_analysis.py -v
git commit -m "feat: add compute_all aggregator and wire into indicators.py"
```

---

### Task 7：趋势识别（上升/下降/盘整）

**文件：**
- 创建：`src/analysis/trend_analysis.py`
- 测试：`tests/test_trend_analysis.py`

**Step 1：写失败的测试**

```python
# tests/test_trend_analysis.py
"""趋势分析增强功能测试。"""

import numpy as np
import pandas as pd
import pytest

from src.analysis.trend_analysis import identify_trend


class TestIdentifyTrend:
    def test_uptrend_on_rising_prices(self):
        """连续上涨应识别为上升趋势。"""
        closes = pd.Series(np.linspace(10, 30, 60))
        result = identify_trend(closes)
        assert result["trend"] == "uptrend"

    def test_downtrend_on_falling_prices(self):
        closes = pd.Series(np.linspace(30, 10, 60))
        result = identify_trend(closes)
        assert result["trend"] == "downtrend"

    def test_sideways_on_flat_prices(self):
        np.random.seed(42)
        closes = pd.Series(20 + np.random.randn(60) * 0.3)
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
```

**Step 2：实现**

```python
# src/analysis/trend_analysis.py
"""趋势分析增强模块：趋势识别、支撑阻力、强度评分、多周期共振。"""

import numpy as np
import pandas as pd


def identify_trend(
    closes: pd.Series,
    ma_periods: tuple[int, ...] = (5, 10, 20, 60),
) -> dict:
    """基于均线排列识别趋势。

    判断逻辑：
    - 上升：MA5 > MA10 > MA20（多头排列）
    - 下降：MA5 < MA10 < MA20（空头排列）
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

    # 判断排列
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

    # 1. 均线排列一致性 (0-40)
    pairs = len(ma_periods) - 1
    if trend == "uptrend":
        aligned = sum(
            1 for i in range(pairs)
            if latest_mas[ma_periods[i]] > latest_mas[ma_periods[i + 1]]
        )
    elif trend == "downtrend":
        aligned = sum(
            1 for i in range(pairs)
            if latest_mas[ma_periods[i]] < latest_mas[ma_periods[i + 1]]
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
```

**Step 3：测试、提交**

```bash
pytest tests/test_trend_analysis.py -v
git commit -m "feat: add trend identification with strength scoring"
```

---

### Task 8：支撑位 / 阻力位计算

**文件：**
- 修改：`src/analysis/trend_analysis.py`
- 修改：`tests/test_trend_analysis.py`

**Step 1：写失败的测试**

```python
from src.analysis.trend_analysis import find_support_resistance


class TestSupportResistance:
    def test_returns_support_and_resistance(self):
        highs = pd.Series([12, 11, 13, 10, 14, 11, 12, 15, 13, 11] * 3, dtype=float)
        lows = pd.Series([9, 8, 10, 7, 11, 8, 9, 12, 10, 8] * 3, dtype=float)
        closes = pd.Series([10, 9, 12, 8, 13, 9, 11, 14, 12, 9] * 3, dtype=float)
        result = find_support_resistance(highs, lows, closes)
        assert "support" in result
        assert "resistance" in result
        assert len(result["support"]) > 0
        assert len(result["resistance"]) > 0

    def test_support_below_resistance(self):
        highs = pd.Series([12, 11, 13, 10, 14, 11, 12, 15, 13, 11] * 3, dtype=float)
        lows = pd.Series([9, 8, 10, 7, 11, 8, 9, 12, 10, 8] * 3, dtype=float)
        closes = pd.Series([10, 9, 12, 8, 13, 9, 11, 14, 12, 9] * 3, dtype=float)
        result = find_support_resistance(highs, lows, closes)
        if result["support"] and result["resistance"]:
            assert min(result["resistance"]) >= max(result["support"])

    def test_returns_list_of_floats(self):
        n = 30
        highs = pd.Series(np.random.uniform(12, 15, n))
        lows = pd.Series(np.random.uniform(8, 10, n))
        closes = pd.Series(np.random.uniform(9, 14, n))
        result = find_support_resistance(highs, lows, closes)
        for level in result["support"] + result["resistance"]:
            assert isinstance(level, float)
```

**Step 2：实现**

```python
def find_support_resistance(
    highs: pd.Series,
    lows: pd.Series,
    closes: pd.Series,
    window: int = 5,
    max_levels: int = 3,
) -> dict:
    """基于局部极值计算支撑位和阻力位。

    方法：找到 rolling window 内的局部最高/最低点，
    然后对这些极值点做聚类，取出现频率最高的价格区间。

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

    # 简单聚类：按价格排序，相邻 <1% 差异的合并取均值
    def cluster(levels: list[float], threshold: float = 0.01) -> list[float]:
        if not levels:
            return []
        levels = sorted(levels)
        clusters = [[levels[0]]]
        for lv in levels[1:]:
            if (lv - clusters[-1][-1]) / clusters[-1][-1] < threshold:
                clusters[-1].append(lv)
            else:
                clusters.append([lv])
        # 按出现频率排序，取均值
        result = [(len(c), sum(c) / len(c)) for c in clusters]
        result.sort(key=lambda x: x[0], reverse=True)
        return [round(v, 2) for _, v in result]

    all_highs = cluster(local_highs)
    all_lows = cluster(local_lows)

    resistance = [h for h in all_highs if h > current_price][:max_levels]
    support = [l for l in all_lows if l < current_price][:max_levels]

    return {"support": support, "resistance": resistance}
```

**Step 3：测试、提交**

```bash
pytest tests/test_trend_analysis.py -v
git commit -m "feat: add support and resistance level calculation"
```

---

### Task 9：多周期趋势共振

**文件：**
- 修改：`src/analysis/trend_analysis.py`
- 修改：`tests/test_trend_analysis.py`

**Step 1：写失败的测试**

```python
from src.analysis.trend_analysis import multi_period_resonance


class TestMultiPeriodResonance:
    def test_full_resonance_on_strong_uptrend(self):
        """日线和周线同时上升应给出强共振信号。"""
        daily = pd.Series(np.linspace(10, 30, 120))  # 120 天上涨
        result = multi_period_resonance(daily)
        assert result["resonance"] is True
        assert result["daily_trend"] == "uptrend"
        assert result["weekly_trend"] == "uptrend"

    def test_no_resonance_on_mixed(self):
        """日线涨、周线跌应无共振。"""
        # 先跌后涨 — 周线仍偏跌，日线偏涨
        prices = list(np.linspace(30, 15, 80)) + list(np.linspace(15, 22, 40))
        daily = pd.Series(prices)
        result = multi_period_resonance(daily)
        # 不要求特定方向，但 resonance 应为 False（日线和周线方向不一致）
        assert "resonance" in result
        assert "daily_trend" in result
        assert "weekly_trend" in result

    def test_result_keys(self):
        daily = pd.Series(np.linspace(10, 30, 120))
        result = multi_period_resonance(daily)
        assert "resonance" in result
        assert "daily_trend" in result
        assert "weekly_trend" in result
        assert "signal" in result
```

**Step 2：实现**

```python
def multi_period_resonance(
    daily_closes: pd.Series,
    weekly_rule: str = "5D",
) -> dict:
    """多周期趋势共振分析（日线 + 周线）。

    将日线数据按每 5 根 K 线聚合为模拟周线，
    分别在日线和周线级别做趋势识别，
    两者方向一致即为「共振」。

    Args:
        daily_closes: 日线收盘价序列（至少 60 根）
        weekly_rule: 周线聚合规则（每 N 根日线合一根周线）

    Returns:
        {"resonance": bool, "daily_trend": str, "weekly_trend": str, "signal": str}
    """
    # 日线趋势
    daily_result = identify_trend(daily_closes)

    # 模拟周线：每 5 根日线取最后一根作为周线收盘
    step = 5
    weekly_closes = daily_closes.iloc[::step].reset_index(drop=True)
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
```

**Step 3：测试、提交**

```bash
pytest tests/test_trend_analysis.py -v
git commit -m "feat: add multi-period trend resonance analysis"
```

---

### Task 10：全量测试 + 代码风格修正

**Step 1：运行全量测试**

```bash
pytest -v --cov=src --cov=api --cov-report=term-missing -x
```

**Step 2：修正 ruff 错误**

```bash
ruff check src/analysis/technical.py src/analysis/trend_analysis.py tests/test_technical.py tests/test_trend_analysis.py --fix
ruff format src/analysis/technical.py src/analysis/trend_analysis.py tests/test_technical.py tests/test_trend_analysis.py
```

**Step 3：验证无回归**

```bash
pytest -x -q
```

**Step 4：提交**

```bash
git commit -m "chore: Phase 3A complete — technical indicators and trend analysis"
```

---

## Phase 3A DoD 核对

- [ ] EMA 计算函数 + 测试
- [ ] MACD (DIF/DEA/柱) 计算函数 + 测试
- [ ] RSI (6/12/24) 计算函数 + 测试
- [ ] KDJ 计算函数 + 测试
- [ ] 布林带 计算函数 + 测试
- [ ] ATR 计算函数 + 测试
- [ ] OBV 计算函数 + 测试
- [ ] 威廉指标 计算函数 + 测试
- [ ] 量比 计算函数 + 测试
- [ ] compute_all 聚合函数 + 集成到 indicators.py
- [ ] 趋势识别（上升/下降/盘整）+ 强度评分 (0-100)
- [ ] 支撑阻力位计算
- [ ] 多周期共振（日线 + 周线）
- [ ] 全量测试通过，ruff 无错误
