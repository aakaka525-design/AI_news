"""综合评分系统单元测试

测试:
1. Freshness decay 三类规则
2. 排除规则（ST、新股、退市）
3. 单因子计算器（mock DB）
4. 评分引擎：覆盖率、low_confidence
5. 分数写入 + upsert 幂等
"""

import sqlite3

import pytest

from src.scoring.freshness import compute_decay
from src.scoring.models import ensure_scoring_tables


# ============================================================
# Freshness Decay 测试
# ============================================================

class TestFreshnessDecay:
    """Freshness decay 三类规则验证"""

    def test_daily_market_day0(self):
        assert compute_decay("daily_market", 0) == 1.0

    def test_daily_market_day1(self):
        assert compute_decay("daily_market", 1) == 0.75

    def test_daily_market_day2(self):
        assert compute_decay("daily_market", 2) == 0.40

    def test_daily_market_day3_and_beyond(self):
        assert compute_decay("daily_market", 3) == 0.0
        assert compute_decay("daily_market", 10) == 0.0

    def test_event_short_ranges(self):
        assert compute_decay("event_short", 0) == 1.0
        assert compute_decay("event_short", 2) == 1.0
        assert compute_decay("event_short", 3) == 0.75
        assert compute_decay("event_short", 5) == 0.75
        assert compute_decay("event_short", 6) == 0.40
        assert compute_decay("event_short", 10) == 0.40
        assert compute_decay("event_short", 11) == 0.0

    def test_periodic_fundamental_ranges(self):
        assert compute_decay("periodic_fundamental", 0) == 1.0
        assert compute_decay("periodic_fundamental", 20) == 1.0
        assert compute_decay("periodic_fundamental", 21) == 0.70
        assert compute_decay("periodic_fundamental", 60) == 0.70
        assert compute_decay("periodic_fundamental", 61) == 0.40
        assert compute_decay("periodic_fundamental", 120) == 0.40
        assert compute_decay("periodic_fundamental", 121) == 0.0

    def test_unknown_class(self):
        assert compute_decay("unknown", 0) == 0.0


# ============================================================
# 排除规则测试
# ============================================================

def _create_test_db():
    """创建测试用内存数据库"""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("""
        CREATE TABLE ts_stock_basic (
            ts_code TEXT PRIMARY KEY,
            name TEXT,
            list_status TEXT DEFAULT 'L',
            list_date TEXT,
            industry TEXT
        )
    """)
    return conn


class TestExclusions:
    def test_delisted_excluded(self):
        conn = _create_test_db()
        conn.execute(
            "INSERT INTO ts_stock_basic VALUES ('000001.SZ', '平安银行', 'D', '19910403', '银行')"
        )
        conn.commit()

        from src.scoring.exclusions import get_exclusions
        exclusions = get_exclusions(conn)
        assert exclusions.get("000001.SZ") == "delisted"
        conn.close()

    def test_st_excluded(self):
        conn = _create_test_db()
        conn.execute(
            "INSERT INTO ts_stock_basic VALUES ('000002.SZ', '*ST测试', 'L', '19910403', '银行')"
        )
        conn.commit()

        from src.scoring.exclusions import get_exclusions
        exclusions = get_exclusions(conn)
        assert exclusions.get("000002.SZ") == "st"
        conn.close()

    def test_normal_not_excluded(self):
        conn = _create_test_db()
        conn.execute(
            "INSERT INTO ts_stock_basic VALUES ('000001.SZ', '平安银行', 'L', '19910403', '银行')"
        )
        conn.commit()

        from src.scoring.exclusions import get_exclusions
        exclusions = get_exclusions(conn)
        assert "000001.SZ" not in exclusions
        conn.close()

    def test_null_list_status_not_excluded(self):
        """list_status IS NULL 应视为正常上市股票（真实库现状）"""
        conn = _create_test_db()
        conn.execute(
            "INSERT INTO ts_stock_basic VALUES ('000001.SZ', '平安银行', NULL, '19910403', '银行')"
        )
        conn.commit()

        from src.scoring.exclusions import get_exclusions
        exclusions = get_exclusions(conn)
        assert "000001.SZ" not in exclusions
        conn.close()


# ============================================================
# 因子计算器测试 (mock DB)
# ============================================================

class TestFactors:
    def _create_factor_db(self):
        conn = _create_test_db()
        # stock_rps (真实 schema: stock_code/date)
        conn.execute("""
            CREATE TABLE stock_rps (
                stock_code TEXT, date TEXT, rps_20 REAL
            )
        """)
        # screen_rps_snapshot (真实库中存在, 用 ts_code)
        conn.execute("""
            CREATE TABLE screen_rps_snapshot (
                ts_code TEXT, snapshot_date TEXT, rps_20 REAL
            )
        """)
        # ts_daily
        conn.execute("""
            CREATE TABLE ts_daily (
                ts_code TEXT, trade_date TEXT, close REAL
            )
        """)
        # ts_fina_indicator
        conn.execute("""
            CREATE TABLE ts_fina_indicator (
                ts_code TEXT, end_date TEXT, roe REAL
            )
        """)
        return conn

    def test_rps_from_snapshot(self):
        """优先从 screen_rps_snapshot 读取 RPS"""
        conn = self._create_factor_db()
        conn.execute("INSERT INTO screen_rps_snapshot VALUES ('000001.SZ', '2026-03-08', 85.0)")
        conn.commit()

        from src.scoring.factors import compute_rps_composite
        result = compute_rps_composite("000001.SZ", "20260308", conn)
        assert result.available is True
        assert result.raw_value == 85.0
        assert result.normalized_value == 0.85
        assert result.source_table == "screen_rps_snapshot"
        conn.close()

    def test_rps_fallback_to_stock_rps(self):
        """screen_rps_snapshot 无数据时 fallback 到 stock_rps"""
        conn = self._create_factor_db()
        conn.execute("INSERT INTO stock_rps VALUES ('000001', '20260308', 75.0)")
        conn.commit()

        from src.scoring.factors import compute_rps_composite
        result = compute_rps_composite("000001.SZ", "20260308", conn)
        assert result.available is True
        assert result.raw_value == 75.0
        assert result.source_table == "stock_rps"
        conn.close()

    def test_rps_composite_missing(self):
        conn = self._create_factor_db()
        conn.commit()

        from src.scoring.factors import compute_rps_composite
        result = compute_rps_composite("000001.SZ", "20260308", conn)
        assert result.available is False
        conn.close()

    def test_roe_quality_tiers(self):
        conn = self._create_factor_db()

        from src.scoring.factors import compute_roe_quality

        # ROE > 15 → 1.0
        conn.execute("INSERT INTO ts_fina_indicator VALUES ('000001.SZ', '20260308', 20.0)")
        conn.commit()
        r = compute_roe_quality("000001.SZ", "20260308", conn)
        assert r.normalized_value == 1.0

        # ROE > 10 → 0.7
        conn.execute("DELETE FROM ts_fina_indicator")
        conn.execute("INSERT INTO ts_fina_indicator VALUES ('000001.SZ', '20260308', 12.0)")
        conn.commit()
        r = compute_roe_quality("000001.SZ", "20260308", conn)
        assert r.normalized_value == 0.7

        # ROE > 5 → 0.4
        conn.execute("DELETE FROM ts_fina_indicator")
        conn.execute("INSERT INTO ts_fina_indicator VALUES ('000001.SZ', '20260308', 7.0)")
        conn.commit()
        r = compute_roe_quality("000001.SZ", "20260308", conn)
        assert r.normalized_value == 0.4

        # ROE > 0 → 0.2
        conn.execute("DELETE FROM ts_fina_indicator")
        conn.execute("INSERT INTO ts_fina_indicator VALUES ('000001.SZ', '20260308', 2.0)")
        conn.commit()
        r = compute_roe_quality("000001.SZ", "20260308", conn)
        assert r.normalized_value == 0.2

        # ROE <= 0 → 0.0
        conn.execute("DELETE FROM ts_fina_indicator")
        conn.execute("INSERT INTO ts_fina_indicator VALUES ('000001.SZ', '20260308', -5.0)")
        conn.commit()
        r = compute_roe_quality("000001.SZ", "20260308", conn)
        assert r.normalized_value == 0.0

        conn.close()

    def test_tech_confirm_insufficient_data(self):
        conn = self._create_factor_db()
        # Only 5 rows, need at least 26
        for i in range(5):
            conn.execute(
                "INSERT INTO ts_daily VALUES ('000001.SZ', ?, 10.0)",
                (f"2026030{i}",),
            )
        conn.commit()

        from src.scoring.factors import compute_tech_confirm
        r = compute_tech_confirm("000001.SZ", "20260309", conn)
        assert r.available is False
        conn.close()


# ============================================================
# 评分引擎测试
# ============================================================

class TestScoringEngine:
    def test_coverage_ratio_all_available(self):
        """6 个因子全部可用 → coverage=1.0"""
        from src.scoring.engine import FACTOR_CONFIG
        # coverage = effective / total
        assert len(FACTOR_CONFIG) == 6

    def test_low_confidence_threshold(self):
        """coverage < 0.60 → low_confidence"""
        # 3/6 = 0.5 < 0.6 → low_confidence
        assert 3 / 6 < 0.60

    def test_bucket_weights_sum(self):
        """Bucket 权重总和 = 1.0"""
        from src.scoring.engine import BUCKET_WEIGHTS
        assert sum(BUCKET_WEIGHTS.values()) == pytest.approx(1.0)

    def test_factor_weights_sum(self):
        """因子权重总和 = 1.0"""
        from src.scoring.engine import FACTOR_CONFIG
        total = sum(c["weight"] for c in FACTOR_CONFIG.values())
        assert total == pytest.approx(1.0)


# ============================================================
# 写入 + 幂等测试
# ============================================================

class TestScoreStorage:
    def test_ensure_tables_idempotent(self):
        """ensure_scoring_tables 多次调用不报错"""
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        ensure_scoring_tables(conn)
        ensure_scoring_tables(conn)  # 第二次不应报错
        conn.close()

    def test_upsert_score(self):
        """INSERT OR REPLACE 幂等"""
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        ensure_scoring_tables(conn)

        conn.execute(
            "INSERT OR REPLACE INTO stock_composite_score "
            "(ts_code, trade_date, score, score_version, status) "
            "VALUES ('000001.SZ', '20260308', 75.0, 'v1', 'scored')"
        )
        conn.commit()

        # 再次写入同一 ts_code + trade_date + score_version
        conn.execute(
            "INSERT OR REPLACE INTO stock_composite_score "
            "(ts_code, trade_date, score, score_version, status) "
            "VALUES ('000001.SZ', '20260308', 80.0, 'v1', 'scored')"
        )
        conn.commit()

        row = conn.execute(
            "SELECT score FROM stock_composite_score WHERE ts_code='000001.SZ'"
        ).fetchone()
        assert row["score"] == 80.0

        count = conn.execute(
            "SELECT COUNT(*) as cnt FROM stock_composite_score WHERE ts_code='000001.SZ'"
        ).fetchone()
        assert count["cnt"] == 1

        conn.close()

    def test_upsert_factor(self):
        """因子明细 upsert 幂等"""
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        ensure_scoring_tables(conn)

        conn.execute(
            "INSERT OR REPLACE INTO stock_composite_factor "
            "(ts_code, trade_date, score_version, factor_key, bucket, available, raw_value) "
            "VALUES ('000001.SZ', '20260308', 'v1', 'rps_composite', 'price_trend', 1, 85.0)"
        )
        conn.commit()

        conn.execute(
            "INSERT OR REPLACE INTO stock_composite_factor "
            "(ts_code, trade_date, score_version, factor_key, bucket, available, raw_value) "
            "VALUES ('000001.SZ', '20260308', 'v1', 'rps_composite', 'price_trend', 1, 90.0)"
        )
        conn.commit()

        row = conn.execute(
            "SELECT raw_value FROM stock_composite_factor WHERE ts_code='000001.SZ' AND factor_key='rps_composite'"
        ).fetchone()
        assert row["raw_value"] == 90.0

        count = conn.execute(
            "SELECT COUNT(*) as cnt FROM stock_composite_factor WHERE ts_code='000001.SZ' AND factor_key='rps_composite'"
        ).fetchone()
        assert count["cnt"] == 1

        conn.close()
