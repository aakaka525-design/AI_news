#!/usr/bin/env python3
"""
Integration tests for FastAPI API endpoints.

Uses httpx.AsyncClient with ASGITransport against a temporary SQLite database
so every test run is fully isolated.
"""

from pathlib import Path
from unittest.mock import MagicMock, patch

import httpx
import pytest
import pytest_asyncio
from httpx import ASGITransport

from api import main as api_main
from src.database.engine import create_engine_from_url, get_session_factory
from src.database.repositories.news import NewsRepository


def _make_test_repo(tmp_path: Path):
    """Create an isolated engine/session/repo backed by a temp SQLite file."""
    db_file = tmp_path / "test_news.db"
    db_url = f"sqlite:///{db_file}"
    engine = create_engine_from_url(db_url)
    session_factory = get_session_factory(engine)
    repo = NewsRepository(session_factory)
    repo.create_tables(engine)
    return engine, session_factory, repo


@pytest_asyncio.fixture()
async def client(tmp_path: Path):
    """
    Yield an ``httpx.AsyncClient`` wired to the FastAPI app with:
      - _engine, _Session, _repo pointed at a fresh temporary database
      - Scheduler calls stubbed out (no real APScheduler activity)
      - AI analyser disabled
    """
    engine, session_factory, repo = _make_test_repo(tmp_path)

    # Patch the module-level database objects and heavy side-effects.
    with (
        patch("api.main._engine", engine),
        patch("api.main._Session", session_factory),
        patch("api.main._repo", repo),
        patch("api.main.register_default_tasks"),
        patch("api.main.scheduler_manager") as mock_sched,
        patch("api.main.create_analyzer_from_env", return_value=None),
    ):
        mock_sched.start = MagicMock()
        mock_sched.stop = MagicMock()
        mock_sched._running = False

        from api.main import app

        transport = ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://testserver",
        ) as ac:
            yield ac


# ---------------------------------------------------------------------------
# GET /health
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_health_returns_200(client):
    resp = await client.get("/health")
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_health_body_structure(client):
    data = (await client.get("/health")).json()
    # The endpoint returns "healthy" or "degraded"
    assert data["status"] in ("healthy", "degraded")
    assert "db" in data
    assert data["db"]["ok"] is True
    assert "url" not in data["db"]
    assert "scheduler" in data
    assert "version" in data
    assert data["version"] == "2.0.0"


# ---------------------------------------------------------------------------
# POST /webhook/receive
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_webhook_receive_success(client):
    payload = {"title": "Test News", "content": "Some breaking content here"}
    resp = await client.post("/webhook/receive", json=payload)
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert "news_id" in body
    assert isinstance(body["news_id"], int)


@pytest.mark.asyncio
async def test_webhook_receive_missing_fields(client):
    """Omitting required fields should return 422."""
    resp = await client.post("/webhook/receive", json={"title": "only title"})
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_webhook_receive_returns_hotspots_and_keywords(client):
    payload = {"title": "AI芯片突破", "content": "华为发布新一代AI芯片"}
    resp = await client.post("/webhook/receive", json=payload)
    body = resp.json()
    assert "hotspots" in body
    assert "keywords" in body
    assert isinstance(body["hotspots"], list)
    assert isinstance(body["keywords"], list)


@pytest.mark.asyncio
async def test_webhook_rejects_when_secret_enabled_and_header_missing(client, monkeypatch):
    monkeypatch.setattr(api_main, "WEBHOOK_SECRET", "unit-secret")
    resp = await client.post(
        "/webhook/receive",
        json={"title": "Secret", "content": "missing header"},
    )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_webhook_accepts_when_secret_header_matches(client, monkeypatch):
    monkeypatch.setattr(api_main, "WEBHOOK_SECRET", "unit-secret")
    resp = await client.post(
        "/webhook/receive",
        headers={"X-Webhook-Token": "unit-secret"},
        json={"title": "Secret", "content": "header ok"},
    )
    assert resp.status_code == 200


# ---------------------------------------------------------------------------
# GET /api/news
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_news_empty_db(client):
    resp = await client.get("/api/news")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 0
    assert data["data"] == []


@pytest.mark.asyncio
async def test_webhook_then_get_news(client):
    """After posting via webhook, the news list should reflect the new item."""
    await client.post(
        "/webhook/receive",
        json={"title": "Breaking", "content": "Market surge in tech stocks"},
    )
    resp = await client.get("/api/news")
    data = resp.json()
    assert data["total"] >= 1
    assert len(data["data"]) >= 1
    # Verify shape of the first record
    record = data["data"][0]
    assert "id" in record
    assert record["title"] == "Breaking"
    assert "content_html" in record


@pytest.mark.asyncio
async def test_news_content_html_is_sanitized(client):
    """Markdown 渲染结果应去除危险脚本与 javascript 协议。"""
    await client.post(
        "/webhook/receive",
        json={"title": "XSS", "content": "hello<script>alert('x')</script> [x](javascript:alert(1))"},
    )
    resp = await client.get("/api/news?limit=1")
    body = resp.json()
    html = body["data"][0]["content_html"].lower()
    assert "<script" not in html
    assert "javascript:" not in html


@pytest.mark.asyncio
async def test_get_news_limit_param(client):
    """The ?limit query parameter should cap the result count."""
    for i in range(3):
        await client.post(
            "/webhook/receive",
            json={"title": f"Item {i}", "content": f"Content {i}"},
        )
    resp = await client.get("/api/news?limit=2")
    data = resp.json()
    assert data["total"] == 3  # total is the DB count
    assert len(data["data"]) == 2  # but only 2 returned


# ---------------------------------------------------------------------------
# POST /api/clean
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_clean_endpoint_success(client):
    resp = await client.post(
        "/api/clean",
        json={"title": "Test", "content": "**Bold** text with [link](http://x.com)"},
    )
    assert resp.status_code == 200
    body = resp.json()
    # CleanedData.to_dict() shape
    assert "title" in body
    assert "summary" in body
    assert "facts" in body
    assert "hotspots" in body
    assert "keywords" in body
    assert "cleaned_at" in body


@pytest.mark.asyncio
async def test_clean_endpoint_missing_fields(client):
    resp = await client.post("/api/clean", json={"title": "only title"})
    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# GET / (homepage)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_homepage_returns_html(client):
    resp = await client.get("/")
    assert resp.status_code == 200
    content_type = resp.headers.get("content-type", "")
    assert "text/html" in content_type


@pytest.mark.asyncio
async def test_homepage_contains_title(client):
    resp = await client.get("/")
    assert resp.status_code == 200
    assert "AI News" in resp.text


# ---------------------------------------------------------------------------
# GET /api/hotspots
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_hotspots_empty(client):
    resp = await client.get("/api/hotspots")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 0
    assert data["data"] == []


@pytest.mark.asyncio
async def test_hotspots_after_webhook(client):
    await client.post(
        "/webhook/receive",
        json={"title": "AI芯片突破", "content": "AI人工智能芯片新突破"},
    )
    resp = await client.get("/api/hotspots")
    data = resp.json()
    assert isinstance(data["total"], int)
    assert isinstance(data["data"], list)


# ---------------------------------------------------------------------------
# GET /api/facts/{news_id}
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_facts_not_found(client):
    resp = await client.get("/api/facts/9999")
    assert resp.status_code == 200
    body = resp.json()
    assert "error" in body


@pytest.mark.asyncio
async def test_facts_after_webhook(client):
    post_resp = await client.post(
        "/webhook/receive",
        json={"title": "FactTest", "content": "Some fact content"},
    )
    news_id = post_resp.json()["news_id"]
    resp = await client.get(f"/api/facts/{news_id}")
    assert resp.status_code == 200
    body = resp.json()
    # Should contain cleaned_data keys
    assert "title" in body
    assert "facts" in body


# ---------------------------------------------------------------------------
# Concurrency / idempotency quick-checks
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_multiple_webhooks_sequential(client):
    """Multiple sequential webhook posts should each succeed."""
    for i in range(5):
        resp = await client.post(
            "/webhook/receive",
            json={"title": f"News {i}", "content": f"Content {i}"},
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"
    news_resp = await client.get("/api/news")
    assert news_resp.json()["total"] == 5


# ---------------------------------------------------------------------------
# Research / anomalies endpoints
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_research_reports_endpoint_has_no_import_error(client):
    resp = await client.get("/api/research/reports?limit=1")
    assert resp.status_code == 200
    body = resp.json()
    assert "error" not in body
    assert "data" in body


@pytest.mark.asyncio
async def test_research_stats_endpoint_has_no_import_error(client):
    resp = await client.get("/api/research/stats")
    assert resp.status_code == 200
    body = resp.json()
    assert "error" not in body


@pytest.mark.asyncio
async def test_research_reports_endpoint_returns_500_when_fetcher_fails(client, monkeypatch):
    import fetchers.research_report as report_fetcher

    def _raise_runtime_error(*_args, **_kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr(report_fetcher, "get_latest_reports", _raise_runtime_error)
    resp = await client.get("/api/research/reports?limit=1")
    assert resp.status_code == 500
    assert "failed" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_research_stats_endpoint_returns_500_when_fetcher_fails(client, monkeypatch):
    import fetchers.research_report as report_fetcher

    def _raise_runtime_error(*_args, **_kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr(report_fetcher, "get_rating_stats", _raise_runtime_error)
    resp = await client.get("/api/research/stats")
    assert resp.status_code == 500
    assert "failed" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_anomalies_limit_out_of_range_returns_422(client):
    resp = await client.get("/api/anomalies?limit=10000")
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_anomalies_days_out_of_range_returns_422(client):
    resp = await client.get("/api/anomalies?days=0")
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_console_page_returns_html(client):
    resp = await client.get("/console")
    assert resp.status_code == 200
    assert "text/html" in resp.headers.get("content-type", "")


@pytest.mark.asyncio
async def test_analyze_endpoint_success(client, monkeypatch):
    class _DummyAnalyzer:
        async def analyze_opportunities(self, _items):
            return {
                "analysis_summary": "ok",
                "opportunities": [{"stock_code": "000001"}],
            }

    monkeypatch.setattr(api_main, "create_analyzer_from_env", lambda: _DummyAnalyzer())
    monkeypatch.setattr(
        api_main,
        "get_news_by_date",
        lambda _date, _limit: [{"id": 1, "title": "t", "content": "c"}],
    )
    monkeypatch.setattr(api_main, "save_analysis_result", lambda *_args: 99)

    resp = await client.post("/api/analyze", json={"date": "2026-03-01", "limit": 5})
    assert resp.status_code == 200
    body = resp.json()
    assert body["analysis_id"] == 99
    assert body["input_count"] == 1
    assert body["date"] == "2026-03-01"


@pytest.mark.asyncio
async def test_get_analysis_endpoint_returns_row(client, monkeypatch):
    monkeypatch.setattr(
        api_main._repo,
        "get_analysis_by_id",
        lambda analysis_id: {"id": analysis_id, "analysis_summary": "ok"},
    )
    resp = await client.get("/api/analysis/7")
    assert resp.status_code == 200
    assert resp.json()["id"] == 7


@pytest.mark.asyncio
async def test_rss_sentiment_stats_endpoint_success(client, monkeypatch):
    import src.ai_engine.sentiment as sentiment_module

    monkeypatch.setattr(
        sentiment_module,
        "get_sentiment_stats",
        lambda: {
            "analyzed_count": 3,
            "pending_count": 1,
            "distribution": {"positive": 2, "neutral": 1},
        },
    )
    resp = await client.get("/api/rss/sentiment_stats")
    assert resp.status_code == 200
    body = resp.json()
    assert body["analyzed_count"] == 3
    assert body["pending_count"] == 1


@pytest.mark.asyncio
async def test_anomalies_stats_endpoint_success(client, monkeypatch):
    import src.analysis.anomaly as anomaly_module

    monkeypatch.setattr(anomaly_module, "get_anomaly_stats", lambda: {"breakout": 4})
    resp = await client.get("/api/anomalies/stats")
    assert resp.status_code == 200
    assert resp.json()["breakout"] == 4


@pytest.mark.asyncio
async def test_integrity_check_endpoint_success(client, monkeypatch):
    import fetchers.integrity_checker as integrity_module

    monkeypatch.setattr(
        integrity_module,
        "generate_integrity_report",
        lambda: {"ok": True, "tables": []},
    )
    resp = await client.get("/api/integrity/check")
    assert resp.status_code == 200
    assert resp.json()["ok"] is True


@pytest.mark.asyncio
async def test_freshness_endpoint_success(client, monkeypatch):
    import fetchers.integrity_checker as integrity_module

    monkeypatch.setattr(
        integrity_module,
        "check_table_freshness",
        lambda: [{"table": "ts_daily", "latest_date": "2026-03-01"}],
    )
    resp = await client.get("/api/integrity/freshness")
    assert resp.status_code == 200
    body = resp.json()
    assert body["tables"][0]["table"] == "ts_daily"


@pytest.mark.asyncio
async def test_trading_day_endpoint_success(client, monkeypatch):
    import fetchers.trading_calendar as calendar_module

    monkeypatch.setattr(calendar_module, "is_trading_day", lambda _date: True)
    monkeypatch.setattr(calendar_module, "get_latest_trading_day", lambda: "2026-03-02")

    resp = await client.get("/api/calendar/is_trading_day?date=2026-03-03")
    assert resp.status_code == 200
    body = resp.json()
    assert body["date"] == "2026-03-03"
    assert body["is_trading_day"] is True
    assert body["latest_trading_day"] == "2026-03-02"
