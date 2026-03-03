#!/usr/bin/env python3
"""
涨停板数据获取模块
用途：追踪市场情绪高度、连板龙头、首板标的

数据源：akshare (东方财富)
"""
import sqlite3
import sys
from datetime import datetime, timedelta
from pathlib import Path
import akshare as ak
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[3]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# 使用公共数据库模块
from src.database.connection import get_connection, STOCKS_DB_PATH


def init_table():
    """初始化涨停池表"""
    conn = get_connection()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS limit_up_pool (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT NOT NULL,                    -- 交易日期
            stock_code TEXT NOT NULL,              -- 股票代码
            stock_name TEXT,                       -- 股票名称
            close_price REAL,                      -- 收盘价
            change_pct REAL,                       -- 涨跌幅
            turnover_rate REAL,                    -- 换手率
            limit_up_type TEXT,                    -- 涨停类型: 一字板/T字板/普通涨停
            continuous_days INTEGER,               -- 连板天数 (1=首板)
            first_limit_time TEXT,                 -- 首次涨停时间 (HH:MM:SS)
            last_limit_time TEXT,                  -- 最后涨停时间
            open_count INTEGER,                    -- 打开涨停次数 (封板强度)
            limit_up_reason TEXT,                  -- 涨停原因/题材
            industry TEXT,                         -- 所属行业
            total_mv REAL,                         -- 总市值
            circ_mv REAL,                          -- 流通市值
            buy_lock_amount REAL,                  -- 封板资金
            amount REAL,                           -- 成交额
            turnover_ratio REAL,                   -- 封成比
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(date, stock_code)
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_limit_up_date ON limit_up_pool(date)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_limit_up_code ON limit_up_pool(stock_code)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_limit_up_days ON limit_up_pool(continuous_days)")
    conn.commit()
    conn.close()
    print("✅ 涨停池表初始化完成")


def fetch_limit_up_pool(date: str = None):
    """
    获取指定日期的涨停池数据
    
    Args:
        date: 日期字符串 YYYYMMDD，默认为最近交易日
    """
    if not date:
        # 获取最近交易日
        today = datetime.now()
        if today.weekday() >= 5:  # 周末
            today = today - timedelta(days=today.weekday() - 4)
        date = today.strftime("%Y%m%d")
    
    print(f"\n📈 获取涨停池数据 ({date})...")
    
    conn = get_connection()
    
    try:
        # 1. 涨停股池 (包含连板天数等)
        df = ak.stock_zt_pool_em(date=date)
        
        if df.empty:
            print(f"   ⚠️ {date} 无涨停数据")
            return 0
        
        print(f"   获取到 {len(df)} 只涨停股")
        
        count = 0
        for _, row in df.iterrows():
            try:
                code = str(row.get("代码", ""))
                name = row.get("名称", "")
                
                # 解析数据
                close_price = row.get("最新价", None)
                change_pct = row.get("涨跌幅", None)
                turnover = row.get("换手率", None)
                
                # 🔥 封板资金和成交额 (龙头打板核心指标)
                buy_lock_amount = row.get("封板资金", None)
                amount = row.get("成交额", None)
                
                # 计算封成比 (封板资金/成交额)
                lock_ratio = None
                if buy_lock_amount and amount and amount > 0:
                    lock_ratio = round(buy_lock_amount / amount, 2)
                
                # 连板天数
                continuous = row.get("连板数", 1)
                if pd.isna(continuous):
                    continuous = 1
                
                # 涨停时间
                first_time = str(row.get("首次封板时间", ""))
                last_time = str(row.get("最后封板时间", ""))
                
                # 打开次数
                open_count = row.get("炸板次数", 0)
                if pd.isna(open_count):
                    open_count = 0
                
                # 涨停原因
                reason = row.get("涨停原因", "")
                if pd.isna(reason):
                    reason = ""
                
                # 行业
                industry = row.get("所属行业", "")
                if pd.isna(industry):
                    industry = ""
                
                # 市值
                total_mv = row.get("总市值", None)
                circ_mv = row.get("流通市值", None)
                
                # 判断涨停类型
                limit_type = "普通涨停"
                if open_count == 0 and first_time == last_time:
                    limit_type = "一字板"
                elif open_count == 0:
                    limit_type = "T字板"
                
                # 格式化日期
                date_formatted = f"{date[:4]}-{date[4:6]}-{date[6:8]}"
                
                conn.execute("""
                    INSERT OR REPLACE INTO limit_up_pool
                    (date, stock_code, stock_name, close_price, change_pct, turnover_rate,
                     limit_up_type, continuous_days, first_limit_time, last_limit_time,
                     open_count, limit_up_reason, industry, total_mv, circ_mv,
                     buy_lock_amount, amount, turnover_ratio, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    date_formatted, code, name, close_price, change_pct, turnover,
                    limit_type, continuous, first_time, last_time,
                    open_count, reason, industry, total_mv, circ_mv,
                    buy_lock_amount, amount, lock_ratio,
                    datetime.now().isoformat()
                ))
                count += 1
                
            except Exception as e:
                print(f"   ⚠️ 保存 {code} 失败: {e}")
        
        conn.commit()
        print(f"   ✅ 保存 {count} 条涨停记录")
        
        # 统计
        cursor = conn.execute("""
            SELECT continuous_days, COUNT(*) 
            FROM limit_up_pool 
            WHERE date = ?
            GROUP BY continuous_days
            ORDER BY continuous_days DESC
        """, (date_formatted,))
        
        print(f"\n   📊 连板统计:")
        for days, cnt in cursor.fetchall():
            label = f"{days}连板" if days > 1 else "首板"
            print(f"      {label}: {cnt} 只")
        
        return count
        
    except Exception as e:
        print(f"   ❌ 获取失败: {e}")
        import traceback
        traceback.print_exc()
        return 0
    finally:
        conn.close()


def fetch_history(days: int = 30):
    """获取最近N个交易日的涨停数据"""
    print(f"\n📊 获取最近 {days} 个交易日的涨停数据...")
    
    # 获取交易日历
    try:
        df = ak.tool_trade_date_hist_sina()
        trade_dates = df['trade_date'].astype(str).tolist()
        
        # 过滤到最近的交易日
        today = datetime.now().strftime("%Y-%m-%d")
        past_dates = [d for d in trade_dates if d <= today][-days:]
        
        total = 0
        for date in past_dates:
            date_str = date.replace("-", "")
            count = fetch_limit_up_pool(date_str)
            total += count
        
        print(f"\n✅ 共获取 {total} 条涨停记录")
        return total
        
    except Exception as e:
        print(f"❌ 获取交易日历失败: {e}")
        return 0


def print_stats():
    """打印统计信息"""
    conn = get_connection()
    
    print("\n📈 涨停池统计:")
    
    cursor = conn.execute("SELECT COUNT(*), MIN(date), MAX(date) FROM limit_up_pool")
    total, min_date, max_date = cursor.fetchone()
    print(f"   总记录数: {total} 条")
    print(f"   日期范围: {min_date} ~ {max_date}")
    
    # 最高连板
    cursor = conn.execute("""
        SELECT date, stock_code, stock_name, continuous_days 
        FROM limit_up_pool 
        ORDER BY continuous_days DESC 
        LIMIT 5
    """)
    print(f"\n   🔥 历史连板王:")
    for date, code, name, days in cursor.fetchall():
        print(f"      {name}({code}) {days}连板 @ {date}")
    
    conn.close()


def main():
    import argparse
    parser = argparse.ArgumentParser(description="涨停池数据获取")
    parser.add_argument("--date", type=str, help="指定日期 YYYYMMDD")
    parser.add_argument("--history", type=int, default=0, help="获取最近N天历史")
    parser.add_argument("--stats", action="store_true", help="显示统计")
    args = parser.parse_args()
    
    print("=" * 50)
    print("涨停池数据获取")
    print(f"数据库: {STOCKS_DB_PATH}")
    print("=" * 50)
    
    init_table()
    
    if args.stats:
        print_stats()
    elif args.history > 0:
        fetch_history(args.history)
        print_stats()
    else:
        fetch_limit_up_pool(args.date)
        print_stats()
    
    print("\n✅ 完成!")


if __name__ == "__main__":
    main()
