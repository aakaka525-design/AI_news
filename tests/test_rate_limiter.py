"""
限流器单元测试

验证令牌桶算法严格遵守速率限制。
"""

import time
import pytest
import threading
import concurrent.futures


class TestTokenBucket:
    """令牌桶测试"""
    
    def test_basic_acquire(self):
        """测试基本令牌获取"""
        from src.utils.rate_limiter import TokenBucket
        
        bucket = TokenBucket(rate=10, capacity=10)
        
        # 应该能立即获取 10 个令牌
        for _ in range(10):
            assert bucket.acquire(blocking=False) is True
        
        # 第 11 个应该失败（非阻塞模式）
        assert bucket.acquire(blocking=False) is False
    
    def test_token_refill(self):
        """测试令牌补充"""
        from src.utils.rate_limiter import TokenBucket
        
        bucket = TokenBucket(rate=10, capacity=10)
        
        # 消耗所有令牌
        for _ in range(10):
            bucket.acquire(blocking=False)
        
        # 等待 0.5 秒应该补充 5 个令牌
        time.sleep(0.5)
        
        # 应该能获取 5 个
        for _ in range(5):
            assert bucket.acquire(blocking=False) is True
    
    def test_blocking_acquire(self):
        """测试阻塞获取"""
        from src.utils.rate_limiter import TokenBucket
        
        bucket = TokenBucket(rate=10, capacity=1)
        
        # 消耗令牌
        bucket.acquire(blocking=False)
        
        # 阻塞获取应该等待约 0.1 秒
        start = time.time()
        bucket.acquire(blocking=True)
        elapsed = time.time() - start
        
        assert elapsed >= 0.09  # 允许一点误差

    def test_init_rejects_non_positive_rate(self):
        from src.utils.rate_limiter import TokenBucket

        with pytest.raises(ValueError):
            TokenBucket(rate=0, capacity=1)

    def test_acquire_rejects_request_larger_than_capacity(self):
        from src.utils.rate_limiter import TokenBucket

        bucket = TokenBucket(rate=1, capacity=1)
        with pytest.raises(ValueError):
            bucket.acquire(tokens=2, blocking=True)
    
    def test_rate_limit_decorator(self):
        """测试限流装饰器"""
        from src.utils.rate_limiter import TokenBucket, rate_limit
        
        bucket = TokenBucket(rate=10, capacity=10)
        call_count = 0
        
        @rate_limit(bucket=bucket)
        def limited_function():
            nonlocal call_count
            call_count += 1
            return call_count
        
        start = time.time()
        
        # 调用 15 次，前 10 次应该立即完成，后 5 次需要等待
        for _ in range(15):
            limited_function()
        
        elapsed = time.time() - start
        
        assert call_count == 15
        assert elapsed >= 0.4  # 至少需要 0.5 秒来补充 5 个令牌
    
    def test_tushare_rate_limit(self):
        """
        测试 Tushare 限流（300请求/分钟 = 5/秒）
        
        模拟 25 次请求，应该至少需要 3 秒
        （前 10 次立即完成，后 15 次需要 3 秒）
        """
        from src.utils.rate_limiter import create_rate_limiter, rate_limit
        
        # 使用 5/秒 的限流器
        bucket = create_rate_limiter(requests_per_minute=300)
        request_count = 0
        
        @rate_limit(bucket=bucket)
        def mock_tushare_api():
            nonlocal request_count
            request_count += 1
        
        start = time.time()
        
        # 模拟 25 次请求
        for _ in range(25):
            mock_tushare_api()
        
        elapsed = time.time() - start
        
        print(f"\n25 次请求耗时: {elapsed:.2f}s (预期 >= 3s)")
        
        assert request_count == 25
        # 速率为 5/秒，25 次需要 5 秒（减去初始容量 10，剩余 15 次需要 3 秒）
        assert elapsed >= 2.5
    
    def test_concurrent_rate_limit(self):
        """
        测试并发限流
        
        多线程同时请求，验证不会突破速率限制
        """
        from src.utils.rate_limiter import TokenBucket, rate_limit
        
        bucket = TokenBucket(rate=10, capacity=10)
        call_times = []
        lock = threading.Lock()
        
        @rate_limit(bucket=bucket)
        def concurrent_function():
            with lock:
                call_times.append(time.time())
        
        start = time.time()
        
        # 使用 5 个线程，每个线程调用 10 次
        with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
            futures = [executor.submit(concurrent_function) for _ in range(50)]
            concurrent.futures.wait(futures)
        
        elapsed = time.time() - start
        
        print(f"\n50 次并发请求耗时: {elapsed:.2f}s")
        
        assert len(call_times) == 50
        # 50 次请求，速率 10/秒，至少需要 4 秒
        assert elapsed >= 3.5


class TestRateLimitStrict:
    """严格限流测试"""

    def test_strict_mode_disables_burst(self):
        from src.utils.rate_limiter import create_rate_limiter

        bucket = create_rate_limiter(requests_per_minute=300, strict=True)
        assert bucket.capacity == 1

    def test_create_rate_limiter_rejects_invalid_rpm(self):
        from src.utils.rate_limiter import create_rate_limiter

        with pytest.raises(ValueError):
            create_rate_limiter(requests_per_minute=0)
    
    def test_305_requests_over_60_seconds(self, monkeypatch):
        """
        验证 305 次请求严格耗时 > 60 秒（虚拟时钟，不做真实等待）
        
        这是 Tushare 的核心限制验证：
        - 300 请求/分钟
        - 305 次应该需要超过 60 秒
        
        使用 monkeypatch 驱动虚拟时间，避免 CI 真实等待 60+ 秒。
        """
        import src.utils.rate_limiter as rl

        current = 0.0

        def fake_monotonic():
            return current

        def fake_sleep(seconds: float):
            nonlocal current
            current += max(seconds, 1e-6)

        monkeypatch.setattr(rl.time, "monotonic", fake_monotonic)
        monkeypatch.setattr(rl.time, "sleep", fake_sleep)
        
        bucket = rl.create_rate_limiter(requests_per_minute=300, strict=True)
        request_count = 0
        
        @rl.rate_limit(bucket=bucket)
        def mock_request():
            nonlocal request_count
            request_count += 1
        
        for _ in range(305):
            mock_request()

        elapsed = current
        actual_rate = request_count / elapsed * 60 if elapsed else float("inf")
        
        assert request_count == 305
        assert elapsed > 60, f"305 次请求应耗时 > 60s，实际 {elapsed:.2f}s"
        assert actual_rate <= 310, f"速率应 <= 310/分钟，实际 {actual_rate:.1f}"


if __name__ == '__main__':
    pytest.main([__file__, '-v', '-s'])
