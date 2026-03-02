"""Tests for ReportRepository."""

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.database.repositories.report import ReportRepository


@pytest.fixture()
def repo(tmp_path):
    """Create a ReportRepository backed by SQLite."""
    db_url = f"sqlite:///{tmp_path / 'test.db'}"
    engine = create_engine(db_url)
    Session = sessionmaker(bind=engine)
    repository = ReportRepository(Session)
    repository.create_tables(engine)
    return repository


class TestReportRepositoryUpsert:
    def test_upsert_single_report(self, repo):
        report = {
            "ts_code": "000001.SZ",
            "stock_name": "平安银行",
            "title": "业绩超预期，维持买入",
            "institution": "中信证券",
            "rating": "买入",
            "publish_date": "20260301",
        }
        repo.upsert_report(report)
        reports = repo.get_reports(ts_code="000001.SZ")
        assert len(reports) == 1
        assert reports[0]["title"] == "业绩超预期，维持买入"

    def test_upsert_updates_existing(self, repo):
        report = {
            "ts_code": "000001.SZ",
            "stock_name": "平安银行",
            "title": "旧标题",
            "institution": "中信证券",
            "rating": "增持",
            "publish_date": "20260301",
        }
        repo.upsert_report(report)
        report["title"] = "新标题"
        report["rating"] = "买入"
        repo.upsert_report(report)
        reports = repo.get_reports(ts_code="000001.SZ")
        assert len(reports) == 1
        assert reports[0]["title"] == "新标题"
        assert reports[0]["rating"] == "买入"


class TestReportRepositoryQuery:
    def test_get_reports_by_code(self, repo):
        for i in range(3):
            repo.upsert_report(
                {
                    "ts_code": "000001.SZ",
                    "stock_name": "平安银行",
                    "title": f"报告{i}",
                    "institution": f"机构{i}",
                    "rating": "买入",
                    "publish_date": f"2026030{i + 1}",
                }
            )
        reports = repo.get_reports(ts_code="000001.SZ", limit=2)
        assert len(reports) == 2

    def test_get_latest_reports(self, repo):
        for code in ["000001.SZ", "600519.SH"]:
            repo.upsert_report(
                {
                    "ts_code": code,
                    "stock_name": "测试",
                    "title": f"{code}报告",
                    "institution": "中信证券",
                    "rating": "买入",
                    "publish_date": "20260301",
                }
            )
        reports = repo.get_reports(limit=10)
        assert len(reports) == 2

    def test_get_rating_stats(self, repo):
        ratings_and_institutions = [
            ("买入", "机构A"),
            ("买入", "机构B"),
            ("增持", "机构C"),
            ("中性", "机构D"),
        ]
        for rating, inst in ratings_and_institutions:
            repo.upsert_report(
                {
                    "ts_code": "000001.SZ",
                    "stock_name": "测试",
                    "title": f"{rating}报告",
                    "institution": inst,
                    "rating": rating,
                    "publish_date": "20260301",
                }
            )
        stats = repo.get_rating_stats()
        assert stats["买入"] == 2
        assert stats["增持"] == 1


class TestReportRepositoryAnalysis:
    def test_save_analysis_fields(self, repo):
        repo.upsert_report(
            {
                "ts_code": "000001.SZ",
                "stock_name": "平安银行",
                "title": "目标价：50元",
                "institution": "中信证券",
                "rating": "买入",
                "publish_date": "20260301",
            }
        )
        repo.save_analysis(
            ts_code="000001.SZ",
            publish_date="20260301",
            institution="中信证券",
            analysis={
                "target_price": 50.0,
                "rating_change": None,
                "key_points": ["业绩点评"],
                "risk_factors": [],
                "sentiment": "positive",
                "summary": "看好长期发展",
                "sentiment_score": 0.85,
            },
        )
        reports = repo.get_reports(ts_code="000001.SZ")
        r = reports[0]
        assert r["target_price"] == 50.0
        assert r["key_points"] == ["业绩点评"]
        assert r["summary"] == "看好长期发展"
        assert float(r["sentiment_score"]) == pytest.approx(0.85, abs=0.01)
