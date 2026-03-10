"""
stock_basic producer — 用 AkShare 替代 Tushare stock_basic()

写入 ts_stock_basic 表，保持 schema 契约不变。
8 必须字段: ts_code, symbol, name, industry, market, exchange, list_status, list_date
5 可降级字段: area, is_hs, fullname, delist_date, cn_spell (写 NULL)

DoD: list_date >= 99%, industry >= 95%
"""

import logging
import time
from datetime import datetime

import akshare as ak
import pandas as pd

from src.database.connection import get_connection
from src.data_ingestion.akshare.producers.utils import (
    akshare_limiter, safe_str, ts_code_from_symbol,
)
from src.telemetry.models import DatasetTelemetry

logger = logging.getLogger(__name__)


def _market_from_symbol(symbol: str) -> str:
    s = str(symbol).strip()
    if s.startswith("688"):
        return "科创板"
    if s.startswith("3"):
        return "创业板"
    if s.startswith("8") or s.startswith("4"):
        return "北交所"
    return "主板"


def _exchange_from_symbol(symbol: str) -> str:
    s = str(symbol).strip()
    if s.startswith(("6", "9", "688")):
        return "SSE"
    if s.startswith(("8", "4")):
        return "BSE"
    return "SZSE"


def _fetch_stock_list() -> pd.DataFrame:
    """获取全 A 股列表"""
    akshare_limiter.acquire()
    df = ak.stock_info_a_code_name()
    if df is None or df.empty:
        return pd.DataFrame()
    df = df.rename(columns={"code": "symbol", "name": "name"})
    df["symbol"] = df["symbol"].astype(str).str.zfill(6)
    df["ts_code"] = df["symbol"].apply(ts_code_from_symbol)
    df["market"] = df["symbol"].apply(_market_from_symbol)
    df["exchange"] = df["symbol"].apply(_exchange_from_symbol)
    df["list_status"] = "L"
    return df


def _fetch_industry_mapping() -> dict[str, str]:
    """通过行业板块成分股反查，建立 symbol → industry 映射"""
    mapping = {}
    try:
        akshare_limiter.acquire()
        boards = ak.stock_board_industry_name_em()
        if boards is None or boards.empty:
            return mapping
        for _, row in boards.iterrows():
            board_name = row.get("板块名称", "")
            if not board_name:
                continue
            try:
                akshare_limiter.acquire()
                cons = ak.stock_board_industry_cons_em(symbol=board_name)
                if cons is not None and not cons.empty:
                    code_col = "代码" if "代码" in cons.columns else cons.columns[0]
                    for code in cons[code_col]:
                        symbol = str(code).strip().zfill(6)
                        if symbol not in mapping:
                            mapping[symbol] = board_name
                time.sleep(0.2)  # 额外礼貌延迟
            except Exception as e:
                logger.debug(f"获取板块 {board_name} 成分股失败: {e}")
                continue
    except Exception as e:
        logger.error(f"获取行业板块列表失败: {e}")
    logger.info(f"行业映射完成: {len(mapping)} 只股票有行业归属")
    return mapping


def _fetch_list_dates(symbols: list[str]) -> dict[str, str]:
    """批量获取上市日期 — 通过 stock_individual_info_em 逐股查询"""
    dates = {}
    for symbol in symbols:
        try:
            akshare_limiter.acquire()
            info = ak.stock_individual_info_em(symbol=symbol)
            if info is not None and not info.empty:
                for _, r in info.iterrows():
                    item = str(r.iloc[0]) if len(r) > 0 else ""
                    if "上市" in item and len(r) > 1:
                        val = str(r.iloc[1]).replace("-", "")
                        if len(val) == 8 and val.isdigit():
                            dates[symbol] = val
                            break
        except Exception as e:
            logger.debug(f"获取 {symbol} 上市日期失败: {e}")
        if len(dates) % 500 == 0 and len(dates) > 0:
            logger.info(f"已获取 {len(dates)}/{len(symbols)} 个上市日期")
    return dates


def _write_stock_basic(conn, df: pd.DataFrame) -> int:
    """写入 ts_stock_basic 表"""
    count = 0
    now = datetime.now().isoformat()
    for _, row in df.iterrows():
        try:
            conn.execute("""
                INSERT OR REPLACE INTO ts_stock_basic
                (ts_code, symbol, name, area, industry, fullname, market,
                 exchange, list_status, list_date, delist_date, is_hs, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                row.get("ts_code"),
                row.get("symbol"),
                row.get("name"),
                None,  # area — 可降级
                safe_str(row.get("industry")),
                None,  # fullname — 可降级
                row.get("market"),
                row.get("exchange"),
                row.get("list_status", "L"),
                safe_str(row.get("list_date")),
                None,  # delist_date — 可降级
                None,  # is_hs — 可降级
                now,
            ))
            count += 1
        except Exception as e:
            logger.warning(f"写入 {row.get('ts_code')} 失败: {e}")
    conn.commit()
    return count


def run_stock_basic() -> list[DatasetTelemetry]:
    """stock_basic producer 入口 — scheduler 调用"""
    from src.data_ingestion.akshare.producers.utils import ensure_tables_exist
    ensure_tables_exist()

    logger.info("开始获取全 A 股列表...")
    df = _fetch_stock_list()
    if df.empty:
        return [DatasetTelemetry(
            source_key="akshare", dataset_key="ts_stock_basic",
            db_name="stocks", record_count=0, status="empty",
        )]

    # 获取行业映射
    logger.info("获取行业板块映射...")
    industry_map = _fetch_industry_mapping()
    df["industry"] = df["symbol"].map(industry_map)

    # 获取上市日期（仅对缺失 list_date 的股票查询）
    conn = get_connection()
    existing = {}
    try:
        rows = conn.execute(
            "SELECT ts_code, list_date FROM ts_stock_basic WHERE list_date IS NOT NULL"
        ).fetchall()
        existing = {r[0]: r[1] for r in rows}
    except Exception:
        pass

    need_dates = [s for s in df["symbol"] if ts_code_from_symbol(s) not in existing]
    if need_dates:
        logger.info(f"需要查询 {len(need_dates)} 个股票的上市日期...")
        date_map = _fetch_list_dates(need_dates)
        df["list_date"] = df["symbol"].map(
            lambda s: date_map.get(s) or existing.get(ts_code_from_symbol(s))
        )
    else:
        df["list_date"] = df["ts_code"].map(existing)

    count = _write_stock_basic(conn, df)
    conn.close()

    # 覆盖率检查
    industry_coverage = df["industry"].notna().mean()
    list_date_coverage = df["list_date"].notna().mean()
    logger.info(
        f"stock_basic 完成: {count} 条, "
        f"industry 覆盖率 {industry_coverage:.1%}, "
        f"list_date 覆盖率 {list_date_coverage:.1%}"
    )

    return [DatasetTelemetry(
        source_key="akshare", dataset_key="ts_stock_basic",
        db_name="stocks", record_count=count,
    )]
