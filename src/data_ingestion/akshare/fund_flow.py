#!/usr/bin/env python3
"""
资金流向数据获取脚本

使用 akshare 获取：
1. 沪深股通资金流向（北向资金）
2. 龙虎榜机构买卖统计
3. 股东户数变化
4. 营业部交易统计（游资）

存入 stocks.db 数据库（与板块数据同库）
"""

import sqlite3
import sys
from datetime import datetime, timedelta
from pathlib import Path

import akshare as ak

PROJECT_ROOT = Path(__file__).resolve().parents[3]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# 使用公共数据库模块
from src.database.connection import get_connection, STOCKS_DB_PATH


def init_fund_flow_tables():
    """初始化资金流向相关表"""
    conn = get_connection()
    
    # 沪深股通资金流向
    conn.execute("""
        CREATE TABLE IF NOT EXISTS hsgt_fund_flow (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT NOT NULL,
            type TEXT NOT NULL,
            board TEXT NOT NULL,
            direction TEXT,
            net_buy REAL,
            net_flow REAL,
            balance REAL,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(date, type, board)
        )
    """)
    
    # 龙虎榜机构买卖
    conn.execute("""
        CREATE TABLE IF NOT EXISTS lhb_institution (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT NOT NULL,
            stock_code TEXT NOT NULL,
            stock_name TEXT,
            close_price REAL,
            change_pct REAL,
            buy_inst_count INTEGER,
            sell_inst_count INTEGER,
            inst_buy_amount REAL,
            inst_sell_amount REAL,
            inst_net_buy REAL,
            total_amount REAL,
            reason TEXT,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(date, stock_code)
        )
    """)
    
    # 营业部交易统计（游资）
    conn.execute("""
        CREATE TABLE IF NOT EXISTS lhb_trader (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT NOT NULL,
            trader_name TEXT NOT NULL,
            times INTEGER,
            buy_amount REAL,
            sell_amount REAL,
            net_buy REAL,
            buy_stocks TEXT,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(date, trader_name)
        )
    """)
    
    # 股东户数变化
    conn.execute("""
        CREATE TABLE IF NOT EXISTS shareholder_count (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            stock_code TEXT NOT NULL,
            stock_name TEXT,
            price REAL,
            holder_count_current INTEGER,
            holder_count_last INTEGER,
            holder_change INTEGER,
            holder_change_pct REAL,
            price_change_pct REAL,
            stats_date_current TEXT,
            stats_date_last TEXT,
            announce_date TEXT,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(stock_code, stats_date_current)
        )
    """)
    
    # 索引
    conn.execute("CREATE INDEX IF NOT EXISTS idx_hsgt_date ON hsgt_fund_flow(date)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_lhb_inst_date ON lhb_institution(date)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_lhb_trader_date ON lhb_trader(date)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_shareholder_code ON shareholder_count(stock_code)")
    
    conn.commit()
    conn.close()
    print("✅ 资金流向表初始化完成")


def fetch_hsgt_fund_flow():
    """获取沪深股通资金流向"""
    print("\n📈 获取沪深股通资金流向...")
    try:
        df = ak.stock_hsgt_fund_flow_summary_em()
        conn = get_connection()
        
        count = 0
        for _, row in df.iterrows():
            try:
                date = str(row.get("交易日", ""))
                if not date:
                    continue
                
                conn.execute("""
                    INSERT OR REPLACE INTO hsgt_fund_flow 
                    (date, type, board, direction, net_buy, net_flow, balance, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    date,
                    row.get("类型", ""),
                    row.get("板块", ""),
                    row.get("资金方向", ""),
                    row.get("成交净买额", None),
                    row.get("资金净流入", None),
                    row.get("当日资金余额", None),
                    datetime.now().isoformat()
                ))
                count += 1
            except Exception as e:
                print(f"  ⚠️ 保存失败: {e}")
        
        conn.commit()
        conn.close()
        print(f"   ✅ 保存 {count} 条沪深股通数据")
        return count
    except Exception as e:
        print(f"   ⚠️ 获取失败: {e}")
        return 0


def fetch_lhb_institution(days: int = 30):
    """获取龙虎榜机构买卖统计"""
    print(f"\n🐉 获取龙虎榜机构买卖统计（近{days}天）...")
    try:
        end_date = datetime.now().strftime("%Y%m%d")
        start_date = (datetime.now() - timedelta(days=days)).strftime("%Y%m%d")
        
        df = ak.stock_lhb_jgmmtj_em(start_date=start_date, end_date=end_date)
        conn = get_connection()
        
        count = 0
        for _, row in df.iterrows():
            try:
                date = str(row.get("上榜日期", ""))
                if not date:
                    continue
                
                conn.execute("""
                    INSERT OR REPLACE INTO lhb_institution 
                    (date, stock_code, stock_name, close_price, change_pct,
                     buy_inst_count, sell_inst_count, inst_buy_amount, inst_sell_amount,
                     inst_net_buy, total_amount, reason, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    date,
                    str(row.get("代码", "")),
                    row.get("名称", ""),
                    row.get("收盘价", None),
                    row.get("涨跌幅", None),
                    row.get("买方机构数", None),
                    row.get("卖方机构数", None),
                    row.get("机构买入总额", None),
                    row.get("机构卖出总额", None),
                    row.get("机构买入净额", None),
                    row.get("市场总成交额", None),
                    row.get("上榜原因", ""),
                    datetime.now().isoformat()
                ))
                count += 1
            except Exception as e:
                print(f"  ⚠️ 保存失败: {e}")
        
        conn.commit()
        conn.close()
        print(f"   ✅ 保存 {count} 条龙虎榜机构数据")
        return count
    except Exception as e:
        print(f"   ⚠️ 获取失败: {e}")
        return 0


def fetch_lhb_trader(days: int = 30):
    """获取龙虎榜营业部统计（游资）"""
    # 根据天数选择不同的 symbol
    if days <= 5:
        symbol = "近五日"
    elif days <= 10:
        symbol = "近十日"
    else:
        symbol = "近一月"
    
    print(f"\n💰 获取龙虎榜营业部统计（{symbol}）...")
    try:
        df = ak.stock_lhb_traderstatistic_em(symbol=symbol)
        conn = get_connection()
        
        count = 0
        for _, row in df.iterrows():
            try:
                # 使用今天作为日期
                date = datetime.now().strftime("%Y-%m-%d")
                
                buy_amt = row.get("买入额", 0)
                sell_amt = row.get("卖出额", 0)
                net_buy = None
                if buy_amt and sell_amt:
                    net_buy = buy_amt - sell_amt
                
                conn.execute("""
                    INSERT OR REPLACE INTO lhb_trader 
                    (date, trader_name, times, buy_amount, sell_amount, net_buy, buy_stocks, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    date,
                    row.get("营业部名称", ""),
                    row.get("上榜次数", None),
                    buy_amt,
                    sell_amt,
                    net_buy,
                    "",  # 该 API 没有买入股票字段
                    datetime.now().isoformat()
                ))
                count += 1
            except Exception as e:
                print(f"  ⚠️ 保存失败: {e}")
        
        conn.commit()
        conn.close()
        print(f"   ✅ 保存 {count} 条营业部数据")
        return count
    except Exception as e:
        print(f"   ⚠️ 获取失败: {e}")
        return 0


def fetch_shareholder_count():
    """获取股东户数变化（使用 tinyshare/Tushare API）"""
    print("\n👥 获取股东户数变化 via Tushare...")
    try:
        from src.data_ingestion.tushare.client import get_tushare_client

        client = get_tushare_client()

        # 获取最近3个月数据，用于计算前后对比
        end_date = datetime.now().strftime("%Y%m%d")
        start_date = (datetime.now() - timedelta(days=90)).strftime("%Y%m%d")

        df = client.stk_holdernumber(start_date=start_date, end_date=end_date)
        if df is None or df.empty:
            print("   ⚠️ 无数据返回")
            return 0

        # 去除 holder_num 为 NaN 的行
        import pandas as pd
        df = df.dropna(subset=['holder_num'])
        df = df.sort_values(['ts_code', 'end_date'], ascending=[True, False])

        conn = get_connection()
        count = 0

        for ts_code, group in df.groupby('ts_code'):
            rows = group.head(2)
            if len(rows) < 1:
                continue

            current = rows.iloc[0]
            holder_current = int(current['holder_num']) if pd.notna(current['holder_num']) else None
            stats_date_current = str(current['end_date'])
            ann_date = str(current.get('ann_date', ''))

            holder_last = None
            holder_change = None
            holder_change_pct = None
            stats_date_last = ''

            if len(rows) >= 2:
                prev = rows.iloc[1]
                holder_last = int(prev['holder_num']) if pd.notna(prev['holder_num']) else None
                stats_date_last = str(prev['end_date'])
                if holder_current and holder_last and holder_last > 0:
                    holder_change = holder_current - holder_last
                    holder_change_pct = round(holder_change / holder_last * 100, 4)

            stock_code = ts_code[:6]
            try:
                conn.execute("""
                    INSERT OR REPLACE INTO shareholder_count
                    (stock_code, stock_name, price, holder_count_current, holder_count_last,
                     holder_change, holder_change_pct, price_change_pct,
                     stats_date_current, stats_date_last, announce_date, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    stock_code, None, None,
                    holder_current, holder_last,
                    holder_change, holder_change_pct, None,
                    stats_date_current, stats_date_last, ann_date,
                    datetime.now().isoformat()
                ))
                count += 1
            except Exception:
                pass

        conn.commit()
        conn.close()
        print(f"   ✅ 保存 {count} 条股东户数数据")
        return count
    except Exception as e:
        print(f"   ⚠️ Tushare 获取失败({e})，回退到 akshare...")
        return _fetch_shareholder_count_akshare()


def _fetch_shareholder_count_akshare():
    """akshare 回退方案"""
    try:
        df = ak.stock_zh_a_gdhs(symbol="最新")
        conn = get_connection()
        count = 0
        for _, row in df.iterrows():
            try:
                conn.execute("""
                    INSERT OR REPLACE INTO shareholder_count
                    (stock_code, stock_name, price, holder_count_current, holder_count_last,
                     holder_change, holder_change_pct, price_change_pct,
                     stats_date_current, stats_date_last, announce_date, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    str(row.get("代码", "")),
                    row.get("名称", ""),
                    row.get("最新价", None),
                    row.get("股东户数-本次", None),
                    row.get("股东户数-上次", None),
                    row.get("股东户数-增减", None),
                    row.get("股东户数-增减比例", None),
                    row.get("区间涨跌幅", None),
                    str(row.get("股东户数统计截止日-本次", "")),
                    str(row.get("股东户数统计截止日-上次", "")),
                    str(row.get("公告日期", "")),
                    datetime.now().isoformat()
                ))
                count += 1
            except Exception:
                pass
        conn.commit()
        conn.close()
        print(f"   ✅ 保存 {count} 条股东户数数据 (akshare)")
        return count
    except Exception as e:
        print(f"   ⚠️ akshare 也失败: {e}")
        return 0


def print_stats():
    """打印统计信息"""
    conn = get_connection()
    
    print("\n📈 资金流向数据统计:")
    
    tables = [
        ("hsgt_fund_flow", "沪深股通"),
        ("lhb_institution", "龙虎榜机构"),
        ("lhb_trader", "营业部游资"),
        ("shareholder_count", "股东户数"),
    ]
    
    for table, name in tables:
        try:
            cursor = conn.execute(f"SELECT COUNT(*) FROM {table}")
            count = cursor.fetchone()[0]
            print(f"   {name}: {count} 条")
        except Exception:  # noqa: BLE001
            print(f"   {name}: 0 条")
    
    conn.close()


def get_latest_north_flow():
    """获取最新北向资金流向"""
    conn = get_connection()
    cursor = conn.execute("""
        SELECT date, board, net_buy, net_flow 
        FROM hsgt_fund_flow 
        WHERE direction = '北向'
        ORDER BY date DESC LIMIT 4
    """)
    rows = cursor.fetchall()
    conn.close()
    return [{"date": r[0], "board": r[1], "net_buy": r[2], "net_flow": r[3]} for r in rows]


def main():
    """主入口"""
    import argparse
    parser = argparse.ArgumentParser(description="资金流向数据获取")
    parser.add_argument("--stats", action="store_true", help="只显示统计信息")
    parser.add_argument("--days", type=int, default=30, help="龙虎榜查询天数")
    args = parser.parse_args()
    
    if args.stats:
        print_stats()
        return
    
    print("=" * 50)
    print("资金流向数据获取")
    print(f"数据库: {STOCKS_DB_PATH}")
    print("=" * 50)
    
    init_fund_flow_tables()
    
    # 获取数据
    fetch_hsgt_fund_flow()
    fetch_lhb_institution(days=args.days)
    fetch_lhb_trader(days=args.days)
    fetch_shareholder_count()
    
    # 统计
    print_stats()
    
    # 显示最新北向资金
    north_flow = get_latest_north_flow()
    if north_flow:
        print("\n🔥 最新北向资金:")
        for f in north_flow[:2]:
            print(f"   {f['date']} {f['board']}: 净买入 {f['net_buy']} 亿")
    
    print("\n✅ 完成!")


if __name__ == "__main__":
    main()
