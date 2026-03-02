#!/usr/bin/env python3
"""
技术面异常检测模块

功能：
1. 检测量价异常（放量突破、缩量下跌）
2. 检测均线交叉信号
3. 检测价格偏离度异常
4. 生成异常信号报告
"""

import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional
import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.database.connection import STOCKS_DB_PATH, get_connection


def log(msg: str):
    """格式化输出日志信息。"""
    ts = datetime.now().strftime("%H:%M:%S")
    print(f"[{ts}] {msg}", flush=True)


def _table_exists(conn, table_name: str) -> bool:
    try:
        conn.execute(f"SELECT 1 FROM {table_name} LIMIT 0")
        return True
    except Exception:
        return False


# ============================================================
# 初始化
# ============================================================

def init_anomaly_table():
    """初始化异常检测结果表"""
    conn = get_connection()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS technical_anomalies (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            stock_code TEXT NOT NULL,
            stock_name TEXT,
            date TEXT NOT NULL,
            anomaly_type TEXT NOT NULL,  -- volume_surge, ma_cross, price_deviation
            signal TEXT,                 -- bullish, bearish
            score REAL,                  -- 信号强度 0-100
            description TEXT,            -- 描述
            details TEXT,                -- JSON 详情
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(stock_code, date, anomaly_type)
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_anomaly_stock ON technical_anomalies(stock_code)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_anomaly_date ON technical_anomalies(date)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_anomaly_type ON technical_anomalies(anomaly_type)")
    conn.commit()
    conn.close()
    log("异常检测表初始化完成")


# ============================================================
# 异常检测算法
# ============================================================

def detect_volume_surge(stock_code: str, days: int = 60, threshold: float = 2.0) -> list[dict]:
    """
    检测量能突变
    
    Args:
        stock_code: 股票代码
        days: 检测天数
        threshold: 相对于 20 日均量的倍数阈值
        
    Returns:
        list[dict]: 异常信号列表
    """
    conn = get_connection()
    
    end_date = datetime.now().strftime("%Y-%m-%d")
    start_date = (datetime.now() - timedelta(days=days + 30)).strftime("%Y-%m-%d")
    
    cursor = conn.execute("""
        SELECT date, volume, close, change_pct
        FROM stock_daily
        WHERE stock_code = ? AND date BETWEEN ? AND ?
        ORDER BY date
    """, (stock_code, start_date, end_date))
    
    rows = cursor.fetchall()
    conn.close()
    
    if len(rows) < 25:
        return []
    
    signals = []
    volumes = [r['volume'] for r in rows]
    
    for i in range(20, len(rows)):
        # 计算 20 日均量
        ma20_vol = np.mean(volumes[i-20:i])
        current_vol = volumes[i]
        
        if ma20_vol > 0:
            vol_ratio = current_vol / ma20_vol
            
            if vol_ratio >= threshold:
                row = rows[i]
                change = row['change_pct'] or 0
                
                # 判断信号类型
                if change > 0:
                    signal = 'bullish'
                    desc = f"放量上涨 {change:.2f}%，量比 {vol_ratio:.1f}倍"
                else:
                    signal = 'bearish'
                    desc = f"放量下跌 {change:.2f}%，量比 {vol_ratio:.1f}倍"
                
                signals.append({
                    'stock_code': stock_code,
                    'date': row['date'],
                    'anomaly_type': 'volume_surge',
                    'signal': signal,
                    'score': min(100, vol_ratio * 30),
                    'description': desc,
                    'details': f'{{"vol_ratio": {vol_ratio:.2f}, "change_pct": {change:.2f}}}'
                })
    
    return signals


def detect_ma_cross(stock_code: str, days: int = 60) -> list[dict]:
    """
    检测均线交叉
    
    Args:
        stock_code: 股票代码
        days: 检测天数
        
    Returns:
        list[dict]: 交叉信号列表
    """
    conn = get_connection()
    
    end_date = datetime.now().strftime("%Y-%m-%d")
    start_date = (datetime.now() - timedelta(days=days + 30)).strftime("%Y-%m-%d")
    
    cursor = conn.execute("""
        SELECT date, ma5, ma10, ma20
        FROM stock_technicals
        WHERE stock_code = ? AND date BETWEEN ? AND ?
        ORDER BY date
    """, (stock_code, start_date, end_date))
    
    rows = cursor.fetchall()
    conn.close()
    
    if len(rows) < 2:
        return []
    
    signals = []
    
    for i in range(1, len(rows)):
        prev = rows[i-1]
        curr = rows[i]
        
        # 检测 MA5 上穿 MA20（金叉）
        if prev['ma5'] and prev['ma20'] and curr['ma5'] and curr['ma20']:
            prev_diff = prev['ma5'] - prev['ma20']
            curr_diff = curr['ma5'] - curr['ma20']
            
            if prev_diff < 0 and curr_diff > 0:
                signals.append({
                    'stock_code': stock_code,
                    'date': curr['date'],
                    'anomaly_type': 'ma_cross',
                    'signal': 'bullish',
                    'score': 70,
                    'description': "MA5 上穿 MA20（金叉）",
                    'details': f'{{"ma5": {curr["ma5"]:.2f}, "ma20": {curr["ma20"]:.2f}}}'
                })
            elif prev_diff > 0 and curr_diff < 0:
                signals.append({
                    'stock_code': stock_code,
                    'date': curr['date'],
                    'anomaly_type': 'ma_cross',
                    'signal': 'bearish',
                    'score': 70,
                    'description': "MA5 下穿 MA20（死叉）",
                    'details': f'{{"ma5": {curr["ma5"]:.2f}, "ma20": {curr["ma20"]:.2f}}}'
                })
    
    return signals


def detect_price_deviation(stock_code: str, days: int = 60, threshold: float = 10.0) -> list[dict]:
    """
    检测价格偏离度异常（价格偏离 MA20 超过阈值%）
    
    Args:
        stock_code: 股票代码
        days: 检测天数
        threshold: 偏离度阈值（百分比）
        
    Returns:
        list[dict]: 异常信号列表
    """
    conn = get_connection()
    
    end_date = datetime.now().strftime("%Y-%m-%d")
    start_date = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
    
    cursor = conn.execute("""
        SELECT d.date, d.close, t.ma20
        FROM stock_daily d
        LEFT JOIN stock_technicals t ON d.stock_code = t.stock_code AND d.date = t.date
        WHERE d.stock_code = ? AND d.date BETWEEN ? AND ?
        ORDER BY d.date
    """, (stock_code, start_date, end_date))
    
    rows = cursor.fetchall()
    conn.close()
    
    signals = []
    
    for row in rows:
        if row['close'] and row['ma20'] and row['ma20'] > 0:
            deviation = (row['close'] - row['ma20']) / row['ma20'] * 100
            
            if abs(deviation) >= threshold:
                if deviation > 0:
                    signal = 'overbought'
                    desc = f"价格偏离 MA20 +{deviation:.1f}%（超买）"
                else:
                    signal = 'oversold'
                    desc = f"价格偏离 MA20 {deviation:.1f}%（超卖）"
                
                signals.append({
                    'stock_code': stock_code,
                    'date': row['date'],
                    'anomaly_type': 'price_deviation',
                    'signal': signal,
                    'score': min(100, abs(deviation) * 5),
                    'description': desc,
                    'details': f'{{"deviation": {deviation:.2f}, "close": {row["close"]:.2f}, "ma20": {row["ma20"]:.2f}}}'
                })
    
    return signals


# ============================================================
# 批量检测
# ============================================================

def save_anomalies(anomalies: list[dict]) -> int:
    """保存异常信号"""
    if not anomalies:
        return 0
    
    conn = get_connection()
    count = 0
    
    for a in anomalies:
        try:
            conn.execute("""
                INSERT INTO technical_anomalies
                (stock_code, date, anomaly_type, signal, score, description, details)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT (stock_code, date, anomaly_type) DO UPDATE SET
                    signal = EXCLUDED.signal,
                    score = EXCLUDED.score,
                    description = EXCLUDED.description,
                    details = EXCLUDED.details
            """, (
                a['stock_code'], a['date'], a['anomaly_type'],
                a['signal'], a['score'], a['description'], a['details']
            ))
            count += 1
        except Exception as e:
            log(f"   ⚠️ 保存异常信号失败 {a.get('stock_code')} {a.get('date')}: {e}")
    
    conn.commit()
    conn.close()
    return count


def detect_anomalies_for_stock(stock_code: str) -> dict:
    """
    对单只股票进行全面异常检测
    
    Returns:
        dict: 各类型异常数量
    """
    results = {
        'volume_surge': 0,
        'ma_cross': 0,
        'price_deviation': 0
    }
    
    # 量能突变
    vol_signals = detect_volume_surge(stock_code)
    if vol_signals:
        results['volume_surge'] = save_anomalies(vol_signals)
    
    # 均线交叉
    ma_signals = detect_ma_cross(stock_code)
    if ma_signals:
        results['ma_cross'] = save_anomalies(ma_signals)
    
    # 价格偏离
    dev_signals = detect_price_deviation(stock_code)
    if dev_signals:
        results['price_deviation'] = save_anomalies(dev_signals)
    
    return results


def detect_all_hot_stocks(limit: int = 100) -> dict:
    """
    对热门股票进行异常检测
    
    Args:
        limit: 检测的股票数量
        
    Returns:
        dict: 检测统计
    """
    log("📊 技术面异常检测...")
    
    # 从龙虎榜和北向资金获取热门股票
    conn = get_connection()
    stocks: list[str] = []
    try:
        threshold_legacy = (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d")
        threshold_ts = (datetime.now() - timedelta(days=7)).strftime("%Y%m%d")

        if _table_exists(conn, "ts_top_list"):
            cursor = conn.execute(
                "SELECT DISTINCT ts_code FROM ts_top_list WHERE trade_date >= ?",
                (threshold_ts,),
            )
            stocks.extend([row["ts_code"] for row in cursor.fetchall()])
        elif _table_exists(conn, "dragon_tiger_stock"):
            cursor = conn.execute(
                "SELECT DISTINCT stock_code FROM dragon_tiger_stock WHERE date >= ?",
                (threshold_legacy,),
            )
            stocks.extend([row["stock_code"] for row in cursor.fetchall()])

        if _table_exists(conn, "ts_hsgt_top10"):
            cursor = conn.execute(
                "SELECT DISTINCT ts_code FROM ts_hsgt_top10 ORDER BY net_amount DESC LIMIT 50"
            )
            stocks.extend([row["ts_code"] for row in cursor.fetchall()])
        elif _table_exists(conn, "north_money_holding"):
            cursor = conn.execute(
                "SELECT DISTINCT stock_code FROM north_money_holding ORDER BY net_buy_value DESC LIMIT 50"
            )
            stocks.extend([row["stock_code"] for row in cursor.fetchall()])
    finally:
        conn.close()

    normalized = []
    for code in stocks:
        if not code:
            continue
        raw = code.split(".")[0]
        normalized.append(raw.zfill(6))
    stocks = list(dict.fromkeys(normalized))[:limit]
    
    log(f"   目标股票: {len(stocks)} 只")
    
    total = {'volume_surge': 0, 'ma_cross': 0, 'price_deviation': 0}
    
    for i, code in enumerate(stocks):
        result = detect_anomalies_for_stock(code)
        for k, v in result.items():
            total[k] += v
        
        if (i + 1) % 20 == 0:
            log(f"   进度: {i+1}/{len(stocks)}...")
    
    log(f"   ✅ 检测完成:")
    log(f"      量能突变: {total['volume_surge']} 条")
    log(f"      均线交叉: {total['ma_cross']} 条")
    log(f"      价格偏离: {total['price_deviation']} 条")
    
    return total


def get_recent_anomalies(days: int = 7, limit: int = 50) -> list[dict]:
    """获取最近的异常信号"""
    conn = get_connection()
    
    start_date = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
    
    cursor = conn.execute("""
        SELECT a.*, s.name as stock_name
        FROM technical_anomalies a
        LEFT JOIN stocks s ON a.stock_code = s.code
        WHERE a.date >= ?
        ORDER BY a.score DESC, a.date DESC
        LIMIT ?
    """, (start_date, limit))
    
    anomalies = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return anomalies


def get_stock_anomalies(stock_code: str, days: int = 30) -> list[dict]:
    """获取指定股票的异常信号"""
    conn = get_connection()
    
    start_date = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
    
    cursor = conn.execute("""
        SELECT * FROM technical_anomalies
        WHERE stock_code = ? AND date >= ?
        ORDER BY date DESC
    """, (stock_code, start_date))
    
    anomalies = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return anomalies


def get_anomaly_stats() -> dict:
    """获取异常统计"""
    conn = get_connection()
    
    # 按类型统计
    seven_days_ago = (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d")
    cursor = conn.execute("""
        SELECT anomaly_type, signal, COUNT(*) as count
        FROM technical_anomalies
        WHERE date > ?
        GROUP BY anomaly_type, signal
        ORDER BY count DESC
    """, (seven_days_ago,))
    
    stats = {}
    for row in cursor.fetchall():
        key = f"{row['anomaly_type']}_{row['signal']}"
        stats[key] = row['count']
    
    conn.close()
    return stats


# ============================================================
# AI 信号解读
# ============================================================

def generate_signal_interpretation(anomaly: dict) -> str:
    """
    为异常信号生成智能解读（规则模板）
    
    Args:
        anomaly: 异常信号字典
        
    Returns:
        解读文本
    """
    anomaly_type = anomaly.get('anomaly_type', '')
    signal = anomaly.get('signal', '')
    description = anomaly.get('description', '')
    score = anomaly.get('score', 0)
    
    interpretations = {
        ('volume_surge', 'bullish'): (
            "🔥 **放量上涨信号**\n"
            f"- {description}\n"
            "- 解读：资金积极入场，可能预示短期突破行情\n"
            "- 注意：若后续无法维持量能，警惕冲高回落"
        ),
        ('volume_surge', 'bearish'): (
            "⚠️ **放量下跌信号**\n"
            f"- {description}\n"
            "- 解读：恐慌盘或主力出货迹象\n"
            "- 注意：短期可能继续承压，观望为主"
        ),
        ('ma_cross', 'bullish'): (
            "📈 **均线金叉信号**\n"
            f"- {description}\n"
            "- 解读：短期均线上穿长期均线，趋势可能转强\n"
            "- 注意：需配合成交量确认有效性"
        ),
        ('ma_cross', 'bearish'): (
            "📉 **均线死叉信号**\n"
            f"- {description}\n"
            "- 解读：短期均线下穿长期均线，趋势可能走弱\n"
            "- 注意：若跌破重要支撑位，可能加速下跌"
        ),
        ('price_deviation', 'overbought'): (
            "🔴 **超买信号**\n"
            f"- {description}\n"
            "- 解读：价格偏离均线过大，短期获利盘较重\n"
            "- 注意：存在回调风险，不宜追高"
        ),
        ('price_deviation', 'oversold'): (
            "🟢 **超卖信号**\n"
            f"- {description}\n"
            "- 解读：价格偏离均线过大，可能超跌反弹\n"
            "- 注意：需确认底部支撑有效性"
        ),
    }
    
    key = (anomaly_type, signal)
    if key in interpretations:
        return interpretations[key]
    
    return f"📊 **{anomaly_type}** - {signal}\n- {description}"


def get_top_signals_with_interpretation(days: int = 7, limit: int = 10) -> list[dict]:
    """
    获取最强信号并附带解读
    
    Args:
        days: 查询天数
        limit: 返回数量
        
    Returns:
        带解读的信号列表
    """
    conn = get_connection()
    
    start_date = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
    
    cursor = conn.execute("""
        SELECT a.*, s.name as stock_name
        FROM technical_anomalies a
        LEFT JOIN stocks s ON a.stock_code = s.code
        WHERE a.date >= ?
        ORDER BY a.score DESC, a.date DESC
        LIMIT ?
    """, (start_date, limit))
    
    results = []
    for row in cursor.fetchall():
        anomaly = dict(row)
        anomaly['interpretation'] = generate_signal_interpretation(anomaly)
        results.append(anomaly)
    
    conn.close()
    return results


def generate_daily_signal_report() -> str:
    """
    生成每日信号摘要报告
    
    Returns:
        Markdown 格式报告
    """
    log("📊 生成每日信号报告...")
    
    # 获取今日统计
    stats = get_anomaly_stats()
    
    # 获取最强信号
    top_signals = get_top_signals_with_interpretation(days=1, limit=5)
    
    report = "# 📊 今日技术面信号摘要\n\n"
    
    # 统计概览
    report += "## 信号统计\n\n"
    report += "| 类型 | 看涨 | 看跌 |\n"
    report += "|:---|:---:|:---:|\n"
    
    for atype in ['volume_surge', 'ma_cross', 'price_deviation']:
        bullish = stats.get(f'{atype}_bullish', 0) + stats.get(f'{atype}_overbought', 0)
        bearish = stats.get(f'{atype}_bearish', 0) + stats.get(f'{atype}_oversold', 0)
        name = {'volume_surge': '量能突变', 'ma_cross': '均线交叉', 'price_deviation': '价格偏离'}[atype]
        report += f"| {name} | {bullish} | {bearish} |\n"
    
    # 重点信号
    if top_signals:
        report += "\n## 🔥 重点信号\n\n"
        for sig in top_signals[:3]:
            report += f"### {sig['stock_code']} {sig.get('stock_name', '')}\n"
            report += f"{sig['interpretation']}\n\n"
    
    log("   ✅ 报告生成完成")
    return report


# ============================================================
# 主函数
# ============================================================

def main():
    log("=" * 50)
    log("技术面异常检测")
    log(f"数据库: {STOCKS_DB_PATH}")
    log("=" * 50)
    
    # 初始化表
    init_anomaly_table()
    
    # 检测热门股票
    detect_all_hot_stocks(limit=50)
    
    # 显示最新异常
    log("\n📈 最新异常信号:")
    recent = get_recent_anomalies(days=7, limit=10)
    for a in recent:
        log(f"   [{a['anomaly_type']}] {a['stock_code']} {a['date']}: {a['description']}")
    
    log("✅ 完成!")


if __name__ == "__main__":
    main()
