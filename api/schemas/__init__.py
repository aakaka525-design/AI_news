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
