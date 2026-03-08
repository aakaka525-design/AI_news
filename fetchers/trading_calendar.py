#!/usr/bin/env python3
"""
交易日历工具模块

功能：
1. 获取 A 股交易日历
2. 判断指定日期是否为交易日
3. 获取最近的交易日
4. 缓存交易日历以减少 API 调用
"""

import logging
import sqlite3
import threading
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional
import akshare as ak

logger = logging.getLogger(__name__)

# 数据库路径 (使用公共数据库模块)
from fetchers.db import STOCKS_DB_PATH

# 缓存（内存中）— 使用 Lock 保证线程安全
_trading_days_cache: Optional[set[str]] = None
_cache_date: Optional[str] = None
_cache_lock = threading.Lock()


def get_connection() -> sqlite3.Connection:
    """获取数据库连接"""
    conn = sqlite3.connect(STOCKS_DB_PATH)
    return conn


def init_trading_calendar_table():
    """初始化交易日历表"""
    conn = get_connection()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS trading_calendar (
            date TEXT PRIMARY KEY,
            is_trading_day INTEGER DEFAULT 1,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.commit()
    conn.close()


def fetch_trading_calendar(year: int = None, timeout: int = 60) -> list[str]:
    """
    从 akshare 获取交易日历

    Args:
        year: 指定年份，默认当前年份
        timeout: 超时秒数

    Returns:
        list[str]: 交易日列表 (YYYY-MM-DD)
    """
    from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError

    try:
        with ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(ak.tool_trade_date_hist_sina)
            try:
                df = future.result(timeout=timeout)
            except FuturesTimeoutError:
                raise TimeoutError(f"AkShare fetch_trading_calendar timed out after {timeout}s")

        dates = df['trade_date'].astype(str).tolist()
        if year:
            dates = [d for d in dates if d.startswith(str(year))]
        return dates
    except TimeoutError:
        logger.warning("获取交易日历超时 (%ds)", timeout)
        return []
    except Exception as e:
        logger.warning("获取交易日历失败: %s", e)
        return []


def save_trading_calendar(dates: list[str]) -> int:
    """保存交易日历到数据库"""
    if not dates:
        return 0

    init_trading_calendar_table()
    conn = get_connection()
    count = 0

    for date in dates:
        try:
            conn.execute("""
                INSERT OR REPLACE INTO trading_calendar (date, is_trading_day)
                VALUES (?, 1)
            """, (date,))
            count += 1
        except Exception as e:
            logger.warning("保存交易日历记录失败 %s: %s", date, e)

    conn.commit()
    conn.close()
    return count


def clear_cache():
    """清除缓存（供测试使用）。"""
    global _trading_days_cache, _cache_date
    with _cache_lock:
        _trading_days_cache = None
        _cache_date = None


def load_trading_days() -> set[str]:
    """从数据库加载交易日（带缓存，线程安全）"""
    global _trading_days_cache, _cache_date

    today = datetime.now().strftime("%Y-%m-%d")

    # 快速路径：先读取局部引用，避免竞态下读到不一致的 pair
    cache, cache_dt = _trading_days_cache, _cache_date
    if cache is not None and cache_dt == today:
        return cache

    with _cache_lock:
        # Double-check: 另一个线程可能已经刷新了缓存
        if _trading_days_cache is not None and _cache_date == today:
            return _trading_days_cache

        # 从数据库加载
        try:
            conn = get_connection()
            cursor = conn.execute("SELECT date FROM trading_calendar WHERE is_trading_day = 1")
            dates = {row[0] for row in cursor.fetchall()}
            conn.close()

            # 如果数据库为空，从 API 获取并保存
            if not dates:
                logger.info("首次加载交易日历...")
                api_dates = fetch_trading_calendar()
                if api_dates:
                    save_trading_calendar(api_dates)
                    dates = set(api_dates)
                    logger.info("已保存 %d 个交易日", len(dates))

            _trading_days_cache = dates
            _cache_date = today
            return dates

        except Exception as e:
            logger.warning("加载交易日历失败: %s", e)
            return set()


def is_trading_day(date: str) -> bool:
    """
    判断指定日期是否为交易日

    Args:
        date: 日期字符串 (YYYY-MM-DD)

    Returns:
        bool: 是否为交易日
    """
    trading_days = load_trading_days()
    return date in trading_days


def get_latest_trading_day(before_date: str = None) -> Optional[str]:
    """
    获取最近的交易日

    Args:
        before_date: 基准日期，默认今天

    Returns:
        str: 最近交易日
    """
    if before_date is None:
        before_date = datetime.now().strftime("%Y-%m-%d")

    trading_days = load_trading_days()

    # 找到 <= before_date 的最大日期
    valid_days = [d for d in trading_days if d <= before_date]
    return max(valid_days) if valid_days else None


def get_trading_days_range(start_date: str, end_date: str) -> list[str]:
    """
    获取日期范围内的交易日

    Args:
        start_date: 开始日期
        end_date: 结束日期

    Returns:
        list[str]: 交易日列表
    """
    trading_days = load_trading_days()
    return sorted([d for d in trading_days if start_date <= d <= end_date])


def get_prev_n_trading_days(n: int, before_date: str = None) -> list[str]:
    """
    获取前 N 个交易日

    Args:
        n: 天数
        before_date: 基准日期，默认今天

    Returns:
        list[str]: 交易日列表（从近到远）
    """
    if before_date is None:
        before_date = datetime.now().strftime("%Y-%m-%d")

    trading_days = load_trading_days()
    valid_days = sorted([d for d in trading_days if d <= before_date], reverse=True)
    return valid_days[:n]


def calculate_trading_day_delay(last_data_date: str) -> int:
    """
    计算数据延迟的交易日天数

    Args:
        last_data_date: 最后数据日期

    Returns:
        int: 延迟交易日数
    """
    today = datetime.now().strftime("%Y-%m-%d")
    trading_days = get_trading_days_range(last_data_date, today)
    # 不包含 last_data_date 本身
    return max(0, len(trading_days) - 1)


# ============================================================
# 测试
# ============================================================

if __name__ == "__main__":
    print("📅 交易日历工具测试")
    print("=" * 40)

    # 加载交易日历
    days = load_trading_days()
    print(f"已加载 {len(days)} 个交易日")

    # 测试今天
    today = datetime.now().strftime("%Y-%m-%d")
    print(f"\n今天 {today} 是否交易日: {is_trading_day(today)}")

    # 最近交易日
    latest = get_latest_trading_day()
    print(f"最近交易日: {latest}")

    # 最近 5 个交易日
    recent = get_prev_n_trading_days(5)
    print(f"最近 5 个交易日: {recent}")

    # 数据延迟测试
    if latest:
        delay = calculate_trading_day_delay(latest)
        print(f"最新数据延迟: {delay} 个交易日")
