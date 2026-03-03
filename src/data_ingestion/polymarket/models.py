"""Polymarket ORM models for the news database."""

from datetime import datetime, timezone

from sqlalchemy import (
    Column, String, Text, Boolean, Integer, BigInteger,
    DateTime, Index,
)
from sqlalchemy.orm import DeclarativeBase


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class PolymarketBase(DeclarativeBase):
    """Declarative base for Polymarket tables (lives in news.db)."""
    pass


class PolymarketMarket(PolymarketBase):
    """Polymarket prediction market metadata."""

    __tablename__ = "polymarket_markets"

    condition_id = Column(String(256), primary_key=True)
    question = Column(Text, nullable=False)
    description = Column(Text, nullable=True)
    tags = Column(Text, nullable=True)          # JSON string: ["crypto", "politics"]
    outcomes = Column(Text, nullable=True)       # JSON string: ["Yes", "No"]
    clob_token_ids = Column(Text, nullable=True) # JSON string: ["token1", "token2"]
    image = Column(String(512), nullable=True)
    end_date = Column(String(64), nullable=True)
    active = Column(Boolean, default=True)
    closed = Column(Boolean, default=False)
    created_at = Column(DateTime, default=_utcnow)
    updated_at = Column(DateTime, default=_utcnow, onupdate=_utcnow)


class PolymarketSnapshot(PolymarketBase):
    """Price snapshot for volatility detection."""

    __tablename__ = "polymarket_snapshots"

    id = Column(BigInteger().with_variant(Integer, "sqlite"), primary_key=True, autoincrement=True)
    market_id = Column(String(256), nullable=False, index=True)
    outcome_prices = Column(Text, nullable=False)  # JSON string: [0.65, 0.35]
    snapshot_time = Column(DateTime, default=_utcnow)

    __table_args__ = (
        Index("idx_snap_market_time", "market_id", "snapshot_time"),
    )
