#!/usr/bin/env python3
"""
A股板块概念与成分股获取脚本

使用 akshare 获取：
1. 行业板块列表 + 成分股
2. 概念板块列表 + 成分股
3. 地域板块列表
4. 热门财经关键词

存入独立的 stocks.db 数据库
"""

import sqlite3
import sys
from datetime import datetime
from pathlib import Path
import time

import akshare as ak
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[3]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# 使用公共数据库模块
from src.database.connection import get_connection, STOCKS_DB_PATH


def init_database():
    """初始化数据库表结构"""
    conn = get_connection()
    
    # 板块表
    conn.execute("""
        CREATE TABLE IF NOT EXISTS sectors (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            type TEXT NOT NULL,
            code TEXT,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(name, type)
        )
    """)
    
    # 成分股表
    conn.execute("""
        CREATE TABLE IF NOT EXISTS sector_stocks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            sector_name TEXT NOT NULL,
            sector_type TEXT NOT NULL,
            stock_code TEXT NOT NULL,
            stock_name TEXT NOT NULL,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(sector_name, sector_type, stock_code)
        )
    """)
    
    # 全量股票表（去重后的股票列表）
    conn.execute("""
        CREATE TABLE IF NOT EXISTS stocks (
            code TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    # 索引
    conn.execute("CREATE INDEX IF NOT EXISTS idx_sector_type ON sectors(type)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_sector_name ON sectors(name)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_sector_stocks_sector ON sector_stocks(sector_name, sector_type)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_sector_stocks_code ON sector_stocks(stock_code)")
    
    conn.commit()
    conn.close()
    print("✅ 数据库初始化完成:", STOCKS_DB_PATH)


def save_sector(name: str, sector_type: str, code: str = ""):
    """保存板块"""
    conn = get_connection()
    conn.execute(
        "INSERT OR REPLACE INTO sectors (name, type, code, updated_at) VALUES (?, ?, ?, ?)",
        (name, sector_type, code, datetime.now().isoformat())
    )
    conn.commit()
    conn.close()


def save_sector_stocks(sector_name: str, sector_type: str, stocks: list[tuple[str, str]]):
    """保存板块成分股"""
    conn = get_connection()
    for stock_code, stock_name in stocks:
        try:
            conn.execute(
                "INSERT OR REPLACE INTO sector_stocks (sector_name, sector_type, stock_code, stock_name, updated_at) VALUES (?, ?, ?, ?, ?)",
                (sector_name, sector_type, stock_code, stock_name, datetime.now().isoformat())
            )
            # 同时写入全量股票表
            conn.execute(
                "INSERT OR REPLACE INTO stocks (code, name, updated_at) VALUES (?, ?, ?)",
                (stock_code, stock_name, datetime.now().isoformat())
            )
        except Exception as e:
            print(f"  ⚠️ 保存失败 {stock_code}: {e}")
    conn.commit()
    conn.close()


def fetch_industry_sectors(fetch_stocks: bool = True):
    """获取行业板块（统一使用东方财富数据源）"""
    print("\n📊 获取行业板块...")
    try:
        df = ak.stock_board_industry_name_em()
        sectors = []
        for _, row in df.iterrows():
            name = row.get("板块名称", "")
            code = str(row.get("板块代码", ""))
            if name:
                sectors.append({"name": name, "code": code})
                save_sector(name, "行业", code)
        
        print(f"   ✅ 获取 {len(sectors)} 个行业板块")
        
        # 获取成分股
        if fetch_stocks:
            print("   📈 获取成分股...")
            total_stocks = 0
            for i, s in enumerate(sectors):  # 获取全部
                try:
                    df_stocks = ak.stock_board_industry_cons_em(symbol=s["name"])
                    stocks = [(str(row["代码"]), row["名称"]) for _, row in df_stocks.iterrows()]
                    save_sector_stocks(s["name"], "行业", stocks)
                    total_stocks += len(stocks)
                    print(f"      [{i+1}/{len(sectors)}] {s['name']}: {len(stocks)} 只")
                    time.sleep(0.5)  # 控制请求频率
                except Exception as e:
                    print(f"      ⚠️ {s['name']} 获取失败: {e}")
            print(f"   ✅ 共获取 {total_stocks} 只成分股")
        
        return sectors
    except Exception as e:
        print(f"   ⚠️ 获取失败: {e}")
        return []


def fetch_concept_sectors(fetch_stocks: bool = True):
    """获取概念板块（统一使用东方财富数据源）"""
    print("\n💡 获取概念板块...")
    try:
        df = ak.stock_board_concept_name_em()
        sectors = []
        for _, row in df.iterrows():
            name = row.get("板块名称", "")
            code = str(row.get("板块代码", ""))
            if name:
                sectors.append({"name": name, "code": code})
                save_sector(name, "概念", code)
        
        print(f"   ✅ 获取 {len(sectors)} 个概念板块")
        
        # 获取成分股（全部概念）
        if fetch_stocks:
            print("   📈 获取概念板块成分股...")
            total_stocks = 0
            for i, s in enumerate(sectors):  # 获取全部
                try:
                    df_stocks = ak.stock_board_concept_cons_em(symbol=s["name"])
                    stocks = [(str(row["代码"]), row["名称"]) for _, row in df_stocks.iterrows()]
                    save_sector_stocks(s["name"], "概念", stocks)
                    total_stocks += len(stocks)
                    print(f"      [{i+1}/{len(sectors)}] {s['name']}: {len(stocks)} 只")
                    time.sleep(0.5)
                except Exception as e:
                    print(f"      ⚠️ {s['name']} 获取失败: {e}")
            print(f"   ✅ 共获取 {total_stocks} 只成分股")
        
        return sectors
    except Exception as e:
        print(f"   ⚠️ 获取失败: {e}")
        return []


def fetch_hot_keywords():
    """获取热门财经关键词"""
    print("\n🔥 获取热门财经关键词...")
    keywords = [
        # 科技
        "人工智能", "AI", "大模型", "ChatGPT", "机器人", "无人驾驶", "自动驾驶",
        "芯片", "半导体", "光刻机", "存储芯片", "GPU", "CPU", "算力", "数据中心",
        "云计算", "5G", "6G", "物联网", "区块链", "元宇宙", "VR", "AR",
        "量子计算", "卫星互联网", "低空经济", "飞行汽车",
        # 新能源
        "新能源", "光伏", "风电", "锂电池", "钠电池", "固态电池", "储能",
        "充电桩", "氢能源", "燃料电池", "碳中和",
        # 消费
        "白酒", "茅台", "预制菜", "免税", "跨境电商", "直播电商",
        # 医药
        "创新药", "中药", "医美", "CXO", "医疗器械",
        # 金融
        "券商", "保险", "银行", "科创板", "北交所",
        # 其他
        "军工", "航空航天", "核电", "房地产", "黄金", "稀土", "锂矿",
    ]
    
    for kw in keywords:
        save_sector(kw, "热词", "")
    
    print(f"   ✅ 获取 {len(keywords)} 个热门关键词")
    return keywords


def get_all_keywords() -> list[str]:
    """获取所有关键词（用于热点匹配）"""
    conn = get_connection()
    cursor = conn.execute("SELECT DISTINCT name FROM sectors")
    names = [row[0] for row in cursor.fetchall()]
    conn.close()
    return names


def get_stocks_by_sector(sector_name: str) -> list[tuple[str, str]]:
    """获取板块成分股"""
    conn = get_connection()
    cursor = conn.execute(
        "SELECT stock_code, stock_name FROM sector_stocks WHERE sector_name = ?",
        (sector_name,)
    )
    stocks = [(row[0], row[1]) for row in cursor.fetchall()]
    conn.close()
    return stocks



def fetch_sector_daily(sector_name: str, sector_type: str = "行业", days: int = 60):
    """获取板块日行情"""
    try:
        # 调试：使用最近1年
        start_date = "20250101"
        end_date = "20261231"
        
        if sector_type == "行业":
            df = ak.stock_board_industry_hist_em(symbol=sector_name, start_date=start_date, end_date=end_date, period="日k", adjust="qfq")
        else:
            # 概念板块接口不接受 period="日k"，使用默认
            df = ak.stock_board_concept_hist_em(symbol=sector_name, start_date=start_date, end_date=end_date, adjust="qfq")
            
        if df.empty:
            return 0
            
        # 仅保留最近 days 天
        df = df.tail(days)
        
        conn = get_connection()
        
        # 确保表存在
        conn.execute("""
            CREATE TABLE IF NOT EXISTS sector_daily (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                sector_name TEXT NOT NULL,
                sector_type TEXT,
                date TEXT NOT NULL,
                open REAL,
                close REAL,
                high REAL,
                low REAL,
                volume REAL,
                amount REAL,
                change_pct REAL,
                turnover_rate REAL,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(sector_name, date)
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_sector_daily_name ON sector_daily(sector_name)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_sector_daily_date ON sector_daily(date)")
        
        count = 0
        for _, row in df.iterrows():
            try:
                conn.execute("""
                    INSERT OR REPLACE INTO sector_daily 
                    (sector_name, sector_type, date, open, close, high, low, volume, amount, 
                     change_pct, turnover_rate, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    sector_name,
                    sector_type,
                    row.get("日期", ""),
                    row.get("开盘", None),
                    row.get("收盘", None),
                    row.get("最高", None),
                    row.get("最低", None),
                    row.get("成交量", None),
                    row.get("成交额", None),
                    row.get("涨跌幅", None),
                    row.get("换手率", None),
                    datetime.now().isoformat()
                ))
                count += 1
            except Exception:  # noqa: BLE001
                pass
        
        conn.commit()
        conn.close()
        return count
    except Exception as e:
        # print(f"   ⚠️ {sector_name} 获取失败: {e}")
        return 0


def update_all_sectors_daily(workers: int = 4):
    """更新所有板块的日行情"""
    print("\n📈 获取板块日行情...")
    conn = get_connection()
    
    # 获取板块列表
    cursor = conn.execute("SELECT name, type FROM sectors")
    sectors = cursor.fetchall()
    conn.close()
    
    total = 0
    count_sectors = 0
    
    print(f"   共 {len(sectors)} 个板块，开始获取...")
    
    # 暂时使用单线程，因为板块数量不多且akshare内部可能有IO限制
    for i, (name, type_) in enumerate(sectors):
        # 暂时只获取行业和概念
        if type_ not in ["行业", "概念"]:
            continue
            
        c = fetch_sector_daily(name, type_)
        if c > 0:
            total += c
            count_sectors += 1
            
        if (i + 1) % 50 == 0:
            print(f"   进度: {i+1}/{len(sectors)} - 成功获取 {count_sectors} 个板块")
            
    print(f"   ✅ 板块行情更新完成: {count_sectors} 个板块，共 {total} 条记录")
    return total


def print_stats():
    """打印统计信息"""
    conn = get_connection()
    
    print("\n📈 数据统计:")
    cursor = conn.execute("SELECT type, COUNT(*) FROM sectors GROUP BY type")
    for row in cursor.fetchall():
        print(f"   {row[0]}: {row[1]} 条")
    
    cursor = conn.execute("SELECT COUNT(*) FROM sector_stocks")
    print(f"   成分股关系: {cursor.fetchone()[0]} 条")
    
    try:
        cursor = conn.execute("SELECT COUNT(*) FROM sector_daily")
        print(f"   板块日K线: {cursor.fetchone()[0]} 条")
    except Exception:  # noqa: BLE001
        pass

    cursor = conn.execute("SELECT COUNT(*) FROM stocks")
    print(f"   独立股票: {cursor.fetchone()[0]} 只")
    
    conn.close()



def calculate_sector_rps(window: int = 60):
    """计算板块 RPS (Sector RPS)"""
    print(f"\n📊 计算板块 RPS (窗口{window}日)...")
    
    conn = get_connection()
    
    # 1. 获取所有板块的涨跌幅数据 (Pandas处理)
    try:
        df = pd.read_sql("SELECT sector_name, sector_type, date, change_pct, close FROM sector_daily", conn)
        if df.empty:
            print("   ⚠️ 无板块行情数据")
            return
            
        df['date'] = pd.to_datetime(df['date'])
        df = df.sort_values(['sector_name', 'date'])
        
        # 2. 计算各期涨幅 (10/20/50日)
        print("   计算板块阶段涨幅...")
        
        def compute_chg(group):
            group['chg_10'] = group['close'].pct_change(10)
            group['chg_20'] = group['close'].pct_change(20)
            group['chg_50'] = group['close'].pct_change(50)
            return group

        # 过滤过短的数据
        df_valid = df.groupby('sector_name').filter(lambda x: len(x) > 55)
        
        # 计算涨幅
        df_result = df_valid.groupby('sector_name', group_keys=False).apply(compute_chg)
        
        # 3. 计算每日 Rank
        print("   计算板块横截面排名...")
        
        # 准备RPS表
        conn.execute("""
            CREATE TABLE IF NOT EXISTS sector_rps (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                sector_name TEXT NOT NULL,
                sector_type TEXT,
                date TEXT NOT NULL,
                rps_10 REAL,
                rps_20 REAL,
                rps_50 REAL,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(sector_name, date)
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_sector_rps_name ON sector_rps(sector_name)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_sector_rps_date ON sector_rps(date)")

        # 按日期分组计算Rank
        rps_df = df_result.dropna(subset=['chg_10'])[['date', 'sector_name', 'sector_type', 'chg_10', 'chg_20', 'chg_50']]
        
        def compute_daily_rps(day_group):
            if len(day_group) < 10: return day_group
            day_group['rps_10'] = day_group['chg_10'].rank(pct=True) * 100
            day_group['rps_20'] = day_group['chg_20'].rank(pct=True) * 100
            day_group['rps_50'] = day_group['chg_50'].rank(pct=True) * 100
            return day_group
            
        if not rps_df.empty:
            final_rps = rps_df.groupby('date', group_keys=False).apply(compute_daily_rps)
            
            # 批量写入
            print("   写入板块RPS数据...")
            final_rps['date_str'] = final_rps['date'].dt.strftime('%Y-%m-%d')
            
            rows = []
            for _, row in final_rps.iterrows():
                rows.append((
                   row['sector_name'], row['sector_type'], row['date_str'],
                   row.get('rps_10', 0), row.get('rps_20', 0), row.get('rps_50', 0),
                   datetime.now().isoformat()
                ))
            
            cursor = conn.cursor()
            cursor.executemany("""
                INSERT OR REPLACE INTO sector_rps (sector_name, sector_type, date, rps_10, rps_20, rps_50, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, rows)
            conn.commit()
            print(f"   ✅ 板块RPS计算完成: {len(rows)} 条")
            
    except Exception as e:
        print(f"   ⚠️ 计算失败: {e}")
        # traceback.print_exc()
    finally:
        conn.close()


def main():
    """主入口"""
    import argparse
    parser = argparse.ArgumentParser(description="A股板块概念与成分股获取")
    parser.add_argument("--no-stocks", action="store_true", help="不获取成分股")
    parser.add_argument("--daily", action="store_true", help="获取板块日K线")
    parser.add_argument("--test-rps", action="store_true", help="测试计算板块RPS")
    parser.add_argument("--stats", action="store_true", help="只显示统计信息")
    args = parser.parse_args()
    
    if args.stats:
        print_stats()
        return
    
    print("=" * 50)
    print("A股板块概念获取 & 行情更新")
    print(f"数据库: {STOCKS_DB_PATH}")
    print("=" * 50)
    
    init_database()
    
    # 默认只获取列表，不更新日K；除非指定 --daily
    if args.daily:
        update_all_sectors_daily()
        calculate_sector_rps()
    elif args.test_rps:
        calculate_sector_rps()
    else:
        # 获取数据
        fetch_industry_sectors(fetch_stocks=not args.no_stocks)
        fetch_concept_sectors(fetch_stocks=not args.no_stocks)
        fetch_hot_keywords()
    
    # 统计
    print_stats()
    print("\n✅ 完成!")


if __name__ == "__main__":
    main()
