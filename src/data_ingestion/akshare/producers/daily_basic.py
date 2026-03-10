"""
daily_basic producer — 用 AkShare stock_zh_a_spot_em() 批量获取估值数据

写入 ts_daily_basic 表。单次调用返回全市场数据，效率极高。
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

COLUMN_MAP = {
    "代码": "symbol",
    "市盈率-动态": "pe_ttm",
    "市净率": "pb",
    "总市值": "total_mv",
    "流通市值": "circ_mv",
    "换手率": "turnover_rate",
    "量比": "volume_ratio",
}


def _fetch_spot_data() -> pd.DataFrame:
    """获取全市场实时行情快照"""
    akshare_limiter.acquire()
    df = ak.stock_zh_a_spot_em()
    if df is None or df.empty:
        return pd.DataFrame()
    df = df.rename(columns=COLUMN_MAP)
    df["symbol"] = df["symbol"].astype(str).str.zfill(6)
    df["ts_code"] = df["symbol"].apply(ts_code_from_symbol)
    # 市值转换: 元 → 万元 (Tushare 单位)
    if "total_mv" in df.columns:
        df["total_mv"] = df["total_mv"] / 10000.0
    if "circ_mv" in df.columns:
        df["circ_mv"] = df["circ_mv"] / 10000.0
    return df


def _write_daily_basic(conn, df: pd.DataFrame, trade_date: str) -> int:
    """写入 ts_daily_basic 表"""
    count = 0
    now = datetime.now().isoformat()
    for _, row in df.iterrows():
        try:
            conn.execute("""
                INSERT OR REPLACE INTO ts_daily_basic
                (ts_code, trade_date, volume_ratio, pe, pe_ttm, pb,
                 ps, ps_ttm, dv_ratio, dv_ttm, total_mv, circ_mv,
                 total_share, float_share, free_share,
                 turnover_rate, turnover_rate_f, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                row["ts_code"], trade_date,
                safe_float(row.get("volume_ratio")),
                None,  # pe (静态) — 不提供
                safe_float(row.get("pe_ttm")),
                safe_float(row.get("pb")),
                None, None, None, None,  # ps, ps_ttm, dv_ratio, dv_ttm
                safe_float(row.get("total_mv")),
                safe_float(row.get("circ_mv")),
                None, None, None,  # share 字段 — 不提供
                safe_float(row.get("turnover_rate")),
                None,  # turnover_rate_f
                now,
            ))
            count += 1
        except Exception as e:
            logger.warning(f"写入 {row.get('ts_code')} daily_basic 失败: {e}")
    conn.commit()
    return count


def run_daily_basic(trade_date: str | None = None) -> list[DatasetTelemetry]:
    """daily_basic producer 入口"""
    from src.data_ingestion.akshare.producers.utils import ensure_tables_exist
    from fetchers.trading_calendar import get_latest_trading_day
    ensure_tables_exist()

    if trade_date is None:
        td = get_latest_trading_day()
        trade_date = td.replace("-", "") if td else datetime.now().strftime("%Y%m%d")

    logger.info(f"daily_basic producer: 获取全市场估值数据 {trade_date}...")
    df = _fetch_spot_data()
    if df.empty:
        return [DatasetTelemetry(
            source_key="akshare", dataset_key="ts_daily_basic",
            db_name="stocks", record_count=0, status="empty",
        )]

    conn = get_connection()
    count = _write_daily_basic(conn, df, trade_date)
    conn.close()

    logger.info(f"daily_basic producer 完成: {count} 条")
    return [DatasetTelemetry(
        source_key="akshare", dataset_key="ts_daily_basic",
        db_name="stocks", record_count=count,
        latest_record_date=trade_date,
    )]
