"""
Research report fetcher — fetches from AkShare (EastMoney source).

Produces dicts compatible with ReportRepository.upsert_report().
"""

from __future__ import annotations

import logging
import sqlite3

import pandas as pd

from config.settings import DATABASE_URL
from src.database.engine import create_engine_from_url, get_session_factory
from src.database.repositories.report import ReportRepository

logger = logging.getLogger(__name__)

_REPORT_REPO: ReportRepository | None = None


def _stock_suffix(code: str) -> str:
    """Add exchange suffix: 6xx→SH, else→SZ."""
    code = str(code).strip()[:6]
    return f"{code}.SH" if code.startswith("6") else f"{code}.SZ"


def _normalize_date(date_str: str) -> str:
    """Convert 'YYYY-MM-DD' or 'YYYYMMDD' → 'YYYYMMDD'."""
    if not date_str:
        return ""
    return str(date_str)[:10].replace("-", "")


def parse_eastmoney_reports(stock_code: str, df: pd.DataFrame) -> list[dict]:
    """
    Parse an AkShare stock_research_report_em() DataFrame into report dicts.

    Args:
        stock_code: 6-digit stock code
        df: DataFrame from ak.stock_research_report_em()

    Returns:
        List of dicts ready for ReportRepository.upsert_report()
    """
    if df is None or not hasattr(df, "empty") or df.empty:
        return []

    ts_code = _stock_suffix(stock_code)
    reports = []

    for _, row in df.iterrows():
        reports.append(
            {
                "ts_code": ts_code,
                "stock_name": row.get("股票简称") or None,
                "title": row.get("报告名称") or "无标题",
                "rating": row.get("东财评级") or None,
                "institution": row.get("机构") or None,
                "publish_date": _normalize_date(str(row.get("日期", ""))),
            }
        )

    return reports


def fetch_stock_reports(stock_code: str) -> list[dict]:
    """
    Fetch research reports for a single stock from AkShare.

    Args:
        stock_code: 6-digit stock code

    Returns:
        List of report dicts compatible with ReportRepository.upsert_report()
    """
    try:
        import akshare as ak

        df = ak.stock_research_report_em(symbol=stock_code)
        return parse_eastmoney_reports(stock_code, df)
    except Exception as e:
        logger.warning("Failed to fetch reports for %s: %s", stock_code, e)
        return []


def _get_report_repo() -> ReportRepository:
    """Lazy init repository to keep module import lightweight."""
    global _REPORT_REPO
    if _REPORT_REPO is None:
        engine = create_engine_from_url(DATABASE_URL)
        session_factory = get_session_factory(engine)
        _REPORT_REPO = ReportRepository(session_factory)
        _REPORT_REPO.create_tables(engine)
    return _REPORT_REPO


def get_latest_reports(limit: int = 20) -> list[dict]:
    """Read latest saved reports from DB."""
    repo = _get_report_repo()
    safe_limit = max(1, int(limit))
    return repo.get_reports(limit=safe_limit)


def get_stock_reports(stock_code: str, limit: int = 20) -> list[dict]:
    """Read saved reports for one stock code."""
    repo = _get_report_repo()
    safe_limit = max(1, int(limit))
    return repo.get_reports(ts_code=_stock_suffix(stock_code), limit=safe_limit)


def save_reports(reports: list[dict]) -> int:
    """Persist fetched reports, returning successful count."""
    if not reports:
        return 0

    repo = _get_report_repo()
    saved = 0
    for item in reports:
        try:
            repo.upsert_report(item)
            saved += 1
        except Exception as e:  # noqa: BLE001
            logger.warning(
                "Failed to save report for %s/%s: %s",
                item.get("ts_code"),
                item.get("publish_date"),
                e,
            )
    return saved


def _fallback_hot_stock_codes(limit: int) -> list[str]:
    """Get candidate hot stocks; fallback to a stable default set."""
    codes: list[str] = []
    db_path = DATABASE_URL.removeprefix("sqlite:///")
    if db_path != DATABASE_URL:
        try:
            conn = sqlite3.connect(db_path)
            conn.row_factory = sqlite3.Row
            for table, column in (("stocks", "code"), ("dragon_tiger_stock", "stock_code")):
                try:
                    rows = conn.execute(
                        f"SELECT DISTINCT {column} AS code FROM {table} LIMIT ?",
                        (limit,),
                    ).fetchall()
                    codes.extend(str(r["code"]).strip()[:6] for r in rows if r["code"])
                except Exception:
                    continue
            conn.close()
        except Exception:
            pass

    if not codes:
        codes = [
            "600519",
            "000001",
            "300750",
            "601318",
            "002594",
            "600036",
            "601012",
            "688111",
            "600276",
            "000858",
        ]
    # 去重并保留顺序
    uniq: list[str] = []
    seen: set[str] = set()
    for code in codes:
        if code in seen:
            continue
        seen.add(code)
        uniq.append(code)
    return uniq[: max(1, int(limit))]


def fetch_hot_stock_reports(limit: int = 30) -> int:
    """Fetch and save reports for a hot-stock set, returning saved rows."""
    saved_total = 0
    for code in _fallback_hot_stock_codes(limit):
        reports = fetch_stock_reports(code)
        saved_total += save_reports(reports)
    return saved_total


def get_rating_stats() -> dict[str, int]:
    """Read rating distribution from saved reports."""
    repo = _get_report_repo()
    return repo.get_rating_stats()
