"""Pydantic models used by AkShare ingestion pipelines."""

from typing import Optional

from pydantic import BaseModel


class MarginTrading(BaseModel):
    stock_code: str
    stock_name: Optional[str] = None
    date: str
    market: Optional[str] = None
    margin_balance: Optional[float] = None
    margin_buy: Optional[float] = None
    margin_repay: Optional[float] = None
    short_balance: Optional[float] = None
    short_sell: Optional[float] = None
    short_repay: Optional[float] = None


class StockDaily(BaseModel):
    stock_code: str
    date: str
    open: Optional[float] = None
    close: Optional[float] = None
    high: Optional[float] = None
    low: Optional[float] = None
    volume: Optional[float] = None
    amount: Optional[float] = None
    amplitude: Optional[float] = None
    change_pct: Optional[float] = None
    turnover_rate: Optional[float] = None
