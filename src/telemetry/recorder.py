"""Telemetry recorder — persists task execution health to stocks.db."""

import logging

from src.database.connection import get_connection
from src.telemetry.models import TaskExecutionTelemetry

logger = logging.getLogger(__name__)

_DDL = """\
CREATE TABLE IF NOT EXISTS data_source_health (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_key TEXT NOT NULL,
    dataset_key TEXT NOT NULL,
    db_name TEXT NOT NULL DEFAULT 'stocks',
    task_id TEXT NOT NULL,
    record_count INTEGER DEFAULT 0,
    latest_record_date TEXT,
    status TEXT DEFAULT 'ok',
    error_message TEXT,
    started_at TIMESTAMP NOT NULL,
    finished_at TIMESTAMP NOT NULL,
    duration_seconds REAL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(source_key, dataset_key, db_name)
)
"""


def _ensure_table(conn):
    conn.execute(_DDL)
    conn.commit()


def record_telemetry(telemetry: TaskExecutionTelemetry) -> None:
    """Persist telemetry datasets to ``data_source_health``.

    Idempotent: UNIQUE(source_key, dataset_key, db_name) ensures only the
    latest row per dataset is kept via INSERT OR REPLACE.
    """
    if not telemetry.datasets:
        return

    conn = get_connection()
    try:
        _ensure_table(conn)

        duration = None
        if telemetry.started_at and telemetry.finished_at:
            duration = (telemetry.finished_at - telemetry.started_at).total_seconds()

        for ds in telemetry.datasets:
            conn.execute(
                """\
                INSERT OR REPLACE INTO data_source_health
                    (source_key, dataset_key, db_name, task_id, record_count,
                     latest_record_date, status, error_message,
                     started_at, finished_at, duration_seconds)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    ds.source_key,
                    ds.dataset_key,
                    ds.db_name,
                    telemetry.task_id,
                    ds.record_count,
                    ds.latest_record_date,
                    ds.status,
                    ds.error_message,
                    telemetry.started_at.isoformat(),
                    telemetry.finished_at.isoformat() if telemetry.finished_at else None,
                    duration,
                ),
            )

        conn.commit()
        logger.info(
            "Recorded %d dataset(s) for task %s", len(telemetry.datasets), telemetry.task_id
        )
    finally:
        conn.close()
