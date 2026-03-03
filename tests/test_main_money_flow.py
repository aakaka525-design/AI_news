"""Tests for main money flow fetcher reliability fixes."""

import pytest

from fetchers import main_money_flow


class _DummyConn:
    def __init__(self):
        self.committed = False
        self.closed = False

    def commit(self):
        self.committed = True

    def close(self):
        self.closed = True


class _DummyRecord:
    def __init__(self, data: dict):
        self._data = data

    def model_dump(self, exclude_none: bool = False):
        return self._data


def test_save_money_flows_does_not_require_missing_models_module(monkeypatch):
    conn = _DummyConn()
    monkeypatch.setattr(main_money_flow, "get_connection", lambda: conn)

    import fetchers.db as fetcher_db

    monkeypatch.setattr(
        fetcher_db,
        "validate_and_create",
        lambda _model_class, data: _DummyRecord(data),
    )
    monkeypatch.setattr(
        fetcher_db,
        "insert_validated",
        lambda _conn, _table, _record, _keys: True,
    )

    saved = main_money_flow.save_money_flows(
        [{"stock_code": "000001", "date": "2026-03-01", "main_net_inflow": 12.3}],
    )

    assert saved == 1
    assert conn.committed is True
    assert conn.closed is True


@pytest.mark.asyncio
async def test_fetch_concurrent_does_not_disable_ssl_verification(monkeypatch):
    connector_kwargs = {}

    class _FakeConnector:
        def __init__(self, *args, **kwargs):
            connector_kwargs.update(kwargs)

    class _FakeClientSession:
        def __init__(self, connector):
            self.connector = connector

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

    class _ProxyPool:
        def __init__(self):
            self.proxies = ["proxy-1"]

        def is_expired(self):
            return False

        def ensure_proxies(self):
            return None

    async def _fake_fetch_single_money_flow(_session, _code, _pool, _days):
        return []

    monkeypatch.setattr(main_money_flow.aiohttp, "TCPConnector", _FakeConnector)
    monkeypatch.setattr(main_money_flow.aiohttp, "ClientSession", _FakeClientSession)
    monkeypatch.setattr(main_money_flow, "fetch_single_money_flow", _fake_fetch_single_money_flow)
    monkeypatch.setattr(main_money_flow, "save_money_flows", lambda _records: 0)

    await main_money_flow.fetch_concurrent(["000001"], _ProxyPool(), days=1)

    assert connector_kwargs.get("ssl") is not False
