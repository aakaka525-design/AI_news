"""评分引擎核心

全市场批量计算综合评分，支持 6 因子 / 3 bucket / 权重 0.40-0.30-0.30。
"""

import logging
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime

import pandas as pd

from src.scoring.factors import FACTOR_COMPUTERS, FactorResult
from src.scoring.freshness import FACTOR_FRESHNESS_CLASS, compute_decay
from src.scoring.exclusions import get_exclusions
from src.scoring.models import ensure_scoring_tables

logger = logging.getLogger(__name__)

SCORE_VERSION = "v1"

BUCKET_WEIGHTS = {
    "price_trend": 0.40,
    "flow": 0.30,
    "fundamentals": 0.30,
}

FACTOR_CONFIG = {
    "rps_composite": {"bucket": "price_trend", "weight": 0.20},
    "tech_confirm": {"bucket": "price_trend", "weight": 0.20},
    "northbound_flow": {"bucket": "flow", "weight": 0.15},
    "main_money_flow": {"bucket": "flow", "weight": 0.15},
    "valuation": {"bucket": "fundamentals", "weight": 0.15},
    "roe_quality": {"bucket": "fundamentals", "weight": 0.15},
}

CROSS_SECTION_FACTORS = {"northbound_flow", "main_money_flow"}


@dataclass
class CompositeScoreResult:
    ts_code: str
    trade_date: str
    score: float | None
    status: str  # scored / excluded / error
    exclusion_reason: str | None
    coverage_ratio: float
    low_confidence: bool
    bucket_scores: dict[str, float | None]
    factors: list[FactorResult]


@dataclass
class BatchScoreSummary:
    trade_date: str
    total_stocks: int
    scored: int
    excluded: int
    errors: int
    low_confidence: int
    mean_score: float | None
    duration_seconds: float


def _compute_staleness(data_date: str | None) -> int:
    """计算数据过期的交易日数。"""
    if not data_date:
        return 999
    try:
        from fetchers.trading_calendar import calculate_trading_day_delay
        # convert YYYYMMDD to YYYY-MM-DD if needed
        if len(data_date) == 8 and "-" not in data_date:
            date_str = f"{data_date[:4]}-{data_date[4:6]}-{data_date[6:8]}"
        else:
            date_str = data_date
        return calculate_trading_day_delay(date_str)
    except Exception:
        return 999


def compute_score(
    ts_code: str,
    trade_date: str,
    conn: sqlite3.Connection,
    cross_section_normals: dict[str, dict[str, float]] | None = None,
) -> CompositeScoreResult:
    """计算单只股票的综合评分。

    Args:
        ts_code: 股票代码
        trade_date: 评分日期 YYYYMMDD
        conn: 数据库连接
        cross_section_normals: 全市场百分位归一化结果
            {factor_key: {ts_code: normalized_value}}
    """
    factors: list[FactorResult] = []

    for factor_key, computer in FACTOR_COMPUTERS.items():
        try:
            result = computer(ts_code, trade_date, conn)
            # 注入全市场百分位归一化
            if factor_key in CROSS_SECTION_FACTORS and cross_section_normals:
                normals = cross_section_normals.get(factor_key, {})
                if ts_code in normals:
                    result.normalized_value = normals[ts_code]
                elif result.available:
                    result.available = False
                    result.normalized_value = None
            factors.append(result)
        except Exception as e:
            logger.warning(f"因子 {factor_key} 计算失败 ({ts_code}): {e}")
            factors.append(FactorResult(
                factor_key=factor_key,
                bucket=FACTOR_CONFIG[factor_key]["bucket"],
                available=False, raw_value=None, normalized_value=None,
                source_key="", source_table="",
                data_date=None,
                freshness_class=FACTOR_FRESHNESS_CLASS.get(factor_key, "daily_market"),
            ))

    # 计算每个因子的 staleness 和 effective weight
    factor_weights: list[tuple[FactorResult, float, float, int]] = []  # (result, nominal, effective, staleness)
    for fr in factors:
        nominal = FACTOR_CONFIG[fr.factor_key]["weight"]
        staleness = _compute_staleness(fr.data_date) if fr.available else 999
        decay = compute_decay(fr.freshness_class, staleness) if fr.available else 0.0
        effective = nominal * decay
        factor_weights.append((fr, nominal, effective, staleness))

    # 按 bucket 聚合
    bucket_scores: dict[str, float | None] = {}
    bucket_effective_weights: dict[str, float] = {}
    bucket_coverage: dict[str, float] = {}

    for bucket in BUCKET_WEIGHTS:
        bucket_factors = [(fr, nom, eff, st) for fr, nom, eff, st in factor_weights
                          if fr.bucket == bucket]
        total_effective = sum(eff for _, _, eff, _ in bucket_factors)
        n_available = sum(1 for fr, _, eff, _ in bucket_factors if fr.available and eff > 0)
        n_total = len(bucket_factors)

        bucket_coverage[bucket] = n_available / n_total if n_total > 0 else 0.0
        bucket_effective_weights[bucket] = total_effective

        if total_effective > 0:
            weighted_sum = sum(
                (fr.normalized_value or 0) * eff
                for fr, _, eff, _ in bucket_factors
                if fr.available and fr.normalized_value is not None
            )
            bucket_scores[bucket] = (weighted_sum / total_effective) * 100
        else:
            bucket_scores[bucket] = None

    # 总分
    total_score = 0.0
    total_weight = 0.0
    for bucket, bw in BUCKET_WEIGHTS.items():
        if bucket_scores[bucket] is not None:
            total_score += bucket_scores[bucket] * bw
            total_weight += bw

    final_score = round(total_score / total_weight, 2) if total_weight > 0 else None

    # 覆盖率与低置信
    n_effective = sum(1 for fr, _, eff, _ in factor_weights if fr.available and eff > 0)
    coverage_ratio = round(n_effective / len(FACTOR_CONFIG), 4) if FACTOR_CONFIG else 0.0

    any_bucket_zero = any(
        bucket_coverage.get(b, 0) == 0 for b in BUCKET_WEIGHTS
    )
    low_confidence = coverage_ratio < 0.60 or any_bucket_zero

    # 更新 factor staleness 到 FactorResult（用于存储）
    for fr, nom, eff, st in factor_weights:
        fr._staleness = st
        fr._weight_nominal = nom
        fr._weight_effective = eff

    return CompositeScoreResult(
        ts_code=ts_code,
        trade_date=trade_date,
        score=final_score,
        status="scored",
        exclusion_reason=None,
        coverage_ratio=coverage_ratio,
        low_confidence=low_confidence,
        bucket_scores=bucket_scores,
        factors=factors,
    )


def _collect_cross_section_raw(
    all_codes: list[str], trade_date: str, conn: sqlite3.Connection
) -> dict[str, dict[str, float]]:
    """批量计算需要全市场百分位归一化的因子 raw_value。"""
    raw_values: dict[str, dict[str, float]] = {k: {} for k in CROSS_SECTION_FACTORS}

    for ts_code in all_codes:
        for factor_key in CROSS_SECTION_FACTORS:
            computer = FACTOR_COMPUTERS[factor_key]
            try:
                result = computer(ts_code, trade_date, conn)
                if result.available and result.raw_value is not None:
                    raw_values[factor_key][ts_code] = result.raw_value
            except Exception:
                pass

    return raw_values


def _normalize_cross_section(
    raw_values: dict[str, dict[str, float]]
) -> dict[str, dict[str, float]]:
    """对全市场横截面数据做百分位归一化。"""
    normals: dict[str, dict[str, float]] = {}

    for factor_key, code_values in raw_values.items():
        if not code_values:
            normals[factor_key] = {}
            continue

        s = pd.Series(code_values)
        ranked = s.rank(pct=True)
        normals[factor_key] = {code: round(float(v), 4) for code, v in ranked.items()}

    return normals


def compute_all_scores(trade_date: str) -> BatchScoreSummary:
    """全市场批量计算综合评分。

    Args:
        trade_date: 评分日期 YYYYMMDD

    Returns:
        BatchScoreSummary 统计摘要
    """
    start_time = datetime.now()

    from src.database.connection import get_connection
    conn = get_connection()

    try:
        ensure_scoring_tables(conn)

        # 幂等检查
        existing = conn.execute(
            "SELECT COUNT(*) as cnt FROM stock_composite_score WHERE trade_date = ? AND score_version = ?",
            (trade_date, SCORE_VERSION),
        ).fetchone()
        if existing and existing["cnt"] > 0:
            logger.info(f"评分已存在 ({trade_date}, {SCORE_VERSION})，跳过计算")
            duration = (datetime.now() - start_time).total_seconds()
            return BatchScoreSummary(
                trade_date=trade_date, total_stocks=0, scored=0,
                excluded=0, errors=0, low_confidence=0,
                mean_score=None, duration_seconds=duration,
            )

        # 获取所有股票
        all_stocks = conn.execute(
            "SELECT ts_code FROM ts_stock_basic WHERE (list_status = 'L' OR list_status IS NULL)"
        ).fetchall()
        all_codes = [r["ts_code"] for r in all_stocks]

        # 排除名单
        exclusions = get_exclusions(conn)

        # 可评分股票
        scorable = [c for c in all_codes if c not in exclusions]

        logger.info(f"全市场评分: {len(all_codes)} 总股数, {len(exclusions)} 排除, {len(scorable)} 可评分")

        # 全市场百分位归一化（需要横截面数据的因子）
        logger.info("计算全市场横截面因子...")
        raw_cross = _collect_cross_section_raw(scorable, trade_date, conn)
        cross_normals = _normalize_cross_section(raw_cross)

        # 写入排除股票
        excluded_count = 0
        for ts_code, reason in exclusions.items():
            conn.execute(
                "INSERT OR REPLACE INTO stock_composite_score "
                "(ts_code, trade_date, score, score_version, status, exclusion_reason, experimental) "
                "VALUES (?, ?, NULL, ?, 'excluded', ?, 1)",
                (ts_code, trade_date, SCORE_VERSION, reason),
            )
            excluded_count += 1

        # 批量评分
        scored_count = 0
        error_count = 0
        low_conf_count = 0
        scores_for_mean: list[float] = []

        for i, ts_code in enumerate(scorable):
            try:
                result = compute_score(ts_code, trade_date, conn, cross_normals)

                # 写入 score
                conn.execute(
                    "INSERT OR REPLACE INTO stock_composite_score "
                    "(ts_code, trade_date, score, score_version, status, exclusion_reason, "
                    "experimental, coverage_ratio, low_confidence, "
                    "price_trend_score, flow_score, fundamentals_score) "
                    "VALUES (?, ?, ?, ?, ?, NULL, 1, ?, ?, ?, ?, ?)",
                    (
                        ts_code, trade_date, result.score, SCORE_VERSION, result.status,
                        result.coverage_ratio, 1 if result.low_confidence else 0,
                        result.bucket_scores.get("price_trend"),
                        result.bucket_scores.get("flow"),
                        result.bucket_scores.get("fundamentals"),
                    ),
                )

                # 写入 factors
                for fr in result.factors:
                    staleness = getattr(fr, "_staleness", None)
                    w_nom = getattr(fr, "_weight_nominal", None)
                    w_eff = getattr(fr, "_weight_effective", None)

                    conn.execute(
                        "INSERT OR REPLACE INTO stock_composite_factor "
                        "(ts_code, trade_date, score_version, factor_key, bucket, "
                        "available, raw_value, normalized_value, "
                        "weight_nominal, weight_effective, staleness_trading_days, "
                        "source_key, source_table, data_date) "
                        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                        (
                            ts_code, trade_date, SCORE_VERSION, fr.factor_key, fr.bucket,
                            1 if fr.available else 0,
                            fr.raw_value, fr.normalized_value,
                            w_nom, w_eff, staleness,
                            fr.source_key, fr.source_table, fr.data_date,
                        ),
                    )

                scored_count += 1
                if result.score is not None:
                    scores_for_mean.append(result.score)
                if result.low_confidence:
                    low_conf_count += 1

            except Exception as e:
                logger.error(f"评分失败 ({ts_code}): {e}")
                conn.execute(
                    "INSERT OR REPLACE INTO stock_composite_score "
                    "(ts_code, trade_date, score, score_version, status, experimental) "
                    "VALUES (?, ?, NULL, ?, 'error', 1)",
                    (ts_code, trade_date, SCORE_VERSION),
                )
                error_count += 1

            # 每 500 只提交一次
            if (i + 1) % 500 == 0:
                conn.commit()
                logger.info(f"进度: {i + 1}/{len(scorable)}")

        conn.commit()

        duration = (datetime.now() - start_time).total_seconds()
        mean_score = round(sum(scores_for_mean) / len(scores_for_mean), 2) if scores_for_mean else None

        logger.info(
            f"评分完成: scored={scored_count}, excluded={excluded_count}, "
            f"errors={error_count}, low_conf={low_conf_count}, "
            f"mean={mean_score}, duration={duration:.1f}s"
        )

        return BatchScoreSummary(
            trade_date=trade_date,
            total_stocks=len(all_codes),
            scored=scored_count,
            excluded=excluded_count,
            errors=error_count,
            low_confidence=low_conf_count,
            mean_score=mean_score,
            duration_seconds=duration,
        )

    finally:
        conn.close()
