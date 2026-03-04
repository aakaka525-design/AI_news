"""Batch translate Polymarket questions from English to Chinese via Google Translate."""

import logging
import time

from deep_translator import GoogleTranslator

from src.data_ingestion.polymarket.models import PolymarketMarket

logger = logging.getLogger(__name__)

BATCH_SIZE = 50


class MarketTranslator:
    """Translates Polymarket questions to Chinese using free Google Translate."""

    def __init__(self):
        self.translator = GoogleTranslator(source="en", target="zh-CN")

    def translate_markets(self, session_factory, limit: int = 500) -> int:
        """Find untranslated markets and translate them.

        Returns count of successfully translated markets.
        """
        with session_factory() as session:
            untranslated = (
                session.query(PolymarketMarket)
                .filter(
                    PolymarketMarket.question_zh.is_(None),
                    PolymarketMarket.active.is_(True),
                )
                .limit(limit)
                .all()
            )

            if not untranslated:
                return 0

            logger.info(f"Translating {len(untranslated)} markets")
            total = 0

            for i in range(0, len(untranslated), BATCH_SIZE):
                batch = untranslated[i : i + BATCH_SIZE]
                questions = [m.question for m in batch]

                try:
                    translations = self.translator.translate_batch(questions)
                except Exception as e:
                    logger.error(f"Translation batch {i // BATCH_SIZE + 1} failed: {e}")
                    # Fallback: translate one by one
                    translations = []
                    for q in questions:
                        try:
                            translations.append(self.translator.translate(q))
                        except Exception as e:
                            logger.warning(f"Single translation failed for '{q[:50]}': {e}")
                            translations.append(None)

                for market, zh in zip(batch, translations):
                    if zh and isinstance(zh, str) and zh.strip():
                        market.question_zh = zh.strip()
                        total += 1

                session.commit()
                logger.info(
                    f"Translated batch {i // BATCH_SIZE + 1}: "
                    f"{total} done so far"
                )
                # Small delay to be polite to Google
                if i + BATCH_SIZE < len(untranslated):
                    time.sleep(1)

        return total
