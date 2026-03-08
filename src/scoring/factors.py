"""6 个因子计算器

每个因子返回 FactorResult，包含 raw_value / normalized_value / 数据来源等信息。

因子列表:
    price_trend bucket:
        - rps_composite: RPS 相对强度百分位
        - tech_confirm:  技术确认信号 (MA20 + MACD)
    flow bucket:
        - northbound_flow: 北向资金持股变化
        - main_money_flow: 主力资金净流入
    fundamentals bucket:
        - valuation: 行业 PE 百分位
        - roe_quality: ROE 质量分档
"""

import logging
import sqlite3
from dataclasses import dataclass

import pandas as pd

logger = logging.getLogger(__name__)


@dataclass
class FactorResult:
    factor_key: str
    bucket: str
    available: bool
    raw_value: float | None
    normalized_value: float | None  # 0-1
    source_key: str
    source_table: str
    data_date: str | None  # YYYYMMDD
    freshness_class: str


# ============================================================
# 3a. rps_composite (bucket: price_trend)
# ============================================================

def compute_rps_composite(ts_code: str, trade_date: str, conn: sqlite3.Connection) -> FactorResult:
    """查询 stock_rps 表最新 rps_20，归一化 = rps_20 / 100。"""
    row = conn.execute(
        "SELECT rps_20, trade_date FROM stock_rps WHERE ts_code = ? AND trade_date <= ? ORDER BY trade_date DESC LIMIT 1",
        (ts_code, trade_date),
    ).fetchone()

    if not row or row["rps_20"] is None:
        return FactorResult(
            factor_key="rps_composite", bucket="price_trend", available=False,
            raw_value=None, normalized_value=None,
            source_key="tushare", source_table="stock_rps",
            data_date=None, freshness_class="daily_market",
        )

    rps_20 = float(row["rps_20"])
    return FactorResult(
        factor_key="rps_composite", bucket="price_trend", available=True,
        raw_value=rps_20, normalized_value=rps_20 / 100.0,
        source_key="tushare", source_table="stock_rps",
        data_date=row["trade_date"], freshness_class="daily_market",
    )


# ============================================================
# 3b. tech_confirm (bucket: price_trend)
# ============================================================

def compute_tech_confirm(ts_code: str, trade_date: str, conn: sqlite3.Connection) -> FactorResult:
    """MA20 + MACD 技术确认信号。"""
    rows = conn.execute(
        "SELECT close, trade_date FROM ts_daily WHERE ts_code = ? AND trade_date <= ? ORDER BY trade_date DESC LIMIT 60",
        (ts_code, trade_date),
    ).fetchall()

    if len(rows) < 26:  # MACD slow=26 最低要求
        return FactorResult(
            factor_key="tech_confirm", bucket="price_trend", available=False,
            raw_value=None, normalized_value=None,
            source_key="tushare", source_table="ts_daily",
            data_date=None, freshness_class="daily_market",
        )

    # 按时间正序排列
    rows = list(reversed(rows))
    closes = pd.Series([float(r["close"]) for r in rows])
    data_date = rows[-1]["trade_date"]

    # MA20
    ma20 = closes.rolling(20).mean()
    latest_close = closes.iloc[-1]
    latest_ma20 = ma20.iloc[-1]
    above_ma20 = 1.0 if pd.notna(latest_ma20) and latest_close > latest_ma20 else 0.0

    # MACD
    from src.analysis.technical import macd
    _, _, hist = macd(closes)
    hist_vals = hist.dropna()
    if len(hist_vals) >= 2:
        macd_positive = 1.0 if hist_vals.iloc[-1] > 0 or hist_vals.iloc[-1] > hist_vals.iloc[-2] else 0.0
    elif len(hist_vals) == 1:
        macd_positive = 1.0 if hist_vals.iloc[-1] > 0 else 0.0
    else:
        macd_positive = 0.0

    normalized = above_ma20 * 0.6 + macd_positive * 0.4
    raw = normalized  # 信号本身就是 0-1

    return FactorResult(
        factor_key="tech_confirm", bucket="price_trend", available=True,
        raw_value=raw, normalized_value=normalized,
        source_key="tushare", source_table="ts_daily",
        data_date=data_date, freshness_class="daily_market",
    )


# ============================================================
# 3c. northbound_flow (bucket: flow) — 需全市场百分位归一化
# ============================================================

def compute_northbound_flow_raw(ts_code: str, trade_date: str, conn: sqlite3.Connection) -> FactorResult:
    """计算北向资金 20 日持股变化率 raw_value，normalized 由引擎统一做百分位。"""
    rows = conn.execute(
        "SELECT vol, trade_date FROM ts_hk_hold WHERE ts_code = ? AND trade_date <= ? ORDER BY trade_date DESC LIMIT 20",
        (ts_code, trade_date),
    ).fetchall()

    if len(rows) < 2:
        return FactorResult(
            factor_key="northbound_flow", bucket="flow", available=False,
            raw_value=None, normalized_value=None,
            source_key="tushare", source_table="ts_hk_hold",
            data_date=None, freshness_class="daily_market",
        )

    latest_vol = float(rows[0]["vol"])
    oldest_vol = float(rows[-1]["vol"])
    data_date = rows[0]["trade_date"]

    if oldest_vol == 0:
        change_rate = 0.0
    else:
        change_rate = (latest_vol - oldest_vol) / oldest_vol

    return FactorResult(
        factor_key="northbound_flow", bucket="flow", available=True,
        raw_value=change_rate, normalized_value=None,  # 引擎做百分位
        source_key="tushare", source_table="ts_hk_hold",
        data_date=data_date, freshness_class="daily_market",
    )


# ============================================================
# 3d. main_money_flow (bucket: flow) — 需全市场百分位归一化
# ============================================================

def compute_main_money_flow_raw(ts_code: str, trade_date: str, conn: sqlite3.Connection) -> FactorResult:
    """计算近 5 日主力净流入 raw_value，normalized 由引擎统一做百分位。"""
    rows = conn.execute(
        "SELECT buy_elg_amount, buy_lg_amount, sell_elg_amount, sell_lg_amount, trade_date "
        "FROM ts_moneyflow WHERE ts_code = ? AND trade_date <= ? ORDER BY trade_date DESC LIMIT 5",
        (ts_code, trade_date),
    ).fetchall()

    if not rows:
        return FactorResult(
            factor_key="main_money_flow", bucket="flow", available=False,
            raw_value=None, normalized_value=None,
            source_key="tushare", source_table="ts_moneyflow",
            data_date=None, freshness_class="daily_market",
        )

    net_inflow = sum(
        float(r["buy_elg_amount"] or 0) + float(r["buy_lg_amount"] or 0)
        - float(r["sell_elg_amount"] or 0) - float(r["sell_lg_amount"] or 0)
        for r in rows
    )
    data_date = rows[0]["trade_date"]

    return FactorResult(
        factor_key="main_money_flow", bucket="flow", available=True,
        raw_value=net_inflow, normalized_value=None,  # 引擎做百分位
        source_key="tushare", source_table="ts_moneyflow",
        data_date=data_date, freshness_class="daily_market",
    )


# ============================================================
# 3e. valuation (bucket: fundamentals) — 行业 PE 百分位
# ============================================================

def compute_valuation(ts_code: str, trade_date: str, conn: sqlite3.Connection) -> FactorResult:
    """查询 PE_TTM，在同行业做百分位归一化。"""
    # 获取该股的 PE_TTM 和行业
    row = conn.execute(
        "SELECT b.pe_ttm, s.industry FROM ts_daily_basic b "
        "JOIN ts_stock_basic s ON b.ts_code = s.ts_code "
        "WHERE b.ts_code = ? AND b.trade_date <= ? ORDER BY b.trade_date DESC LIMIT 1",
        (ts_code, trade_date),
    ).fetchone()

    if not row or row["pe_ttm"] is None or float(row["pe_ttm"]) <= 0:
        return FactorResult(
            factor_key="valuation", bucket="fundamentals", available=False,
            raw_value=None, normalized_value=None,
            source_key="tushare", source_table="ts_daily_basic",
            data_date=None, freshness_class="daily_market",
        )

    pe_ttm = float(row["pe_ttm"])
    industry = row["industry"]

    # 获取同行业所有 PE
    peer_rows = conn.execute(
        "SELECT b.pe_ttm FROM ts_daily_basic b "
        "JOIN ts_stock_basic s ON b.ts_code = s.ts_code "
        "WHERE s.industry = ? AND b.trade_date = ("
        "  SELECT MAX(trade_date) FROM ts_daily_basic WHERE ts_code = ? AND trade_date <= ?"
        ") AND b.pe_ttm > 0",
        (industry, ts_code, trade_date),
    ).fetchall()

    if not peer_rows:
        return FactorResult(
            factor_key="valuation", bucket="fundamentals", available=False,
            raw_value=pe_ttm, normalized_value=None,
            source_key="tushare", source_table="ts_daily_basic",
            data_date=None, freshness_class="daily_market",
        )

    peer_pe = sorted([float(r["pe_ttm"]) for r in peer_rows])
    rank = sum(1 for p in peer_pe if p <= pe_ttm)
    percentile = rank / len(peer_pe)
    normalized = 1.0 - percentile  # PE 越低越好

    # 获取 data_date
    date_row = conn.execute(
        "SELECT MAX(trade_date) as d FROM ts_daily_basic WHERE ts_code = ? AND trade_date <= ?",
        (ts_code, trade_date),
    ).fetchone()
    data_date = date_row["d"] if date_row else None

    return FactorResult(
        factor_key="valuation", bucket="fundamentals", available=True,
        raw_value=pe_ttm, normalized_value=round(normalized, 4),
        source_key="tushare", source_table="ts_daily_basic",
        data_date=data_date, freshness_class="daily_market",
    )


# ============================================================
# 3f. roe_quality (bucket: fundamentals)
# ============================================================

def compute_roe_quality(ts_code: str, trade_date: str, conn: sqlite3.Connection) -> FactorResult:
    """查询最新 ROE，分档归一化。"""
    row = conn.execute(
        "SELECT roe, end_date FROM ts_fina_indicator WHERE ts_code = ? AND end_date <= ? ORDER BY end_date DESC LIMIT 1",
        (ts_code, trade_date),
    ).fetchone()

    if not row or row["roe"] is None:
        return FactorResult(
            factor_key="roe_quality", bucket="fundamentals", available=False,
            raw_value=None, normalized_value=None,
            source_key="tushare", source_table="ts_fina_indicator",
            data_date=None, freshness_class="periodic_fundamental",
        )

    roe = float(row["roe"])
    if roe > 15:
        normalized = 1.0
    elif roe > 10:
        normalized = 0.7
    elif roe > 5:
        normalized = 0.4
    elif roe > 0:
        normalized = 0.2
    else:
        normalized = 0.0

    return FactorResult(
        factor_key="roe_quality", bucket="fundamentals", available=True,
        raw_value=roe, normalized_value=normalized,
        source_key="tushare", source_table="ts_fina_indicator",
        data_date=row["end_date"], freshness_class="periodic_fundamental",
    )


# ============================================================
# 因子计算器注册表
# ============================================================

FACTOR_COMPUTERS = {
    "rps_composite": compute_rps_composite,
    "tech_confirm": compute_tech_confirm,
    "northbound_flow": compute_northbound_flow_raw,
    "main_money_flow": compute_main_money_flow_raw,
    "valuation": compute_valuation,
    "roe_quality": compute_roe_quality,
}
