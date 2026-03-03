"""Data ingestion package with lazy imports to avoid heavy import side effects."""

from src.data_ingestion.compat import (
    from_ts_code,
    normalize_code,
    query_daily,
    query_financials,
    query_stock_info,
    to_legacy_date,
    to_trade_date,
    to_ts_code,
)

__all__ = [
    "TushareAdapter",
    "get_tushare_client",
    "to_ts_code",
    "from_ts_code",
    "normalize_code",
    "to_trade_date",
    "to_legacy_date",
    "query_daily",
    "query_stock_info",
    "query_financials",
]


def __getattr__(name: str):
    if name in {"TushareAdapter", "get_tushare_client"}:
        from src.data_ingestion.tushare.client import TushareAdapter, get_tushare_client

        return {"TushareAdapter": TushareAdapter, "get_tushare_client": get_tushare_client}[name]
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
