"""Polymarket SDK wrapper with pagination support."""

import logging
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError
from typing import Any

from py_clob_client.client import ClobClient

logger = logging.getLogger(__name__)

CLOB_HOST = "https://clob.polymarket.com"
# Cursors that indicate no more pages
END_CURSORS = {"DONE", "LTE="}  # "LTE=" is base64 for "-1"
MAX_PAGES = 50


class PolymarketClient:
    """Wraps py-clob-client SDK, handles pagination, normalizes data."""

    def __init__(self, host: str = CLOB_HOST, timeout: int = 30):
        self._sdk = ClobClient(host)
        self._timeout = timeout

    def get_active_markets(self) -> list[dict[str, Any]]:
        """Fetch all active (sampling) markets, auto-paginating.

        Returns a list of normalized market dicts with keys:
          condition_id, question, description, tags, outcomes, prices,
          clob_token_ids, image, end_date, active, closed
        """
        all_markets: list[dict[str, Any]] = []
        cursor = "MA=="
        page = 0

        try:
            while page < MAX_PAGES:
                page += 1
                # 设置超时保护，防止 SDK 调用永久挂起
                with ThreadPoolExecutor(max_workers=1) as pool:
                    future = pool.submit(self._sdk.get_sampling_markets, cursor)
                    try:
                        resp = future.result(timeout=self._timeout)
                    except FuturesTimeoutError:
                        raise TimeoutError(f"Polymarket SDK timeout after {self._timeout}s")
                data = resp.get("data", [])
                if not data:
                    break

                for raw in data:
                    all_markets.append(self._normalize(raw))

                cursor = resp.get("next_cursor", "DONE")
                if cursor in END_CURSORS or not cursor:
                    break
        except Exception as e:
            logger.error(
                f"Polymarket SDK error (fetched {len(all_markets)} markets so far): {e}"
            )

        logger.info(f"Polymarket: fetched {len(all_markets)} active markets")
        return all_markets

    @staticmethod
    def _normalize(raw: dict) -> dict[str, Any]:
        """Extract and flatten relevant fields from SDK response."""
        tokens = raw.get("tokens", [])
        return {
            "condition_id": raw.get("condition_id", ""),
            "question": raw.get("question", ""),
            "description": raw.get("description", ""),
            "tags": raw.get("tags", []),
            "outcomes": [t.get("outcome", "") for t in tokens],
            "prices": [float(t.get("price", 0) or 0) for t in tokens],
            "clob_token_ids": [t.get("token_id", "") for t in tokens],
            "image": raw.get("image", ""),
            "end_date": raw.get("end_date_iso", ""),
            "active": raw.get("active", False),
            "closed": raw.get("closed", False),
        }
