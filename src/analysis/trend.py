"""
趋势预测模块

功能：
1. 基于历史价格数据的趋势预测
2. 使用简单的统计方法和可选的 LSTM 模型
3. 生成短期涨跌概率预测
"""

import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional
import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.database.connection import get_connection


def log(msg: str):
    """格式化输出日志信息。"""
    ts = datetime.now().strftime("%H:%M:%S")
    print(f"[{ts}] {msg}", flush=True)


def _to_ts_code(stock_code: str) -> str:
    code = str(stock_code).strip().upper()
    if "." in code:
        return code
    code = code.zfill(6)
    if code.startswith(("6", "5")):
        return f"{code}.SH"
    if code.startswith(("4", "8", "9")):
        return f"{code}.BJ"
    return f"{code}.SZ"


def _table_exists(conn, table_name: str) -> bool:
    return bool(
        conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
            (table_name,),
        ).fetchone()
    )


# ============================================================
# 数据准备
# ============================================================

def get_stock_history(stock_code: str, days: int = 60) -> list[dict]:
    """
    获取股票历史数据
    
    Args:
        stock_code: 股票代码
        days: 历史天数
        
    Returns:
        历史数据列表
    """
    conn = get_connection()
    
    start_date = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
    start_trade_date = start_date.replace("-", "")

    if _table_exists(conn, "ts_daily"):
        ts_code = _to_ts_code(stock_code)
        cursor = conn.execute(
            """
            SELECT trade_date, open, high, low, close, vol, pct_chg
            FROM ts_daily
            WHERE ts_code = ? AND trade_date >= ?
            ORDER BY trade_date
            """,
            (ts_code, start_trade_date),
        )
        rows = cursor.fetchall()
        data = [
            {
                "date": f"{row['trade_date'][:4]}-{row['trade_date'][4:6]}-{row['trade_date'][6:8]}",
                "open": row["open"],
                "high": row["high"],
                "low": row["low"],
                "close": row["close"],
                "volume": row["vol"],
                "change_pct": row["pct_chg"],
            }
            for row in rows
        ]
    else:
        cursor = conn.execute(
            """
            SELECT date, open, high, low, close, volume, change_pct
            FROM stock_daily
            WHERE stock_code = ? AND date >= ?
            ORDER BY date
            """,
            (stock_code, start_date),
        )
        data = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return data


def prepare_features(history: list[dict]) -> dict:
    """
    准备预测特征
    
    Args:
        history: 历史数据
        
    Returns:
        特征字典
    """
    if len(history) < 20:
        return {}
    
    closes = np.array([h['close'] for h in history if h['close']])
    volumes = np.array([h['volume'] for h in history if h['volume']])
    changes = np.array([h['change_pct'] for h in history if h['change_pct'] is not None])
    
    if len(closes) < 20:
        return {}
    
    # 技术指标特征
    features = {
        # 价格动量
        'momentum_5': (closes[-1] / closes[-5] - 1) * 100 if len(closes) >= 5 else 0,
        'momentum_10': (closes[-1] / closes[-10] - 1) * 100 if len(closes) >= 10 else 0,
        'momentum_20': (closes[-1] / closes[-20] - 1) * 100 if len(closes) >= 20 else 0,
        
        # 均线偏离
        'ma5_deviation': (closes[-1] / np.mean(closes[-5:]) - 1) * 100,
        'ma10_deviation': (closes[-1] / np.mean(closes[-10:]) - 1) * 100,
        'ma20_deviation': (closes[-1] / np.mean(closes[-20:]) - 1) * 100,
        
        # 波动率
        'volatility_5': np.std(closes[-5:]) / np.mean(closes[-5:]) * 100,
        'volatility_20': np.std(closes[-20:]) / np.mean(closes[-20:]) * 100,
        
        # 成交量特征
        'volume_ratio': volumes[-1] / np.mean(volumes[-20:]) if len(volumes) >= 20 and np.mean(volumes[-20:]) > 0 else 1,
        
        # 涨跌统计
        'up_days_5': sum(1 for c in changes[-5:] if c > 0) if len(changes) >= 5 else 0,
        'up_days_10': sum(1 for c in changes[-10:] if c > 0) if len(changes) >= 10 else 0,
        
        # 最近涨跌幅
        'last_change': changes[-1] if len(changes) > 0 else 0,
        'avg_change_5': np.mean(changes[-5:]) if len(changes) >= 5 else 0,
    }
    
    return features


# ============================================================
# 规则预测（无需 ML）
# ============================================================

def predict_trend_rule_based(features: dict) -> dict:
    """
    基于规则的趋势预测
    
    Args:
        features: 特征字典
        
    Returns:
        预测结果
    """
    if not features:
        return {'direction': 'unknown', 'confidence': 0, 'signals': []}
    
    bullish_score = 0
    bearish_score = 0
    signals = []
    
    # 动量信号
    if features.get('momentum_5', 0) > 5:
        bullish_score += 2
        signals.append('5日动量强势')
    elif features.get('momentum_5', 0) < -5:
        bearish_score += 2
        signals.append('5日动量弱势')
    
    # 均线偏离信号
    ma20_dev = features.get('ma20_deviation', 0)
    if ma20_dev > 10:
        bearish_score += 1  # 超买
        signals.append('均线超买')
    elif ma20_dev < -10:
        bullish_score += 1  # 超卖
        signals.append('均线超卖')
    elif 0 < ma20_dev < 5:
        bullish_score += 1
        signals.append('站上均线')
    
    # 成交量信号
    vol_ratio = features.get('volume_ratio', 1)
    if vol_ratio > 2 and features.get('last_change', 0) > 0:
        bullish_score += 2
        signals.append('放量上涨')
    elif vol_ratio > 2 and features.get('last_change', 0) < 0:
        bearish_score += 2
        signals.append('放量下跌')
    
    # 连续性信号
    up_days = features.get('up_days_5', 0)
    if up_days >= 4:
        bullish_score += 1
        signals.append('连续上涨')
    elif up_days <= 1:
        bearish_score += 1
        signals.append('连续下跌')
    
    # 波动率信号
    volatility = features.get('volatility_20', 0)
    if volatility > 5:
        signals.append('高波动')
    
    # 计算方向和置信度
    total_score = bullish_score + bearish_score
    if total_score == 0:
        direction = 'neutral'
        confidence = 0.5
    elif bullish_score > bearish_score:
        direction = 'bullish'
        confidence = 0.5 + (bullish_score - bearish_score) / 10
    else:
        direction = 'bearish'
        confidence = 0.5 + (bearish_score - bullish_score) / 10
    
    confidence = min(0.9, max(0.1, confidence))
    
    return {
        'direction': direction,
        'confidence': round(confidence, 2),
        'bullish_score': bullish_score,
        'bearish_score': bearish_score,
        'signals': signals,
    }


# ============================================================
# LSTM 预测（可选）
# ============================================================

def predict_trend_lstm(stock_code: str, days: int = 60) -> Optional[dict]:
    """
    使用 LSTM 模型预测趋势（需要 TensorFlow）
    
    Args:
        stock_code: 股票代码
        days: 历史天数
        
    Returns:
        预测结果或 None
    """
    try:
        import tensorflow as tf
        from sklearn.preprocessing import MinMaxScaler
    except ImportError:
        log("   ⚠️ LSTM 需要 TensorFlow: pip install tensorflow")
        return None
    
    history = get_stock_history(stock_code, days)
    if len(history) < 30:
        return None
    
    # 准备数据
    closes = np.array([h['close'] for h in history if h['close']]).reshape(-1, 1)
    
    scaler = MinMaxScaler()
    scaled = scaler.fit_transform(closes)
    
    # 创建序列
    seq_length = 10
    X, y = [], []
    for i in range(len(scaled) - seq_length):
        X.append(scaled[i:i+seq_length])
        y.append(1 if scaled[i+seq_length] > scaled[i+seq_length-1] else 0)
    
    X = np.array(X)
    y = np.array(y)
    
    if len(X) < 20:
        return None
    
    # 简单 LSTM 模型
    model = tf.keras.Sequential([
        tf.keras.layers.LSTM(32, input_shape=(seq_length, 1)),
        tf.keras.layers.Dense(1, activation='sigmoid')
    ])
    
    model.compile(optimizer='adam', loss='binary_crossentropy', metrics=['accuracy'])
    
    # 训练
    model.fit(X[:-1], y[:-1], epochs=10, verbose=0)
    
    # 预测
    last_seq = scaled[-seq_length:].reshape(1, seq_length, 1)
    prob = model.predict(last_seq, verbose=0)[0][0]
    
    return {
        'direction': 'bullish' if prob > 0.5 else 'bearish',
        'confidence': round(abs(prob - 0.5) * 2, 2),
        'probability': round(float(prob), 3),
        'method': 'lstm',
    }


# ============================================================
# 综合预测
# ============================================================

def predict_stock_trend(stock_code: str, use_lstm: bool = False) -> dict:
    """
    综合预测股票趋势
    
    Args:
        stock_code: 股票代码
        use_lstm: 是否使用 LSTM（需要 TensorFlow）
        
    Returns:
        预测结果
    """
    history = get_stock_history(stock_code, 60)
    
    if not history:
        return {'error': '无历史数据'}
    
    features = prepare_features(history)
    rule_prediction = predict_trend_rule_based(features)
    
    result = {
        'stock_code': stock_code,
        'date': datetime.now().strftime('%Y-%m-%d'),
        'rule_based': rule_prediction,
        'features': features,
    }
    
    if use_lstm:
        lstm_result = predict_trend_lstm(stock_code)
        if lstm_result:
            result['lstm'] = lstm_result
    
    return result


def predict_batch(stock_codes: list[str], limit: int = 20) -> list[dict]:
    """
    批量预测股票趋势
    
    Args:
        stock_codes: 股票代码列表
        limit: 返回数量限制
        
    Returns:
        预测结果列表
    """
    log(f"📊 批量预测 {len(stock_codes)} 只股票...")
    
    results = []
    for code in stock_codes[:limit]:
        prediction = predict_stock_trend(code)
        if 'error' not in prediction:
            results.append(prediction)
    
    # 按看涨置信度排序
    results.sort(key=lambda x: (
        1 if x['rule_based']['direction'] == 'bullish' else 0,
        x['rule_based']['confidence']
    ), reverse=True)
    
    log(f"   ✅ 完成 {len(results)} 只")
    return results


def get_bullish_stocks(limit: int = 20) -> list[dict]:
    """
    获取看涨信号最强的股票
    
    Returns:
        看涨股票列表
    """
    log("📈 寻找看涨信号股票...")
    
    # 从 RPS 高分股中筛选
    conn = get_connection()
    cursor = conn.execute("""
        SELECT DISTINCT stock_code FROM stock_rps
        WHERE date = (SELECT MAX(date) FROM stock_rps)
        AND rps_20 > 80
        ORDER BY rps_20 DESC
        LIMIT 50
    """)
    
    codes = [row['stock_code'] for row in cursor.fetchall()]
    conn.close()
    
    if not codes:
        log("   ⚠️ 无 RPS 高分股")
        return []
    
    # 预测
    results = predict_batch(codes, limit * 2)
    
    # 筛选看涨
    bullish = [r for r in results if r['rule_based']['direction'] == 'bullish']
    
    log(f"   ✅ 找到 {len(bullish)} 只看涨信号股")
    return bullish[:limit]


# ============================================================
# 主函数
# ============================================================

def main():
    log("=" * 50)
    log("趋势预测模块")
    log("=" * 50)
    
    # 测试单只股票
    result = predict_stock_trend('600519')
    log(f"\n📊 贵州茅台预测:")
    log(f"   方向: {result['rule_based']['direction']}")
    log(f"   置信度: {result['rule_based']['confidence']}")
    log(f"   信号: {result['rule_based']['signals']}")
    
    # 批量获取看涨股
    bullish = get_bullish_stocks(limit=5)
    
    log("\n🔥 看涨信号股:")
    for b in bullish:
        log(f"   {b['stock_code']}: {b['rule_based']['confidence']} - {b['rule_based']['signals']}")
    
    log("\n✅ 完成!")


if __name__ == "__main__":
    main()
