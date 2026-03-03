"""Tests for Polymarket ORM models."""

import json
import pytest
from sqlalchemy import create_engine, inspect
from sqlalchemy.orm import sessionmaker

from src.data_ingestion.polymarket.models import (
    PolymarketBase,
    PolymarketMarket,
    PolymarketSnapshot,
)


@pytest.fixture()
def engine():
    eng = create_engine("sqlite:///:memory:")
    PolymarketBase.metadata.create_all(eng)
    yield eng
    eng.dispose()


@pytest.fixture()
def session(engine):
    Session = sessionmaker(bind=engine, expire_on_commit=False)
    with Session() as s:
        yield s


class TestPolymarketMarket:
    def test_tables_created(self, engine):
        tables = inspect(engine).get_table_names()
        assert "polymarket_markets" in tables
        assert "polymarket_snapshots" in tables

    def test_insert_market(self, session):
        m = PolymarketMarket(
            condition_id="0xabc123",
            question="Will BTC reach $100k?",
            description="Test market",
            tags=json.dumps(["crypto"]),
            outcomes=json.dumps(["Yes", "No"]),
            clob_token_ids=json.dumps(["token1", "token2"]),
            image="https://example.com/img.png",
            end_date="2026-12-31T00:00:00Z",
            active=True,
            closed=False,
        )
        session.add(m)
        session.commit()

        result = session.get(PolymarketMarket, "0xabc123")
        assert result is not None
        assert result.question == "Will BTC reach $100k?"
        assert json.loads(result.tags) == ["crypto"]

    def test_upsert_market_updates_on_conflict(self, session):
        m = PolymarketMarket(
            condition_id="0xabc123",
            question="Old question",
            active=True,
            closed=False,
        )
        session.add(m)
        session.commit()

        session.merge(PolymarketMarket(
            condition_id="0xabc123",
            question="New question",
            active=False,
            closed=True,
        ))
        session.commit()

        result = session.get(PolymarketMarket, "0xabc123")
        assert result.question == "New question"
        assert result.active is False


class TestPolymarketSnapshot:
    def test_insert_snapshot(self, session):
        m = PolymarketMarket(
            condition_id="0xabc123",
            question="Test",
            active=True,
            closed=False,
        )
        session.add(m)
        session.commit()

        snap = PolymarketSnapshot(
            market_id="0xabc123",
            outcome_prices=json.dumps([0.65, 0.35]),
        )
        session.add(snap)
        session.commit()

        assert snap.id is not None
        assert json.loads(snap.outcome_prices) == [0.65, 0.35]
        assert snap.snapshot_time is not None
