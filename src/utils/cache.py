"""CacheService abstraction — memory-backed via cachetools, Redis-ready interface."""

import logging
from typing import Any, Optional

from cachetools import TTLCache

logger = logging.getLogger(__name__)

# Default: 512 entries, 5-minute TTL
_DEFAULT_MAXSIZE = 512
_DEFAULT_TTL = 300


class CacheService:
    """Simple cache with get/set/invalidate/invalidate_prefix."""

    def __init__(self, maxsize: int = _DEFAULT_MAXSIZE, ttl: int = _DEFAULT_TTL):
        self._cache: TTLCache = TTLCache(maxsize=maxsize, ttl=ttl)

    def get(self, key: str) -> Optional[Any]:
        val = self._cache.get(key)
        if val is not None:
            logger.debug("cache_hit key=%s", key)
        return val

    def set(self, key: str, value: Any) -> None:
        self._cache[key] = value

    def invalidate(self, key: str) -> bool:
        try:
            del self._cache[key]
            return True
        except KeyError:
            return False

    def invalidate_prefix(self, prefix: str) -> int:
        """Remove all keys starting with *prefix*."""
        to_delete = [k for k in self._cache if k.startswith(prefix)]
        for k in to_delete:
            del self._cache[k]
        return len(to_delete)

    def clear(self) -> None:
        self._cache.clear()


# Global singleton
cache = CacheService()
