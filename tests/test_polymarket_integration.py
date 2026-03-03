"""End-to-end integration test for Polymarket pipeline."""

import json
import pytest
from unittest.mock import MagicMock, patch
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.database.engine import get_session_factory
from src.database.repositories.news import NewsRepository, _Base as NewsBase
from src.data_ingestion.polymarket.models import PolymarketBase, PolymarketSnapshot
from src.data_ingestion.polymarket.fetcher import PolymarketFetcher


@pytest.fixture()
def engine():
    eng = create_engine("sqlite:///:memory:")
    NewsBase.metadata.create_all(eng)
    PolymarketBase.metadata.create_all(eng)
    yield eng
    eng.dispose()


@pytest.fixture()
def Session(engine):
    return get_session_factory(engine)


@pytest.fixture()
def repo(Session):
    return NewsRepository(Session)


class TestE2E:
    @patch("src.data_ingestion.polymarket.fetcher.PolymarketClient")
    def test_full_pipeline_detects_volatility_and_writes_news(self, MockClient, Session, repo):
        """Simulate two fetches: first creates baseline, second detects volatility."""
        mock_client = MagicMock()
        MockClient.return_value = mock_client

        # First fetch: 50/50 market
        mock_client.get_active_markets.return_value = [{
            "condition_id": "0xe2e",
            "question": "Will AI surpass humans by 2030?",
            "outcomes": ["Yes", "No"],
            "prices": [0.50, 0.50],
            "description": "Test", "tags": ["tech"], "clob_token_ids": ["t1", "t2"],
            "image": "", "end_date": "2030-01-01T00:00:00Z", "active": True, "closed": False,
        }]

        fetcher = PolymarketFetcher(Session, repo, threshold=0.10)
        count1 = fetcher.run()
        assert count1 == 0  # first fetch, no baseline to compare

        # Second fetch: big move to 75/25
        mock_client.get_active_markets.return_value = [{
            "condition_id": "0xe2e",
            "question": "Will AI surpass humans by 2030?",
            "outcomes": ["Yes", "No"],
            "prices": [0.75, 0.25],
            "description": "Test", "tags": ["tech"], "clob_token_ids": ["t1", "t2"],
            "image": "", "end_date": "2030-01-01T00:00:00Z", "active": True, "closed": False,
        }]

        count2 = fetcher.run()
        assert count2 >= 1  # should detect 25% move on at least one outcome

        # Verify news was written
        news = repo.get_news_list(limit=10)
        assert len(news) >= 1
        assert any("Will AI surpass humans" in n["title"] for n in news)

    @patch("src.data_ingestion.polymarket.fetcher.PolymarketClient")
    def test_disabled_fetcher_writes_nothing(self, MockClient, Session, repo):
        fetcher = PolymarketFetcher(Session, repo, enabled=False)
        count = fetcher.run()
        assert count == 0
        assert repo.get_news_list() == []
