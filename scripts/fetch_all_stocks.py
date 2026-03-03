#!/usr/bin/env python3
"""
全量股票数据获取脚本

从 stocks 表获取所有股票代码，批量获取：
1. 日行情数据（换手率）
2. 财务指标（ROE、现金流）

支持增量更新，跳过已有数据。
预计耗时：2-3小时（首次运行）
"""

import sqlite3
import time
from datetime import datetime, timedelta
from pathlib import Path

import akshare as ak
import sys

# 添加项目根目录到路径
sys.path.insert(0, str(Path(__file__).parent.parent))

# 使用公共数据库模块
from src.database.connection import get_connection, STOCKS_DB_PATH


def log(msg: str):
    """带时间戳的日志。"""
    ts = datetime.now().strftime("%H:%M:%S")
    print(f"[{ts}] {msg}", flush=True)


def get_all_stock_codes():
    """获取所有股票代码"""
    conn = get_connection()
    cursor = conn.execute("SELECT code FROM stocks")
    codes = [r[0] for r in cursor.fetchall()]
    conn.close()
    return codes


def get_existing_codes(table: str):
    """获取已有数据的股票代码"""
    conn = get_connection()
    try:
        cursor = conn.execute(f"SELECT DISTINCT stock_code FROM {table}")
        codes = set(r[0] for r in cursor.fetchall())
    except Exception as e:
        log(f"   ⚠️ 读取表 {table} 失败: {e}")
        codes = set()
    conn.close()
    return codes


def fetch_stock_daily_batch(stock_codes: list, days: int = 60, skip_existing: bool = True):
    """批量获取日行情"""
    log(f"\n📈 批量获取日行情（{len(stock_codes)} 只股票）...")
    
    if skip_existing:
        existing = get_existing_codes("stock_daily")
        stock_codes = [c for c in stock_codes if c not in existing]
        log(f"   跳过已有 {len(existing)} 只，待获取 {len(stock_codes)} 只")
    
    if not stock_codes:
        print("   ✅ 全部已获取")
        return 0
    
    conn = get_connection()
    total = 0
    errors = 0
    
    for i, code in enumerate(stock_codes):
        try:
            df = ak.stock_zh_a_hist(symbol=code, period="daily", adjust="qfq")
            if df.empty:
                continue
            
            count = 0
            for _, row in df.tail(days).iterrows():
                try:
                    conn.execute("""
                        INSERT OR REPLACE INTO stock_daily 
                        (stock_code, date, open, close, high, low, volume, amount,
                         amplitude, change_pct, turnover_rate, updated_at)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, (
                        code,
                        str(row.get("日期", "")),
                        row.get("开盘", None),
                        row.get("收盘", None),
                        row.get("最高", None),
                        row.get("最低", None),
                        row.get("成交量", None),
                        row.get("成交额", None),
                        row.get("振幅", None),
                        row.get("涨跌幅", None),
                        row.get("换手率", None),
                        datetime.now().isoformat()
                    ))
                    count += 1
                except Exception as e:
                    log(f"   ⚠️ 日行情写入失败 {code} {row.get('日期')}: {e}")
            
            total += count
            
            # 每100只提交一次并显示进度
            if (i + 1) % 100 == 0:
                conn.commit()
                pct = (i + 1) / len(stock_codes) * 100
                log(f"   [{i+1}/{len(stock_codes)}] {pct:.1f}% - 累计 {total} 条")
            
            time.sleep(0.1)  # 控制频率（加速版）
            
        except Exception as e:
            errors += 1
            if errors < 5:
                log(f"   ⚠️ {code} 失败: {e}")
    
    conn.commit()
    conn.close()
    log(f"   ✅ 完成，共 {total} 条，{errors} 个错误")
    return total


def fetch_stock_financials_batch(stock_codes: list, skip_existing: bool = True):
    """批量获取财务指标"""
    log(f"\n📊 批量获取财务指标（{len(stock_codes)} 只股票）...")
    
    if skip_existing:
        existing = get_existing_codes("stock_financials")
        stock_codes = [c for c in stock_codes if c not in existing]
        log(f"   跳过已有 {len(existing)} 只，待获取 {len(stock_codes)} 只")
    
    if not stock_codes:
        print("   ✅ 全部已获取")
        return 0
    
    conn = get_connection()
    
    # 确保表存在
    conn.execute("""
        CREATE TABLE IF NOT EXISTS stock_financials (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            stock_code TEXT NOT NULL,
            report_date TEXT NOT NULL,
            roe REAL,
            roe_avg REAL,
            net_profit REAL,
            net_profit_yoy REAL,
            revenue REAL,
            revenue_yoy REAL,
            deducted_profit REAL,
            operating_cashflow REAL,
            cashflow_profit_ratio REAL,
            gross_margin REAL,
            net_margin REAL,
            debt_ratio REAL,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(stock_code, report_date)
        )
    """)
    
    total = 0
    errors = 0
    
    def safe_get(series_or_val):
        if series_or_val is None:
            return None
        if hasattr(series_or_val, 'iloc'):
            return series_or_val.iloc[0] if len(series_or_val) > 0 else None
        return series_or_val
    
    for i, code in enumerate(stock_codes):
        try:
            # 构造 symbol
            if code.startswith("6"):
                symbol = f"sh{code}"
            else:
                symbol = f"sz{code}"
            
            df = ak.stock_financial_abstract(symbol=symbol)
            if df.empty:
                continue
            
            # 转置并去重
            df = df.set_index("指标").T
            df = df.drop("选项", errors="ignore")
            df = df.loc[:, ~df.columns.duplicated()]
            
            count = 0
            for report_date in list(df.index)[:12]:  # 最近 12 个季度（3年）
                try:
                    row = df.loc[report_date]
                    
                    cashflow = safe_get(row.get("经营现金流量净额", None))
                    profit = safe_get(row.get("净利润", None))
                    cashflow_ratio = None
                    if cashflow and profit and profit != 0:
                        try:
                            cashflow_ratio = float(cashflow) / float(profit)
                        except Exception as e:
                            log(f"   ⚠️ 现金流比率计算失败 {code} {report_date}: {e}")
                    
                    conn.execute("""
                        INSERT OR REPLACE INTO stock_financials 
                        (stock_code, report_date, roe, roe_avg, net_profit, net_profit_yoy,
                         revenue, revenue_yoy, deducted_profit, operating_cashflow,
                         cashflow_profit_ratio, gross_margin, net_margin, debt_ratio, updated_at)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, (
                        code,
                        report_date,
                        safe_get(row.get("净资产收益率(ROE)", None)),
                        safe_get(row.get("净资产收益率_平均", None)),
                        profit,
                        safe_get(row.get("归属母公司净利润增长率", None)),
                        safe_get(row.get("营业总收入", None)),
                        safe_get(row.get("营业总收入增长率", None)),
                        safe_get(row.get("扣非净利润", None)),
                        cashflow,
                        cashflow_ratio,
                        safe_get(row.get("毛利率", None)),
                        safe_get(row.get("销售净利率", None)),
                        safe_get(row.get("资产负债率", None)),
                        datetime.now().isoformat()
                    ))
                    count += 1
                except Exception as e:
                    log(f"   ⚠️ 财务写入失败 {code} {report_date}: {e}")
            
            total += count
            
            # 更频繁的进度输出（每10个）
            if (i + 1) % 10 == 0:
                conn.commit()
                pct = (i + 1) / len(stock_codes) * 100
                log(f"   [{i+1}/{len(stock_codes)}] {pct:.1f}% - 累计 {total} 条")
            
            time.sleep(0.1)  # 控制频率（加速版）
            
        except Exception as e:
            errors += 1
            if errors < 5:
                log(f"   ⚠️ {code} 失败: {e}")
    
    conn.commit()
    conn.close()
    log(f"   ✅ 完成，共 {total} 条，{errors} 个错误")
    return total


def print_stats():
    """打印统计"""
    conn = get_connection()
    print("\n📊 数据覆盖统计:")
    
    cursor = conn.execute("SELECT COUNT(*) FROM stocks")
    total = cursor.fetchone()[0]
    log(f"   股票总数: {total}")
    
    for table, name in [("stock_daily", "日行情"), ("stock_financials", "财务指标")]:
        try:
            cursor = conn.execute(f"SELECT COUNT(DISTINCT stock_code) FROM {table}")
            count = cursor.fetchone()[0]
            pct = count / total * 100 if total > 0 else 0
            log(f"   {name}: {count} 只 ({pct:.1f}%)")
        except Exception as e:
            log(f"   ⚠️ 统计表 {table} 失败: {e}")
            log(f"   {name}: 0 只 (0%)")
    
    conn.close()


def main():
    import argparse
    parser = argparse.ArgumentParser(description="全量股票数据获取")
    parser.add_argument("--daily", action="store_true", help="只获取日行情")
    parser.add_argument("--financial", action="store_true", help="只获取财务指标")
    parser.add_argument("--limit", type=int, default=0, help="限制获取数量（用于测试）")
    parser.add_argument("--force", action="store_true", help="强制重新获取（不跳过已有）")
    parser.add_argument("--stats", action="store_true", help="只显示统计")
    args = parser.parse_args()
    
    if args.stats:
        print_stats()
        return
    
    log("=" * 50)
    print("全量股票数据获取")
    log(f"数据库: {STOCKS_DB_PATH}")
    log("=" * 50)
    
    # 获取所有股票代码
    all_codes = get_all_stock_codes()
    log(f"共 {len(all_codes)} 只股票")
    
    if args.limit > 0:
        all_codes = all_codes[:args.limit]
        log(f"限制获取前 {args.limit} 只")
    
    skip = not args.force
    
    if args.daily or (not args.daily and not args.financial):
        fetch_stock_daily_batch(all_codes, skip_existing=skip)
    
    if args.financial or (not args.daily and not args.financial):
        fetch_stock_financials_batch(all_codes, skip_existing=skip)
    
    print_stats()
    print("\n✅ 完成!")


if __name__ == "__main__":
    main()
