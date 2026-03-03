"""Polymarket fetcher — entry point for the scheduler task."""

import logging
import os

from sqlalchemy.orm import sessionmaker

from src.data_ingestion.polymarket.client import PolymarketClient
from src.data_ingestion.polymarket.detector import VolatilityDetector
from src.data_ingestion.polymarket.models import PolymarketBase

logger = logging.getLogger(__name__)


class PolymarketFetcher:
    """Orchestrates: fetch markets -> detect volatility -> write news."""

    def __init__(
        self,
        session_factory: sessionmaker,
        news_repo,
        threshold: float | None = None,
        enabled: bool | None = None,
    ):
        self.news_repo = news_repo
        self.enabled = enabled if enabled is not None else (
            os.getenv("POLYMARKET_ENABLED", "true").lower() == "true"
        )
        _threshold = threshold if threshold is not None else float(
            os.getenv("POLYMARKET_VOLATILITY_THRESHOLD", "0.10")
        )
        self.client = PolymarketClient()
        self.detector = VolatilityDetector(session_factory, threshold=_threshold)

    def ensure_tables(self, engine) -> None:
        """Create Polymarket tables if they don't exist (idempotent)."""
        PolymarketBase.metadata.create_all(engine)

    def run(self) -> int:
        """Fetch, detect, and write alerts. Returns count of alerts generated."""
        if not self.enabled:
            logger.info("Polymarket fetcher is disabled, skipping")
            return 0

        markets = self.client.get_active_markets()
        if not markets:
            logger.info("Polymarket: no active markets found")
            return 0

        alerts = self.detector.detect(markets)

        for alert in alerts:
            self.news_repo.insert_news(
                title=alert["title"],
                content=alert["content"],
                hotspots="polymarket,预测市场",
                keywords=alert.get("source", "polymarket"),
            )

        if alerts:
            logger.info(f"Polymarket: generated {len(alerts)} news alerts")
        return len(alerts)
