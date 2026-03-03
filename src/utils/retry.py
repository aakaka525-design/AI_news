#!/usr/bin/env python3
"""
通用 API 重试机制

提供装饰器和工具函数，用于处理网络请求重试和错误恢复。
"""

import asyncio
import functools
import random
import time
from typing import Callable, TypeVar, Any

T = TypeVar('T')


def retry(
    max_attempts: int = 3,
    delay: float = 1.0,
    backoff: float = 2.0,
    exceptions: tuple = (Exception,),
    on_retry: Callable[[Exception, int], None] = None
):
    """
    同步重试装饰器
    
    Args:
        max_attempts: 最大重试次数
        delay: 初始延迟（秒）
        backoff: 退避系数（每次重试延迟乘以此系数）
        exceptions: 需要重试的异常类型
        on_retry: 重试时的回调函数
        
    Usage:
        @retry(max_attempts=3, delay=1.0)
        def fetch_data():
            ...
    """
    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @functools.wraps(func)
        def wrapper(*args, **kwargs) -> T:
            current_delay = delay
            last_exception = None
            
            for attempt in range(1, max_attempts + 1):
                try:
                    return func(*args, **kwargs)
                except exceptions as e:
                    last_exception = e
                    if attempt < max_attempts:
                        if on_retry:
                            on_retry(e, attempt)
                        # 抖动：随机 ±20%
                        jitter = current_delay * random.uniform(-0.2, 0.2)
                        sleep_time = current_delay + jitter
                        time.sleep(sleep_time)
                        current_delay *= backoff
            
            raise last_exception
        return wrapper
    return decorator


def async_retry(
    max_attempts: int = 3,
    delay: float = 1.0,
    backoff: float = 2.0,
    exceptions: tuple = (Exception,),
    on_retry: Callable[[Exception, int], None] = None
):
    """
    异步重试装饰器
    
    Args:
        max_attempts: 最大重试次数
        delay: 初始延迟（秒）
        backoff: 退避系数
        exceptions: 需要重试的异常类型
        on_retry: 重试时的回调函数
        
    Usage:
        @async_retry(max_attempts=3, delay=1.0)
        async def fetch_data_async():
            ...
    """
    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @functools.wraps(func)
        async def wrapper(*args, **kwargs) -> T:
            current_delay = delay
            last_exception = None
            
            for attempt in range(1, max_attempts + 1):
                try:
                    return await func(*args, **kwargs)
                except exceptions as e:
                    last_exception = e
                    if attempt < max_attempts:
                        if on_retry:
                            on_retry(e, attempt)
                        jitter = current_delay * random.uniform(-0.2, 0.2)
                        sleep_time = current_delay + jitter
                        await asyncio.sleep(sleep_time)
                        current_delay *= backoff
            
            raise last_exception
        return wrapper
    return decorator


class RetryableRequest:
    """
    可重试的请求包装器
    
    用于需要更细粒度控制的场景
    
    Usage:
        result = RetryableRequest(fetch_func).execute(url, headers=headers)
    """
    
    def __init__(
        self,
        func: Callable,
        max_attempts: int = 3,
        delay: float = 1.0,
        backoff: float = 2.0
    ):
        self.func = func
        self.max_attempts = max_attempts
        self.delay = delay
        self.backoff = backoff
        self.last_error = None
        self.attempts = 0
    
    def execute(self, *args, **kwargs) -> Any:
        """执行请求（带重试）"""
        current_delay = self.delay
        
        for attempt in range(1, self.max_attempts + 1):
            self.attempts = attempt
            try:
                return self.func(*args, **kwargs)
            except Exception as e:
                self.last_error = e
                if attempt < self.max_attempts:
                    jitter = current_delay * random.uniform(-0.2, 0.2)
                    time.sleep(current_delay + jitter)
                    current_delay *= self.backoff
        
        raise self.last_error


# 常用异常类型
NETWORK_EXCEPTIONS = (
    ConnectionError,
    TimeoutError,
    OSError,
)

try:
    import requests
    NETWORK_EXCEPTIONS = NETWORK_EXCEPTIONS + (
        requests.RequestException,
        requests.Timeout,
        requests.ConnectionError,
    )
except ImportError:
    pass

try:
    import aiohttp
    NETWORK_EXCEPTIONS = NETWORK_EXCEPTIONS + (
        aiohttp.ClientError,
        aiohttp.ServerTimeoutError,
    )
except ImportError:
    pass


def log_retry(e: Exception, attempt: int):
    """默认的重试日志回调"""
    print(f"   ⚠️ 重试 {attempt}: {type(e).__name__}: {str(e)[:50]}")
