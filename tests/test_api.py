"""API endpoint integration tests.

Sync TestClient approach with mocked repository layer.
Complements test_api_endpoints.py (async httpx) by focusing on
input validation, error responses, and edge cases.
"""

import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock

from fastapi.testclient import TestClient


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _make_test_fixtures(tmp_path: Path):
    """Create isolated engine/session/repo backed by a temp SQLite file."""
    from src.database.engine import create_engine_from_url, get_session_factory
    from src.database.repositories.news import NewsRepository

    db_file = tmp_path / "test_api_news.db"
    db_url = f"sqlite:///{db_file}"
    engine = create_engine_from_url(db_url)
    session_factory = get_session_factory(engine)
    repo = NewsRepository(session_factory)
    repo.create_tables(engine)
    return engine, session_factory, repo


@pytest.fixture
def client(tmp_path):
    """Create a sync TestClient with mocked database and scheduler."""
    engine, session_factory, repo = _make_test_fixtures(tmp_path)

    from api import main as api_main

    with (
        patch.object(api_main, "_engine", engine),
        patch.object(api_main, "_Session", session_factory),
        patch.object(api_main, "_repo", repo),
        patch.object(api_main, "register_default_tasks"),
        patch.object(api_main, "scheduler_manager") as mock_sched,
        patch.object(api_main, "create_analyzer_from_env", return_value=None),
    ):
        mock_sched.start = MagicMock()
        mock_sched.stop = MagicMock()
        mock_sched._running = False

        with TestClient(api_main.app) as c:
            yield c


# ---------------------------------------------------------------------------
# GET /health
# ---------------------------------------------------------------------------


class TestHealthEndpoint:
    def test_health_returns_status(self, client):
        resp = client.get("/health")
        assert resp.status_code in (200, 503)
        data = resp.json()
        assert "status" in data
        assert "db" in data
        assert "scheduler" in data

    def test_health_has_version(self, client):
        resp = client.get("/health")
        data = resp.json()
        assert "version" in data
        assert data["version"] == "2.0.0"

    def test_health_db_structure(self, client):
        resp = client.get("/health")
        data = resp.json()
        assert "ok" in data["db"]
        assert isinstance(data["db"]["ok"], bool)

    def test_health_scheduler_structure(self, client):
        resp = client.get("/health")
        data = resp.json()
        assert "running" in data["scheduler"]
        assert isinstance(data["scheduler"]["running"], bool)

    def test_health_status_values(self, client):
        resp = client.get("/health")
        data = resp.json()
        assert data["status"] in ("healthy", "degraded")


# ---------------------------------------------------------------------------
# Input Validation
# ---------------------------------------------------------------------------


class TestInputValidation:
    def test_invalid_ts_code_returns_422(self, client):
        r"""ts_code must match pattern ^\d{6}\.(SH|SZ|BJ)$"""
        resp = client.get("/api/stocks/INVALID/profile")
        assert resp.status_code == 422

    def test_invalid_ts_code_no_exchange_suffix(self, client):
        resp = client.get("/api/stocks/000001/profile")
        assert resp.status_code == 422

    def test_invalid_ts_code_wrong_exchange(self, client):
        resp = client.get("/api/stocks/000001.XX/profile")
        assert resp.status_code == 422

    def test_valid_ts_code_format_sz(self, client):
        """Valid ts_code format should not return 422 (may return 404 if stock not found)."""
        resp = client.get("/api/stocks/000001.SZ/profile")
        assert resp.status_code != 422

    def test_valid_ts_code_format_sh(self, client):
        resp = client.get("/api/stocks/600519.SH/profile")
        assert resp.status_code != 422

    def test_valid_ts_code_format_bj(self, client):
        resp = client.get("/api/stocks/830799.BJ/profile")
        assert resp.status_code != 422

    def test_invalid_date_format_daily(self, client):
        resp = client.get(
            "/api/stocks/000001.SZ/daily",
            params={"start_date": "not-a-date"},
        )
        assert resp.status_code == 422

    def test_invalid_date_format_daily_slash(self, client):
        resp = client.get(
            "/api/stocks/000001.SZ/daily",
            params={"start_date": "2026/03/01"},
        )
        assert resp.status_code == 422

    def test_valid_date_format_daily(self, client):
        resp = client.get(
            "/api/stocks/000001.SZ/daily",
            params={"start_date": "2026-03-01"},
        )
        assert resp.status_code != 422

    def test_analyze_invalid_date_returns_422(self, client):
        resp = client.post("/api/analyze", json={"date": "invalid"})
        assert resp.status_code == 422

    def test_analyze_wrong_date_format_returns_422(self, client):
        resp = client.post("/api/analyze", json={"date": "20260301"})
        assert resp.status_code == 422

    def test_analyze_valid_date_format(self, client):
        """Valid date format should not return 422 (may return 503 if AI not configured)."""
        resp = client.post("/api/analyze", json={"date": "2026-03-01"})
        assert resp.status_code != 422

    def test_analyze_missing_date_returns_422(self, client):
        resp = client.post("/api/analyze", json={})
        assert resp.status_code == 422

    def test_research_stock_code_validation(self, client):
        """stock_code must be exactly 6 digits for research endpoints."""
        resp = client.get("/api/research/reports", params={"stock_code": "ABC"})
        assert resp.status_code == 422

    def test_research_stock_code_too_short(self, client):
        resp = client.get("/api/research/reports", params={"stock_code": "123"})
        assert resp.status_code == 422

    def test_anomalies_limit_too_large(self, client):
        resp = client.get("/api/anomalies", params={"limit": 10000})
        assert resp.status_code == 422

    def test_anomalies_days_zero(self, client):
        resp = client.get("/api/anomalies", params={"days": 0})
        assert resp.status_code == 422


# ---------------------------------------------------------------------------
# GET /api/news
# ---------------------------------------------------------------------------


class TestNewsEndpoint:
    def test_news_limit_too_low_returns_422(self, client):
        resp = client.get("/api/news", params={"limit": "0"})
        assert resp.status_code == 422

    def test_news_limit_too_high_returns_422(self, client):
        resp = client.get("/api/news", params={"limit": "501"})
        assert resp.status_code == 422

    def test_news_negative_limit_returns_422(self, client):
        resp = client.get("/api/news", params={"limit": "-1"})
        assert resp.status_code == 422

    def test_news_non_numeric_limit_returns_422(self, client):
        resp = client.get("/api/news", params={"limit": "abc"})
        assert resp.status_code == 422

    def test_news_valid_limit_returns_200(self, client):
        resp = client.get("/api/news", params={"limit": "10"})
        assert resp.status_code == 200

    def test_news_default_returns_200(self, client):
        resp = client.get("/api/news")
        assert resp.status_code == 200
        data = resp.json()
        assert "total" in data
        assert "data" in data
        assert isinstance(data["data"], list)

    def test_news_max_valid_limit(self, client):
        resp = client.get("/api/news", params={"limit": "500"})
        assert resp.status_code == 200

    def test_news_min_valid_limit(self, client):
        resp = client.get("/api/news", params={"limit": "1"})
        assert resp.status_code == 200


# ---------------------------------------------------------------------------
# POST /webhook/receive
# ---------------------------------------------------------------------------


class TestWebhookEndpoint:
    def test_webhook_missing_content_returns_422(self, client):
        resp = client.post("/webhook/receive", json={"title": "only title"})
        assert resp.status_code == 422

    def test_webhook_missing_title_returns_422(self, client):
        resp = client.post("/webhook/receive", json={"content": "only content"})
        assert resp.status_code == 422

    def test_webhook_empty_body_returns_422(self, client):
        resp = client.post("/webhook/receive", json={})
        assert resp.status_code == 422

    def test_webhook_success_returns_ok(self, client):
        resp = client.post(
            "/webhook/receive",
            json={"title": "Test News", "content": "Some breaking content"},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "ok"
        assert "news_id" in body

    def test_webhook_returns_hotspots_and_keywords(self, client):
        resp = client.post(
            "/webhook/receive",
            json={"title": "Test", "content": "Market content"},
        )
        body = resp.json()
        assert "hotspots" in body
        assert "keywords" in body
        assert isinstance(body["hotspots"], list)
        assert isinstance(body["keywords"], list)


# ---------------------------------------------------------------------------
# POST /api/clean
# ---------------------------------------------------------------------------


class TestCleanEndpoint:
    def test_clean_missing_fields_returns_422(self, client):
        resp = client.post("/api/clean", json={"title": "no content"})
        assert resp.status_code == 422

    def test_clean_success(self, client):
        resp = client.post(
            "/api/clean",
            json={"title": "Test", "content": "Content here"},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert "title" in body
        assert "facts" in body
        assert "hotspots" in body
        assert "keywords" in body
        assert "cleaned_at" in body


# ---------------------------------------------------------------------------
# Stock endpoint query parameter validation
# ---------------------------------------------------------------------------


class TestStockQueryParamValidation:
    def test_daily_end_date_invalid(self, client):
        resp = client.get(
            "/api/stocks/000001.SZ/daily",
            params={"end_date": "March 1 2026"},
        )
        assert resp.status_code == 422

    def test_valuation_history_limit_too_large(self, client):
        resp = client.get(
            "/api/stocks/000001.SZ/valuation-history",
            params={"limit": "1001"},
        )
        assert resp.status_code == 422

    def test_valuation_history_limit_zero(self, client):
        resp = client.get(
            "/api/stocks/000001.SZ/valuation-history",
            params={"limit": "0"},
        )
        assert resp.status_code == 422

    def test_market_overview_invalid_date(self, client):
        resp = client.get(
            "/api/market/overview",
            params={"trade_date": "20260301"},
        )
        assert resp.status_code == 422

    def test_calendar_invalid_date(self, client):
        resp = client.get(
            "/api/calendar/is_trading_day",
            params={"date": "20260301"},
        )
        assert resp.status_code == 422

    def test_money_flow_invalid_ts_code(self, client):
        resp = client.get(
            "/api/money-flow",
            params={"ts_code": "INVALID"},
        )
        assert resp.status_code == 422


# ---------------------------------------------------------------------------
# Edge cases and error scenarios
# ---------------------------------------------------------------------------


class TestErrorScenarios:
    def test_analyze_returns_503_when_ai_disabled(self, client):
        """When AI analyzer is not configured, /api/analyze should return 503."""
        resp = client.post("/api/analyze", json={"date": "2026-03-01"})
        assert resp.status_code == 503

    def test_facts_not_found(self, client):
        resp = client.get("/api/facts/99999")
        assert resp.status_code == 404

    def test_analysis_not_found(self, client):
        resp = client.get("/api/analysis/99999")
        assert resp.status_code == 404

    def test_webhook_then_news_roundtrip(self, client):
        """Verify data flows from webhook to news listing."""
        client.post(
            "/webhook/receive",
            json={"title": "Roundtrip Test", "content": "Testing data flow"},
        )
        resp = client.get("/api/news?limit=1")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] >= 1
        assert data["data"][0]["title"] == "Roundtrip Test"
