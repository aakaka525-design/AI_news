"""
Tushare 日线数据抓取模块单元测试

覆盖：TushareAdapter 方法、重试分类、限流集成
"""

import pytest
from unittest.mock import MagicMock, patch, PropertyMock
import pandas as pd


class TestRetryClassification:
    """重试错误分类测试"""

    def test_non_retryable_401_error(self):
        from src.data_ingestion.tushare.client import _is_non_retryable

        exc = Exception("HTTP 401 Unauthorized")
        assert _is_non_retryable(exc) is True

    def test_non_retryable_403_error(self):
        from src.data_ingestion.tushare.client import _is_non_retryable

        exc = Exception("HTTP 403 Forbidden")
        assert _is_non_retryable(exc) is True

    def test_retryable_500_error(self):
        from src.data_ingestion.tushare.client import _is_non_retryable

        exc = Exception("HTTP 500 Internal Server Error")
        assert _is_non_retryable(exc) is False

    def test_retryable_connection_error(self):
        from src.data_ingestion.tushare.client import _is_non_retryable

        exc = ConnectionError("Connection refused")
        assert _is_non_retryable(exc) is False

    def test_non_retryable_token_error(self):
        from src.data_ingestion.tushare.client import _is_non_retryable

        exc = Exception("token无效，请重新获取")
        assert _is_non_retryable(exc) is True


class TestRetryWithBackoff:
    """重试装饰器测试"""

    def test_succeeds_on_first_try(self):
        from src.data_ingestion.tushare.client import retry_with_backoff

        call_count = 0

        @retry_with_backoff(max_retries=3, base_delay=0.01)
        def func():
            nonlocal call_count
            call_count += 1
            return "ok"

        assert func() == "ok"
        assert call_count == 1

    def test_retries_on_transient_error(self):
        from src.data_ingestion.tushare.client import retry_with_backoff

        call_count = 0

        @retry_with_backoff(max_retries=3, base_delay=0.01)
        def func():
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise ConnectionError("transient")
            return "ok"

        assert func() == "ok"
        assert call_count == 3

    def test_raises_immediately_on_auth_error(self):
        from src.data_ingestion.tushare.client import retry_with_backoff

        call_count = 0

        @retry_with_backoff(max_retries=3, base_delay=0.01)
        def func():
            nonlocal call_count
            call_count += 1
            raise Exception("HTTP 403 Forbidden")

        with pytest.raises(Exception, match="403"):
            func()

        assert call_count == 1  # 不应重试

    def test_exhausts_retries(self):
        from src.data_ingestion.tushare.client import retry_with_backoff

        call_count = 0

        @retry_with_backoff(max_retries=2, base_delay=0.01)
        def func():
            nonlocal call_count
            call_count += 1
            raise ConnectionError("always fails")

        with pytest.raises(ConnectionError):
            func()

        assert call_count == 3  # 1 initial + 2 retries


class TestTushareAdapter:
    """TushareAdapter 测试"""

    def test_get_tushare_token_raises_without_env(self):
        from src.data_ingestion.tushare.client import get_tushare_token

        with patch.dict("os.environ", {}, clear=True):
            with pytest.raises(ValueError, match="TUSHARE_TOKEN"):
                get_tushare_token()

    def test_get_tushare_token_returns_value(self):
        from src.data_ingestion.tushare.client import get_tushare_token

        with patch.dict("os.environ", {"TUSHARE_TOKEN": "test_token_123"}):
            assert get_tushare_token() == "test_token_123"

    def test_get_stats(self):
        """测试请求统计"""
        from src.data_ingestion.tushare.client import TushareAdapter

        with patch("src.data_ingestion.tushare.client.get_tushare_token", return_value="fake"), \
             patch("tinyshare.set_token"), \
             patch("tinyshare.pro_api"):
            adapter = TushareAdapter(token="fake")
            stats = adapter.get_stats()
            assert "total_requests" in stats
            assert stats["total_requests"] == 0
