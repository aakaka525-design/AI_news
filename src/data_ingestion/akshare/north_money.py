#!/usr/bin/env python3
"""
北向资金获取模块

获取沪深港通持股数据
数据源：东方财富
"""

import sqlite3
import sys
import time
import requests
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[3]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# 使用公共数据库模块
from src.database.connection import get_connection, STOCKS_DB_PATH

# 东方财富北向持股接口
EM_NORTH_API = "https://push2.eastmoney.com/api/qt/clist/get"


def log(msg: str):
    """格式化输出日志信息。"""
    ts = datetime.now().strftime("%H:%M:%S")
    print(f"[{ts}] {msg}", flush=True)


def init_north_money_table():
    """初始化北向资金表"""
    conn = get_connection()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS north_money_holding (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            stock_code TEXT NOT NULL,
            stock_name TEXT,
            date TEXT NOT NULL,
            
            -- 持仓数据
            hold_shares REAL,            -- 持股数量（股）
            hold_market_value REAL,      -- 持股市值（元）
            hold_ratio REAL,             -- 持股占流通股比例（%）
            hold_ratio_change REAL,      -- 持股比例变化（百分点）
            
            -- 交易数据
            net_buy_shares REAL,         -- 净买入股数
            net_buy_value REAL,          -- 净买入金额
            
            -- 价格
            close_price REAL,            -- 收盘价
            change_pct REAL,             -- 涨跌幅
            
            -- 来源
            market TEXT,                 -- 沪股通/深股通
            
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(stock_code, date, market)
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_north_code ON north_money_holding(stock_code)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_north_date ON north_money_holding(date)")
    conn.commit()
    conn.close()
    log("北向资金表初始化完成")


def fetch_north_money():
    """获取北向资金持股（使用东方财富数据中心 API）"""
    log("📊 获取北向资金持股数据...")
    
    conn = get_connection()
    total = 0
    
    url = 'https://datacenter-web.eastmoney.com/api/data/v1/get'
    headers = {
        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)',
        'Referer': 'https://data.eastmoney.com/',
    }
    
    page = 1
    page_size = 500
    latest_date = None
    
    while True:
        try:
            params = {
                'reportName': 'RPT_MUTUAL_HOLD_DET',
                'columns': 'ALL',
                'pageSize': page_size,
                'pageNumber': page,
                'sortColumns': 'HOLD_DATE',
                'sortTypes': -1,
                'source': 'WEB',
            }
            
            resp = requests.get(url, headers=headers, params=params, timeout=30)
            data = resp.json()
            
            if not data.get('success') or not data.get('result'):
                log(f"   ⚠️ API 返回失败: {data.get('message')}")
                break
            
            items = data['result'].get('data', [])
            if not items:
                break
            
            # 获取最新日期
            if latest_date is None:
                latest_date = items[0].get('HOLD_DATE', '')[:10]
                log(f"   最新日期: {latest_date}")
            
            count = 0
            for item in items:
                date = item.get('HOLD_DATE', '')[:10]
                # 只保存最新日期的数据
                if date != latest_date:
                    continue
                
                code = item.get('SECURITY_CODE', '')
                name = item.get('SECURITY_NAME_ABBR', '')
                market_code = item.get('MARKET_CODE', '')
                
                conn.execute("""
                    INSERT OR REPLACE INTO north_money_holding
                    (stock_code, stock_name, date, hold_shares, hold_market_value, 
                     hold_ratio, close_price, change_pct, market, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    code, name, date,
                    item.get('HOLD_NUM'), item.get('HOLD_MARKET_CAP'),
                    item.get('HOLD_SHARES_RATIO'), item.get('CLOSE_PRICE'), item.get('CHANGE_RATE'),
                    '沪股通' if market_code == '001' else '深股通',
                    datetime.now().isoformat()
                ))
                count += 1
            
            conn.commit()
            total += count
            log(f"   第{page}页: {count} 条，累计 {total} 条")
            
            # 如果获取到的数据不是最新日期，说明已经翻到旧数据
            if date != latest_date:
                break
            
            page += 1
            time.sleep(0.3)
            
        except Exception as e:
            log(f"   ⚠️ 第{page}页获取失败: {e}")
            break
    
    conn.close()
    log(f"   ✅ 北向资金持股: 共 {total} 条 ({latest_date})")
    return total


def fetch_north_fund_flow():
    """获取北向资金流入流出历史"""
    log("📊 获取北向资金流入流出历史...")
    
    try:
        import akshare as ak
    except ImportError:
        log("   ⚠️ 需要安装 akshare")
        return 0
    
    conn = get_connection()
    
    # 创建资金流入流出表
    conn.execute("""
        CREATE TABLE IF NOT EXISTS hsgt_fund_flow (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT NOT NULL UNIQUE,
            net_buy_value REAL,
            buy_value REAL,
            sell_value REAL,
            cumulative_net REAL,
            fund_inflow REAL,
            balance REAL,
            hold_market_value REAL,
            leading_stock TEXT,
            leading_stock_pct REAL,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    try:
        df = ak.stock_hsgt_hist_em(symbol='北向资金')
        log(f"   获取到 {len(df)} 条历史记录")
        
        count = 0
        for _, row in df.iterrows():
            try:
                date_val = str(row['日期'])[:10]
                # 只保存最近一年数据
                if date_val < '2025-01-01':
                    continue
                    
                conn.execute("""
                    INSERT OR REPLACE INTO hsgt_fund_flow
                    (date, net_buy_value, buy_value, sell_value, cumulative_net,
                     fund_inflow, balance, hold_market_value, leading_stock, leading_stock_pct, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    date_val,
                    row.get('当日成交净买额'), row.get('买入成交额'), row.get('卖出成交额'),
                    row.get('历史累计净买额'), row.get('当日资金流入'), row.get('当日余额'),
                    row.get('持股市值'), row.get('领涨股'), row.get('领涨股-涨跌幅'),
                    datetime.now().isoformat()
                ))
                count += 1
            except Exception:
                pass
        
        conn.commit()
        log(f"   ✅ 保存 {count} 条资金流向记录")
        return count
        
    except Exception as e:
        log(f"   ⚠️ 获取失败: {e}")
        return 0
    finally:
        conn.close()


def main():
    log("=" * 50)
    log("北向资金持股数据获取（东方财富）")
    log(f"数据库: {STOCKS_DB_PATH}")
    log("=" * 50)
    
    init_north_money_table()
    fetch_north_money()
    
    # 统计
    conn = get_connection()
    today = datetime.now().strftime("%Y-%m-%d")
    cursor = conn.execute("""
        SELECT COUNT(*), market, SUM(net_buy_value)
        FROM north_money_holding 
        WHERE date = ?
        GROUP BY market
    """, (today,))
    
    rows = cursor.fetchall()
    for count, market, net_buy in rows:
        log(f"📊 {market}: {count} 只股票")
        if net_buy:
            log(f"   主力净流入: {net_buy/1e8:.2f} 亿元")
    
    conn.close()
    log("✅ 完成!")


if __name__ == "__main__":
    main()
