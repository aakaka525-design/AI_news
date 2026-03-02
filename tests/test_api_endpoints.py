#!/usr/bin/env python3
"""
Integration tests for FastAPI API endpoints.

Uses httpx.AsyncClient with ASGITransport against a temporary SQLite database
so every test run is fully isolated.
"""

import sqlite3
from pathlib import Path
from unittest.mock import MagicMock, patch

import httpx
import pytest
import pytest_asyncio
from httpx import ASGITransport


def _create_tables(db_path: Path):
    """Create the same schema that api.main.init_db() would create."""
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("""
        CREATE TABLE IF NOT EXISTS news (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            content TEXT NOT NULL,
            cleaned_data TEXT,
            hotspots TEXT,
            keywords TEXT,
            received_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_received_at ON news(received_at DESC)
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS analysis_results (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT NOT NULL,
            input_count INTEGER,
            analysis_summary TEXT,
            opportunities TEXT,
            analyzed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_analysis_date ON analysis_results(date)
    """)
    conn.commit()
    conn.close()


@pytest_asyncio.fixture()
async def client(tmp_path: Path):
    """
    Yield an ``httpx.AsyncClient`` wired to the FastAPI app with:
      - DB_PATH pointed at a fresh temporary database (tables pre-created)
      - Scheduler calls stubbed out (no real APScheduler activity)
      - AI analyser disabled
    """
    tmp_db = tmp_path / "test_news.db"
    _create_tables(tmp_db)

    # Patch DB_PATH and heavy side-effects in the startup event.
    with (
        patch("api.main.DB_PATH", tmp_db),
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
