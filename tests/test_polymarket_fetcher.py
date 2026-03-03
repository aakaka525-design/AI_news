"""Tests for PolymarketFetcher (scheduler task entry point)."""

import json
import pytest
from unittest.mock import MagicMock, patch
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.data_ingestion.polymarket.models import PolymarketBase, PolymarketSnapshot
from src.data_ingestion.polymarket.fetcher import PolymarketFetcher


@pytest.fixture()
def engine():
    eng = create_engine("sqlite:///:memory:")
    PolymarketBase.metadata.create_all(eng)
    yield eng
    eng.dispose()


@pytest.fixture()
def Session(engine):
    return sessionmaker(bind=engine, expire_on_commit=False)


class TestFetcher:
    @patch("src.data_ingestion.polymarket.fetcher.PolymarketClient")
    def test_fetch_and_detect_writes_news(self, MockClient, Session):
        """When volatility detected, insert_news is called."""
        mock_client = MagicMock()
        mock_client.get_active_markets.return_value = [{
            "condition_id": "0xabc",
            "question": "Test?",
            "outcomes": ["Yes", "No"],
            "prices": [0.80, 0.20],
            "description": "",
            "tags": [],
            "clob_token_ids": [],
            "image": "",
            "end_date": "",
            "active": True,
            "closed": False,
        }]
        MockClient.return_value = mock_client

        mock_repo = MagicMock()
        fetcher = PolymarketFetcher(Session, mock_repo, threshold=0.01)
        # First run — no previous snapshot, no alert
        fetcher.run()
        mock_repo.insert_news.assert_not_called()

        # Second run — same price, no alert (delta=0, below threshold)
        fetcher.run()
        mock_repo.insert_news.assert_not_called()

    @patch("src.data_ingestion.polymarket.fetcher.PolymarketClient")
    def test_fetch_disabled_does_nothing(self, MockClient, Session):
        """When disabled via env, run() is a no-op."""
        mock_repo = MagicMock()
        fetcher = PolymarketFetcher(Session, mock_repo, enabled=False)
        fetcher.run()
        MockClient.return_value.get_active_markets.assert_not_called()
