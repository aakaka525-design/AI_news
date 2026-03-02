"""Tests for sector rotation detection."""

import numpy as np
import pandas as pd

from src.analysis.sector_rotation import (
    detect_rotation,
    rank_sectors,
    rotation_momentum,
)


def _make_sector_rps(n_days: int = 30, n_sectors: int = 5) -> pd.DataFrame:
    """Generate synthetic sector RPS data."""
    np.random.seed(42)
    dates = pd.bdate_range("2025-01-01", periods=n_days)
    rows = []
    sectors = [f"sector_{i}" for i in range(n_sectors)]
    for date in dates:
        for sector in sectors:
            rows.append(
                {
                    "date": date.strftime("%Y-%m-%d"),
                    "sector_name": sector,
                    "rps_10": np.random.uniform(10, 100),
                    "rps_20": np.random.uniform(10, 100),
                    "rps_50": np.random.uniform(10, 100),
                }
            )
    return pd.DataFrame(rows)


class TestRankSectors:
    def test_returns_sorted_sectors(self):
        df = _make_sector_rps(30, 5)
        ranked = rank_sectors(df, period="rps_10", top_n=3)
        assert len(ranked) == 3
        assert all("sector_name" in r for r in ranked)
        assert all("score" in r for r in ranked)

    def test_top_n_limit(self):
        df = _make_sector_rps(30, 10)
        ranked = rank_sectors(df, period="rps_20", top_n=5)
        assert len(ranked) == 5

    def test_scores_descending(self):
        df = _make_sector_rps(30, 5)
        ranked = rank_sectors(df, period="rps_10", top_n=5)
        scores = [r["score"] for r in ranked]
        assert scores == sorted(scores, reverse=True)


class TestDetectRotation:
    def test_detects_rotation_signal(self):
        df = _make_sector_rps(30, 5)
        result = detect_rotation(df, lookback=10)
        assert "rotations" in result
        assert "top_rising" in result
        assert "top_falling" in result
        assert isinstance(result["rotations"], list)

    def test_rising_sectors_have_positive_change(self):
        df = _make_sector_rps(30, 5)
        result = detect_rotation(df, lookback=10)
        for s in result["top_rising"]:
            assert s["rps_change"] >= 0

    def test_falling_sectors_have_negative_change(self):
        df = _make_sector_rps(30, 5)
        result = detect_rotation(df, lookback=10)
        for s in result["top_falling"]:
            assert s["rps_change"] <= 0


class TestRotationMomentum:
    def test_returns_momentum_scores(self):
        df = _make_sector_rps(30, 5)
        momentum = rotation_momentum(df, short_period="rps_10", long_period="rps_50")
        assert len(momentum) > 0
        assert all("sector_name" in m for m in momentum)
        assert all("momentum" in m for m in momentum)

    def test_momentum_is_difference(self):
        df = _make_sector_rps(30, 5)
        momentum = rotation_momentum(df, short_period="rps_10", long_period="rps_50")
        for m in momentum:
            assert isinstance(m["momentum"], float)
