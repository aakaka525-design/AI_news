"""API exception middleware tests."""

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from api.middleware import register_exception_handlers
from src.exceptions import AppError, DatabaseError, DataFetchError


@pytest.fixture
def test_app():
    """Create a minimal FastAPI app with exception handlers."""
    app = FastAPI()
    register_exception_handlers(app)

    @app.get("/trigger-app-error")
    async def trigger_app():
        raise AppError("general app error")

    @app.get("/trigger-data-error")
    async def trigger_data():
        raise DataFetchError("tushare down", source="tushare", code="000001.SZ")

    @app.get("/trigger-db-error")
    async def trigger_db():
        raise DatabaseError("insert failed", table="ts_daily")

    @app.get("/trigger-unexpected")
    async def trigger_unexpected():
        raise RuntimeError("unexpected crash")

    return app


@pytest.mark.asyncio
async def test_app_error_returns_400(test_app):
    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        resp = await c.get("/trigger-app-error")
        assert resp.status_code == 400
        data = resp.json()
        assert "error" in data
        assert data["error"] == "general app error"


@pytest.mark.asyncio
async def test_data_fetch_error_returns_502(test_app):
    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        resp = await c.get("/trigger-data-error")
        assert resp.status_code == 502
        data = resp.json()
        assert data["source"] == "tushare"


@pytest.mark.asyncio
async def test_database_error_returns_503(test_app):
    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        resp = await c.get("/trigger-db-error")
        assert resp.status_code == 503
        data = resp.json()
        assert data["table"] == "ts_daily"


@pytest.mark.asyncio
async def test_unexpected_error_returns_500(test_app):
    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        resp = await c.get("/trigger-unexpected")
        assert resp.status_code == 500
        data = resp.json()
        assert "error" in data
