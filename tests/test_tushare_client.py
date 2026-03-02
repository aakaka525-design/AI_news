"""Tushare client tests (P0) -- tests decorators and adapter patterns without real API calls."""
import time
from io import StringIO
from unittest.mock import MagicMock, patch

import pytest

from src.utils.rate_limiter import TokenBucket, rate_limit
from src.utils.retry import async_retry, retry, RetryableRequest, log_retry


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

    def test_retry_on_retry_callback(self):
        """The on_retry callback should be called with exception and attempt number."""
        callback_calls = []

        def my_callback(exc, attempt):
            callback_calls.append((type(exc).__name__, attempt))

        attempts = 0

        @retry(max_attempts=3, delay=0.01, on_retry=my_callback)
        def flaky():
            nonlocal attempts
            attempts += 1
            if attempts < 3:
                raise ConnectionError("retry me")
            return "done"

        result = flaky()
        assert result == "done"
        assert len(callback_calls) == 2
        assert callback_calls[0] == ("ConnectionError", 1)
        assert callback_calls[1] == ("ConnectionError", 2)


class TestAsyncRetry:
    @pytest.mark.asyncio
    async def test_async_retry_succeeds(self):
        """Async function should succeed after transient failures."""
        attempts = 0

        @async_retry(max_attempts=3, delay=0.01)
        async def flaky_async():
            nonlocal attempts
            attempts += 1
            if attempts < 2:
                raise ConnectionError("timeout")
            return "ok"

        result = await flaky_async()
        assert result == "ok"
        assert attempts == 2

    @pytest.mark.asyncio
    async def test_async_retry_exhausts(self):
        """After exhausting all async attempts the last exception must propagate."""

        @async_retry(max_attempts=2, delay=0.01)
        async def always_fail():
            raise ValueError("boom")

        with pytest.raises(ValueError, match="boom"):
            await always_fail()

    @pytest.mark.asyncio
    async def test_async_retry_on_retry_callback(self):
        """The on_retry callback should be invoked on each async retry."""
        callback_calls = []

        def my_callback(exc, attempt):
            callback_calls.append((type(exc).__name__, attempt))

        attempts = 0

        @async_retry(max_attempts=3, delay=0.01, on_retry=my_callback)
        async def flaky():
            nonlocal attempts
            attempts += 1
            if attempts < 3:
                raise RuntimeError("oops")
            return "recovered"

        result = await flaky()
        assert result == "recovered"
        assert len(callback_calls) == 2
        assert callback_calls[0] == ("RuntimeError", 1)
        assert callback_calls[1] == ("RuntimeError", 2)

    @pytest.mark.asyncio
    async def test_async_retry_immediate_success(self):
        """Async function that succeeds immediately should not retry."""

        @async_retry(max_attempts=3, delay=0.01)
        async def succeed():
            return 42

        assert await succeed() == 42


class TestRetryableRequest:
    def test_execute_succeeds_after_retries(self):
        """RetryableRequest should succeed after transient failures."""
        call_count = 0

        def flaky_func():
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise ConnectionError("fail")
            return "success"

        req = RetryableRequest(flaky_func, max_attempts=3, delay=0.01)
        result = req.execute()
        assert result == "success"
        assert req.attempts == 3
        assert req.last_error is not None

    def test_execute_exhausts_attempts(self):
        """RetryableRequest should raise after exhausting all attempts."""

        def always_fail():
            raise ValueError("permanent")

        req = RetryableRequest(always_fail, max_attempts=2, delay=0.01)
        with pytest.raises(ValueError, match="permanent"):
            req.execute()
        assert req.attempts == 2
        assert isinstance(req.last_error, ValueError)

    def test_execute_immediate_success(self):
        """RetryableRequest should return immediately on first success."""
        req = RetryableRequest(lambda: "instant", max_attempts=3, delay=0.01)
        result = req.execute()
        assert result == "instant"
        assert req.attempts == 1
        assert req.last_error is None

    def test_execute_passes_args(self):
        """RetryableRequest.execute should forward args and kwargs."""

        def add(a, b, extra=0):
            return a + b + extra

        req = RetryableRequest(add, max_attempts=1)
        result = req.execute(2, 3, extra=10)
        assert result == 15

    def test_init_attributes(self):
        """RetryableRequest should set all init attributes correctly."""
        req = RetryableRequest(lambda: None, max_attempts=5, delay=2.0, backoff=3.0)
        assert req.max_attempts == 5
        assert req.delay == 2.0
        assert req.backoff == 3.0
        assert req.last_error is None
        assert req.attempts == 0


class TestLogRetry:
    def test_log_retry_prints_message(self, capsys):
        """log_retry should print a warning with attempt and exception info."""
        log_retry(ConnectionError("test error message"), 2)
        captured = capsys.readouterr()
        assert "2" in captured.out
        assert "ConnectionError" in captured.out
        assert "test error" in captured.out
