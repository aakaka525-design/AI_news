"""
daily producer — 用 AkShare 替代 Tushare daily() + adj_factor()

写入 ts_daily 表。按日期批量获取：遍历全 A 股列表，逐股获取当日数据。
"""

import logging
from datetime import datetime

import akshare as ak
import pandas as pd

from src.database.connection import get_connection
from src.data_ingestion.akshare.producers.utils import (
    akshare_limiter, safe_float, ts_code_from_symbol,
)
from src.telemetry.models import DatasetTelemetry

logger = logging.getLogger(__name__)


def _fetch_daily_one(symbol: str, start_date: str, end_date: str) -> pd.DataFrame:
    """获取单只股票的日线数据（不复权）"""
    akshare_limiter.acquire()
    sd = f"{start_date[:4]}-{start_date[4:6]}-{start_date[6:]}"
    ed = f"{end_date[:4]}-{end_date[4:6]}-{end_date[6:]}"
    df = ak.stock_zh_a_hist(symbol=symbol, period="daily",
                            start_date=sd, end_date=ed, adjust="")
    if df is None or df.empty:
        return pd.DataFrame()
    df = df.rename(columns={
        "日期": "trade_date", "开盘": "open", "收盘": "close",
        "最高": "high", "最低": "low", "成交量": "vol",
        "成交额": "amount", "涨跌幅": "pct_chg", "涨跌额": "change",
    })
    df["trade_date"] = df["trade_date"].astype(str).str.replace("-", "")
    df["ts_code"] = ts_code_from_symbol(symbol)
    df["pre_close"] = df["close"] - df["change"]
    # amount: AkShare 单位是元，Tushare 是千元
    df["amount"] = df["amount"] / 1000.0
    df["adj_factor"] = None  # 稍后计算
    return df


def _fetch_adj_factor(symbol: str, start_date: str, end_date: str) -> dict[str, float]:
    """获取前复权收盘价来计算复权因子"""
    akshare_limiter.acquire()
    sd = f"{start_date[:4]}-{start_date[4:6]}-{start_date[6:]}"
    ed = f"{end_date[:4]}-{end_date[4:6]}-{end_date[6:]}"
    try:
        df = ak.stock_zh_a_hist(symbol=symbol, period="daily",
                                start_date=sd, end_date=ed, adjust="qfq")
        if df is None or df.empty:
            return {}
        df["trade_date"] = df["日期"].astype(str).str.replace("-", "")
        return dict(zip(df["trade_date"], df["收盘"]))
    except Exception:
        return {}


def _write_daily(conn, df: pd.DataFrame) -> int:
    """写入 ts_daily 表"""
    count = 0
    now = datetime.now().isoformat()
    for _, row in df.iterrows():
        try:
            conn.execute("""
                INSERT OR REPLACE INTO ts_daily
                (ts_code, trade_date, open, high, low, close, pre_close,
                 change, pct_chg, vol, amount, adj_factor, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                row["ts_code"], row["trade_date"],
                safe_float(row.get("open")), safe_float(row.get("high")),
                safe_float(row.get("low")), safe_float(row.get("close")),
                safe_float(row.get("pre_close")), safe_float(row.get("change")),
                safe_float(row.get("pct_chg")), safe_float(row.get("vol")),
                safe_float(row.get("amount")), safe_float(row.get("adj_factor")),
                now,
            ))
            count += 1
        except Exception as e:
            logger.warning(f"写入 {row.get('ts_code')} {row.get('trade_date')} 失败: {e}")
    conn.commit()
    return count


def run_daily(trade_date: str | None = None) -> list[DatasetTelemetry]:
    """daily producer 入口"""
    from src.data_ingestion.akshare.producers.utils import ensure_tables_exist
    from fetchers.trading_calendar import get_latest_trading_day
    ensure_tables_exist()

    if trade_date is None:
        td = get_latest_trading_day()
        trade_date = td.replace("-", "") if td else datetime.now().strftime("%Y%m%d")

    conn = get_connection()
    # 获取全 A 股列表
    symbols = [r[0].split(".")[0] for r in
               conn.execute("SELECT ts_code FROM ts_stock_basic WHERE list_status='L'").fetchall()]

    if not symbols:
        conn.close()
        return [DatasetTelemetry(
            source_key="akshare", dataset_key="ts_daily",
            db_name="stocks", record_count=0, status="empty",
        )]

    logger.info(f"daily producer: 获取 {len(symbols)} 只股票 {trade_date} 日线数据...")
    total = 0
    for i, symbol in enumerate(symbols):
        try:
            df = _fetch_daily_one(symbol, trade_date, trade_date)
            if df.empty:
                continue
            # 计算复权因子
            qfq = _fetch_adj_factor(symbol, trade_date, trade_date)
            for idx, row in df.iterrows():
                td_str = row["trade_date"]
                raw_close = row["close"]
                qfq_close = qfq.get(td_str)
                if raw_close and qfq_close and raw_close > 0:
                    df.at[idx, "adj_factor"] = round(qfq_close / raw_close, 6)
            total += _write_daily(conn, df)
        except Exception as e:
            logger.debug(f"获取 {symbol} 日线失败: {e}")
        if (i + 1) % 500 == 0:
            logger.info(f"daily 进度: {i+1}/{len(symbols)}, 已写入 {total} 条")

    conn.close()
    logger.info(f"daily producer 完成: {total} 条")
    return [DatasetTelemetry(
        source_key="akshare", dataset_key="ts_daily",
        db_name="stocks", record_count=total,
        latest_record_date=trade_date,
    )]
