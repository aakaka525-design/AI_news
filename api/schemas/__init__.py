"""Pydantic response models for API documentation."""

from typing import Optional

from pydantic import BaseModel


class HealthDBStatus(BaseModel):
    ok: bool
    error: Optional[str] = None


class HealthSchedulerStatus(BaseModel):
    running: bool
    error: Optional[str] = None


class HealthResponse(BaseModel):
    status: str
    db: HealthDBStatus
    scheduler: HealthSchedulerStatus
    version: str


class NewsItem(BaseModel):
    id: int
    title: str
    content: str
    content_html: str
    received_at: str
    cleaned_data: Optional[dict] = None
    source: Optional[str] = None


class NewsListResponse(BaseModel):
    total: int
    data: list[NewsItem]


class WebhookResponse(BaseModel):
    status: str
    message: str
    news_id: Optional[int] = None
    hotspots: Optional[list[str]] = None
    keywords: Optional[list[str]] = None


class ErrorResponse(BaseModel):
    error: str
    type: str = "Error"
    detail: Optional[str] = None


class CleanResponse(BaseModel):
    title: str
    summary: str
    facts: list[dict]
    hotspots: list[str]
    keywords: list[str]
    cleaned_at: str


# ===== Stocks =====

class StockBasicItem(BaseModel):
    ts_code: str
    symbol: str
    name: str
    industry: Optional[str] = None
    market: Optional[str] = None
    area: Optional[str] = None
    list_date: Optional[str] = None
    close: Optional[float] = None
    pct_chg: Optional[float] = None
    amount: Optional[float] = None
    turnover_rate: Optional[float] = None
    total_mv: Optional[float] = None


class StockListResponse(BaseModel):
    total: int
    page: int
    page_size: int
    data: list[StockBasicItem]


class ValuationItem(BaseModel):
    trade_date: str
    pe: Optional[float] = None
    pe_ttm: Optional[float] = None
    pb: Optional[float] = None
    ps: Optional[float] = None
    ps_ttm: Optional[float] = None
    dv_ratio: Optional[float] = None
    dv_ttm: Optional[float] = None
    total_mv: Optional[float] = None
    circ_mv: Optional[float] = None
    total_share: Optional[float] = None
    float_share: Optional[float] = None
    turnover_rate: Optional[float] = None
    volume_ratio: Optional[float] = None


class StockProfileResponse(BaseModel):
    ts_code: str
    symbol: str
    name: str
    industry: Optional[str] = None
    market: Optional[str] = None
    area: Optional[str] = None
    exchange: Optional[str] = None
    list_date: Optional[str] = None
    fullname: Optional[str] = None
    is_hs: Optional[str] = None
    valuation: Optional[ValuationItem] = None


class StockDailyItem(BaseModel):
    trade_date: str
    open: Optional[float] = None
    high: Optional[float] = None
    low: Optional[float] = None
    close: Optional[float] = None
    pre_close: Optional[float] = None
    change: Optional[float] = None
    pct_chg: Optional[float] = None
    vol: Optional[float] = None
    amount: Optional[float] = None
    turnover_rate: Optional[float] = None


class StockDailyResponse(BaseModel):
    data: list[StockDailyItem]


# ===== Market Overview =====

class IndexItem(BaseModel):
    ts_code: str
    trade_date: str
    open: Optional[float] = None
    high: Optional[float] = None
    low: Optional[float] = None
    close: Optional[float] = None
    pre_close: Optional[float] = None
    change: Optional[float] = None
    pct_chg: Optional[float] = None
    vol: Optional[float] = None
    amount: Optional[float] = None
    up_count: Optional[int] = None
    down_count: Optional[int] = None


class MarketOverviewResponse(BaseModel):
    data: list[IndexItem]


# ===== Screener Snapshots =====

class ScreenRpsItem(BaseModel):
    ts_code: str
    stock_name: Optional[str] = None
    rps_10: Optional[float] = None
    rps_20: Optional[float] = None
    rps_50: Optional[float] = None
    rps_120: Optional[float] = None
    rank: Optional[int] = None


class ScreenRpsResponse(BaseModel):
    snapshot_date: str
    source_trade_date: str
    generated_at: str
    total: int
    items: list[ScreenRpsItem]


class ScreenPotentialItem(BaseModel):
    ts_code: str
    stock_name: Optional[str] = None
    total_score: Optional[float] = None
    capital_score: Optional[float] = None
    trading_score: Optional[float] = None
    fundamental_score: Optional[float] = None
    technical_score: Optional[float] = None
    signals: Optional[str] = None
    rank: Optional[int] = None


class ScreenPotentialResponse(BaseModel):
    snapshot_date: str
    source_trade_date: str
    generated_at: str
    total: int
    items: list[ScreenPotentialItem]
