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
        self.rate = rate
        self.capacity = capacity or int(rate)
        self.tokens = self.capacity
        self.last_time = time.monotonic()
        self._lock = threading.Lock()
    
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
        with self._lock:
            self._refill()
            
            if self.tokens >= tokens:
                self.tokens -= tokens
                return True
            
            if not blocking:
                return False
            
            # 计算需要等待的时间
            wait_time = (tokens - self.tokens) / self.rate
        
        # 在锁外等待
        time.sleep(wait_time)
        
        with self._lock:
            self._refill()
            self.tokens -= tokens
            return True
    
    async def acquire_async(self, tokens: int = 1) -> bool:
        """异步获取令牌"""
        with self._lock:
            self._refill()
            
            if self.tokens >= tokens:
                self.tokens -= tokens
                return True
            
            wait_time = (tokens - self.tokens) / self.rate
        
        await asyncio.sleep(wait_time)
        
        with self._lock:
            self._refill()
            self.tokens -= tokens
            return True


# ============================================================
# 全局限流器实例
# ============================================================

# Tushare: 300 请求/分钟 = 5 请求/秒
TUSHARE_BUCKET = TokenBucket(rate=5.0, capacity=10)


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
    burst_capacity: int = None
) -> TokenBucket:
    """
    创建自定义限流器
    
    Args:
        requests_per_minute: 每分钟最大请求数
        burst_capacity: 突发容量，默认为每秒速率的2倍
        
    Returns:
        TokenBucket 实例
        
    Example:
        # 创建 100 请求/分钟的限流器
        bucket = create_rate_limiter(100)
    """
    rate = requests_per_minute / 60.0
    capacity = burst_capacity or int(rate * 2)
    return TokenBucket(rate=rate, capacity=capacity)
