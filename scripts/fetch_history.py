#!/usr/bin/env python3
"""
历史数据补充脚本

抓取：
1. 日线补充至 1 年 (2025-01 ~ 2026-01)
2. 周线 3 年 (2023-01 ~ 2026-01)
3. 估值周度 3 年

速率限制: 300 请求/分钟 (已内置)
"""

import sqlite3
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

# 添加项目根目录
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.data_ingestion.tushare.client import TushareAdapter, get_tushare_client


def log(msg: str):
    ts = datetime.now().strftime("%H:%M:%S")
    print(f"[{ts}] {msg}", flush=True)


def get_db_connection():
    db_path = PROJECT_ROOT / 'data' / 'stocks.db'
    conn = sqlite3.connect(str(db_path), timeout=30)
    conn.row_factory = sqlite3.Row
    return conn


# ============================================================
# 表初始化
# ============================================================

def init_tables():
    """初始化周线表"""
    conn = get_db_connection()
    
    # 周线表
    conn.execute("""
        CREATE TABLE IF NOT EXISTS ts_weekly (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts_code TEXT NOT NULL,
            trade_date TEXT NOT NULL,
            open REAL,
            high REAL,
            low REAL,
            close REAL,
            pre_close REAL,
            change REAL,
            pct_chg REAL,
            vol REAL,
            amount REAL,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(ts_code, trade_date)
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_ts_weekly_code ON ts_weekly(ts_code)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_ts_weekly_date ON ts_weekly(trade_date)")
    
    # 周度估值表
    conn.execute("""
        CREATE TABLE IF NOT EXISTS ts_weekly_valuation (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts_code TEXT NOT NULL,
            trade_date TEXT NOT NULL,
            pe REAL,
            pe_ttm REAL,
            pb REAL,
            ps REAL,
            ps_ttm REAL,
            total_mv REAL,
            circ_mv REAL,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(ts_code, trade_date)
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_ts_wv_code ON ts_weekly_valuation(ts_code)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_ts_wv_date ON ts_weekly_valuation(trade_date)")
    
    conn.commit()
    conn.close()
    log("✅ 表结构初始化完成")


# ============================================================
# 获取交易日列表
# ============================================================

def get_trading_weeks(client: TushareAdapter, start_date: str, end_date: str):
    """
    获取每周最后一个交易日列表（用于周线采样）
    """
    df = client.trade_cal(start_date=start_date, end_date=end_date, is_open=1)
    dates = df['cal_date'].tolist()
    
    # 按周分组，取每周最后一个交易日
    from collections import defaultdict
    weeks = defaultdict(list)
    for d in dates:
        # 计算周数
        dt = datetime.strptime(d, '%Y%m%d')
        week_key = dt.strftime('%Y-%W')
        weeks[week_key].append(d)
    
    # 每周取最后一天
    week_ends = [max(days) for days in weeks.values()]
    return sorted(week_ends)


# ============================================================
# 周线抓取
# ============================================================

def fetch_weekly_data(client: TushareAdapter, start_date: str, end_date: str):
    """
    抓取周线数据
    
    策略: 按日期批量获取（而非按股票），减少 API 调用
    """
    log(f"📈 抓取周线数据: {start_date} ~ {end_date}")
    
    conn = get_db_connection()
    
    # 获取周末列表
    week_ends = get_trading_weeks(client, start_date, end_date)
    log(f"   共 {len(week_ends)} 个周末交易日")
    
    total = 0
    for i, trade_date in enumerate(week_ends):
        try:
            # 按日期获取全市场周线
            df = client.api.weekly(trade_date=trade_date)
            
            if df is None or df.empty:
                continue
            
            count = 0
            for _, row in df.iterrows():
                try:
                    conn.execute("""
                        INSERT OR REPLACE INTO ts_weekly
                        (ts_code, trade_date, open, high, low, close, pre_close,
                         change, pct_chg, vol, amount, updated_at)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, (
                        row.get('ts_code'),
                        trade_date,
                        row.get('open'),
                        row.get('high'),
                        row.get('low'),
                        row.get('close'),
                        row.get('pre_close'),
                        row.get('change'),
                        row.get('pct_chg'),
                        row.get('vol'),
                        row.get('amount'),
                        datetime.now().isoformat()
                    ))
                    count += 1
                except Exception as e:
                    log(f"   ⚠️ 周线写入失败 {row.get('ts_code')} {trade_date}: {e}")
            
            conn.commit()
            total += count
            
            if (i + 1) % 10 == 0:
                log(f"   [{i+1}/{len(week_ends)}] {trade_date}: +{count} 条, 累计 {total}")
            
        except Exception as e:
            log(f"   ⚠️ {trade_date} 失败: {e}")
    
    conn.close()
    log(f"   ✅ 周线完成: {total} 条")
    return total


# ============================================================
# 周度估值抓取
# ============================================================

def fetch_weekly_valuation(client: TushareAdapter, start_date: str, end_date: str):
    """
    抓取周度估值数据
    """
    log(f"💰 抓取周度估值: {start_date} ~ {end_date}")
    
    conn = get_db_connection()
    
    # 获取周末列表
    week_ends = get_trading_weeks(client, start_date, end_date)
    log(f"   共 {len(week_ends)} 个周末")
    
    total = 0
    for i, trade_date in enumerate(week_ends):
        try:
            df = client.daily_basic(trade_date=trade_date)
            
            if df is None or df.empty:
                continue
            
            count = 0
            for _, row in df.iterrows():
                try:
                    conn.execute("""
                        INSERT OR REPLACE INTO ts_weekly_valuation
                        (ts_code, trade_date, pe, pe_ttm, pb, ps, ps_ttm,
                         total_mv, circ_mv, updated_at)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, (
                        row.get('ts_code'),
                        trade_date,
                        row.get('pe'),
                        row.get('pe_ttm'),
                        row.get('pb'),
                        row.get('ps'),
                        row.get('ps_ttm'),
                        row.get('total_mv'),
                        row.get('circ_mv'),
                        datetime.now().isoformat()
                    ))
                    count += 1
                except Exception as e:
                    log(f"   ⚠️ 周估值写入失败 {row.get('ts_code')} {trade_date}: {e}")
            
            conn.commit()
            total += count
            
            if (i + 1) % 10 == 0:
                log(f"   [{i+1}/{len(week_ends)}] {trade_date}: +{count} 条, 累计 {total}")
            
        except Exception as e:
            log(f"   ⚠️ {trade_date} 失败: {e}")
    
    conn.close()
    log(f"   ✅ 周度估值完成: {total} 条")
    return total


# ============================================================
# 日线补充
# ============================================================

def fetch_daily_history(client: TushareAdapter, start_date: str, end_date: str):
    """
    补充日线历史数据
    """
    log(f"📊 补充日线历史: {start_date} ~ {end_date}")
    
    conn = get_db_connection()
    
    # 获取交易日列表
    trading_days = client.get_trading_days(start_date=start_date, end_date=end_date)
    
    # 过滤已存在的日期
    cursor = conn.execute("SELECT DISTINCT trade_date FROM ts_daily")
    existing = set(row[0] for row in cursor.fetchall())
    
    to_fetch = [d for d in trading_days if d not in existing]
    log(f"   需抓取 {len(to_fetch)} 个交易日 (已有 {len(existing)} 天)")
    
    if not to_fetch:
        log("   ✅ 无需补充")
        return 0
    
    total = 0
    for i, trade_date in enumerate(to_fetch):
        try:
            df = client.daily(trade_date=trade_date)
            
            if df is None or df.empty:
                continue
            
            count = 0
            for _, row in df.iterrows():
                try:
                    conn.execute("""
                        INSERT OR REPLACE INTO ts_daily
                        (ts_code, trade_date, open, high, low, close, pre_close,
                         change, pct_chg, vol, amount, updated_at)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, (
                        row.get('ts_code'),
                        trade_date,
                        row.get('open'),
                        row.get('high'),
                        row.get('low'),
                        row.get('close'),
                        row.get('pre_close'),
                        row.get('change'),
                        row.get('pct_chg'),
                        row.get('vol'),
                        row.get('amount'),
                        datetime.now().isoformat()
                    ))
                    count += 1
                except Exception as e:
                    log(f"   ⚠️ 日线写入失败 {row.get('ts_code')} {trade_date}: {e}")
            
            conn.commit()
            total += count
            
            if (i + 1) % 20 == 0:
                stats = client.get_stats()
                log(f"   [{i+1}/{len(to_fetch)}] {trade_date}: +{count}, 累计 {total}, API {stats['requests_per_minute']:.0f}/min")
            
        except Exception as e:
            log(f"   ⚠️ {trade_date} 失败: {e}")
    
    conn.close()
    log(f"   ✅ 日线补充完成: {total} 条")
    return total


# ============================================================
# 主函数
# ============================================================

def main():
    log("=" * 60)
    log("历史数据补充")
    log("=" * 60)
    
    init_tables()
    client = get_tushare_client()
    
    # 时间范围
    end_date = datetime.now().strftime('%Y%m%d')
    daily_start = (datetime.now() - timedelta(days=365)).strftime('%Y%m%d')  # 1年
    weekly_start = (datetime.now() - timedelta(days=365*3)).strftime('%Y%m%d')  # 3年
    
    log(f"\n📅 日线范围: {daily_start} ~ {end_date}")
    log(f"📅 周线范围: {weekly_start} ~ {end_date}")
    
    # 1. 补充日线
    log("\n" + "=" * 40)
    fetch_daily_history(client, daily_start, end_date)
    
    # 2. 抓取周线
    log("\n" + "=" * 40)
    fetch_weekly_data(client, weekly_start, end_date)
    
    # 3. 抓取周度估值
    log("\n" + "=" * 40)
    fetch_weekly_valuation(client, weekly_start, end_date)
    
    # 统计
    stats = client.get_stats()
    log(f"\n📊 API 统计: {stats['total_requests']} 次, {stats['elapsed_seconds']:.0f}s")
    log("\n✅ 历史数据补充完成!")


if __name__ == "__main__":
    main()
