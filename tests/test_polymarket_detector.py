"""Tests for Polymarket volatility detector."""

import json
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.data_ingestion.polymarket.models import (
    PolymarketBase, PolymarketMarket, PolymarketSnapshot,
)
from src.data_ingestion.polymarket.detector import VolatilityDetector


@pytest.fixture()
def engine():
    eng = create_engine("sqlite:///:memory:")
    PolymarketBase.metadata.create_all(eng)
    yield eng
    eng.dispose()


@pytest.fixture()
def Session(engine):
    return sessionmaker(bind=engine, expire_on_commit=False)


@pytest.fixture()
def detector(Session):
    return VolatilityDetector(Session, threshold=0.10)


class TestDetectVolatility:
    def test_no_previous_snapshot_no_alert(self, detector, Session):
        """First snapshot ever — no alert."""
        market_data = {
            "condition_id": "0xabc",
            "question": "Test?",
            "outcomes": ["Yes", "No"],
            "prices": [0.7, 0.3],
        }
        alerts = detector.detect([market_data])
        assert alerts == []

    def test_small_change_no_alert(self, detector, Session):
        """5% change — below threshold, no alert."""
        with Session() as s:
            s.add(PolymarketMarket(condition_id="0xabc", question="Test?", active=True, closed=False))
            s.add(PolymarketSnapshot(
                market_id="0xabc",
                outcome_prices=json.dumps([0.70, 0.30]),
            ))
            s.commit()

        alerts = detector.detect([{
            "condition_id": "0xabc",
            "question": "Test?",
            "outcomes": ["Yes", "No"],
            "prices": [0.75, 0.25],
        }])
        assert alerts == []

    def test_large_change_triggers_alert(self, detector, Session):
        """15% change — above threshold, should alert.

        Both outcomes move by 15% (Yes 50->65, No 50->35), so two alerts
        are generated.
        """
        with Session() as s:
            s.add(PolymarketMarket(condition_id="0xabc", question="Will X happen?", active=True, closed=False))
            s.add(PolymarketSnapshot(
                market_id="0xabc",
                outcome_prices=json.dumps([0.50, 0.50]),
            ))
            s.commit()

        alerts = detector.detect([{
            "condition_id": "0xabc",
            "question": "Will X happen?",
            "outcomes": ["Yes", "No"],
            "prices": [0.65, 0.35],
        }])
        assert len(alerts) == 2
        assert "Will X happen?" in alerts[0]["title"]
        assert "Yes" in alerts[0]["content"]
        assert "No" in alerts[1]["content"]

    def test_snapshot_is_saved(self, detector, Session):
        """After detection, new snapshot should be persisted."""
        detector.detect([{
            "condition_id": "0xnew",
            "question": "New market?",
            "outcomes": ["Yes", "No"],
            "prices": [0.80, 0.20],
        }])

        with Session() as s:
            snaps = s.query(PolymarketSnapshot).filter_by(market_id="0xnew").all()
            assert len(snaps) == 1
            assert json.loads(snaps[0].outcome_prices) == [0.80, 0.20]
