"""
通用限流器模块

实现令牌桶算法 (Token Bucket) 用于 API 限流。
支持同步和异步装饰器。
"""

import asyncio
import functools
import threading
import time
from typing import Callable, Optional


class TokenBucket:
    """
    令牌桶限流器
    
    使用令牌桶算法控制请求速率，线程安全。
    
    Args:
        rate: 每秒生成的令牌数
        capacity: 桶的容量（最大令牌数）
    
    Example:
        # 300 请求/分钟 = 5 请求/秒
        bucket = TokenBucket(rate=5, capacity=10)
        bucket.acquire()  # 阻塞直到获取令牌
    """
    
    def __init__(self, rate: float, capacity: int = None):
        """
        初始化令牌桶
        
        Args:
            rate: 每秒令牌生成速率
            capacity: 桶容量，默认为 rate
        """
        if rate <= 0:
            raise ValueError("rate must be > 0")

        self.rate = rate
        self.capacity = capacity if capacity is not None else max(1, int(rate))
        if self.capacity <= 0:
            raise ValueError("capacity must be > 0")
        self.tokens = self.capacity
        self.last_time = time.monotonic()
        self._lock = threading.Lock()

    def _validate_request_tokens(self, tokens: int) -> None:
        if tokens <= 0:
            raise ValueError("tokens must be > 0")
        if tokens > self.capacity:
            raise ValueError("tokens cannot exceed bucket capacity")
    
    def _refill(self):
        """补充令牌"""
        now = time.monotonic()
        elapsed = now - self.last_time
        new_tokens = elapsed * self.rate
        self.tokens = min(self.capacity, self.tokens + new_tokens)
        self.last_time = now
    
    def acquire(self, tokens: int = 1, blocking: bool = True) -> bool:
        """
        获取令牌
        
        Args:
            tokens: 需要的令牌数
            blocking: 是否阻塞等待
            
        Returns:
            是否成功获取令牌
        """
        self._validate_request_tokens(tokens)

        while True:
            with self._lock:
                self._refill()

                if self.tokens >= tokens:
                    self.tokens -= tokens
                    return True

                if not blocking:
                    return False

                # 计算需要等待的时间
                wait_time = (tokens - self.tokens) / self.rate

            # 在锁外等待，避免阻塞其他调用
            time.sleep(wait_time)
    
    async def acquire_async(self, tokens: int = 1) -> bool:
        """异步获取令牌"""
        self._validate_request_tokens(tokens)

        while True:
            with self._lock:
                self._refill()

                if self.tokens >= tokens:
                    self.tokens -= tokens
                    return True

                wait_time = (tokens - self.tokens) / self.rate

            await asyncio.sleep(wait_time)


# ============================================================
# 全局限流器实例
# ============================================================

# Tushare: 300 请求/分钟 = 5 请求/秒
TUSHARE_BUCKET = TokenBucket(rate=5.0, capacity=10)

# Gemini: free tier 15 RPM ≈ 0.25 请求/秒
GEMINI_BUCKET = TokenBucket(rate=14 / 60, capacity=15)


# ============================================================
# 装饰器
# ============================================================

def rate_limit(bucket: TokenBucket = None, tokens: int = 1):
    """
    同步限流装饰器
    
    Args:
        bucket: 令牌桶实例，默认使用 Tushare 限流器
        tokens: 每次调用消耗的令牌数
        
    Example:
        @rate_limit()
        def fetch_data():
            return api.call()
    """
    if bucket is None:
        bucket = TUSHARE_BUCKET
    
    def decorator(func: Callable):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            bucket.acquire(tokens)
            return func(*args, **kwargs)
        return wrapper
    return decorator


def rate_limit_async(bucket: TokenBucket = None, tokens: int = 1):
    """
    异步限流装饰器
    
    Args:
        bucket: 令牌桶实例
        tokens: 每次调用消耗的令牌数
        
    Example:
        @rate_limit_async()
        async def fetch_data():
            return await api.call()
    """
    if bucket is None:
        bucket = TUSHARE_BUCKET
    
    def decorator(func: Callable):
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            await bucket.acquire_async(tokens)
            return await func(*args, **kwargs)
        return wrapper
    return decorator


# ============================================================
# 工厂函数
# ============================================================

def create_rate_limiter(
    requests_per_minute: int = 300,
    burst_capacity: int = None,
    strict: bool = False,
) -> TokenBucket:
    """
    创建自定义限流器
    
    Args:
        requests_per_minute: 每分钟最大请求数
        burst_capacity: 突发容量，默认为每秒速率的2倍
        strict: 是否启用严格模式（禁用突发容量）
        
    Returns:
        TokenBucket 实例
        
    Example:
        # 创建 100 请求/分钟的限流器
        bucket = create_rate_limiter(100)
    """
    if requests_per_minute <= 0:
        raise ValueError("requests_per_minute must be > 0")
    if burst_capacity is not None and burst_capacity <= 0:
        raise ValueError("burst_capacity must be > 0")

    rate = requests_per_minute / 60.0
    if strict:
        capacity = 1
    else:
        capacity = burst_capacity if burst_capacity is not None else max(1, int(rate * 2))
    return TokenBucket(rate=rate, capacity=capacity)
