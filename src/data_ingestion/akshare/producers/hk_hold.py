"""
hk_hold producer — 用 AkShare 替代 Tushare hk_hold()

写入 ts_hk_hold 表。单次批量获取北向持股数据。
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


def _fetch_hk_hold_data() -> pd.DataFrame:
    """获取当日北向持股数据"""
    akshare_limiter.acquire()
    try:
        df = ak.stock_hsgt_hold_stock_em(market="北向", indicator="今日排行")
        if df is None or df.empty:
            return pd.DataFrame()
        return df
    except Exception as e:
        logger.error(f"获取北向持股数据失败: {e}")
        return pd.DataFrame()


def _write_hk_hold(conn, df: pd.DataFrame, trade_date: str) -> int:
    """写入 ts_hk_hold 表"""
    count = 0
    now = datetime.now().isoformat()
    code_col = "代码" if "代码" in df.columns else df.columns[0]
    vol_col = next((c for c in df.columns if "股数" in c), None)
    ratio_col = next((c for c in df.columns if "占" in c and "比" in c), None)

    for _, row in df.iterrows():
        try:
            symbol = str(row[code_col]).strip().zfill(6)
            ts_code = ts_code_from_symbol(symbol)
            exchange = "SH" if symbol.startswith(("6", "9")) else "SZ"
            vol = safe_float(row.get(vol_col)) if vol_col else None
            ratio = safe_float(row.get(ratio_col)) if ratio_col else None

            conn.execute("""
                INSERT OR REPLACE INTO ts_hk_hold
                (ts_code, trade_date, vol, ratio, exchange, updated_at)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (ts_code, trade_date, vol, ratio, exchange, now))
            count += 1
        except Exception as e:
            logger.warning(f"写入 hk_hold 失败: {e}")
    conn.commit()
    return count


def run_hk_hold(trade_date: str | None = None) -> list[DatasetTelemetry]:
    """hk_hold producer 入口"""
    from src.data_ingestion.akshare.producers.utils import ensure_tables_exist
    from fetchers.trading_calendar import get_latest_trading_day
    ensure_tables_exist()

    if trade_date is None:
        td = get_latest_trading_day()
        trade_date = td.replace("-", "") if td else datetime.now().strftime("%Y%m%d")

    logger.info(f"hk_hold producer: 获取 {trade_date} 北向持股数据...")
    df = _fetch_hk_hold_data()
    if df.empty:
        return [DatasetTelemetry(
            source_key="akshare", dataset_key="ts_hk_hold",
            db_name="stocks", record_count=0, status="empty",
        )]

    conn = get_connection()
    count = _write_hk_hold(conn, df, trade_date)
    conn.close()

    logger.info(f"hk_hold producer 完成: {count} 条")
    return [DatasetTelemetry(
        source_key="akshare", dataset_key="ts_hk_hold",
        db_name="stocks", record_count=count,
        latest_record_date=trade_date,
    )]
