#!/usr/bin/env python3
"""
数据完整性检查模块

功能：
1. 检测缺失的交易日数据
2. 检测股票数据覆盖率
3. 识别数据断点和异常
4. 生成完整性报告
"""

import sqlite3
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional
from collections import defaultdict

# 数据库路径 (使用公共数据库模块)
from fetchers.db import STOCKS_DB_PATH


def get_connection() -> sqlite3.Connection:
    """获取数据库连接"""
    conn = sqlite3.connect(STOCKS_DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


# ============================================================
# 交易日历
# ============================================================

def get_trading_days(start_date: str, end_date: str) -> list[str]:
    """
    获取交易日列表（基于已有数据推断）

    注：实际应用中应使用 akshare 的交易日历 API
    这里使用数据库中的最大覆盖日期作为近似
    """
    conn = get_connection()
    cursor = conn.execute("""
        SELECT DISTINCT date FROM stock_daily
        WHERE date BETWEEN ? AND ?
        ORDER BY date
    """, (start_date, end_date))
    days = [row['date'] for row in cursor.fetchall()]
    conn.close()
    return days


def get_all_stock_codes() -> list[str]:
    """获取所有股票代码"""
    conn = get_connection()
    cursor = conn.execute("SELECT DISTINCT code FROM stocks ORDER BY code")
    codes = [row['code'] for row in cursor.fetchall()]
    conn.close()
    return codes


# ============================================================
# 完整性检查
# ============================================================

def check_daily_coverage(days: int = 30) -> dict:
    """
    检查日行情数据覆盖率

    Returns:
        dict: {
            'total_stocks': int,
            'total_days': int,
            'coverage_rate': float,
            'missing_days': list[str],
            'low_coverage_days': list[dict]
        }
    """
    conn = get_connection()

    # 最近 N 天的日期范围
    end_date = datetime.now().strftime("%Y-%m-%d")
    start_date = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")

    # 获取交易日
    trading_days = get_trading_days(start_date, end_date)

    # 获取总股票数
    cursor = conn.execute("SELECT COUNT(DISTINCT code) FROM stocks")
    total_stocks = cursor.fetchone()[0]

    # 检查每个交易日的数据覆盖
    coverage = []
    for day in trading_days:
        cursor = conn.execute("""
            SELECT COUNT(DISTINCT stock_code) as count FROM stock_daily WHERE date = ?
        """, (day,))
        count = cursor.fetchone()['count']
        rate = count / total_stocks * 100 if total_stocks > 0 else 0
        coverage.append({
            'date': day,
            'count': count,
            'total': total_stocks,
            'rate': round(rate, 2)
        })

    # 识别低覆盖日（< 80%）
    low_coverage = [c for c in coverage if c['rate'] < 80]

    # 计算总体覆盖率
    avg_rate = sum(c['rate'] for c in coverage) / len(coverage) if coverage else 0

    conn.close()

    return {
        'total_stocks': total_stocks,
        'total_days': len(trading_days),
        'coverage_rate': round(avg_rate, 2),
        'trading_days': trading_days,
        'low_coverage_days': low_coverage,
        'coverage_detail': coverage
    }


def check_table_freshness() -> list[dict]:
    """
    检查各表数据新鲜度（使用交易日历计算延迟）

    Returns:
        list[dict]: 各表最新数据日期
    """
    # 导入交易日历
    try:
        from fetchers.trading_calendar import calculate_trading_day_delay, get_latest_trading_day
        use_trading_calendar = True
    except ImportError:
        use_trading_calendar = False

    conn = get_connection()

    tables = [
        ('stock_daily', 'date', '日行情'),
        ('stock_financials', 'report_date', '财务指标'),
        ('main_money_flow', 'date', '主力资金'),
        ('north_money_holding', 'date', '北向持股'),
        ('dragon_tiger_stock', 'date', '龙虎榜'),
        ('margin_trading', 'date', '融资融券'),
        ('stock_rps', 'date', 'RPS强度'),
        ('stock_technicals', 'date', '技术指标'),
    ]

    results = []
    for table, date_col, name in tables:
        try:
            cursor = conn.execute(f"""
                SELECT MAX({date_col}) as latest, COUNT(*) as count
                FROM {table}
            """)
            row = cursor.fetchone()
            latest = row['latest'] if row else None
            count = row['count'] if row else 0

            # 计算数据延迟（交易日天数）
            delay = None
            delay_type = "自然日"
            if latest:
                try:
                    latest_str = str(latest)[:10]
                    if use_trading_calendar:
                        delay = calculate_trading_day_delay(latest_str)
                        delay_type = "交易日"
                    else:
                        latest_dt = datetime.strptime(latest_str, "%Y-%m-%d")
                        delay = (datetime.now() - latest_dt).days
                except Exception:
                    pass

            # 判断状态（财务指标特殊处理：允许 > 90 天）
            if name == '财务指标':
                status = 'ok' if delay is not None else 'empty'
            else:
                status = 'ok' if delay is not None and delay <= 1 else 'stale' if delay else 'empty'

            results.append({
                'table': table,
                'name': name,
                'latest_date': latest,
                'record_count': count,
                'delay_days': delay,
                'delay_type': delay_type,
                'status': status
            })
        except Exception as e:
            results.append({
                'table': table,
                'name': name,
                'error': str(e),
                'status': 'error'
            })

    conn.close()
    return results


def check_stock_data_gaps(stock_code: str, days: int = 60) -> dict:
    """
    检查单只股票的数据断点

    Args:
        stock_code: 股票代码
        days: 检查的天数范围

    Returns:
        dict: 断点信息
    """
    conn = get_connection()

    end_date = datetime.now().strftime("%Y-%m-%d")
    start_date = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")

    # 获取该股票的数据日期
    cursor = conn.execute("""
        SELECT date FROM stock_daily
        WHERE stock_code = ? AND date BETWEEN ? AND ?
        ORDER BY date
    """, (stock_code, start_date, end_date))
    dates = [row['date'] for row in cursor.fetchall()]

    # 获取交易日历
    trading_days = get_trading_days(start_date, end_date)

    # 计算缺失日期
    missing = set(trading_days) - set(dates)

    conn.close()

    return {
        'stock_code': stock_code,
        'expected_days': len(trading_days),
        'actual_days': len(dates),
        'missing_days': sorted(list(missing)),
        'coverage_rate': round(len(dates) / len(trading_days) * 100, 2) if trading_days else 0
    }


def check_data_anomalies(limit: int = 100) -> list[dict]:
    """
    检查数据异常（极端值）

    Returns:
        list[dict]: 异常记录
    """
    conn = get_connection()
    anomalies = []

    # 1. 涨跌幅异常（> 20% 或 < -20%，非新股）
    cursor = conn.execute("""
        SELECT stock_code, date, change_pct
        FROM stock_daily
        WHERE ABS(change_pct) > 20
        AND date > date('now', '-30 days')
        ORDER BY ABS(change_pct) DESC
        LIMIT ?
    """, (limit,))
    for row in cursor.fetchall():
        anomalies.append({
            'type': 'extreme_change',
            'stock_code': row['stock_code'],
            'date': row['date'],
            'value': row['change_pct'],
            'description': f"涨跌幅 {row['change_pct']:.2f}%"
        })

    # 2. 换手率异常（> 50%）
    cursor = conn.execute("""
        SELECT stock_code, date, turnover_rate
        FROM stock_daily
        WHERE turnover_rate > 50
        AND date > date('now', '-30 days')
        ORDER BY turnover_rate DESC
        LIMIT ?
    """, (limit,))
    for row in cursor.fetchall():
        anomalies.append({
            'type': 'high_turnover',
            'stock_code': row['stock_code'],
            'date': row['date'],
            'value': row['turnover_rate'],
            'description': f"换手率 {row['turnover_rate']:.2f}%"
        })

    conn.close()
    return anomalies


# ============================================================
# 综合报告
# ============================================================

def generate_integrity_report() -> dict:
    """生成完整性检查报告"""
    print("📊 数据完整性检查")
    print("=" * 50)

    report = {
        'generated_at': datetime.now().isoformat(),
        'checks': {}
    }

    # 1. 表新鲜度检查
    print("\n📅 表数据新鲜度检查...")
    freshness = check_table_freshness()
    report['checks']['freshness'] = freshness

    stale_tables = [t for t in freshness if t['status'] == 'stale']
    empty_tables = [t for t in freshness if t['status'] == 'empty']

    for t in freshness:
        icon = "✅" if t['status'] == 'ok' else "⚠️" if t['status'] == 'stale' else "❌"
        delay_type = t.get('delay_type', '天')
        delay = f"(延迟 {t.get('delay_days', '?')} {delay_type})" if t.get('delay_days') else ""
        print(f"   {icon} {t['name']}: {t.get('latest_date', 'N/A')} {delay}")

    # 2. 日行情覆盖率检查
    print("\n📈 日行情覆盖率检查...")
    coverage = check_daily_coverage(days=30)
    report['checks']['daily_coverage'] = {
        'total_stocks': coverage['total_stocks'],
        'total_days': coverage['total_days'],
        'coverage_rate': coverage['coverage_rate'],
        'low_coverage_days': coverage['low_coverage_days']
    }

    print(f"   总股票数: {coverage['total_stocks']}")
    print(f"   检查天数: {coverage['total_days']}")
    print(f"   平均覆盖率: {coverage['coverage_rate']}%")

    if coverage['low_coverage_days']:
        print(f"   低覆盖日({len(coverage['low_coverage_days'])}天):")
        for d in coverage['low_coverage_days'][:5]:
            print(f"      {d['date']}: {d['rate']}%")

    # 3. 数据异常检查
    print("\n🔍 数据异常检查...")
    anomalies = check_data_anomalies(limit=10)
    report['checks']['anomalies'] = anomalies[:20]

    print(f"   发现 {len(anomalies)} 条异常记录")
    for a in anomalies[:5]:
        print(f"      {a['stock_code']} {a['date']}: {a['description']}")

    # 4. 汇总
    print("\n" + "=" * 50)
    issues = len(stale_tables) + len(empty_tables) + len(coverage['low_coverage_days'])
    if issues == 0:
        print("✅ 数据完整性检查通过")
    else:
        print(f"⚠️ 发现 {issues} 个潜在问题")

    report['summary'] = {
        'stale_tables': len(stale_tables),
        'empty_tables': len(empty_tables),
        'low_coverage_days': len(coverage['low_coverage_days']),
        'total_issues': issues
    }

    return report


if __name__ == "__main__":
    report = generate_integrity_report()
