"""Unit tests for the telemetry subsystem."""

import sqlite3
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from src.telemetry.models import DatasetTelemetry, TaskExecutionTelemetry
from src.telemetry.recorder import record_telemetry, _DDL


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


@pytest.fixture
def tmp_db(tmp_path, monkeypatch):
    """Redirect get_connection() to a temporary SQLite file."""
    db_file = tmp_path / "test_stocks.db"

    def _fake_get_connection(timeout=30):
        conn = sqlite3.connect(str(db_file), timeout=timeout)
        conn.row_factory = sqlite3.Row
        return conn

    monkeypatch.setattr("src.telemetry.recorder.get_connection", _fake_get_connection)
    return db_file


def _read_all(db_file: Path) -> list[dict]:
    conn = sqlite3.connect(str(db_file))
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute("SELECT * FROM data_source_health ORDER BY source_key, dataset_key").fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Dataclass construction
# ---------------------------------------------------------------------------


class TestDataclasses:
    def test_dataset_telemetry_defaults(self):
        ds = DatasetTelemetry(source_key="rss", dataset_key="rss_items", db_name="news", record_count=42)
        assert ds.status == "ok"
        assert ds.error_message is None
        assert ds.latest_record_date is None

    def test_task_execution_telemetry_defaults(self):
        tel = TaskExecutionTelemetry(task_id="test", started_at=datetime.now())
        assert tel.success is False
        assert tel.datasets == []
        assert tel.error is None

    def test_error_status(self):
        ds = DatasetTelemetry(
            source_key="tushare", dataset_key="ts_daily", db_name="stocks",
            record_count=0, status="error", error_message="API timeout",
        )
        assert ds.status == "error"
        assert ds.error_message == "API timeout"


# ---------------------------------------------------------------------------
# Recorder
# ---------------------------------------------------------------------------


class TestRecorder:
    def test_record_creates_table_and_inserts(self, tmp_db):
        now = datetime.now()
        tel = TaskExecutionTelemetry(
            task_id="rss_fetch",
            started_at=now,
            finished_at=now + timedelta(seconds=5),
            success=True,
            datasets=[
                DatasetTelemetry(source_key="rss", dataset_key="rss_items", db_name="news", record_count=100),
            ],
        )
        record_telemetry(tel)

        rows = _read_all(tmp_db)
        assert len(rows) == 1
        assert rows[0]["source_key"] == "rss"
        assert rows[0]["record_count"] == 100
        assert rows[0]["task_id"] == "rss_fetch"
        assert rows[0]["duration_seconds"] == pytest.approx(5.0, abs=0.1)

    def test_upsert_keeps_latest(self, tmp_db):
        """Writing twice for same (source_key, dataset_key, db_name) keeps only the latest."""
        now = datetime.now()

        for count in (10, 42):
            tel = TaskExecutionTelemetry(
                task_id="rss_fetch",
                started_at=now,
                finished_at=now + timedelta(seconds=1),
                success=True,
                datasets=[
                    DatasetTelemetry(source_key="rss", dataset_key="rss_items", db_name="news", record_count=count),
                ],
            )
            record_telemetry(tel)

        rows = _read_all(tmp_db)
        assert len(rows) == 1
        assert rows[0]["record_count"] == 42

    def test_multiple_datasets(self, tmp_db):
        now = datetime.now()
        tel = TaskExecutionTelemetry(
            task_id="stock_indicators",
            started_at=now,
            finished_at=now + timedelta(seconds=30),
            success=True,
            datasets=[
                DatasetTelemetry(source_key="tushare", dataset_key="ts_daily", db_name="stocks", record_count=5000),
                DatasetTelemetry(source_key="tushare", dataset_key="ts_weekly", db_name="stocks", record_count=1000),
            ],
        )
        record_telemetry(tel)

        rows = _read_all(tmp_db)
        assert len(rows) == 2

    def test_error_state_recorded(self, tmp_db):
        now = datetime.now()
        tel = TaskExecutionTelemetry(
            task_id="fund_flow",
            started_at=now,
            finished_at=now + timedelta(seconds=2),
            success=False,
            error="API timeout",
            datasets=[
                DatasetTelemetry(
                    source_key="tushare", dataset_key="ts_moneyflow", db_name="stocks",
                    record_count=0, status="error", error_message="API timeout",
                ),
            ],
        )
        record_telemetry(tel)

        rows = _read_all(tmp_db)
        assert len(rows) == 1
        assert rows[0]["status"] == "error"
        assert rows[0]["error_message"] == "API timeout"

    def test_empty_datasets_is_noop(self, tmp_db):
        tel = TaskExecutionTelemetry(task_id="noop", started_at=datetime.now(), datasets=[])
        record_telemetry(tel)

        conn = sqlite3.connect(str(tmp_db))
        # Table may not even exist since no write happened
        tables = conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
        conn.close()
        table_names = [t[0] for t in tables]
        assert "data_source_health" not in table_names
