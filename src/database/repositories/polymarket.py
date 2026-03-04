"""Polymarket repository — data access layer for prediction market data."""

from __future__ import annotations

import json
from typing import Any, Optional

from sqlalchemy import func
from sqlalchemy.orm import sessionmaker

from src.data_ingestion.polymarket.models import PolymarketMarket, PolymarketSnapshot


class PolymarketRepository:
    """Read-only queries for Polymarket tables (polymarket_markets, polymarket_snapshots)."""

    def __init__(self, session_factory: sessionmaker) -> None:
        self.Session = session_factory

    def get_active_markets(self, limit: int = 50) -> list[dict[str, Any]]:
        """Return active markets with their latest price snapshot (single JOIN query)."""
        with self.Session() as session:
            # Subquery: latest snapshot id per market
            latest_snap_sq = (
                session.query(
                    PolymarketSnapshot.market_id,
                    func.max(PolymarketSnapshot.id).label("max_id"),
                )
                .group_by(PolymarketSnapshot.market_id)
                .subquery()
            )

            rows = (
                session.query(PolymarketMarket, PolymarketSnapshot)
                .outerjoin(
                    latest_snap_sq,
                    PolymarketMarket.condition_id == latest_snap_sq.c.market_id,
                )
                .outerjoin(
                    PolymarketSnapshot,
                    PolymarketSnapshot.id == latest_snap_sq.c.max_id,
                )
                .filter(PolymarketMarket.active.is_(True))
                .order_by(PolymarketMarket.updated_at.desc())
                .limit(limit)
                .all()
            )

            results = []
            for m, snap in rows:
                outcome_prices = None
                if snap and snap.outcome_prices:
                    try:
                        outcome_prices = json.loads(snap.outcome_prices)
                    except (json.JSONDecodeError, TypeError):
                        pass

                results.append({
                    "condition_id": m.condition_id,
                    "question": m.question,
                    "question_zh": m.question_zh,
                    "description": m.description,
                    "tags": _parse_json(m.tags),
                    "outcomes": _parse_json(m.outcomes),
                    "outcome_prices": outcome_prices,
                    "image": m.image,
                    "end_date": m.end_date,
                    "active": m.active,
                    "closed": m.closed,
                    "created_at": m.created_at.isoformat() if m.created_at else None,
                    "updated_at": m.updated_at.isoformat() if m.updated_at else None,
                })
            return results

    def get_market_detail(self, condition_id: str) -> Optional[dict[str, Any]]:
        """Return a single market with its latest snapshot."""
        with self.Session() as session:
            m = session.get(PolymarketMarket, condition_id)
            if m is None:
                return None

            latest_snap = (
                session.query(PolymarketSnapshot)
                .filter(PolymarketSnapshot.market_id == condition_id)
                .order_by(PolymarketSnapshot.snapshot_time.desc())
                .first()
            )
            outcome_prices = None
            if latest_snap and latest_snap.outcome_prices:
                try:
                    outcome_prices = json.loads(latest_snap.outcome_prices)
                except (json.JSONDecodeError, TypeError):
                    pass

            return {
                "condition_id": m.condition_id,
                "question": m.question,
                "question_zh": m.question_zh,
                "description": m.description,
                "tags": _parse_json(m.tags),
                "outcomes": _parse_json(m.outcomes),
                "clob_token_ids": _parse_json(m.clob_token_ids),
                "outcome_prices": outcome_prices,
                "image": m.image,
                "end_date": m.end_date,
                "active": m.active,
                "closed": m.closed,
                "created_at": m.created_at.isoformat() if m.created_at else None,
                "updated_at": m.updated_at.isoformat() if m.updated_at else None,
            }

    def get_price_history(
        self, condition_id: str, limit: int = 100
    ) -> list[dict[str, Any]]:
        """Return price snapshots for a market, newest first."""
        with self.Session() as session:
            snapshots = (
                session.query(PolymarketSnapshot)
                .filter(PolymarketSnapshot.market_id == condition_id)
                .order_by(PolymarketSnapshot.snapshot_time.desc())
                .limit(limit)
                .all()
            )
            results = []
            for s in snapshots:
                prices = None
                try:
                    prices = json.loads(s.outcome_prices)
                except (json.JSONDecodeError, TypeError):
                    pass
                results.append({
                    "id": s.id,
                    "market_id": s.market_id,
                    "outcome_prices": prices,
                    "snapshot_time": s.snapshot_time.isoformat() if s.snapshot_time else None,
                })
            return results


def _parse_json(val: Optional[str]) -> Any:
    """Parse a JSON string, returning None on failure."""
    if not val:
        return None
    try:
        return json.loads(val)
    except (json.JSONDecodeError, TypeError):
        return val
