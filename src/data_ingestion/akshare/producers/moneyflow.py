"""
moneyflow producer — 用 AkShare 替代 Tushare moneyflow()

写入 ts_moneyflow 表。逐股获取资金流向数据。
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


def _market_for_symbol(symbol: str) -> str:
    s = str(symbol).strip()
    if s.startswith(("6", "9")):
        return "sh"
    return "sz"


def _fetch_moneyflow_one(symbol: str, trade_date: str) -> pd.DataFrame | None:
    """获取单只股票的资金流向"""
    akshare_limiter.acquire()
    try:
        market = _market_for_symbol(symbol)
        df = ak.stock_individual_fund_flow(stock=symbol, market=market)
        if df is None or df.empty:
            return None
        # 过滤到目标日期
        df["日期"] = pd.to_datetime(df["日期"]).dt.strftime("%Y%m%d")
        df = df[df["日期"] == trade_date]
        if df.empty:
            return None
        return df
    except Exception as e:
        logger.debug(f"获取 {symbol} 资金流向失败: {e}")
        return None


def _split_net_to_buy_sell(net_amount) -> tuple[float | None, float | None]:
    """将净流入净额拆分为 buy/sell amount。

    AkShare 只提供各档净流入净额，scoring 需要 buy/sell 分开。
    正值 → buy=net, sell=0；负值 → buy=0, sell=|net|。
    这样 buy - sell == net，保持 compute_main_money_flow_raw 信号正确。
    """
    v = safe_float(net_amount)
    if v is None:
        return None, None
    if v >= 0:
        return v, 0.0
    return 0.0, abs(v)


def _write_moneyflow(conn, ts_code: str, trade_date: str, row) -> bool:
    """写入 ts_moneyflow 表。

    AkShare 列：超大单/大单/中单/小单净流入-净额
    → 拆为 buy/sell amount 填入对应分档，保证下游 scoring factor 可用。
    """
    try:
        now = datetime.now().isoformat()
        buy_elg, sell_elg = _split_net_to_buy_sell(row.get("超大单净流入-净额"))
        buy_lg, sell_lg = _split_net_to_buy_sell(row.get("大单净流入-净额"))
        buy_md, sell_md = _split_net_to_buy_sell(row.get("中单净流入-净额"))
        buy_sm, sell_sm = _split_net_to_buy_sell(row.get("小单净流入-净额"))

        conn.execute("""
            INSERT OR REPLACE INTO ts_moneyflow
            (ts_code, trade_date,
             buy_sm_vol, buy_md_vol, buy_lg_vol, buy_elg_vol,
             sell_sm_vol, sell_md_vol, sell_lg_vol, sell_elg_vol,
             buy_sm_amount, buy_md_amount, buy_lg_amount, buy_elg_amount,
             sell_sm_amount, sell_md_amount, sell_lg_amount, sell_elg_amount,
             net_mf_vol, net_mf_amount, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            ts_code, trade_date,
            None, None, None, None,  # buy vol — AkShare 不提供成交量分档
            None, None, None, None,  # sell vol
            buy_sm, buy_md, buy_lg, buy_elg,
            sell_sm, sell_md, sell_lg, sell_elg,
            None,  # net_mf_vol
            safe_float(row.get("主力净流入-净额")),
            now,
        ))
        return True
    except Exception as e:
        logger.warning(f"写入 {ts_code} moneyflow 失败: {e}")
        return False


def run_moneyflow(trade_date: str | None = None) -> list[DatasetTelemetry]:
    """moneyflow producer 入口"""
    from src.data_ingestion.akshare.producers.utils import ensure_tables_exist
    from fetchers.trading_calendar import get_latest_trading_day
    ensure_tables_exist()

    if trade_date is None:
        td = get_latest_trading_day()
        trade_date = td.replace("-", "") if td else datetime.now().strftime("%Y%m%d")

    conn = get_connection()
    symbols = [r[0].split(".")[0] for r in
               conn.execute("SELECT ts_code FROM ts_stock_basic WHERE list_status='L'").fetchall()]

    logger.info(f"moneyflow producer: 获取 {len(symbols)} 只股票 {trade_date} 资金流向...")
    total = 0
    for i, symbol in enumerate(symbols):
        df = _fetch_moneyflow_one(symbol, trade_date)
        if df is not None and not df.empty:
            ts_code = ts_code_from_symbol(symbol)
            for _, row in df.iterrows():
                if _write_moneyflow(conn, ts_code, trade_date, row):
                    total += 1
        if (i + 1) % 500 == 0:
            conn.commit()
            logger.info(f"moneyflow 进度: {i+1}/{len(symbols)}, 已写入 {total} 条")

    conn.commit()
    conn.close()
    logger.info(f"moneyflow producer 完成: {total} 条")
    return [DatasetTelemetry(
        source_key="akshare", dataset_key="ts_moneyflow",
        db_name="stocks", record_count=total,
        latest_record_date=trade_date,
    )]
