"""
板块轮动检测 -- 纯计算，无副作用

基于板块 RPS 数据识别轮动信号、排名变化、动量差异。
"""

from __future__ import annotations

import pandas as pd


def rank_sectors(
    sector_rps: pd.DataFrame,
    period: str = "rps_10",
    top_n: int = 5,
) -> list[dict]:
    """对板块按最新 RPS 排名。

    Args:
        sector_rps: DataFrame with date, sector_name, rps_10, rps_20, rps_50
        period: RPS 周期列名
        top_n: 返回前 N 个

    Returns:
        [{"sector_name": str, "score": float}, ...]
    """
    latest_date = sector_rps["date"].max()
    latest = sector_rps[sector_rps["date"] == latest_date].copy()
    latest = latest.sort_values(period, ascending=False).head(top_n)
    return [
        {"sector_name": row["sector_name"], "score": float(row[period])}
        for _, row in latest.iterrows()
    ]


def detect_rotation(
    sector_rps: pd.DataFrame,
    lookback: int = 10,
    period: str = "rps_10",
) -> dict:
    """检测板块轮动信号。

    比较最新 RPS 与 lookback 天前的 RPS，找出上升和下降幅度最大的板块。

    Args:
        sector_rps: DataFrame with date, sector_name, rps_10, rps_20, rps_50
        lookback: 回看天数
        period: RPS 周期列名

    Returns:
        {"rotations": [...], "top_rising": [...], "top_falling": [...]}
    """
    dates = sorted(sector_rps["date"].unique())
    if len(dates) < lookback + 1:
        return {"rotations": [], "top_rising": [], "top_falling": []}

    latest_date = dates[-1]
    past_date = dates[-lookback - 1]

    latest = sector_rps[sector_rps["date"] == latest_date].set_index("sector_name")
    past = sector_rps[sector_rps["date"] == past_date].set_index("sector_name")

    common = latest.index.intersection(past.index)
    changes = []
    for sector in common:
        change = float(latest.loc[sector, period]) - float(past.loc[sector, period])
        changes.append({"sector_name": sector, "rps_change": change})

    changes.sort(key=lambda x: x["rps_change"], reverse=True)

    top_rising = [c for c in changes if c["rps_change"] >= 0][:5]
    top_falling = [c for c in changes if c["rps_change"] < 0][-5:]
    top_falling.sort(key=lambda x: x["rps_change"])

    rotations = [c for c in changes if abs(c["rps_change"]) > 20]

    return {
        "rotations": rotations,
        "top_rising": top_rising,
        "top_falling": top_falling,
    }


def rotation_momentum(
    sector_rps: pd.DataFrame,
    short_period: str = "rps_10",
    long_period: str = "rps_50",
) -> list[dict]:
    """计算板块轮动动量 = 短期 RPS - 长期 RPS。

    动量为正 → 板块加速走强；动量为负 → 板块走弱。

    Args:
        sector_rps: DataFrame with date, sector_name, rps_10, rps_50 etc.
        short_period: 短期 RPS 列名
        long_period: 长期 RPS 列名

    Returns:
        [{"sector_name": str, "momentum": float, "short_rps": float, "long_rps": float}, ...]
    """
    latest_date = sector_rps["date"].max()
    latest = sector_rps[sector_rps["date"] == latest_date].copy()

    result = []
    for _, row in latest.iterrows():
        short_val = float(row.get(short_period, 0))
        long_val = float(row.get(long_period, 0))
        result.append(
            {
                "sector_name": row["sector_name"],
                "momentum": short_val - long_val,
                "short_rps": short_val,
                "long_rps": long_val,
            }
        )

    result.sort(key=lambda x: x["momentum"], reverse=True)
    return result
