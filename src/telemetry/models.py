"""Telemetry data structures for data source health monitoring."""

from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class DatasetTelemetry:
    """Health snapshot for a single dataset."""

    source_key: str  # "tushare" / "rss" / "akshare" / "ai"
    dataset_key: str  # "ts_daily" / "rss_items" / etc.
    db_name: str  # "stocks" / "news"
    record_count: int
    latest_record_date: str | None = None
    status: str = "ok"  # "ok" / "empty" / "error"
    error_message: str | None = None


@dataclass
class TaskExecutionTelemetry:
    """Execution record for a scheduled task."""

    task_id: str
    started_at: datetime
    finished_at: datetime | None = None
    success: bool = False
    error: str | None = None
    datasets: list[DatasetTelemetry] = field(default_factory=list)
