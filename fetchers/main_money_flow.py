#!/usr/bin/env python3
"""
主力资金流获取模块

获取全A股每日主力净买入数据
数据源：东方财富
"""

import sqlite3
import time
import asyncio
import aiohttp
from datetime import datetime
from pathlib import Path

from .proxy_pool import ProxyPool

# 使用公共数据库模块
from fetchers.db import get_connection, STOCKS_DB_PATH

MAX_WORKERS = 30

# 东方财富资金流日K API（历史接口）
EM_MONEY_FLOW_API = "https://push2his.eastmoney.com/api/qt/stock/fflow/daykline/get"


def log(msg: str):
    """格式化输出日志信息。"""
    ts = datetime.now().strftime("%H:%M:%S")
    print(f"[{ts}] {msg}", flush=True)


def init_main_money_flow_table():
    """初始化主力资金流表"""
    conn = get_connection()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS main_money_flow (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            stock_code TEXT NOT NULL,
            date TEXT NOT NULL,

            -- 资金净流入（万元）
            main_net_inflow REAL,        -- 主力净流入
            super_large_net REAL,        -- 超大单净流入
            large_net REAL,              -- 大单净流入
            medium_net REAL,             -- 中单净流入
            small_net REAL,              -- 小单净流入

            -- 资金流入占比
            main_net_ratio REAL,         -- 主力净流入占比（%）

            -- 价格相关
            close_price REAL,            -- 收盘价
            change_pct REAL,             -- 涨跌幅（%）

            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(stock_code, date)
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_main_flow_code ON main_money_flow(stock_code)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_main_flow_date ON main_money_flow(date)")
    conn.commit()
    conn.close()
    log("主力资金流表初始化完成")


def get_pending_codes():
    """获取待获取的股票代码（跳过当天已有数据）"""
    conn = get_connection()
    cursor = conn.execute("SELECT code FROM stocks")
    all_codes = [r[0] for r in cursor.fetchall()]

    today = datetime.now().strftime("%Y-%m-%d")
    cursor = conn.execute("SELECT DISTINCT stock_code FROM main_money_flow WHERE date = ?", (today,))
    existing = set(r[0] for r in cursor.fetchall())

    conn.close()
    return [c for c in all_codes if c not in existing]


def safe_float(val):
    if val is None or val == "-" or val == "":
        return None
    try:
        return float(val)
    except (ValueError, TypeError):
        return None


async def fetch_single_money_flow(session: aiohttp.ClientSession, code: str, proxy_pool: ProxyPool, days: int = 30) -> list:
    """异步获取单只股票的历史资金流数据（使用日K接口）"""

    # 东方财富代码格式
    secid = f"1.{code}" if code.startswith("6") else f"0.{code}"

    # 资金流日K接口参数
    params = {
        "secid": secid,
        "fields1": "f1,f2,f3,f7",
        "fields2": "f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61,f62,f63,f64,f65",
        "lmt": days,  # 获取最近N天
        "klt": 101,  # 日K
        "ut": "fa5fd1943c7b386f172d6893dbfba10b"
    }

    # 尝试代理，失败则直连
    for attempt in range(2):
        try:
            proxy_url = None
            if attempt == 0:
                proxy_addr = proxy_pool.get_proxy()
                if proxy_addr:
                    proxy_url = f"http://{proxy_pool.AUTH_KEY}:{proxy_pool.AUTH_PWD}@{proxy_addr}"

            async with session.get(EM_MONEY_FLOW_API, params=params, proxy=proxy_url, timeout=aiohttp.ClientTimeout(total=15)) as resp:
                data = await resp.json()

                if data.get("rc") != 0 or not data.get("data") or not data["data"].get("klines"):
                    if attempt == 0:
                        continue  # 代理失败，尝试直连
                    return []

                results = []
                # 解析所有日K数据
                for kline in data["data"]["klines"]:
                    parts = kline.split(",")

                    if len(parts) < 13:
                        continue

                    results.append({
                        "stock_code": code,
                        "date": parts[0],
                        "main_net_inflow": safe_float(parts[1]) / 10000 if parts[1] else None,  # 转万元
                        "small_net": safe_float(parts[2]) / 10000 if parts[2] else None,
                        "medium_net": safe_float(parts[3]) / 10000 if parts[3] else None,
                        "large_net": safe_float(parts[4]) / 10000 if parts[4] else None,
                        "super_large_net": safe_float(parts[5]) / 10000 if parts[5] else None,
                        "main_net_ratio": safe_float(parts[6]),  # 已是百分比
                        "close_price": safe_float(parts[11]),
                        "change_pct": safe_float(parts[12]),
                    })
                return results
        except Exception as e:
            if attempt == 0:
                continue  # 代理失败，尝试直连
            return []
    return []


def save_money_flows(records: list[dict]):
    """批量保存资金流记录（带数据验证）"""
    if not records:
        return 0

    from fetchers.models import MainMoneyFlow
    from fetchers.db import validate_and_create, insert_validated

    conn = get_connection()
    count = 0

    for r in records:
        if not r or r.get("main_net_inflow") is None:
            continue

        # 使用 Pydantic 验证
        validated = validate_and_create(MainMoneyFlow, r)
        if validated is None:
            continue  # 验证失败，跳过

        if insert_validated(conn, "main_money_flow", validated,
                           ["stock_code", "date"]):
            count += 1

    conn.commit()
    conn.close()
    return count


async def fetch_concurrent(stock_codes: list, proxy_pool: ProxyPool, days: int = 30):
    """并发获取资金流数据（历史N天）"""
    log(f"📊 并发获取主力资金流（{len(stock_codes)} 只股票 × {days}天）")
    log(f"   并发数: {MAX_WORKERS}")

    total_saved = 0
    start_time = time.time()

    semaphore = asyncio.Semaphore(MAX_WORKERS)

    async def fetch_with_semaphore(session, code):
        async with semaphore:
            return await fetch_single_money_flow(session, code, proxy_pool, days)

    connector = aiohttp.TCPConnector(limit=MAX_WORKERS * 2, ssl=False)
    async with aiohttp.ClientSession(connector=connector) as session:
        batch_size = 50  # 因为每只股票返回30条，减小批次
        for batch_start in range(0, len(stock_codes), batch_size):
            batch = stock_codes[batch_start:batch_start + batch_size]

            # 代理过期或数量不够时刷新
            if proxy_pool.is_expired() or len(proxy_pool.proxies) < 20:
                proxy_pool.proxies.clear()
                proxy_pool.ensure_proxies()
                log(f"   🔄 刷新代理池: {len(proxy_pool.proxies)} 个")

            tasks = [fetch_with_semaphore(session, code) for code in batch]
            results = await asyncio.gather(*tasks, return_exceptions=True)

            # 展平结果列表（每只股票返回多条记录）
            all_records = []
            for r in results:
                if isinstance(r, list) and r:
                    all_records.extend(r)

            saved = save_money_flows(all_records)
            total_saved += saved

            pct = (batch_start + len(batch)) / len(stock_codes) * 100
            elapsed = time.time() - start_time
            speed = (batch_start + len(batch)) / elapsed if elapsed > 0 else 0
            eta = (len(stock_codes) - batch_start - len(batch)) / speed if speed > 0 else 0

            log(f"   [{batch_start + len(batch)}/{len(stock_codes)}] {pct:.1f}% - "
                f"累计 {total_saved} 条 - 速度 {speed:.1f} 只/秒 - ETA {eta/60:.1f} 分钟")

    elapsed = time.time() - start_time
    log(f"   ✅ 完成，共 {total_saved} 条，耗时 {elapsed/60:.1f} 分钟")
    return total_saved


def main():
    import argparse
    parser = argparse.ArgumentParser(description="并发获取主力资金流数据")
    parser.add_argument("--workers", type=int, default=30, help="并发数")
    parser.add_argument("--days", type=int, default=1, help="获取最近N天数据（默认1天，历史模式用30）")
    parser.add_argument("--all", action="store_true", help="强制获取所有股票（忽略已有数据）")
    args = parser.parse_args()

    global MAX_WORKERS
    MAX_WORKERS = args.workers

    log("=" * 50)
    log(f"主力资金流数据获取（{args.days}天历史）")
    log(f"数据库: {STOCKS_DB_PATH}")
    log(f"并发数: {MAX_WORKERS}")
    log("=" * 50)

    init_main_money_flow_table()

    log("初始化代理池...")
    proxy_pool = ProxyPool(min_proxies=MAX_WORKERS)
    proxy_pool.ensure_proxies()
    log(f"可用代理: {len(proxy_pool.proxies)} 个")

    if args.all:
        # 强制获取所有股票
        conn = get_connection()
        cursor = conn.execute("SELECT code FROM stocks")
        codes = [r[0] for r in cursor.fetchall()]
        conn.close()
        log(f"获取全部: {len(codes)} 只股票")
    else:
        codes = get_pending_codes()
        log(f"待获取: {len(codes)} 只股票")

    if not codes:
        log("✅ 当天数据已全部获取")
        return

    asyncio.run(fetch_concurrent(codes, proxy_pool, args.days))

    # 统计
    conn = get_connection()
    cursor = conn.execute("SELECT COUNT(*), COUNT(DISTINCT date) FROM main_money_flow")
    count, days_count = cursor.fetchone()
    conn.close()

    log(f"📊 主力资金流: {count} 条记录，覆盖 {days_count} 个交易日")
    log("✅ 完成!")


if __name__ == "__main__":
    main()
