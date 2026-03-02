"""Tushare client tests (P0) -- tests decorators and adapter patterns without real API calls."""
import time
from unittest.mock import MagicMock, patch

import pytest

from src.utils.rate_limiter import TokenBucket, rate_limit


class TestRateLimitDecorator:
    def test_rate_limit_allows_burst(self):
        """Burst of calls within capacity should complete instantly."""
        bucket = TokenBucket(rate=100.0, capacity=10)
        call_count = 0

        @rate_limit(bucket=bucket)
        def fast_call():
            nonlocal call_count
            call_count += 1
            return call_count

        start = time.monotonic()
        for _ in range(10):
            fast_call()
        elapsed = time.monotonic() - start
        assert call_count == 10
        assert elapsed < 1.0

    def test_rate_limit_throttles_beyond_capacity(self):
        """Calls exceeding bucket capacity must block until tokens refill."""
        bucket = TokenBucket(rate=10.0, capacity=2)
        call_count = 0

        @rate_limit(bucket=bucket)
        def throttled_call():
            nonlocal call_count
            call_count += 1

        start = time.monotonic()
        for _ in range(4):
            throttled_call()
        elapsed = time.monotonic() - start
        assert call_count == 4
        assert elapsed >= 0.1


class TestRetryWithBackoff:
    def test_retry_succeeds_after_failures(self):
        """Function should succeed on the third attempt after two failures."""
        from src.utils.retry import retry

        attempts = 0

        @retry(max_attempts=3, delay=0.01)
        def flaky():
            nonlocal attempts
            attempts += 1
            if attempts < 3:
                raise ConnectionError("timeout")
            return "success"

        assert flaky() == "success"
        assert attempts == 3

    def test_retry_exhausts_attempts(self):
        """After exhausting all attempts the last exception must propagate."""
        from src.utils.retry import retry

        @retry(max_attempts=2, delay=0.01)
        def always_fail():
            raise ValueError("permanent")

        with pytest.raises(ValueError, match="permanent"):
            always_fail()
