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
