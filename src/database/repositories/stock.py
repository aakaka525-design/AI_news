"""
Stock repository — read-only queries against the stocks database (stocks.db).

Covers tables: ts_stock_basic, ts_daily, stock_index, block_daily,
               money_flow, dragon_tiger, ts_daily_basic.

Usage:
    from src.database.engine import create_engine_from_url, get_session_factory
    from src.database.repositories.stock import StockRepository

    engine = create_engine_from_url(DATABASE_URL)
    Session = get_session_factory(engine)
    repo = StockRepository(Session)

    stocks = repo.get_stock_list(page=1, page_size=20)
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any, Optional

from sqlalchemy import func, desc, asc, case
from sqlalchemy.orm import sessionmaker

from src.database.models import (
    StockBasic,
    StockDaily,
    StockIndex,
    BlockDaily,
    MoneyFlow,
    DragonTiger,
    TsDailyBasic,
)


def _num(v: Any) -> Any:
    """Convert Decimal/Numeric to float for JSON serialization."""
    if isinstance(v, Decimal):
        return float(v)
    return v


class StockRepository:
    """Read-only data-access layer for the stocks database.

    Every public method opens (and closes) its own session.
    All public methods return plain ``dict`` / ``list`` values.
    """

    def __init__(self, session_factory: sessionmaker) -> None:
        self.Session = session_factory

    # ----------------------------------------------------------
    # Stock list & profile
    # ----------------------------------------------------------

    # Allowed sort columns for stock list
    _STOCK_SORT_COLUMNS = {
        "ts_code", "pct_chg", "amount", "total_mv", "turnover_rate",
    }

    def get_stock_list(
        self,
        search: Optional[str] = None,
        industry: Optional[str] = None,
        market: Optional[str] = None,
        page: int = 1,
        page_size: int = 20,
        sort_by: Optional[str] = None,
        sort_order: str = "asc",
    ) -> dict[str, Any]:
        """Paginated stock list with optional search/filter and trading data."""
        with self.Session() as session:
            # Find the latest trade_date in StockDaily for the JOIN
            latest_date_sub = session.query(func.max(StockDaily.trade_date)).scalar()
            latest_basic_sub = session.query(func.max(TsDailyBasic.trade_date)).scalar()

            q = (
                session.query(
                    StockBasic,
                    StockDaily.close,
                    StockDaily.pct_chg,
                    StockDaily.amount,
                    TsDailyBasic.turnover_rate,
                    TsDailyBasic.total_mv,
                )
                .outerjoin(
                    StockDaily,
                    (StockBasic.ts_code == StockDaily.ts_code)
                    & (StockDaily.trade_date == latest_date_sub),
                )
                .outerjoin(
                    TsDailyBasic,
                    (StockBasic.ts_code == TsDailyBasic.ts_code)
                    & (TsDailyBasic.trade_date == latest_basic_sub),
                )
                .filter(
                    (StockBasic.list_status == "L")
                    | (StockBasic.list_status.is_(None))
                )
            )

            if search:
                pattern = f"%{search}%"
                q = q.filter(
                    (StockBasic.name.like(pattern))
                    | (StockBasic.ts_code.like(pattern))
                    | (StockBasic.symbol.like(pattern))
                )
            if industry:
                q = q.filter(StockBasic.industry == industry)
            if market:
                q = q.filter(StockBasic.market == market)

            total = q.count()

            # Determine sort column
            # Use case() for nulls-last ordering (SQLite compatible)
            sort_fn = desc if sort_order == "desc" else asc
            if sort_by in self._STOCK_SORT_COLUMNS and sort_by != "ts_code":
                col_map = {
                    "pct_chg": StockDaily.pct_chg,
                    "amount": StockDaily.amount,
                    "total_mv": TsDailyBasic.total_mv,
                    "turnover_rate": TsDailyBasic.turnover_rate,
                }
                col = col_map[sort_by]
                # nulls last: sort NULL rows to end regardless of direction
                q = q.order_by(
                    case((col.is_(None), 1), else_=0),
                    sort_fn(col),
                )
            else:
                q = q.order_by(sort_fn(StockBasic.ts_code))

            rows = q.offset((page - 1) * page_size).limit(page_size).all()

            return {
                "total": total,
                "page": page,
                "page_size": page_size,
                "data": [
                    {
                        "ts_code": r.StockBasic.ts_code,
                        "symbol": r.StockBasic.symbol,
                        "name": r.StockBasic.name,
                        "industry": r.StockBasic.industry,
                        "market": r.StockBasic.market,
                        "area": r.StockBasic.area,
                        "list_date": r.StockBasic.list_date,
                        "close": _num(r.close),
                        "pct_chg": _num(r.pct_chg),
                        "amount": _num(r.amount),
                        "turnover_rate": _num(r.turnover_rate),
                        "total_mv": _num(r.total_mv),
                    }
                    for r in rows
                ],
            }

    def get_stock_profile(self, ts_code: str) -> Optional[dict[str, Any]]:
        """Stock basic info + latest valuation metrics."""
        with self.Session() as session:
            stock = session.get(StockBasic, ts_code)
            if stock is None:
                return None

            profile: dict[str, Any] = {
                "ts_code": stock.ts_code,
                "symbol": stock.symbol,
                "name": stock.name,
                "industry": stock.industry,
                "market": stock.market,
                "area": stock.area,
                "exchange": stock.exchange,
                "list_date": stock.list_date,
                "fullname": stock.fullname,
                "is_hs": stock.is_hs,
            }

            # Latest valuation
            val = (
                session.query(TsDailyBasic)
                .filter(TsDailyBasic.ts_code == ts_code)
                .order_by(desc(TsDailyBasic.trade_date))
                .first()
            )
            if val:
                profile["valuation"] = {
                    "trade_date": val.trade_date,
                    "pe": _num(val.pe),
                    "pe_ttm": _num(val.pe_ttm),
                    "pb": _num(val.pb),
                    "ps": _num(val.ps),
                    "ps_ttm": _num(val.ps_ttm),
                    "dv_ratio": _num(val.dv_ratio),
                    "dv_ttm": _num(val.dv_ttm),
                    "total_mv": _num(val.total_mv),
                    "circ_mv": _num(val.circ_mv),
                    "total_share": _num(val.total_share),
                    "float_share": _num(val.float_share),
                    "turnover_rate": _num(val.turnover_rate),
                    "volume_ratio": _num(val.volume_ratio),
                }
            else:
                profile["valuation"] = None

            return profile

    def get_valuation_history(
        self, ts_code: str, limit: int = 250
    ) -> list[dict[str, Any]]:
        """Historical valuation metrics (PE/PB/PS/DV/MV)."""
        with self.Session() as session:
            rows = (
                session.query(TsDailyBasic)
                .filter(TsDailyBasic.ts_code == ts_code)
                .order_by(desc(TsDailyBasic.trade_date))
                .limit(limit)
                .all()
            )
            return [
                {
                    "trade_date": r.trade_date,
                    "pe_ttm": _num(r.pe_ttm),
                    "pb": _num(r.pb),
                    "ps_ttm": _num(r.ps_ttm),
                    "dv_ttm": _num(r.dv_ttm),
                    "total_mv": _num(r.total_mv),
                }
                for r in rows
            ]

    def get_industries(self) -> list[str]:
        """Distinct industry list for filter dropdown."""
        with self.Session() as session:
            rows = (
                session.query(StockBasic.industry)
                .filter(
                    StockBasic.industry.isnot(None),
                    (StockBasic.list_status == "L") | (StockBasic.list_status.is_(None)),
                )
                .distinct()
                .order_by(StockBasic.industry)
                .all()
            )
            return [r[0] for r in rows if r[0]]

    # ----------------------------------------------------------
    # Daily price data
    # ----------------------------------------------------------

    def get_stock_daily(
        self,
        ts_code: str,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        limit: int = 250,
    ) -> list[dict[str, Any]]:
        """Daily OHLCV data for a stock, newest first."""
        with self.Session() as session:
            q = session.query(StockDaily).filter(StockDaily.ts_code == ts_code)
            if start_date:
                q = q.filter(StockDaily.trade_date >= start_date)
            if end_date:
                q = q.filter(StockDaily.trade_date <= end_date)

            rows = q.order_by(desc(StockDaily.trade_date)).limit(limit).all()

            return [
                {
                    "trade_date": r.trade_date,
                    "open": _num(r.open),
                    "high": _num(r.high),
                    "low": _num(r.low),
                    "close": _num(r.close),
                    "pre_close": _num(r.pre_close),
                    "change": _num(r.change),
                    "pct_chg": _num(r.pct_chg),
                    "vol": r.vol,
                    "amount": _num(r.amount),
                    "turnover_rate": _num(r.turnover_rate),
                }
                for r in rows
            ]

    # ----------------------------------------------------------
    # Market overview (index data)
    # ----------------------------------------------------------

    def get_market_overview(self, trade_date: Optional[str] = None) -> list[dict[str, Any]]:
        """Index quotes for major indices. Uses latest date if not specified."""
        with self.Session() as session:
            if not trade_date:
                latest = session.query(func.max(StockIndex.trade_date)).scalar()
                if not latest:
                    return []
                trade_date = latest

            rows = (
                session.query(StockIndex)
                .filter(StockIndex.trade_date == trade_date)
                .order_by(StockIndex.ts_code)
                .all()
            )

            return [
                {
                    "ts_code": r.ts_code,
                    "trade_date": r.trade_date,
                    "open": _num(r.open),
                    "high": _num(r.high),
                    "low": _num(r.low),
                    "close": _num(r.close),
                    "pre_close": _num(r.pre_close),
                    "change": _num(r.change),
                    "pct_chg": _num(r.pct_chg),
                    "vol": r.vol,
                    "amount": _num(r.amount),
                    "up_count": r.up_count,
                    "down_count": r.down_count,
                }
                for r in rows
            ]

    # ----------------------------------------------------------
    # Money flow
    # ----------------------------------------------------------

    def get_money_flow(
        self,
        trade_date: Optional[str] = None,
        flow_type: Optional[str] = None,
        ts_code: Optional[str] = None,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        """Capital flow data."""
        with self.Session() as session:
            q = session.query(MoneyFlow)

            if ts_code:
                q = q.filter(MoneyFlow.ts_code == ts_code)
            if trade_date:
                q = q.filter(MoneyFlow.trade_date == trade_date)
            else:
                latest = session.query(func.max(MoneyFlow.trade_date)).scalar()
                if latest:
                    q = q.filter(MoneyFlow.trade_date == latest)
            if flow_type:
                q = q.filter(MoneyFlow.flow_type == flow_type)

            rows = (
                q.order_by(desc(MoneyFlow.net_mf_amount))
                .limit(limit)
                .all()
            )

            return [
                {
                    "ts_code": r.ts_code,
                    "trade_date": r.trade_date,
                    "flow_type": r.flow_type,
                    "buy_elg_amount": _num(r.buy_elg_amount),
                    "sell_elg_amount": _num(r.sell_elg_amount),
                    "buy_lg_amount": _num(r.buy_lg_amount),
                    "sell_lg_amount": _num(r.sell_lg_amount),
                    "net_mf_amount": _num(r.net_mf_amount),
                    "net_mf_rate": _num(r.net_mf_rate),
                    "north_amount": _num(r.north_amount),
                    "north_net": _num(r.north_net),
                }
                for r in rows
            ]

    # ----------------------------------------------------------
    # Dragon tiger
    # ----------------------------------------------------------

    def get_dragon_tiger(
        self,
        trade_date: Optional[str] = None,
        ts_code: Optional[str] = None,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        """Dragon tiger list data."""
        with self.Session() as session:
            q = session.query(DragonTiger)

            if ts_code:
                q = q.filter(DragonTiger.ts_code == ts_code)
            if trade_date:
                q = q.filter(DragonTiger.trade_date == trade_date)
            else:
                latest = session.query(func.max(DragonTiger.trade_date)).scalar()
                if latest:
                    q = q.filter(DragonTiger.trade_date == latest)

            rows = q.order_by(desc(DragonTiger.net_amount)).limit(limit).all()

            return [
                {
                    "ts_code": r.ts_code,
                    "trade_date": r.trade_date,
                    "name": r.name,
                    "close": _num(r.close),
                    "pct_chg": _num(r.pct_chg),
                    "turnover_rate": _num(r.turnover_rate),
                    "amount": _num(r.amount),
                    "l_buy": _num(r.l_buy),
                    "l_sell": _num(r.l_sell),
                    "net_amount": _num(r.net_amount),
                    "net_rate": _num(r.net_rate),
                    "reason": r.reason,
                    "inst_buy": _num(r.inst_buy),
                    "inst_sell": _num(r.inst_sell),
                }
                for r in rows
            ]

    # ----------------------------------------------------------
    # Sectors / blocks
    # ----------------------------------------------------------

    def get_sectors(
        self,
        block_type: Optional[str] = None,
        trade_date: Optional[str] = None,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        """Sector/block daily data."""
        with self.Session() as session:
            q = session.query(BlockDaily)

            if block_type:
                q = q.filter(BlockDaily.block_type == block_type)
            if trade_date:
                q = q.filter(BlockDaily.trade_date == trade_date)
            else:
                sub = session.query(func.max(BlockDaily.trade_date))
                if block_type:
                    sub = sub.filter(BlockDaily.block_type == block_type)
                latest = sub.scalar()
                if latest:
                    q = q.filter(BlockDaily.trade_date == latest)

            rows = q.order_by(desc(BlockDaily.pct_chg)).limit(limit).all()

            return [
                {
                    "block_code": r.block_code,
                    "block_name": r.block_name,
                    "block_type": r.block_type,
                    "trade_date": r.trade_date,
                    "open": _num(r.open),
                    "high": _num(r.high),
                    "low": _num(r.low),
                    "close": _num(r.close),
                    "pct_chg": _num(r.pct_chg),
                    "vol": r.vol,
                    "amount": _num(r.amount),
                    "turnover_rate": _num(r.turnover_rate),
                    "lead_stock": r.lead_stock,
                    "up_count": r.up_count,
                    "down_count": r.down_count,
                }
                for r in rows
            ]
