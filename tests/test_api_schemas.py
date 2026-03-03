"""API response schema tests."""

import pytest
from api.schemas import (
    ErrorResponse,
    HealthResponse,
    NewsItem,
    NewsListResponse,
    WebhookResponse,
)
from pydantic import ValidationError


def test_health_response_fields():
    resp = HealthResponse(
        status="healthy",
        db={"ok": True, "error": None},
        scheduler={"running": True, "error": None},
        version="2.0.0",
    )
    assert resp.status == "healthy"
    assert resp.db.ok is True
    assert resp.scheduler.running is True
    assert resp.version == "2.0.0"


def test_health_response_rejects_legacy_flat_shape():
    with pytest.raises(ValidationError):
        HealthResponse(
            status="healthy",
            db="connected",
            scheduler="active",
            version="2.0.0",
        )


def test_news_list_response():
    item = NewsItem(
        id=1,
        title="Test",
        content="Content",
        content_html="<p>Content</p>",
        received_at="2026-03-01T00:00:00",
    )
    resp = NewsListResponse(total=1, data=[item])
    assert resp.total == 1
    assert len(resp.data) == 1


def test_webhook_response():
    resp = WebhookResponse(status="success", message="saved", news_id=42)
    assert resp.news_id == 42


def test_error_response():
    resp = ErrorResponse(error="not found", type="NotFoundError")
    assert resp.error == "not found"
