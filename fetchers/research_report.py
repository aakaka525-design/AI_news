"""
Research report fetcher — fetches from AkShare (EastMoney source).

Produces dicts compatible with ReportRepository.upsert_report().
"""

from __future__ import annotations

import logging

import pandas as pd

logger = logging.getLogger(__name__)


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
