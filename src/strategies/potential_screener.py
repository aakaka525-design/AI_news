#!/usr/bin/env python3
"""
多因子潜力股筛选系统

评分体系 (总分100):
  - 资金面 30分: 主力资金净流入(15) + 融资余额增长(10) + 北向资金加持(5)
  - 交易面 25分: 龙虎榜净买入(10) + 机构席位净买入(10) + 量价配合度(5)
  - 基本面 20分: ROE质量(8) + 估值合理(7) + 盈利增长(5)
  - 技术面 25分: 趋势强度(10) + 短期动量(10) + 波动可控(5)

用法:
  python -m src.strategies.potential_screener
  python -m src.strategies.potential_screener --top 30
  python -m src.strategies.potential_screener --detail
"""
import argparse
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.database.connection import get_connection, STOCKS_DB_PATH


def log(msg: str):
    ts = datetime.now().strftime("%H:%M:%S")
    print(f"[{ts}] {msg}", flush=True)


def percentile_score(series: pd.Series, max_score: float) -> pd.Series:
    """将 Series 按百分位映射到 [0, max_score] 分数。"""
    ranks = series.rank(pct=True, na_option="bottom")
    return (ranks * max_score).round(2)


def get_latest_trade_date(conn: sqlite3.Connection) -> str:
    """获取 ts_daily 中的最新交易日 (YYYYMMDD)。"""
    row = conn.execute("SELECT MAX(trade_date) FROM ts_daily").fetchone()
    return row[0]


def get_candidate_pool(conn: sqlite3.Connection, latest_date: str) -> pd.DataFrame:
    """
    构建候选股票池。
    过滤: 非ST, 日均成交额>=5000万, 上市>=60天。
    """
    # 60 trading days roughly = 60 calendar days before latest_date
    cutoff_list_date = str(int(latest_date) - 1000)  # ~3 months buffer

    query = """
        SELECT b.ts_code, b.name, b.industry, b.list_date
        FROM ts_stock_basic b
        WHERE b.name NOT LIKE '%ST%'
          AND b.name NOT LIKE '%退%'
          AND b.list_date IS NOT NULL
          AND b.list_date <= ?
          AND (b.list_status = 'L' OR b.list_status IS NULL)
    """
    pool = pd.read_sql_query(query, conn, params=[cutoff_list_date])
    log(f"基础过滤后: {len(pool)} 只股票")

    # 过滤流动性: 近20日日均成交额 >= 5000万 (amount单位: 千元, 5000万=50000千元)
    liq_query = """
        SELECT ts_code, AVG(amount) as avg_amount
        FROM ts_daily
        WHERE trade_date > (
            SELECT trade_date FROM (
                SELECT DISTINCT trade_date FROM ts_daily
                ORDER BY trade_date DESC LIMIT 20
            ) ORDER BY trade_date ASC LIMIT 1
        )
        GROUP BY ts_code
        HAVING avg_amount >= 50000
    """
    liq = pd.read_sql_query(liq_query, conn)
    pool = pool[pool["ts_code"].isin(liq["ts_code"])]
    log(f"流动性过滤后: {len(pool)} 只股票")

    return pool[["ts_code", "name", "industry"]].reset_index(drop=True)


# ── 因子1: 资金面 (30分) ──────────────────────────────────────────

def score_capital_flow(conn: sqlite3.Connection, candidates: pd.Series) -> pd.DataFrame:
    """资金面评分: 主力资金(15) + 融资余额增长(10) + 北向(5)"""
    log("计算资金面因子...")
    scores = pd.DataFrame({"ts_code": candidates})

    # ── 1a. 主力资金净流入 (15分): 近5日大单+超大单净额
    mf_query = """
        SELECT ts_code,
               SUM(buy_lg_amount + buy_elg_amount - sell_lg_amount - sell_elg_amount) as net_main
        FROM ts_moneyflow
        WHERE trade_date IN (
            SELECT DISTINCT trade_date FROM ts_moneyflow
            ORDER BY trade_date DESC LIMIT 5
        )
        GROUP BY ts_code
    """
    mf = pd.read_sql_query(mf_query, conn)
    scores = scores.merge(mf, on="ts_code", how="left")
    scores["capital_main"] = percentile_score(scores["net_main"], 15)

    # ── 1b. 融资余额增长 (10分): 最新 vs 20日前
    margin_query = """
        WITH latest AS (
            SELECT stock_code, margin_balance
            FROM margin_trading
            WHERE date = (SELECT MAX(date) FROM margin_trading)
        ),
        past AS (
            SELECT stock_code, margin_balance
            FROM margin_trading
            WHERE date = (
                SELECT date FROM (
                    SELECT DISTINCT date FROM margin_trading
                    ORDER BY date DESC LIMIT 20
                ) ORDER BY date ASC LIMIT 1
            )
        )
        SELECT l.stock_code,
               CASE WHEN p.margin_balance > 0
                    THEN (l.margin_balance - p.margin_balance) / p.margin_balance
                    ELSE 0 END as margin_growth
        FROM latest l
        LEFT JOIN past p ON l.stock_code = p.stock_code
    """
    mg = pd.read_sql_query(margin_query, conn)
    # margin_trading uses 6-digit stock_code, convert to ts_code for join
    mg["ts_code_prefix"] = mg["stock_code"]
    scores["ts_code_prefix"] = scores["ts_code"].str[:6]
    scores = scores.merge(mg[["ts_code_prefix", "margin_growth"]], on="ts_code_prefix", how="left")
    scores["capital_margin"] = percentile_score(scores["margin_growth"], 10)
    # Non-margin-eligible stocks (not found in margin_trading) get NaN, not 0
    scores.loc[scores["margin_growth"].isna(), "capital_margin"] = np.nan

    # ── 1c. 北向资金加持 (5分): 近20日出现次数 × 净买入额加权
    hsgt_query = """
        SELECT ts_code,
               COUNT(*) as appear_count,
               SUM(net_amount) as total_net
        FROM ts_hsgt_top10
        WHERE trade_date IN (
            SELECT DISTINCT trade_date FROM ts_hsgt_top10
            ORDER BY trade_date DESC LIMIT 20
        )
        GROUP BY ts_code
    """
    hsgt = pd.read_sql_query(hsgt_query, conn)
    scores = scores.merge(hsgt[["ts_code", "appear_count", "total_net"]], on="ts_code", how="left")
    # 出现即得分, 加权: appear_count * total_net
    hsgt_weight = scores["appear_count"].fillna(0) * scores["total_net"].fillna(0).clip(lower=0)
    scores["capital_north"] = np.where(hsgt_weight > 0, percentile_score(hsgt_weight, 5), 0)

    scores["score_capital"] = (
        scores["capital_main"].fillna(0)
        + scores["capital_margin"].fillna(0)
        + scores["capital_north"].fillna(0)
    ).round(2)

    cols_drop = ["net_main", "margin_growth", "ts_code_prefix", "appear_count", "total_net"]
    scores.drop(columns=[c for c in cols_drop if c in scores.columns], inplace=True)
    return scores


# ── 因子2: 交易面 (25分) ──────────────────────────────────────────

def score_trading_activity(conn: sqlite3.Connection, candidates: pd.Series) -> pd.DataFrame:
    """交易面评分: 龙虎榜(10) + 机构席位(10) + 量价配合(5)"""
    log("计算交易面因子...")
    scores = pd.DataFrame({"ts_code": candidates})

    # ── 2a. 龙虎榜净买入 (10分)
    top_query = """
        SELECT ts_code, SUM(net_amount) as top_net
        FROM ts_top_list
        WHERE trade_date IN (
            SELECT DISTINCT trade_date FROM ts_top_list
            ORDER BY trade_date DESC LIMIT 20
        )
        GROUP BY ts_code
    """
    top_df = pd.read_sql_query(top_query, conn)
    scores = scores.merge(top_df, on="ts_code", how="left")
    # 正值按百分位打分，负值0分
    positive_net = scores["top_net"].clip(lower=0)
    scores["trade_toplist"] = np.where(
        positive_net > 0, percentile_score(positive_net, 10), 0
    )

    # ── 2b. 机构席位净买入 (10分)
    inst_query = """
        SELECT ts_code,
               SUM(CASE WHEN side = '买入' THEN buy ELSE 0 END)
             - SUM(CASE WHEN side = '卖出' THEN sell ELSE 0 END) as inst_net
        FROM ts_top_inst
        WHERE trade_date IN (
            SELECT DISTINCT trade_date FROM ts_top_inst
            ORDER BY trade_date DESC LIMIT 20
        )
        GROUP BY ts_code
    """
    inst = pd.read_sql_query(inst_query, conn)
    scores = scores.merge(inst, on="ts_code", how="left")
    positive_inst = scores["inst_net"].clip(lower=0)
    scores["trade_inst"] = np.where(
        positive_inst > 0, percentile_score(positive_inst, 10), 0
    )

    # ── 2c. 量价配合度 (5分): 近5日量>20日均量 且 收盘>5日前
    vp_query = """
        WITH recent AS (
            SELECT ts_code, trade_date, close, vol,
                   ROW_NUMBER() OVER (PARTITION BY ts_code ORDER BY trade_date DESC) as rn
            FROM ts_daily
            WHERE trade_date IN (
                SELECT DISTINCT trade_date FROM ts_daily
                ORDER BY trade_date DESC LIMIT 25
            )
        ),
        stats AS (
            SELECT ts_code,
                   AVG(CASE WHEN rn <= 5 THEN vol END) as avg_vol_5,
                   AVG(CASE WHEN rn <= 20 THEN vol END) as avg_vol_20,
                   MAX(CASE WHEN rn = 1 THEN close END) as close_now,
                   MAX(CASE WHEN rn = 5 THEN close END) as close_5ago
            FROM recent
            GROUP BY ts_code
        )
        SELECT ts_code,
               CASE WHEN avg_vol_5 > avg_vol_20 AND close_now > close_5ago THEN 1 ELSE 0 END as vp_ok
        FROM stats
    """
    vp = pd.read_sql_query(vp_query, conn)
    scores = scores.merge(vp, on="ts_code", how="left")
    scores["trade_vp"] = (scores["vp_ok"].fillna(0) * 5).astype(float)

    scores["score_trading"] = (
        scores["trade_toplist"].fillna(0)
        + scores["trade_inst"].fillna(0)
        + scores["trade_vp"].fillna(0)
    ).round(2)

    cols_drop = ["top_net", "inst_net", "vp_ok"]
    scores.drop(columns=[c for c in cols_drop if c in scores.columns], inplace=True)
    return scores


# ── 因子3: 基本面 (20分) ──────────────────────────────────────────

def score_fundamentals(conn: sqlite3.Connection, candidates: pd.Series) -> pd.DataFrame:
    """基本面评分: ROE(8) + PE_TTM(7) + 盈利增长(5)

    改进:
    - PE 相对行业中位数评分 (industry_valuation 表可用时)
    - NULL PE 处理: fund_pe=NaN, 权重重分配给 ROE(+3) 和 growth(+4)
    - 输出 data_completeness 字段: "full" 或 "pe_missing"
    """
    log("计算基本面因子...")
    scores = pd.DataFrame({"ts_code": candidates})

    # ── 3a+3c. ROE 和 盈利增长 from ts_fina_indicator (取最新报告期)
    fina_query = """
        SELECT ts_code, roe, netprofit_yoy
        FROM ts_fina_indicator f1
        WHERE end_date = (
            SELECT MAX(end_date) FROM ts_fina_indicator f2
            WHERE f2.ts_code = f1.ts_code
        )
    """
    fina = pd.read_sql_query(fina_query, conn)
    # 去重 (同一 end_date 可能有多条记录)
    fina = fina.drop_duplicates(subset="ts_code", keep="first")
    scores = scores.merge(fina, on="ts_code", how="left")

    # ── 数据新鲜度: 计算财报滞后季度数
    ref_date_row = conn.execute("SELECT MAX(trade_date) FROM ts_daily_basic").fetchone()
    ref_date = ref_date_row[0] if ref_date_row else datetime.now().strftime("%Y%m%d")

    fina_freshness_query = """
        SELECT ts_code, MAX(end_date) as latest_end_date
        FROM ts_fina_indicator
        GROUP BY ts_code
    """
    freshness = pd.read_sql_query(fina_freshness_query, conn)
    scores = scores.merge(freshness, on="ts_code", how="left")

    def calc_lag_quarters(row):
        if pd.isna(row.get("latest_end_date")):
            return 4
        try:
            ref = datetime.strptime(str(ref_date)[:8], "%Y%m%d")
            end = datetime.strptime(str(row["latest_end_date"])[:8], "%Y%m%d")
            return max(0, int((ref - end).days / 90))
        except (ValueError, TypeError):
            return 4
    scores["financial_lag_quarters"] = scores.apply(calc_lag_quarters, axis=1)

    # ROE评分 (base): >15%=8, >10%=5, >5%=2, else 0
    scores["fund_roe"] = np.select(
        [scores["roe"] > 15, scores["roe"] > 10, scores["roe"] > 5],
        [8.0, 5.0, 2.0],
        default=0.0,
    )

    # 盈利增长 (base): >30%=5, >10%=3, >0%=1, else 0
    scores["fund_growth"] = np.select(
        [scores["netprofit_yoy"] > 30, scores["netprofit_yoy"] > 10, scores["netprofit_yoy"] > 0],
        [5.0, 3.0, 1.0],
        default=0.0,
    )

    # ── 3b. 估值 PE_TTM from ts_daily_basic (取最新日期)
    pe_query = """
        SELECT ts_code, pe_ttm
        FROM ts_daily_basic
        WHERE trade_date = (SELECT MAX(trade_date) FROM ts_daily_basic)
    """
    pe = pd.read_sql_query(pe_query, conn)
    scores = scores.merge(pe, on="ts_code", how="left")

    # 标记 PE 缺失: pe_ttm 为 NaN 的行
    pe_missing = scores["pe_ttm"].isna()
    scores["data_completeness"] = np.where(pe_missing, "pe_missing", "full")

    # ── 尝试加载行业估值数据 (industry_valuation 表可能不存在)
    industry_val = None
    try:
        # 获取每只股票的行业
        basic_query = "SELECT ts_code, industry FROM ts_stock_basic"
        basic = pd.read_sql_query(basic_query, conn)
        scores = scores.merge(basic, on="ts_code", how="left")

        # 获取最新日期的行业估值中位数
        iv_query = """
            SELECT industry, pe_median, pe_p25, pe_p75
            FROM industry_valuation
            WHERE trade_date = (SELECT MAX(trade_date) FROM industry_valuation)
        """
        industry_val = pd.read_sql_query(iv_query, conn)
        if industry_val.empty:
            industry_val = None
    except Exception:
        # industry_valuation 表不存在或查询失败, 使用绝对值 fallback
        industry_val = None

    # ── PE 评分
    if industry_val is not None and not industry_val.empty:
        # 行业相对估值模式: 合并行业中位数
        scores = scores.merge(industry_val, on="industry", how="left")

        # PE <= p25 → 7pts (明显低估)
        # PE <= median → 5pts
        # PE <= p75 → 3pts
        # PE > p75 → 1pt
        has_pe = ~pe_missing
        scores["fund_pe"] = np.where(
            has_pe,
            np.select(
                [
                    has_pe & (scores["pe_ttm"] <= scores["pe_p25"]),
                    has_pe & (scores["pe_ttm"] <= scores["pe_median"]),
                    has_pe & (scores["pe_ttm"] <= scores["pe_p75"]),
                ],
                [7.0, 5.0, 3.0],
                default=1.0,
            ),
            np.nan,
        )
        # 清理合并的行业估值列
        cols_iv = ["industry", "pe_median", "pe_p25", "pe_p75"]
        scores.drop(columns=[c for c in cols_iv if c in scores.columns], inplace=True)
    else:
        # Fallback: 绝对 PE 范围评分 (无行业估值数据时)
        has_pe = ~pe_missing
        scores["fund_pe"] = np.where(
            has_pe,
            np.select(
                [
                    has_pe & (scores["pe_ttm"] >= 10) & (scores["pe_ttm"] <= 30),
                    has_pe & (scores["pe_ttm"] > 30) & (scores["pe_ttm"] <= 50),
                    has_pe & (scores["pe_ttm"] >= 5) & (scores["pe_ttm"] < 10),
                ],
                [7.0, 4.0, 3.0],
                default=0.0,
            ),
            np.nan,
        )
        # 清理可能存在的 industry 列
        if "industry" in scores.columns:
            scores.drop(columns=["industry"], inplace=True)

    # ── PE 缺失时: 重分配 7 分 PE 权重 → ROE(+3) + growth(+4)
    scores.loc[pe_missing, "fund_roe"] = scores.loc[pe_missing, "fund_roe"] + 3.0
    scores.loc[pe_missing, "fund_growth"] = scores.loc[pe_missing, "fund_growth"] + 4.0

    # ── 综合评分: pe_missing 时 fund_pe 为 NaN, 用 fillna(0) 计算总分
    scores["score_fundamental"] = (
        scores["fund_roe"] + scores["fund_pe"].fillna(0) + scores["fund_growth"]
    ).round(2)

    # 滞后加权: 滞后 >= 3 个季度，基本面总分减半
    stale = scores["financial_lag_quarters"] >= 3
    scores.loc[stale, "score_fundamental"] = (scores.loc[stale, "score_fundamental"] * 0.5).round(2)

    cols_drop = ["roe", "netprofit_yoy", "pe_ttm", "latest_end_date"]
    scores.drop(columns=[c for c in cols_drop if c in scores.columns], inplace=True)
    return scores


# ── 因子4: 技术面 (25分) ──────────────────────────────────────────

def score_technicals(conn: sqlite3.Connection, candidates: pd.Series) -> pd.DataFrame:
    """技术面评分: 趋势(10) + 动量(10) + 波动(5)"""
    log("计算技术面因子...")
    scores = pd.DataFrame({"ts_code": candidates})

    # 取近25个交易日数据计算 MA
    tech_query = """
        SELECT ts_code, trade_date, close, high, low, vol,
               ROW_NUMBER() OVER (PARTITION BY ts_code ORDER BY trade_date DESC) as rn
        FROM ts_daily
        WHERE trade_date IN (
            SELECT DISTINCT trade_date FROM ts_daily
            ORDER BY trade_date DESC LIMIT 25
        )
    """
    daily = pd.read_sql_query(tech_query, conn)

    # MA5, MA20
    ma5 = daily[daily["rn"] <= 5].groupby("ts_code")["close"].mean().rename("ma5")
    ma20 = daily[daily["rn"] <= 20].groupby("ts_code")["close"].mean().rename("ma20")
    latest_close = daily[daily["rn"] == 1].set_index("ts_code")["close"].rename("latest_close")

    ma_df = pd.concat([latest_close, ma5, ma20], axis=1).reset_index()
    scores = scores.merge(ma_df, on="ts_code", how="left")

    # ── 4a. 趋势强度 (10分): close>MA20且MA5>MA20=10, 仅close>MA20=6, else 0
    scores["tech_trend"] = np.select(
        [
            (scores["latest_close"] > scores["ma20"]) & (scores["ma5"] > scores["ma20"]),
            scores["latest_close"] > scores["ma20"],
        ],
        [10.0, 6.0],
        default=0.0,
    )

    # ── 4b. 短期动量 (10分): 近5日涨幅按百分位, >20%扣分
    close_5ago = daily[daily["rn"] == 5].set_index("ts_code")["close"].rename("close_5ago")
    scores = scores.merge(close_5ago.reset_index(), on="ts_code", how="left")
    scores["ret_5d"] = (scores["latest_close"] / scores["close_5ago"] - 1) * 100

    base_momentum = percentile_score(scores["ret_5d"], 10)
    # 涨幅>20%扣分 (追高风险)
    scores["tech_momentum"] = np.where(scores["ret_5d"] > 20, base_momentum * 0.5, base_momentum)
    scores["tech_momentum"] = scores["tech_momentum"].round(2)

    # ── 4c. 波动可控 (5分): 近20日振幅标准差，中段得分高
    daily["amplitude"] = (daily["high"] - daily["low"]) / daily["low"] * 100
    amp_std = daily[daily["rn"] <= 20].groupby("ts_code")["amplitude"].std().rename("amp_std")
    scores = scores.merge(amp_std.reset_index(), on="ts_code", how="left")

    # 中段波动最佳: 取百分位, 但距中位数越近得分越高
    amp_rank = scores["amp_std"].rank(pct=True, na_option="bottom")
    # 距0.5越近越好: score = 5 * (1 - 2*|rank - 0.5|)
    scores["tech_vol"] = (5 * (1 - 2 * (amp_rank - 0.5).abs())).clip(lower=0).round(2)

    scores["score_technical"] = (
        scores["tech_trend"].fillna(0)
        + scores["tech_momentum"].fillna(0)
        + scores["tech_vol"].fillna(0)
    ).round(2)

    cols_drop = ["ma5", "ma20", "latest_close", "close_5ago", "ret_5d", "amp_std"]
    scores.drop(columns=[c for c in cols_drop if c in scores.columns], inplace=True)
    return scores


# ── 主流程 ────────────────────────────────────────────────────────

def run_screening(top_n: int = 20, detail: bool = False) -> pd.DataFrame:
    """执行多因子筛选, 返回 Top N 潜力股。"""
    conn = get_connection()
    latest_date = get_latest_trade_date(conn)
    log(f"最新交易日: {latest_date}")
    log(f"数据库: {STOCKS_DB_PATH}")

    # 1. 候选池
    pool = get_candidate_pool(conn, latest_date)
    candidates = pool["ts_code"]

    # 2. 计算各因子
    capital = score_capital_flow(conn, candidates)
    trading = score_trading_activity(conn, candidates)
    fundamental = score_fundamentals(conn, candidates)
    technical = score_technicals(conn, candidates)

    # 3. 合并
    result = pool.copy()
    for df in [capital, trading, fundamental, technical]:
        cols = [c for c in df.columns if c != "ts_code"]
        result = result.merge(df[["ts_code"] + cols], on="ts_code", how="left")

    # 4. 综合评分
    score_cols = ["score_capital", "score_trading", "score_fundamental", "score_technical"]
    for col in score_cols:
        result[col] = result[col].fillna(0)
    result["total_score"] = result[score_cols].sum(axis=1).round(2)

    # 5. 生成关键信号
    result["signals"] = result.apply(_make_signals, axis=1)

    # 6. 排序
    result = result.sort_values("total_score", ascending=False).reset_index(drop=True)

    conn.close()
    return result.head(top_n), result, detail


def _make_signals(row) -> str:
    """根据各子因子分数生成关键信号标签。"""
    signals = []
    if row.get("capital_main", 0) >= 12:
        signals.append("主力流入")
    if row.get("capital_north", 0) >= 3:
        signals.append("北向加持")
    if row.get("trade_toplist", 0) >= 8:
        signals.append("龙虎榜")
    if row.get("trade_inst", 0) >= 8:
        signals.append("机构买入")
    if row.get("fund_roe", 0) >= 8:
        signals.append("高ROE")
    if row.get("fund_pe", 0) >= 7:
        signals.append("估值合理")
    if row.get("tech_trend", 0) >= 10:
        signals.append("趋势向上")
    if row.get("trade_vp", 0) >= 5:
        signals.append("量价齐升")
    return ", ".join(signals) if signals else "-"


def print_results(top_df: pd.DataFrame, full_df: pd.DataFrame, detail: bool):
    """打印筛选结果。"""
    print("\n" + "=" * 90)
    print(f"  多因子潜力股 Top {len(top_df)}    (总分 = 资金30 + 交易25 + 基本面20 + 技术25)")
    print("=" * 90)

    header = f"  {'排名':<4} {'代码':<12} {'名称':<10} {'行业':<10} {'总分':<7} {'资金':<6} {'交易':<6} {'基面':<6} {'技术':<6} {'关键信号'}"
    print(header)
    print("  " + "-" * 86)

    for i, row in top_df.iterrows():
        rank = i + 1
        line = (
            f"  {rank:<4} {row['ts_code']:<12} {row['name']:<10} "
            f"{str(row.get('industry', '-')):<10} "
            f"{row['total_score']:<7.1f} "
            f"{row['score_capital']:<6.1f} {row['score_trading']:<6.1f} "
            f"{row['score_fundamental']:<6.1f} {row['score_technical']:<6.1f} "
            f"{row['signals']}"
        )
        print(line)

    if detail:
        print("\n" + "=" * 90)
        print("  因子明细")
        print("=" * 90)
        detail_cols = [
            ("capital_main", "主力资金", 15),
            ("capital_margin", "融资增长", 10),
            ("capital_north", "北向资金", 5),
            ("trade_toplist", "龙虎榜", 10),
            ("trade_inst", "机构席位", 10),
            ("trade_vp", "量价配合", 5),
            ("fund_roe", "ROE", 8),
            ("fund_pe", "估值PE", 7),
            ("fund_growth", "盈利增长", 5),
            ("tech_trend", "趋势", 10),
            ("tech_momentum", "动量", 10),
            ("tech_vol", "波动", 5),
        ]
        for _, row in top_df.iterrows():
            print(f"\n  {row['ts_code']} {row['name']}  总分: {row['total_score']:.1f}")
            parts = []
            for col, label, max_s in detail_cols:
                val = row.get(col, 0) or 0
                parts.append(f"{label}:{val:.1f}/{max_s}")
            # 每行4个
            for j in range(0, len(parts), 4):
                print("    " + "  ".join(parts[j : j + 4]))

    # 分数分布
    print("\n" + "-" * 60)
    print("  分数分布:")
    for label, col in [("总分", "total_score"), ("资金面", "score_capital"),
                       ("交易面", "score_trading"), ("基本面", "score_fundamental"),
                       ("技术面", "score_technical")]:
        s = full_df[col]
        print(f"    {label:<8} 均值={s.mean():.1f}  中位={s.median():.1f}  "
              f"最高={s.max():.1f}  P90={s.quantile(0.9):.1f}")
    print(f"  候选池: {len(full_df)} 只股票")

    # 数据质量摘要
    print("\n  数据质量:")
    if "data_completeness" in full_df.columns:
        pe_missing = (full_df["data_completeness"] == "pe_missing").sum()
        print(f"    PE缺失: {pe_missing}/{len(full_df)} ({pe_missing/len(full_df)*100:.1f}%)")
    if "financial_lag_quarters" in full_df.columns:
        stale = (full_df["financial_lag_quarters"] >= 3).sum()
        print(f"    财报滞后≥3季: {stale}/{len(full_df)} ({stale/len(full_df)*100:.1f}%)")
    if "capital_margin" in full_df.columns:
        margin_na = full_df["capital_margin"].isna().sum()
        print(f"    非两融标的: {margin_na}/{len(full_df)} ({margin_na/len(full_df)*100:.1f}%)")


def main():
    parser = argparse.ArgumentParser(description="多因子潜力股筛选系统")
    parser.add_argument("--top", type=int, default=20, help="输出Top N (默认20)")
    parser.add_argument("--detail", action="store_true", help="显示每只股票的因子明细")
    args = parser.parse_args()

    print("=" * 60)
    print("  多因子潜力股筛选系统")
    print(f"  运行时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)

    top_df, full_df, _ = run_screening(top_n=args.top, detail=args.detail)
    print_results(top_df, full_df, args.detail)

    print("\n" + "=" * 60)
    print("  筛选完成!")
    print("=" * 60)


if __name__ == "__main__":
    main()
