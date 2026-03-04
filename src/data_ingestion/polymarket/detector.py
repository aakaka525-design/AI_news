"""Volatility detector — compares snapshots to detect big price moves."""

import json
import logging
from typing import Any

from sqlalchemy import func
from sqlalchemy.orm import sessionmaker

from src.data_ingestion.polymarket.models import (
    PolymarketMarket,
    PolymarketSnapshot,
    _utcnow,
)

logger = logging.getLogger(__name__)


class VolatilityDetector:
    """Compares current prices with the last snapshot to detect volatility."""

    # Keep at most 288 snapshots per market (~24h at 5-min intervals)
    MAX_SNAPSHOTS_PER_MARKET = 288

    def __init__(self, session_factory: sessionmaker, threshold: float = 0.10):
        self.Session = session_factory
        self.threshold = threshold

    def detect(self, markets: list[dict[str, Any]]) -> list[dict[str, str]]:
        """Process market data, save snapshots, return alerts for big moves.

        Each market is processed in its own transaction so a single failure
        does not roll back all other markets.

        Each alert dict has keys: title, content, source.
        """
        alerts: list[dict[str, str]] = []

        for m in markets:
            try:
                market_alerts = self._process_market(m)
                alerts.extend(market_alerts)
            except Exception as e:
                logger.warning(
                    f"Market {m.get('condition_id', '?')} failed: {e}"
                )

        # Cleanup old snapshots
        self._cleanup_old_snapshots()

        return alerts

    def _cleanup_old_snapshots(self) -> None:
        """Remove old snapshots beyond MAX_SNAPSHOTS_PER_MARKET per market."""
        try:
            with self.Session() as session:
                # Find markets that have too many snapshots
                counts = (
                    session.query(
                        PolymarketSnapshot.market_id,
                        func.count(PolymarketSnapshot.id).label("cnt"),
                    )
                    .group_by(PolymarketSnapshot.market_id)
                    .having(func.count(PolymarketSnapshot.id) > self.MAX_SNAPSHOTS_PER_MARKET)
                    .all()
                )

                total_deleted = 0
                for market_id, cnt in counts:
                    excess = cnt - self.MAX_SNAPSHOTS_PER_MARKET
                    # Get IDs to delete (oldest first)
                    old_ids = (
                        session.query(PolymarketSnapshot.id)
                        .filter(PolymarketSnapshot.market_id == market_id)
                        .order_by(PolymarketSnapshot.snapshot_time.asc())
                        .limit(excess)
                        .all()
                    )
                    if old_ids:
                        ids_to_delete = [r[0] for r in old_ids]
                        session.query(PolymarketSnapshot).filter(
                            PolymarketSnapshot.id.in_(ids_to_delete)
                        ).delete(synchronize_session=False)
                        total_deleted += len(ids_to_delete)

                if total_deleted:
                    session.commit()
                    logger.info(f"Polymarket: cleaned up {total_deleted} old snapshots")
        except Exception as e:
            logger.warning(f"Snapshot cleanup failed (non-fatal): {e}")

    def _process_market(self, m: dict[str, Any]) -> list[dict[str, str]]:
        """Process a single market in its own session/transaction."""
        alerts: list[dict[str, str]] = []
        cid = m["condition_id"]
        prices = m["prices"]
        outcomes = m["outcomes"]
        question = m["question"]

        with self.Session() as session:
            # Get latest previous snapshot
            prev = (
                session.query(PolymarketSnapshot)
                .filter_by(market_id=cid)
                .order_by(PolymarketSnapshot.snapshot_time.desc())
                .first()
            )

            # JSON parse with protection
            prev_prices = None
            if prev:
                try:
                    prev_prices = json.loads(prev.outcome_prices)
                except (json.JSONDecodeError, TypeError):
                    prev_prices = None

            # Save new snapshot
            snap = PolymarketSnapshot(
                market_id=cid,
                outcome_prices=json.dumps(prices),
            )
            session.add(snap)

            # Upsert market record — use get+update to preserve question_zh
            existing = session.get(PolymarketMarket, cid)
            if existing:
                existing.question = question
                existing.description = m.get("description", "")
                existing.tags = json.dumps(m.get("tags", []))
                existing.outcomes = json.dumps(outcomes)
                existing.clob_token_ids = json.dumps(m.get("clob_token_ids", []))
                existing.image = m.get("image", "")
                existing.end_date = m.get("end_date", "")
                existing.active = m.get("active", True)
                existing.closed = m.get("closed", False)
                existing.updated_at = _utcnow()
            else:
                session.add(PolymarketMarket(
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
