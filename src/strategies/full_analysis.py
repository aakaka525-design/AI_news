#!/usr/bin/env python3
"""
完整个股分析脚本 - 301033 迈普医学
"""
import logging
import akshare as ak
import pandas as pd
import sqlite3
from pathlib import Path
from datetime import datetime, timedelta
import sys

logger = logging.getLogger(__name__)

# 添加项目根目录到路径
PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# 使用公共数据库模块
from src.database.connection import get_connection, STOCKS_DB_PATH

# 默认股票代码（可通过命令行参数覆盖）
STOCK_CODE = "301033"
DB_PATH = STOCKS_DB_PATH  # 保持向后兼容

def get_kline():
    """获取最新K线数据"""
    logger.info("=" * 60)
    logger.info("【1. K线数据】股票代码: %s", STOCK_CODE)
    logger.info("=" * 60)

    df = ak.stock_zh_a_hist(symbol=STOCK_CODE, period="daily", adjust="qfq")
    df = df.tail(60)  # 最近60天

    logger.info("数据范围: %s ~ %s", df['日期'].min(), df['日期'].max())
    logger.info("最近5日K线:\n%s", df.tail(5)[['日期', '开盘', '收盘', '最高', '最低', '成交量', '涨跌幅']].to_string(index=False))

    return df

def analyze_pattern(df):
    """识别K线形态"""
    logger.info("=" * 60)
    logger.info("【2. 技术形态分析】")
    logger.info("=" * 60)

    closes = df['收盘'].values
    highs = df['最高'].values
    lows = df['最低'].values
    volumes = df['成交量'].values

    # 计算均线
    ma5 = pd.Series(closes).rolling(5).mean().iloc[-1]
    ma10 = pd.Series(closes).rolling(10).mean().iloc[-1]
    ma20 = pd.Series(closes).rolling(20).mean().iloc[-1]
    ma60 = pd.Series(closes).rolling(60).mean().iloc[-1] if len(closes) >= 60 else None

    current_price = closes[-1]

    logger.info("当前价格: %.2f", current_price)
    ma60_str = f"{ma60:.2f}" if ma60 else 'N/A'
    logger.info("MA5: %.2f | MA10: %.2f | MA20: %.2f | MA60: %s", ma5, ma10, ma20, ma60_str)

    # 均线排列
    if ma5 > ma10 > ma20:
        logger.info("均线排列: 多头排列 (MA5 > MA10 > MA20)")
    elif ma5 < ma10 < ma20:
        logger.info("均线排列: 空头排列 (MA5 < MA10 < MA20)")
    else:
        logger.info("均线排列: 交叉/纠缠")

    # 价格位置
    if current_price > ma20:
        logger.info("价格位置: 站上20日线 (距离: +%.2f%%)", (current_price/ma20-1)*100)
    else:
        logger.info("价格位置: 跌破20日线 (距离: %.2f%%)", (current_price/ma20-1)*100)

    # 近期高低点
    recent_high = max(highs[-20:])
    recent_low = min(lows[-20:])
    logger.info("近20日高点: %.2f (距离: %.2f%%)", recent_high, (current_price/recent_high-1)*100)
    logger.info("近20日低点: %.2f (距离: %.2f%%)", recent_low, (current_price/recent_low-1)*100)

    # 量能分析
    vol_ma5 = pd.Series(volumes).rolling(5).mean().iloc[-1]
    vol_today = volumes[-1]
    vol_ratio = vol_today / vol_ma5
    logger.info("今日成交量: %s | 5日均量: %s | 量比: %.2f", f"{vol_today:,.0f}", f"{vol_ma5:,.0f}", vol_ratio)

    if vol_ratio < 0.8:
        logger.info("量能状态: 缩量")
    elif vol_ratio > 1.5:
        logger.info("量能状态: 放量")
    else:
        logger.info("量能状态: 平量")

    return {
        'price': current_price,
        'ma20': ma20,
        'recent_high': recent_high,
        'recent_low': recent_low
    }

def calc_support_resistance(df, metrics):
    """计算支撑阻力位"""
    logger.info("=" * 60)
    logger.info("【3. 支撑阻力位】")
    logger.info("=" * 60)

    price = metrics['price']

    # 整数关口
    round_price = round(price / 5) * 5  # 5元整数关口

    # 前高前低
    highs = df['最高'].values
    lows = df['最低'].values

    # 近期支撑 (最近低点)
    support1 = min(lows[-5:])   # 5日低点
    support2 = min(lows[-10:])  # 10日低点
    support3 = metrics['ma20']  # 20日线

    # 近期阻力 (最近高点)
    resist1 = max(highs[-5:])   # 5日高点
    resist2 = max(highs[-10:])  # 10日高点
    resist3 = max(highs[-20:])  # 20日高点

    logger.info("当前价格: %.2f", price)
    logger.info("【阻力位】")
    logger.info("  R3 (20日高点): %.2f", resist3)
    logger.info("  R2 (10日高点): %.2f", resist2)
    logger.info("  R1 (5日高点):  %.2f", resist1)
    logger.info("【支撑位】")
    logger.info("  S1 (5日低点):  %.2f", support1)
    logger.info("  S2 (10日低点): %.2f", support2)
    logger.info("  S3 (20日线):   %.2f", support3)

def get_announcements():
    """获取最新公告"""
    logger.info("=" * 60)
    logger.info("【4. 最新公告】")
    logger.info("=" * 60)

    try:
        df = ak.stock_notice_report(symbol=STOCK_CODE)
        if df.empty:
            logger.info("  暂无公告")
            return

        # 最近5条
        for i, row in df.head(5).iterrows():
            date = row.get('公告日期', row.get('date', ''))
            title = row.get('公告标题', row.get('title', ''))
            logger.info("  [%s] %s", date, title)
    except Exception as e:
        logger.error("获取公告失败: %s", e)

def calc_sector_rank():
    """计算板块内排名"""
    logger.info("=" * 60)
    logger.info("【5. 板块内排名】")
    logger.info("=" * 60)

    conn = sqlite3.connect(DB_PATH)

    # 获取该股票所属的主要板块
    cursor = conn.execute("""
        SELECT sector_name, sector_type FROM sector_stocks
        WHERE stock_code = ? AND sector_type IN ('行业', '概念')
    """, (STOCK_CODE,))
    sectors = cursor.fetchall()

    for sector_name, sector_type in sectors[:3]:  # 取前3个板块
        # 获取板块内所有股票的RPS
        cursor = conn.execute("""
            SELECT ss.stock_code, s.name, r.rps_20
            FROM sector_stocks ss
            JOIN stocks s ON ss.stock_code = s.code
            LEFT JOIN stock_rps r ON ss.stock_code = r.stock_code
                AND r.date = (SELECT MAX(date) FROM stock_rps)
            WHERE ss.sector_name = ?
            ORDER BY r.rps_20 DESC
        """, (sector_name,))
        stocks = cursor.fetchall()

        # 找到301033的排名
        for rank, (code, name, rps) in enumerate(stocks, 1):
            if code == STOCK_CODE:
                total = len(stocks)
                logger.info("【%s】(%s)", sector_name, sector_type)
                logger.info("  板块内排名: 第 %d/%d 名", rank, total)
                logger.info("  RPS 20: %.2f", rps) if rps else logger.info("  RPS: N/A")

                # 显示龙头
                if rank > 1:
                    leader = stocks[0]
                    if leader[2]:
                        logger.info("  板块龙头: %s (%s) RPS=%.2f", leader[1], leader[0], leader[2])
                    else:
                        logger.info("  板块龙头: %s", leader[1])
                break

    conn.close()

def analyze_market():
    """分析大盘环境"""
    logger.info("=" * 60)
    logger.info("【6. 大盘环境】")
    logger.info("=" * 60)

    try:
        # 上证指数
        df = ak.stock_zh_index_daily(symbol="sh000001")
        df = df.tail(10)

        latest = df.iloc[-1]
        prev = df.iloc[-2]

        change = (latest['close'] - prev['close']) / prev['close'] * 100

        logger.info("上证指数: %.2f (%s%.2f%%)", latest['close'], '+' if change > 0 else '', change)

        # 计算5日涨跌
        ma5 = df['close'].tail(5).mean()
        if latest['close'] > ma5:
            logger.info("短期趋势: 站上5日均线")
        else:
            logger.warning("短期趋势: 跌破5日均线")

    except Exception as e:
        logger.error("获取大盘数据失败: %s", e)

def main():
    print("\n" + "=" * 60)
    print(f"  完整分析报告: {STOCK_CODE}")
    print(f"  生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)
    
    # 1. K线数据
    df = get_kline()
    
    # 2. 技术形态
    metrics = analyze_pattern(df)
    
    # 3. 支撑阻力
    calc_support_resistance(df, metrics)
    
    # 4. 公告
    get_announcements()
    
    # 5. 板块排名
    calc_sector_rank()
    
    # 6. 大盘
    analyze_market()
    
    print("\n" + "=" * 60)
    print("【分析完成】")
    print("=" * 60)

if __name__ == "__main__":
    main()
