#!/usr/bin/env python3
"""
市场情绪统计模块
用途：判断大盘情绪、仓位管理

数据源：
- 涨停池/跌停池 (akshare)
- 北向资金 (已有表)
- 大盘成交额 (akshare)

情绪评分逻辑：
- 炸板率 < 20% + 连板高度 ≥ 5 → 高情绪
- 跌停 > 涨停 → 风险市场
"""
import logging
import sys
from datetime import datetime, timedelta
from pathlib import Path
import akshare as ak
import json

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# 使用公共数据库模块
from src.database.connection import get_connection, STOCKS_DB_PATH


def _table_exists(conn, table_name: str) -> bool:
    try:
        conn.execute(f"SELECT 1 FROM {table_name} LIMIT 0")
        return True
    except Exception:
        return False


def init_table():
    """初始化市场情绪表"""
    conn = get_connection()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS market_sentiment (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT NOT NULL UNIQUE,             -- 交易日期
            limit_up_count INTEGER,                -- 涨停家数
            limit_down_count INTEGER,              -- 跌停家数
            continuous_limit_up_max INTEGER,       -- 最高连板数
            continuous_limit_up_stocks TEXT,       -- 最高连板股票(JSON)
            first_board_count INTEGER,             -- 首板数量
            broken_board_count INTEGER,            -- 炸板数量
            broken_board_rate REAL,                -- 炸板率 (%)
            up_count INTEGER,                      -- 上涨家数
            down_count INTEGER,                    -- 下跌家数
            up_down_ratio REAL,                    -- 涨跌比
            avg_change_pct REAL,                   -- 平均涨幅
            total_amount REAL,                     -- 两市成交额（亿）
            north_net_buy REAL,                    -- 北向净买入（亿）
            sentiment_score INTEGER,               -- 情绪评分 (0-100)
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_sentiment_date ON market_sentiment(date)")
    conn.commit()
    conn.close()
    logger.info("市场情绪表初始化完成")


def get_last_trade_date():
    """获取最近交易日"""
    today = datetime.now()
    if today.weekday() == 5:
        today = today - timedelta(days=1)
    elif today.weekday() == 6:
        today = today - timedelta(days=2)
    return today.strftime("%Y%m%d")


def fetch_sentiment(date: str = None):
    """
    获取并计算市场情绪数据
    
    Args:
        date: 日期字符串 YYYYMMDD
    """
    if not date:
        date = get_last_trade_date()
    
    date_formatted = f"{date[:4]}-{date[4:6]}-{date[6:8]}"
    
    logger.info("计算市场情绪 (%s)...", date_formatted)

    conn = get_connection()

    # 1. 涨停数据
    logger.info("   获取涨停数据...")
    limit_up_count = 0
    first_board_count = 0
    continuous_max = 0
    continuous_stocks = []
    broken_board_count = 0
    
    try:
        df = ak.stock_zt_pool_em(date=date)
        if not df.empty:
            limit_up_count = len(df)
            
            # 首板数量 (连板数=1)
            if '连板数' in df.columns:
                first_board_count = len(df[df['连板数'] == 1])
                continuous_max = int(df['连板数'].max())
                top_stocks = df[df['连板数'] == continuous_max][['代码', '名称', '连板数']].head(3)
                continuous_stocks = top_stocks.to_dict('records')
            
            # 炸板数量
            if '炸板次数' in df.columns:
                broken_board_count = len(df[df['炸板次数'] > 0])
        
        logger.info("   涨停: %d, 首板: %d, 最高连板: %d", limit_up_count, first_board_count, continuous_max)
    except Exception as e:
        logger.warning("涨停数据获取失败: %s", e)
    
    # 2. 跌停数据
    logger.info("   获取跌停数据...")
    limit_down_count = 0
    try:
        df = ak.stock_zt_pool_dtgc_em(date=date)  # 跌停池
        if not df.empty:
            limit_down_count = len(df)
        logger.info("   跌停: %d", limit_down_count)
    except Exception as e:
        logger.warning("跌停数据获取失败: %s", e)
    
    # 3. 涨跌家数 + 平均涨幅
    logger.info("   获取涨跌家数...")
    up_count = 0
    down_count = 0
    avg_change = 0
    try:
        if _table_exists(conn, "ts_daily"):
            cursor = conn.execute(
                """
                SELECT
                    SUM(CASE WHEN pct_chg > 0 THEN 1 ELSE 0 END) as up_cnt,
                    SUM(CASE WHEN pct_chg < 0 THEN 1 ELSE 0 END) as down_cnt,
                    AVG(pct_chg) as avg_chg
                FROM ts_daily
                WHERE trade_date = ?
                """,
                (date,),
            )
        else:
            cursor = conn.execute(
                """
                SELECT
                    SUM(CASE WHEN change_pct > 0 THEN 1 ELSE 0 END) as up_cnt,
                    SUM(CASE WHEN change_pct < 0 THEN 1 ELSE 0 END) as down_cnt,
                    AVG(change_pct) as avg_chg
                FROM stock_daily
                WHERE date = ?
                """,
                (date_formatted,),
            )
        row = cursor.fetchone()
        if row and row[0]:
            up_count = row[0]
            down_count = row[1]
            avg_change = row[2]
        logger.info("   上涨: %d, 下跌: %d, 平均涨幅: %.2f%%", up_count, down_count, avg_change)
    except Exception as e:
        logger.warning("涨跌家数统计失败: %s", e)
    
    # 4. 两市成交额
    logger.info("   获取两市成交额...")
    total_amount = 0
    try:
        if _table_exists(conn, "ts_daily"):
            cursor = conn.execute(
                "SELECT SUM(amount) / 100000000 FROM ts_daily WHERE trade_date = ?",
                (date,),
            )
        else:
            cursor = conn.execute(
                "SELECT SUM(amount) / 100000000 FROM stock_daily WHERE date = ?",
                (date_formatted,),
            )
        row = cursor.fetchone()
        if row and row[0]:
            total_amount = row[0]
        logger.info("   两市成交: %.0f亿", total_amount)
    except Exception as e:
        logger.warning("成交额统计失败: %s", e)
    
    # 5. 北向资金
    logger.info("   获取北向资金...")
    north_net = 0
    try:
        if _table_exists(conn, "ts_hsgt_top10"):
            cursor = conn.execute(
                "SELECT SUM(net_amount) / 100000000 FROM ts_hsgt_top10 WHERE trade_date = ?",
                (date,),
            )
        else:
            cursor = conn.execute(
                "SELECT SUM(net_buy_value) / 100000000 FROM north_money_holding WHERE date = ?",
                (date_formatted,),
            )
        row = cursor.fetchone()
        if row and row[0]:
            north_net = row[0]
        logger.info("   北向净买: %.2f亿", north_net)
    except Exception as e:
        logger.warning("北向资金统计失败: %s", e)
    
    # 6. 计算情绪评分 (0-100)
    broken_rate = 0
    if limit_up_count > 0:
        broken_rate = broken_board_count / limit_up_count * 100
    
    up_down_ratio = 0
    if down_count > 0:
        up_down_ratio = up_count / down_count
    
    # 情绪评分算法
    score = 50  # 基准分
    
    # 涨停数量 (+/- 10分)
    if limit_up_count >= 100:
        score += 10
    elif limit_up_count >= 50:
        score += 5
    elif limit_up_count < 30:
        score -= 5
    
    # 连板高度 (+/- 10分)
    if continuous_max >= 8:
        score += 10
    elif continuous_max >= 5:
        score += 5
    elif continuous_max <= 2:
        score -= 10
    
    # 炸板率 (+/- 10分)
    if broken_rate < 15:
        score += 10
    elif broken_rate < 25:
        score += 5
    elif broken_rate > 40:
        score -= 10
    
    # 涨跌比 (+/- 10分)
    if up_down_ratio >= 3:
        score += 10
    elif up_down_ratio >= 1.5:
        score += 5
    elif up_down_ratio < 0.5:
        score -= 15
    
    # 跌停惩罚
    if limit_down_count > limit_up_count:
        score -= 20
    elif limit_down_count > 20:
        score -= 10
    
    # 北向资金 (+/- 5分)
    if north_net > 50:
        score += 5
    elif north_net < -50:
        score -= 5
    
    score = max(0, min(100, score))  # 限制在0-100
    
    logger.info("   情绪评分: %d/100", score)
    
    # 保存数据
    conn.execute("""
        INSERT INTO market_sentiment
        (date, limit_up_count, limit_down_count, continuous_limit_up_max,
         continuous_limit_up_stocks, first_board_count, broken_board_count,
         broken_board_rate, up_count, down_count, up_down_ratio, avg_change_pct,
         total_amount, north_net_buy, sentiment_score, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT (date) DO UPDATE SET
            limit_up_count = EXCLUDED.limit_up_count,
            limit_down_count = EXCLUDED.limit_down_count,
            continuous_limit_up_max = EXCLUDED.continuous_limit_up_max,
            continuous_limit_up_stocks = EXCLUDED.continuous_limit_up_stocks,
            first_board_count = EXCLUDED.first_board_count,
            broken_board_count = EXCLUDED.broken_board_count,
            broken_board_rate = EXCLUDED.broken_board_rate,
            up_count = EXCLUDED.up_count,
            down_count = EXCLUDED.down_count,
            up_down_ratio = EXCLUDED.up_down_ratio,
            avg_change_pct = EXCLUDED.avg_change_pct,
            total_amount = EXCLUDED.total_amount,
            north_net_buy = EXCLUDED.north_net_buy,
            sentiment_score = EXCLUDED.sentiment_score,
            updated_at = EXCLUDED.updated_at
    """, (
        date_formatted, limit_up_count, limit_down_count, continuous_max,
        json.dumps(continuous_stocks, ensure_ascii=False), first_board_count, broken_board_count,
        broken_rate, up_count, down_count, up_down_ratio, avg_change,
        total_amount, north_net, score, datetime.now().isoformat()
    ))
    conn.commit()
    
    # 输出情绪解读
    logger.info("   情绪解读:")
    if score >= 80:
        logger.info("   极度乐观！市场亢奋，注意高位风险")
    elif score >= 60:
        logger.info("   积极向上，可适当进攻")
    elif score >= 40:
        logger.info("   情绪中性，观望为主")
    elif score >= 20:
        logger.warning("   情绪低迷，控制仓位")
    else:
        logger.warning("   极度恐慌！风险市场，防守为主")
    
    conn.close()
    return score


def fetch_history(days: int = 30):
    """获取历史情绪数据"""
    logger.info("获取最近 %d 个交易日的情绪数据...", days)

    try:
        df = ak.tool_trade_date_hist_sina()
        trade_dates = df['trade_date'].astype(str).tolist()

        today = datetime.now().strftime("%Y-%m-%d")
        past_dates = [d for d in trade_dates if d <= today][-days:]

        for date in past_dates:
            date_str = date.replace("-", "")
            fetch_sentiment(date_str)

        logger.info("共处理 %d 个交易日", len(past_dates))

    except Exception as e:
        logger.error("获取交易日历失败: %s", e)


def print_stats():
    """打印统计信息"""
    conn = get_connection()

    logger.info("市场情绪统计:")

    cursor = conn.execute("SELECT COUNT(*), MIN(date), MAX(date) FROM market_sentiment")
    total, min_date, max_date = cursor.fetchone()
    logger.info("   总记录数: %d 条", total)
    logger.info("   日期范围: %s ~ %s", min_date, max_date)

    # 最新情绪
    cursor = conn.execute("""
        SELECT date, limit_up_count, limit_down_count, continuous_limit_up_max,
               broken_board_rate, sentiment_score
        FROM market_sentiment
        ORDER BY date DESC
        LIMIT 5
    """)
    logger.info("   近期情绪:")
    logger.info("   %-12s %-6s %-6s %-6s %-8s %-6s", '日期', '涨停', '跌停', '连板', '炸板率', '评分')
    logger.info("   " + "-" * 50)
    for row in cursor.fetchall():
        date, up, down, cont, broken, score = row
        logger.info("   %-12s %-6d %-6d %-6d %.1f%%    %d", date, up, down, cont, broken, score)

    conn.close()


def main():
    import argparse
    parser = argparse.ArgumentParser(description="市场情绪统计")
    parser.add_argument("--date", type=str, help="指定日期 YYYYMMDD")
    parser.add_argument("--history", type=int, default=0, help="获取最近N天历史")
    parser.add_argument("--stats", action="store_true", help="显示统计")
    args = parser.parse_args()
    
    print("=" * 60)
    print("市场情绪统计系统")
    print(f"数据库: {STOCKS_DB_PATH}")
    print("=" * 60)
    
    init_table()
    
    if args.stats:
        print_stats()
    elif args.history > 0:
        fetch_history(args.history)
        print_stats()
    else:
        fetch_sentiment(args.date)
        print_stats()
    
    print("\n✅ 完成!")


if __name__ == "__main__":
    main()
