#!/usr/bin/env python3
"""API 鉴权与生命周期策略测试。"""

import inspect
from fastapi import HTTPException
from fastapi.routing import APIRoute
import pytest

from api import main as api_main


def _route_requires_api_key(path: str, method: str) -> bool:
    for route in api_main.app.routes:
        if not isinstance(route, APIRoute):
            continue
        if route.path != path or method not in route.methods:
            continue
        return any(dep.call == api_main.verify_api_key for dep in route.dependant.dependencies)
    return False


@pytest.mark.asyncio
async def test_verify_api_key_rejects_misconfigured_required_mode(monkeypatch):
    monkeypatch.setattr(api_main, "API_KEY_REQUIRED", True)
    monkeypatch.setattr(api_main, "DASHBOARD_API_KEY", "")

    with pytest.raises(HTTPException) as exc:
        await api_main.verify_api_key(None)

    assert exc.value.status_code == 500


@pytest.mark.asyncio
async def test_verify_api_key_accepts_valid_value(monkeypatch):
    monkeypatch.setattr(api_main, "API_KEY_REQUIRED", True)
    monkeypatch.setattr(api_main, "DASHBOARD_API_KEY", "unit-test-key")

    result = await api_main.verify_api_key("unit-test-key")
    assert result == "unit-test-key"


def test_mutating_endpoints_are_protected():
    protected_routes = [
        ("/api/clean", "POST"),
        ("/api/analyze", "POST"),
        ("/api/rss/fetch", "POST"),
        ("/api/rss/analyze", "POST"),
        ("/api/research/fetch", "POST"),
        ("/api/anomalies/detect", "POST"),
        ("/api/scheduler/jobs", "GET"),
        ("/api/scheduler/trigger/{job_id}", "POST"),
        ("/api/scheduler/pause/{job_id}", "POST"),
        ("/api/scheduler/resume/{job_id}", "POST"),
        ("/api/scheduler/history/{job_id}", "GET"),
        ("/api/run_task", "POST"),
    ]
    for path, method in protected_routes:
        assert _route_requires_api_key(path, method), f"{method} {path} 未绑定鉴权依赖"


def test_app_uses_lifespan_instead_of_on_event():
    assert api_main.app.router.on_startup == []
    assert api_main.app.router.on_shutdown == []


def test_anomaly_api_imports_src_module():
    get_anomalies_source = inspect.getsource(api_main.get_anomalies)
    detect_anomalies_source = inspect.getsource(api_main.detect_anomalies)
    assert "src.analysis.anomaly" in get_anomalies_source
    assert "src.analysis.anomaly" in detect_anomalies_source
