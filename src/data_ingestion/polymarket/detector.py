"""Volatility detector — compares snapshots to detect big price moves."""

import json
import logging
from typing import Any

from sqlalchemy.orm import sessionmaker

from src.data_ingestion.polymarket.models import (
    PolymarketMarket,
    PolymarketSnapshot,
)

logger = logging.getLogger(__name__)


class VolatilityDetector:
    """Compares current prices with the last snapshot to detect volatility."""

    def __init__(self, session_factory: sessionmaker, threshold: float = 0.10):
        self.Session = session_factory
        self.threshold = threshold

    def detect(self, markets: list[dict[str, Any]]) -> list[dict[str, str]]:
        """Process market data, save snapshots, return alerts for big moves.

        Each alert dict has keys: title, content, source.
        """
        alerts: list[dict[str, str]] = []

        with self.Session() as session:
            for m in markets:
                cid = m["condition_id"]
                prices = m["prices"]
                outcomes = m["outcomes"]
                question = m["question"]

                # Get latest previous snapshot
                prev = (
                    session.query(PolymarketSnapshot)
                    .filter_by(market_id=cid)
                    .order_by(PolymarketSnapshot.snapshot_time.desc())
                    .first()
                )

                prev_prices = json.loads(prev.outcome_prices) if prev else None

                # Save new snapshot
                snap = PolymarketSnapshot(
                    market_id=cid,
                    outcome_prices=json.dumps(prices),
                )
                session.add(snap)

                # Upsert market record
                session.merge(PolymarketMarket(
                    condition_id=cid,
                    question=question,
                    description=m.get("description", ""),
                    tags=json.dumps(m.get("tags", [])),
                    outcomes=json.dumps(outcomes),
                    clob_token_ids=json.dumps(m.get("clob_token_ids", [])),
                    image=m.get("image", ""),
                    end_date=m.get("end_date", ""),
                    active=m.get("active", True),
                    closed=m.get("closed", False),
                ))

                # Compare
                if prev_prices and len(prev_prices) == len(prices):
                    for i, outcome in enumerate(outcomes):
                        delta = prices[i] - prev_prices[i]
                        if abs(delta) >= self.threshold:
                            direction = "\u2191" if delta > 0 else "\u2193"
                            alerts.append({
                                "title": f"\u9884\u6d4b\u5e02\u573a\u6ce2\u52a8: {question}",
                                "content": (
                                    f"'{outcome}' \u6982\u7387\u4ece {prev_prices[i]:.0%} "
                                    f"\u53d8\u4e3a {prices[i]:.0%} ({direction}{abs(delta):.0%})"
                                ),
                                "source": "polymarket",
                            })
                            logger.info(
                                f"Polymarket alert: {question} "
                                f"{outcome} {prev_prices[i]:.0%}->{prices[i]:.0%}"
                            )

            session.commit()

        return alerts
