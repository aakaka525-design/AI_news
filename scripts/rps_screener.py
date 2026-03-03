#!/usr/bin/env python3
"""
多周期RPS选股脚本
用途：捕捉不同阶段的强势股

选股逻辑：
1. 刚启动：RPS_10 > 90 且 RPS_50 < 80 → 短期爆发，中期尚未走强
2. 三线共振：RPS_10/20/50 均 > 90 → 超级强势股
3. 均线向上：RPS_10 > RPS_20 > RPS_50 → 强度递增
"""
import sqlite3
from datetime import datetime
from pathlib import Path
import pandas as pd
import sys

# 添加项目根目录到路径
sys.path.insert(0, str(Path(__file__).parent.parent))

# 使用公共数据库模块
from src.database.connection import get_connection, STOCKS_DB_PATH


def screen_just_started(date: str = None, min_rps10: float = 90, max_rps50: float = 80):
    """
    选股策略1：刚启动的强势股
    
    条件：RPS_10 > 90 且 RPS_50 < 80
    逻辑：短期刚开始走强，但中期还没涨多少，安全边际高
    """
    print(f"\n🚀 选股策略：刚启动 (RPS_10>{min_rps10} & RPS_50<{max_rps50})")
    print("=" * 60)
    
    conn = get_connection()
    
    if not date:
        cursor = conn.execute("SELECT MAX(date) FROM stock_rps")
        date = cursor.fetchone()[0]
    
    print(f"   日期: {date}")
    
    query = """
        SELECT r.stock_code, s.name, r.rps_10, r.rps_20, r.rps_50
        FROM stock_rps r
        LEFT JOIN stocks s ON r.stock_code = s.code
        WHERE r.date = ?
          AND r.rps_10 > ?
          AND r.rps_50 < ?
        ORDER BY r.rps_10 DESC
        LIMIT 20
    """
    
    cursor = conn.execute(query, (date, min_rps10, max_rps50))
    results = cursor.fetchall()
    
    print(f"\n   找到 {len(results)} 只符合条件的股票:\n")
    print(f"   {'代码':<8} {'名称':<10} {'RPS10':<8} {'RPS20':<8} {'RPS50':<8}")
    print("   " + "-" * 50)
    
    for code, name, rps10, rps20, rps50 in results:
        print(f"   {code:<8} {name or 'N/A':<10} {rps10:.2f}    {rps20:.2f}    {rps50:.2f}")
    
    conn.close()
    return results


def screen_triple_strong(date: str = None, min_rps: float = 90):
    """
    选股策略2：三线共振超强股
    
    条件：RPS_10 > 90 且 RPS_20 > 90 且 RPS_50 > 90
    逻辑：短中长期全面强势，市场龙头
    """
    print(f"\n🔥 选股策略：三线共振 (RPS全>90)")
    print("=" * 60)
    
    conn = get_connection()
    
    if not date:
        cursor = conn.execute("SELECT MAX(date) FROM stock_rps")
        date = cursor.fetchone()[0]
    
    print(f"   日期: {date}")
    
    query = """
        SELECT r.stock_code, s.name, r.rps_10, r.rps_20, r.rps_50,
               (r.rps_10 + r.rps_20 + r.rps_50) / 3.0 as avg_rps
        FROM stock_rps r
        LEFT JOIN stocks s ON r.stock_code = s.code
        WHERE r.date = ?
          AND r.rps_10 > ?
          AND r.rps_20 > ?
          AND r.rps_50 > ?
        ORDER BY avg_rps DESC
        LIMIT 30
    """
    
    cursor = conn.execute(query, (date, min_rps, min_rps, min_rps))
    results = cursor.fetchall()
    
    print(f"\n   找到 {len(results)} 只符合条件的股票:\n")
    print(f"   {'代码':<8} {'名称':<10} {'RPS10':<8} {'RPS20':<8} {'RPS50':<8} {'均值':<8}")
    print("   " + "-" * 60)
    
    for code, name, rps10, rps20, rps50, avg_rps in results:
        print(f"   {code:<8} {name or 'N/A':<10} {rps10:.2f}    {rps20:.2f}    {rps50:.2f}    {avg_rps:.2f}")
    
    conn.close()
    return results


def screen_accelerating(date: str = None, min_rps10: float = 80):
    """
    选股策略3：加速上涨股
    
    条件：RPS_10 > RPS_20 > RPS_50 且 RPS_10 > 80
    逻辑：短期强于中期强于长期，说明在加速上涨
    """
    print(f"\n📈 选股策略：加速上涨 (RPS_10>RPS_20>RPS_50)")
    print("=" * 60)
    
    conn = get_connection()
    
    if not date:
        cursor = conn.execute("SELECT MAX(date) FROM stock_rps")
        date = cursor.fetchone()[0]
    
    print(f"   日期: {date}")
    
    query = """
        SELECT r.stock_code, s.name, r.rps_10, r.rps_20, r.rps_50,
               (r.rps_10 - r.rps_50) as momentum
        FROM stock_rps r
        LEFT JOIN stocks s ON r.stock_code = s.code
        WHERE r.date = ?
          AND r.rps_10 > r.rps_20
          AND r.rps_20 > r.rps_50
          AND r.rps_10 > ?
        ORDER BY momentum DESC
        LIMIT 20
    """
    
    cursor = conn.execute(query, (date, min_rps10))
    results = cursor.fetchall()
    
    print(f"\n   找到 {len(results)} 只符合条件的股票:\n")
    print(f"   {'代码':<8} {'名称':<10} {'RPS10':<8} {'RPS20':<8} {'RPS50':<8} {'动量':<8}")
    print("   " + "-" * 60)
    
    for code, name, rps10, rps20, rps50, momentum in results:
        print(f"   {code:<8} {name or 'N/A':<10} {rps10:.2f}    {rps20:.2f}    {rps50:.2f}    +{momentum:.2f}")
    
    conn.close()
    return results


def screen_with_sector(date: str = None, min_rps: float = 90, top_sector_count: int = 5):
    """
    选股策略4：强势板块中的强势股
    
    条件：个股RPS_10 > 90 且 所属板块RPS > 90
    逻辑：板块和个股共振，确定性最高
    """
    print(f"\n⭐ 选股策略：强势板块中的强势股")
    print("=" * 60)
    
    conn = get_connection()
    
    if not date:
        cursor = conn.execute("SELECT MAX(date) FROM stock_rps")
        date = cursor.fetchone()[0]
    
    print(f"   日期: {date}")
    
    # 先找强势板块
    cursor = conn.execute("""
        SELECT sector_name, rps_20 
        FROM sector_rps 
        WHERE date = ? AND rps_20 > ?
        ORDER BY rps_20 DESC
        LIMIT ?
    """, (date, min_rps, top_sector_count))
    
    strong_sectors = cursor.fetchall()
    print(f"\n   强势板块 (RPS>{min_rps}):")
    for sector, rps in strong_sectors:
        print(f"      {sector}: {rps:.2f}")
    
    # 在这些板块中找强势股
    print(f"\n   板块内强势股 (RPS_10>{min_rps}):")
    
    all_results = []
    for sector, sector_rps in strong_sectors:
        cursor = conn.execute("""
            SELECT ss.stock_code, s.name, r.rps_10, r.rps_20, r.rps_50
            FROM sector_stocks ss
            JOIN stock_rps r ON ss.stock_code = r.stock_code AND r.date = ?
            LEFT JOIN stocks s ON ss.stock_code = s.code
            WHERE ss.sector_name = ?
              AND r.rps_10 > ?
            ORDER BY r.rps_10 DESC
            LIMIT 5
        """, (date, sector, min_rps))
        
        stocks = cursor.fetchall()
        if stocks:
            print(f"\n   【{sector}】")
            for code, name, rps10, rps20, rps50 in stocks:
                print(f"      {code} {name or 'N/A'}: RPS10={rps10:.2f}")
                all_results.append((code, name, sector, rps10))
    
    conn.close()
    return all_results


def main():
    import argparse
    parser = argparse.ArgumentParser(description="多周期RPS选股")
    parser.add_argument("--strategy", type=str, choices=['just_started', 'triple', 'accelerating', 'sector'],
                        help="选股策略")
    parser.add_argument("--date", type=str, help="指定日期 YYYY-MM-DD")
    parser.add_argument("--all", action="store_true", help="运行所有策略")
    args = parser.parse_args()
    
    print("=" * 60)
    print("多周期RPS选股系统")
    print(f"数据库: {STOCKS_DB_PATH}")
    print("=" * 60)
    
    if args.all or not args.strategy:
        screen_just_started(args.date)
        screen_triple_strong(args.date)
        screen_accelerating(args.date)
        screen_with_sector(args.date)
    elif args.strategy == 'just_started':
        screen_just_started(args.date)
    elif args.strategy == 'triple':
        screen_triple_strong(args.date)
    elif args.strategy == 'accelerating':
        screen_accelerating(args.date)
    elif args.strategy == 'sector':
        screen_with_sector(args.date)
    
    print("\n" + "=" * 60)
    print("✅ 选股完成!")


if __name__ == "__main__":
    main()
