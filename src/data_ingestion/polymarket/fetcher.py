"""Polymarket fetcher — entry point for the scheduler task."""

import logging

from sqlalchemy.orm import sessionmaker

from config.settings import POLYMARKET_ENABLED, POLYMARKET_VOLATILITY_THRESHOLD
from src.data_ingestion.polymarket.client import PolymarketClient
from src.data_ingestion.polymarket.detector import VolatilityDetector
from src.data_ingestion.polymarket.models import PolymarketBase
from src.data_ingestion.polymarket.translator import MarketTranslator

logger = logging.getLogger(__name__)


class PolymarketFetcher:
    """Orchestrates: fetch markets -> detect volatility -> translate -> write news."""

    def __init__(
        self,
        session_factory: sessionmaker,
        news_repo,
        threshold: float | None = None,
        enabled: bool | None = None,
    ):
        self.session_factory = session_factory
        self.news_repo = news_repo
        self.enabled = enabled if enabled is not None else POLYMARKET_ENABLED
        _threshold = threshold if threshold is not None else POLYMARKET_VOLATILITY_THRESHOLD
        self.client = PolymarketClient()
        self.detector = VolatilityDetector(session_factory, threshold=_threshold)
        try:
            self.translator = MarketTranslator()
        except Exception as e:
            logger.warning(f"Polymarket translator init failed (non-fatal): {e}")
            self.translator = None

    def ensure_tables(self, engine) -> None:
        """Create Polymarket tables if they don't exist (idempotent)."""
        PolymarketBase.metadata.create_all(engine)

    def run(self) -> int:
        """Fetch, detect, translate, and write alerts. Returns count of alerts generated."""
        if not self.enabled:
            logger.info("Polymarket fetcher is disabled, skipping")
            return 0

        try:
            markets = self.client.get_active_markets()
        except Exception as e:
            logger.error(f"Polymarket fetch failed: {e}")
            return 0

        if not markets:
            logger.info("Polymarket: no active markets found")
            return 0

        try:
            alerts = self.detector.detect(markets)
        except Exception as e:
            logger.error(f"Polymarket detect failed: {e}")
            return 0

        # Translate untranslated markets (best-effort, won't block on failure)
        if self.translator is not None:
            try:
                translated = self.translator.translate_markets(self.session_factory)
                if translated:
                    logger.info(f"Polymarket: translated {translated} markets to Chinese")
            except Exception as e:
                logger.warning(f"Polymarket translation failed (non-fatal): {e}")

        for alert in alerts:
            self.news_repo.insert_news(
                title=alert["title"],
                content=alert["content"],
                hotspots="polymarket,预测市场",
                keywords=alert.get("source", "polymarket"),
                source="polymarket",
            )

        if alerts:
            logger.info(f"Polymarket: generated {len(alerts)} news alerts")
        return len(alerts)
