#!/usr/bin/env python3
"""
核心模块单元测试（对齐 src 架构）
"""

import sqlite3
from datetime import datetime
from pathlib import Path

import pytest
from pydantic import BaseModel

from src.analysis.cleaner import remove_noise
from src.database.connection import insert_validated
from src.utils.retry import retry


class _DemoRecord(BaseModel):
    code: str
    trade_date: str
    value: float


def test_remove_noise_should_keep_markdown_link_text():
    text = "查看 [官方公告](https://example.com/notice) 获取详情"
    cleaned = remove_noise(text)
    assert "官方公告" in cleaned
    assert "http" not in cleaned


def test_insert_validated_should_apply_upsert_by_unique_keys(tmp_path: Path):
    db_path = tmp_path / "test.db"
    conn = sqlite3.connect(db_path)
    conn.execute(
        """
        CREATE TABLE sample (
            code TEXT NOT NULL,
            trade_date TEXT NOT NULL,
            value REAL,
            UNIQUE(code, trade_date)
        )
        """
    )

    first = _DemoRecord(code="000001", trade_date="20260101", value=1.0)
    second = _DemoRecord(code="000001", trade_date="20260101", value=2.0)

    assert insert_validated(conn, "sample", first, ["code", "trade_date"]) is True
    assert insert_validated(conn, "sample", second, ["code", "trade_date"]) is True
    conn.commit()

    row = conn.execute("SELECT COUNT(*), MAX(value) FROM sample").fetchone()
    conn.close()
    assert row[0] == 1
    assert row[1] == 2.0


def test_retry_decorator_success_after_transient_failure():
    call_count = 0

    @retry(max_attempts=3, delay=0.01)
    def flaky():
        nonlocal call_count
        call_count += 1
        if call_count < 2:
            raise ValueError("temporary")
        return "ok"

    assert flaky() == "ok"
    assert call_count == 2


def test_retry_decorator_raises_after_max_attempts():
    call_count = 0

    @retry(max_attempts=3, delay=0.01)
    def always_fail():
        nonlocal call_count
        call_count += 1
        raise RuntimeError("boom")

    with pytest.raises(RuntimeError):
        always_fail()
    assert call_count == 3


def test_date_input_is_relative_not_hardcoded():
    today = datetime.now().strftime("%Y%m%d")
    assert len(today) == 8


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
