#!/usr/bin/env python3
"""
策略名称：强力封板挖掘 (Strong Limit-Up Scanner)
逻辑：
1. 筛选当日涨停股 (limit_up_pool)
2. 过滤掉"一字板" (买不到，无博弈价值) -> 可选，或者保留作为风向标
3. 核心指标筛选：
   - 封板强度 (turnover_ratio > 0.1 OR buy_lock_amount > 5000万)
   - 炸板次数 == 0 (均线坚挺)
4. 输出：符合条件的"打板/排板"候选池
"""
import sqlite3
import pandas as pd
from datetime import datetime
from src.database.connection import STOCKS_DB_PATH

def get_connection():
    return sqlite3.connect(STOCKS_DB_PATH)

def run_strategy():
    conn = get_connection()
    
    # 1. 获取最近的一个交易日
    cursor = conn.execute("SELECT MAX(date) FROM limit_up_pool")
    latest_date = cursor.fetchone()[0]
    print(f"📅 策略执行日期: {latest_date}")
    
    # 2. SQL 筛选逻辑
    # 逻辑：非ST，非退市 (假设数据已过滤)，炸板=0，封单金额>3000万 或 封成比>0.1
    query = """
    SELECT 
        stock_code, stock_name, 
        limit_up_reason, 
        continuous_days, 
        limit_up_type,
        buy_lock_amount,     -- 封单金额
        turnover_ratio,      -- 封成比
        open_count,          -- 炸板次数
        first_limit_time
    FROM limit_up_pool
    WHERE date = ?
      AND open_count = 0                -- 必须封死
      AND (buy_lock_amount > 30000000 OR turnover_ratio > 0.1) -- 资金认可度
    ORDER BY continuous_days DESC, turnover_ratio DESC
    """
    
    df = pd.read_sql_query(query, conn, params=(latest_date,))
    
    print(f"\n🚀 筛选出 {len(df)} 只【强力封板】标的:\n")
    
    # 分类展示
    # 1. 连板龙头 (高度)
    dragons = df[df['continuous_days'] >= 2]
    if not dragons.empty:
        print(f"🐲 【连板龙头】 ({len(dragons)} 只):")
        print(dragons[['stock_name', 'continuous_days', 'limit_up_reason', 'turnover_ratio']].to_string(index=False))
        print("-" * 50)
        
    # 2. 首板挖掘 (潜力)
    first_boards = df[df['continuous_days'] == 1]
    # 取前10名按封成比
    top_first = first_boards.head(10)
    
    if not top_first.empty:
        print(f"💎 【首板潜力 (Top 10)】:")
        print(top_first[['stock_name', 'stock_code', 'limit_up_reason', 'turnover_ratio', 'buy_lock_amount']].to_string(index=False))

    conn.close()

if __name__ == "__main__":
    run_strategy()
