"""Tests for PolymarketClient (SDK wrapper with pagination)."""

import pytest
from unittest.mock import MagicMock, patch

from src.data_ingestion.polymarket.client import PolymarketClient


@pytest.fixture()
def client():
    return PolymarketClient()


class TestGetActiveMarkets:
    def test_returns_list_of_markets(self, client):
        """Mock SDK to return one page of data."""
        fake_market = {
            "condition_id": "0xabc",
            "question": "Test?",
            "description": "desc",
            "tags": ["crypto"],
            "tokens": [
                {"token_id": "t1", "outcome": "Yes", "price": 0.7},
                {"token_id": "t2", "outcome": "No", "price": 0.3},
            ],
            "active": True,
            "closed": False,
            "image": "https://img.png",
            "end_date_iso": "2026-12-31T00:00:00Z",
        }
        mock_sdk = MagicMock()
        mock_sdk.get_sampling_markets.return_value = {
            "data": [fake_market],
            "next_cursor": "DONE",
            "count": 1,
        }
        client._sdk = mock_sdk

        markets = client.get_active_markets()

        assert len(markets) == 1
        assert markets[0]["condition_id"] == "0xabc"
        assert markets[0]["outcomes"] == ["Yes", "No"]
        assert markets[0]["prices"] == [0.7, 0.3]

    def test_pagination_fetches_all_pages(self, client):
        """Mock SDK to return two pages."""
        page1_market = {"condition_id": "0x1", "question": "Q1", "tokens": [
            {"token_id": "t1", "outcome": "Yes", "price": 0.5},
        ], "active": True, "closed": False, "tags": [], "description": "", "image": "", "end_date_iso": ""}
        page2_market = {"condition_id": "0x2", "question": "Q2", "tokens": [
            {"token_id": "t2", "outcome": "Yes", "price": 0.6},
        ], "active": True, "closed": False, "tags": [], "description": "", "image": "", "end_date_iso": ""}

        call_count = 0
        def fake_get(cursor="MA=="):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return {"data": [page1_market], "next_cursor": "PAGE2", "count": 1}
            return {"data": [page2_market], "next_cursor": "DONE", "count": 1}

        mock_sdk = MagicMock()
        mock_sdk.get_sampling_markets.side_effect = fake_get
        client._sdk = mock_sdk

        markets = client.get_active_markets()
        assert len(markets) == 2

    def test_empty_response(self, client):
        mock_sdk = MagicMock()
        mock_sdk.get_sampling_markets.return_value = {
            "data": [], "next_cursor": "DONE", "count": 0
        }
        client._sdk = mock_sdk

        markets = client.get_active_markets()
        assert markets == []
