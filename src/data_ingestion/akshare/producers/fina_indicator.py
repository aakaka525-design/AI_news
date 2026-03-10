"""
fina_indicator producer — 用 AkShare 替代 Tushare fina_indicator()

写入 ts_fina_indicator 表。逐股获取财务指标。
因为是季度数据 (periodic_fundamental)，只需获取最新报告期即可。
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

# AkShare 列名 → ts_fina_indicator 字段映射
FIELD_MAP = {
    "摊薄每股收益": "eps",
    "每股净资产": "bps",
    "净资产收益率": "roe",
    "加权净资产收益率": "roe_waa",
    "总资产报酬率": "roa",
    "销售毛利率": "grossprofit_margin",
    "销售净利率": "netprofit_margin",
    "资产负债率": "debt_to_assets",
    "流动比率": "current_ratio",
    "速动比率": "quick_ratio",
    "应收账款周转率": "ar_turn",
    "存货周转率": "inv_turn",
    "固定资产周转率": "fa_turn",
    "总资产周转率": "assets_turn",
}


def _fetch_fina_one(symbol: str) -> pd.DataFrame | None:
    """获取单只股票的财务指标"""
    akshare_limiter.acquire()
    try:
        df = ak.stock_financial_analysis_indicator(symbol=symbol)
        if df is None or df.empty:
            return None
        return df
    except Exception as e:
        logger.debug(f"获取 {symbol} 财务指标失败: {e}")
        return None


def _write_fina_indicator(conn, ts_code: str, df: pd.DataFrame) -> int:
    """写入最近 4 个报告期的财务指标"""
    count = 0
    now = datetime.now().isoformat()

    # 取最新 4 期
    df_recent = df.head(4)

    for _, row in df_recent.iterrows():
        try:
            # 报告期列名可能是 "日期" 或第一列
            end_date_raw = str(row.iloc[0]) if len(row) > 0 else ""
            end_date = end_date_raw.replace("-", "").replace("/", "")[:8]
            if len(end_date) != 8 or not end_date.isdigit():
                continue

            values = {"ts_code": ts_code, "end_date": end_date}
            for ak_col, db_col in FIELD_MAP.items():
                if ak_col in row.index:
                    values[db_col] = safe_float(row[ak_col])

            conn.execute("""
                INSERT OR REPLACE INTO ts_fina_indicator
                (ts_code, end_date, eps, bps, roe, roe_waa, roa,
                 grossprofit_margin, netprofit_margin,
                 debt_to_assets, current_ratio, quick_ratio,
                 ar_turn, inv_turn, fa_turn, assets_turn,
                 updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                values.get("ts_code"), values.get("end_date"),
                values.get("eps"), values.get("bps"),
                values.get("roe"), values.get("roe_waa"), values.get("roa"),
                values.get("grossprofit_margin"), values.get("netprofit_margin"),
                values.get("debt_to_assets"), values.get("current_ratio"),
                values.get("quick_ratio"),
                values.get("ar_turn"), values.get("inv_turn"),
                values.get("fa_turn"), values.get("assets_turn"),
                now,
            ))
            count += 1
        except Exception as e:
            logger.warning(f"写入 {ts_code} fina_indicator 失败: {e}")
    conn.commit()
    return count


def run_fina_indicator() -> list[DatasetTelemetry]:
    """fina_indicator producer 入口"""
    from src.data_ingestion.akshare.producers.utils import ensure_tables_exist
    ensure_tables_exist()

    conn = get_connection()
    symbols = [r[0].split(".")[0] for r in
               conn.execute("SELECT ts_code FROM ts_stock_basic WHERE list_status='L'").fetchall()]

    logger.info(f"fina_indicator producer: 获取 {len(symbols)} 只股票财务指标...")
    total = 0
    for i, symbol in enumerate(symbols):
        ts_code = ts_code_from_symbol(symbol)
        df = _fetch_fina_one(symbol)
        if df is not None:
            total += _write_fina_indicator(conn, ts_code, df)
        if (i + 1) % 200 == 0:
            logger.info(f"fina_indicator 进度: {i+1}/{len(symbols)}, 已写入 {total} 条")

    conn.close()
    logger.info(f"fina_indicator producer 完成: {total} 条")
    return [DatasetTelemetry(
        source_key="akshare", dataset_key="ts_fina_indicator",
        db_name="stocks", record_count=total,
    )]
