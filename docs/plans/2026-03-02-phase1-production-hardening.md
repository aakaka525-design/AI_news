# Phase 1: Production Hardening Implementation Plan

> **状态：部分完成**
> 本计划的部分目标（测试、CI/CD、错误处理、Telemetry）已被 Phase 1/2 实际实现吸收，但并非所有条目都已完整落地。请参考 `docs/ai-handoff/` 中的执行报告和复核结论确认具体完成度。

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Stabilize the AI_news platform with tests, CI/CD, structured logging, unified error handling, and API documentation — making the existing functionality reliable before adding new features.

**Architecture:** Add a test layer (pytest + fixtures), exception hierarchy (`src/exceptions.py`), structured logging (structlog), and API documentation (FastAPI Swagger + versioned routes). No behavioral changes to existing code — only wrapping/improving reliability.

**Tech Stack:** pytest, pytest-asyncio, pytest-cov, httpx, structlog, ruff, GitHub Actions

---

## Prerequisites

Before starting, install dev dependencies:

```bash
cd /Users/xa/Desktop/projiect/AI_news
pip install pytest pytest-asyncio pytest-cov httpx structlog ruff pre-commit
```

---

### Task 1: Define Exception Hierarchy

**Files:**
- Create: `src/exceptions.py`
- Test: `tests/test_exceptions.py`

**Step 1: Write the failing test**

```python
# tests/test_exceptions.py
"""Exception hierarchy tests."""
import pytest
from src.exceptions import (
    AppError,
    DataFetchError,
    AnalysisError,
    DatabaseError,
    ConfigError,
)


def test_app_error_is_base():
    err = AppError("base error")
    assert str(err) == "base error"
    assert isinstance(err, Exception)


def test_data_fetch_error_inherits_app_error():
    err = DataFetchError("tushare timeout", source="tushare", code="000001.SZ")
    assert isinstance(err, AppError)
    assert err.source == "tushare"
    assert err.code == "000001.SZ"


def test_analysis_error_inherits_app_error():
    err = AnalysisError("sentiment calc failed", module="sentiment")
    assert isinstance(err, AppError)
    assert err.module == "sentiment"


def test_database_error_inherits_app_error():
    err = DatabaseError("upsert failed", table="ts_daily")
    assert isinstance(err, AppError)
    assert err.table == "ts_daily"


def test_config_error_inherits_app_error():
    err = ConfigError("missing TUSHARE_TOKEN")
    assert isinstance(err, AppError)
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_exceptions.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'src.exceptions'`

**Step 3: Write minimal implementation**

```python
# src/exceptions.py
"""
Unified exception hierarchy for AI_news.

AppError
├── DataFetchError   — data ingestion failures
├── AnalysisError    — analysis module failures
├── DatabaseError    — database operation failures
└── ConfigError      — configuration/env errors
"""


class AppError(Exception):
    """Base exception for all AI_news errors."""
    pass


class DataFetchError(AppError):
    """Raised when data fetching fails (Tushare, AkShare, RSS, etc.)."""

    def __init__(self, message: str, *, source: str = "", code: str = ""):
        super().__init__(message)
        self.source = source
        self.code = code


class AnalysisError(AppError):
    """Raised when an analysis module fails."""

    def __init__(self, message: str, *, module: str = ""):
        super().__init__(message)
        self.module = module


class DatabaseError(AppError):
    """Raised when a database operation fails."""

    def __init__(self, message: str, *, table: str = ""):
        super().__init__(message)
        self.table = table


class ConfigError(AppError):
    """Raised when required configuration is missing or invalid."""
    pass
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_exceptions.py -v`
Expected: 5 passed

**Step 5: Commit**

```bash
git add src/exceptions.py tests/test_exceptions.py
git commit -m "feat: add unified exception hierarchy"
```

---

### Task 2: Add structlog Integration

**Files:**
- Create: `src/logging.py`
- Test: `tests/test_logging_setup.py`

**Step 1: Write the failing test**

```python
# tests/test_logging_setup.py
"""Structured logging setup tests."""
import json
import pytest
from src.logging import get_logger, setup_logging


def test_get_logger_returns_bound_logger():
    logger = get_logger("test_module")
    assert logger is not None
    assert hasattr(logger, "info")
    assert hasattr(logger, "error")
    assert hasattr(logger, "warning")


def test_logger_binds_module_name(capsys):
    setup_logging(json_output=False)
    logger = get_logger("my_module")
    logger.info("hello")
    captured = capsys.readouterr()
    assert "my_module" in captured.out
    assert "hello" in captured.out


def test_logger_json_mode(capsys):
    setup_logging(json_output=True)
    logger = get_logger("json_test")
    logger.info("structured")
    captured = capsys.readouterr()
    parsed = json.loads(captured.out.strip())
    assert parsed["module"] == "json_test"
    assert parsed["event"] == "structured"
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_logging_setup.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'src.logging'`

**Step 3: Write minimal implementation**

```python
# src/logging.py
"""
Structured logging for AI_news.

Usage:
    from src.logging import get_logger
    logger = get_logger(__name__)
    logger.info("fetching data", stock="000001.SZ")
"""
import structlog


def setup_logging(json_output: bool = True) -> None:
    """Configure structlog processors."""
    processors = [
        structlog.stdlib.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
    ]
    if json_output:
        processors.append(structlog.processors.JSONRenderer())
    else:
        processors.append(structlog.dev.ConsoleRenderer())

    structlog.configure(
        processors=processors,
        wrapper_class=structlog.make_filtering_bound_logger(0),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=False,
    )


def get_logger(module: str) -> structlog.BoundLogger:
    """Get a logger bound with module name."""
    return structlog.get_logger(module=module)


# Default setup (JSON in production, console in dev)
setup_logging(json_output=True)
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_logging_setup.py -v`
Expected: 3 passed

**Step 5: Commit**

```bash
git add src/logging.py tests/test_logging_setup.py
git commit -m "feat: add structlog-based structured logging"
```

---

### Task 3: Test database connection.py — upsert and get_connection

**Files:**
- Modify: `src/database/connection.py` (replace bare `except Exception: pass`)
- Test: `tests/test_database_connection.py`

**Context:** `src/database/connection.py` has functions `get_connection()`, `insert_validated()`, `batch_insert_validated()`, and `validate_and_create()`. The existing `tests/test_core.py` covers `insert_validated` lightly. We need deeper coverage.

**Step 1: Write the failing tests**

```python
# tests/test_database_connection.py
"""Database connection module tests (P0)."""
import sqlite3
from pathlib import Path
from unittest.mock import patch

import pytest
from pydantic import BaseModel

from src.database.connection import (
    get_connection,
    insert_validated,
    batch_insert_validated,
    validate_and_create,
)


class StockRecord(BaseModel):
    ts_code: str
    trade_date: str
    close: float
    vol: float


@pytest.fixture
def mem_db():
    """In-memory SQLite database with test table."""
    conn = sqlite3.connect(":memory:")
    conn.execute(
        """
        CREATE TABLE ts_daily (
            ts_code TEXT NOT NULL,
            trade_date TEXT NOT NULL,
            close REAL,
            vol REAL,
            UNIQUE(ts_code, trade_date)
        )
        """
    )
    yield conn
    conn.close()


class TestInsertValidated:
    def test_insert_new_record(self, mem_db):
        record = StockRecord(ts_code="000001.SZ", trade_date="20260301", close=10.5, vol=1000.0)
        result = insert_validated(mem_db, "ts_daily", record, ["ts_code", "trade_date"])
        assert result is True
        row = mem_db.execute("SELECT close FROM ts_daily WHERE ts_code='000001.SZ'").fetchone()
        assert row[0] == 10.5

    def test_upsert_updates_existing(self, mem_db):
        r1 = StockRecord(ts_code="000001.SZ", trade_date="20260301", close=10.0, vol=800.0)
        r2 = StockRecord(ts_code="000001.SZ", trade_date="20260301", close=11.0, vol=900.0)
        insert_validated(mem_db, "ts_daily", r1, ["ts_code", "trade_date"])
        insert_validated(mem_db, "ts_daily", r2, ["ts_code", "trade_date"])
        mem_db.commit()
        row = mem_db.execute("SELECT close, vol FROM ts_daily").fetchone()
        assert row[0] == 11.0
        assert row[1] == 900.0

    def test_insert_without_unique_keys(self, mem_db):
        mem_db.execute("CREATE TABLE simple (name TEXT, value REAL)")
        record = StockRecord(ts_code="test", trade_date="20260301", close=1.0, vol=1.0)
        # When no unique_keys, uses INSERT OR REPLACE
        result = insert_validated(mem_db, "simple", record, [])
        assert result is True


class TestBatchInsertValidated:
    def test_batch_insert_multiple(self, mem_db):
        records = [
            StockRecord(ts_code="000001.SZ", trade_date=f"2026030{i}", close=10.0 + i, vol=100.0)
            for i in range(1, 6)
        ]
        count = batch_insert_validated(mem_db, "ts_daily", records, ["ts_code", "trade_date"])
        assert count == 5
        total = mem_db.execute("SELECT COUNT(*) FROM ts_daily").fetchone()[0]
        assert total == 5

    def test_batch_insert_with_duplicates(self, mem_db):
        records = [
            StockRecord(ts_code="000001.SZ", trade_date="20260301", close=10.0, vol=100.0),
            StockRecord(ts_code="000001.SZ", trade_date="20260301", close=11.0, vol=200.0),
        ]
        count = batch_insert_validated(mem_db, "ts_daily", records, ["ts_code", "trade_date"])
        assert count == 2  # both succeed (second is upsert)
        row = mem_db.execute("SELECT close FROM ts_daily").fetchone()
        assert row[0] == 11.0


class TestValidateAndCreate:
    def test_valid_data(self):
        data = {"ts_code": "000001.SZ", "trade_date": "20260301", "close": 10.5, "vol": 1000.0}
        result = validate_and_create(StockRecord, data)
        assert result is not None
        assert result.ts_code == "000001.SZ"

    def test_invalid_data_returns_none(self):
        data = {"ts_code": "000001.SZ"}  # missing required fields
        result = validate_and_create(StockRecord, data)
        assert result is None

    def test_invalid_data_strict_raises(self):
        data = {"ts_code": "000001.SZ"}
        with pytest.raises(Exception):
            validate_and_create(StockRecord, data, strict=True)


class TestGetConnection:
    def test_returns_connection_with_row_factory(self, tmp_path):
        db_path = tmp_path / "test.db"
        with patch("src.database.connection.STOCKS_DB_PATH", str(db_path)):
            conn = get_connection()
            assert conn.row_factory == sqlite3.Row
            conn.close()
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_database_connection.py -v`
Expected: Some tests may pass, some may fail depending on import paths. The key is validating the test structure works.

**Step 3: Fix any import issues if needed**

If `get_connection` uses a hardcoded path, the `tmp_path` mock ensures we don't touch the real database. No production code changes needed for this task unless tests reveal an actual bug.

**Step 4: Run test to verify all pass**

Run: `pytest tests/test_database_connection.py -v`
Expected: All 8 tests passed

**Step 5: Commit**

```bash
git add tests/test_database_connection.py
git commit -m "test: add P0 tests for database connection module"
```

---

### Task 4: Test Tushare client — rate limiting and retry

**Files:**
- Test: `tests/test_tushare_client.py`

**Context:** `src/data_ingestion/tushare/client.py` has `TushareAdapter` with `@rate_limit()` and `@retry_with_backoff()` decorators. We test the decorator behavior without calling real Tushare API.

**Step 1: Write the failing tests**

```python
# tests/test_tushare_client.py
"""Tushare client tests (P0) — tests decorators and adapter patterns without real API calls."""
import time
from unittest.mock import MagicMock, patch

import pytest

from src.utils.rate_limiter import TokenBucket, rate_limit


class TestRateLimitDecorator:
    def test_rate_limit_allows_burst(self):
        bucket = TokenBucket(rate=100.0, capacity=10)
        call_count = 0

        @rate_limit(bucket=bucket)
        def fast_call():
            nonlocal call_count
            call_count += 1
            return call_count

        # Should allow burst of 10 without blocking
        start = time.monotonic()
        for _ in range(10):
            fast_call()
        elapsed = time.monotonic() - start
        assert call_count == 10
        assert elapsed < 1.0  # burst should be fast

    def test_rate_limit_throttles_beyond_capacity(self):
        bucket = TokenBucket(rate=10.0, capacity=2)
        call_count = 0

        @rate_limit(bucket=bucket)
        def throttled_call():
            nonlocal call_count
            call_count += 1

        start = time.monotonic()
        for _ in range(4):
            throttled_call()
        elapsed = time.monotonic() - start
        assert call_count == 4
        assert elapsed >= 0.1  # must wait for token refill


class TestRetryWithBackoff:
    def test_retry_succeeds_after_failures(self):
        from src.utils.retry import retry

        attempts = 0

        @retry(max_attempts=3, delay=0.01)
        def flaky():
            nonlocal attempts
            attempts += 1
            if attempts < 3:
                raise ConnectionError("timeout")
            return "success"

        assert flaky() == "success"
        assert attempts == 3

    def test_retry_exhausts_attempts(self):
        from src.utils.retry import retry

        @retry(max_attempts=2, delay=0.01)
        def always_fail():
            raise ValueError("permanent")

        with pytest.raises(ValueError, match="permanent"):
            always_fail()


class TestTushareAdapterInit:
    @patch.dict("os.environ", {"TUSHARE_TOKEN": "test_token_123"})
    @patch("src.data_ingestion.tushare.client.ts")
    def test_adapter_reads_token_from_env(self, mock_ts):
        mock_ts.pro_api.return_value = MagicMock()
        from src.data_ingestion.tushare.client import TushareAdapter

        adapter = TushareAdapter(token="test_token_123")
        assert adapter.token == "test_token_123"
        mock_ts.set_token.assert_called_with("test_token_123")
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_tushare_client.py -v`
Expected: Some may fail if `tushare` is not installed or import paths differ. Adjust imports as needed.

**Step 3: Fix import issues if any**

The TushareAdapter test mocks the `tushare` import so it doesn't need a real token. If the import structure in `client.py` differs, adjust the mock path.

**Step 4: Run test to verify all pass**

Run: `pytest tests/test_tushare_client.py -v`
Expected: 5 passed

**Step 5: Commit**

```bash
git add tests/test_tushare_client.py
git commit -m "test: add P0 tests for Tushare client rate limiting and retry"
```

---

### Task 5: Test API endpoints (P0 — webhook, news, health)

**Files:**
- Test: `tests/test_api_endpoints.py`

**Context:** `api/main.py` is a FastAPI app. We use `httpx.AsyncClient` with `app` to test endpoints without a running server. The app uses `data/news.db` (SQLite). We need to mock or use a temp DB.

**Step 1: Write the failing tests**

```python
# tests/test_api_endpoints.py
"""API endpoint tests (P0)."""
import sqlite3
from pathlib import Path
from unittest.mock import patch

import pytest
from httpx import AsyncClient, ASGITransport

# Patch DB_PATH before importing the app
_test_db_path = None


@pytest.fixture(autouse=True)
def setup_test_db(tmp_path):
    """Create a temporary database for API tests."""
    global _test_db_path
    _test_db_path = tmp_path / "test_news.db"
    conn = sqlite3.connect(_test_db_path)
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS news (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            content TEXT NOT NULL,
            content_html TEXT DEFAULT '',
            cleaned_data TEXT,
            hotspots TEXT,
            keywords TEXT,
            received_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS analysis_results (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT NOT NULL,
            news_count INTEGER DEFAULT 0,
            analysis_summary TEXT,
            opportunities TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS rss_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source TEXT,
            title TEXT,
            link TEXT UNIQUE,
            summary TEXT,
            published TEXT,
            sentiment_score REAL,
            sentiment_label TEXT,
            fetched_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    conn.commit()
    conn.close()


@pytest.fixture
async def client(setup_test_db):
    """Async test client with patched DB path."""
    with patch("api.main.DB_PATH", _test_db_path):
        from api.main import app
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as c:
            yield c


@pytest.mark.asyncio
async def test_health_check(client):
    resp = await client.get("/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "running"
    assert "version" in data


@pytest.mark.asyncio
async def test_get_news_empty(client):
    resp = await client.get("/api/news")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 0
    assert data["data"] == []


@pytest.mark.asyncio
async def test_webhook_receive(client):
    payload = {"title": "Test News", "content": "Some content about AI"}
    resp = await client.post("/webhook/receive", json=payload)
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "success"
    assert "news_id" in data


@pytest.mark.asyncio
async def test_webhook_then_get_news(client):
    # Insert via webhook
    await client.post("/webhook/receive", json={"title": "Breaking", "content": "Market surge"})
    # Retrieve
    resp = await client.get("/api/news")
    data = resp.json()
    assert data["total"] >= 1
    assert any("Breaking" in item["title"] for item in data["data"])


@pytest.mark.asyncio
async def test_clean_endpoint(client):
    resp = await client.post("/api/clean", json={"title": "Test", "content": "**Bold** text with [link](http://example.com)"})
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_homepage_returns_html(client):
    resp = await client.get("/")
    assert resp.status_code == 200
    assert "text/html" in resp.headers.get("content-type", "")
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_api_endpoints.py -v`
Expected: May fail on imports or DB patching. Key is to identify the right patch target.

**Step 3: Fix import/patch issues**

The `api/main.py` calls `init_db()` at import time. We need to ensure our patch happens before the import or that `init_db()` is deferred. If `init_db()` runs at module load, we may need to restructure the test to patch earlier, or modify `api/main.py` to use a `@app.on_event("startup")` pattern.

If `init_db()` is called at module level in `api/main.py`, add this small change:

In `api/main.py`, change the `init_db()` call to a startup event:
```python
@app.on_event("startup")
def startup():
    init_db()
```

**Step 4: Run test to verify all pass**

Run: `pytest tests/test_api_endpoints.py -v`
Expected: 6 passed

**Step 5: Commit**

```bash
git add tests/test_api_endpoints.py
# If api/main.py was modified:
git add api/main.py
git commit -m "test: add P0 API endpoint tests with temp DB fixture"
```

---

### Task 6: Test analysis modules (P1 — cleaner, sentiment, anomaly)

**Files:**
- Test: `tests/test_analysis.py`

**Context:** `src/analysis/cleaner.py` has `remove_noise()`, `clean_raw_data()`, `extract_keywords()`, `identify_hotspots()`. `src/analysis/anomaly.py` detects volume surges and MA crosses. `src/analysis/sentiment.py` calculates market sentiment scores.

**Step 1: Write the failing tests**

```python
# tests/test_analysis.py
"""Analysis module tests (P1)."""
import sqlite3
import pytest

from src.analysis.cleaner import (
    remove_noise,
    clean_raw_data,
    extract_keywords,
    identify_hotspots,
    extract_time,
    extract_location,
)


class TestRemoveNoise:
    def test_removes_markdown_bold(self):
        assert "重要" in remove_noise("**重要**消息")
        assert "**" not in remove_noise("**重要**消息")

    def test_removes_html_tags(self):
        result = remove_noise("<p>Hello</p>")
        assert "<p>" not in result
        assert "Hello" in result

    def test_preserves_link_text(self):
        result = remove_noise("[公告](https://example.com)")
        assert "公告" in result
        assert "http" not in result

    def test_collapses_whitespace(self):
        result = remove_noise("hello   \n\n\n   world")
        assert "\n\n\n" not in result


class TestExtractTime:
    def test_extracts_date(self):
        result = extract_time("发布于 2026-03-01 的公告")
        assert result is not None
        assert "2026" in result

    def test_extracts_chinese_date(self):
        result = extract_time("3月1日消息")
        assert result is not None

    def test_returns_none_for_no_date(self):
        result = extract_time("没有日期的文本")
        assert result is None


class TestExtractLocation:
    def test_extracts_chinese_city(self):
        result = extract_location("北京时间今日")
        assert result is not None
        assert "北京" in result

    def test_returns_none_for_no_location(self):
        result = extract_location("一段普通的文本")
        assert result is None


class TestIdentifyHotspots:
    def test_identifies_ai_hotspot(self):
        hotspots = identify_hotspots("ChatGPT 发布了新版本，AI 技术再次突破")
        assert len(hotspots) > 0
        assert any("AI" in h or "ChatGPT" in h for h in hotspots)

    def test_identifies_finance_hotspot(self):
        hotspots = identify_hotspots("股市暴跌，比特币价格大幅波动")
        assert len(hotspots) > 0


class TestExtractKeywords:
    def test_extracts_meaningful_words(self):
        keywords = extract_keywords("人工智能技术在金融领域的应用越来越广泛")
        assert len(keywords) > 0
        # Should not contain stopwords
        assert "的" not in keywords
        assert "在" not in keywords

    def test_returns_empty_for_empty_text(self):
        keywords = extract_keywords("")
        assert keywords == []


class TestCleanRawData:
    def test_returns_cleaned_data_structure(self):
        result = clean_raw_data("AI突破", "1. **ChatGPT** 发布新版本\n2. 股市大涨")
        assert result.title == "AI突破"
        assert len(result.summary) > 0
        assert isinstance(result.facts, list)
        assert isinstance(result.hotspots, list)
        assert isinstance(result.keywords, list)
        assert result.cleaned_at is not None
```

**Step 2: Run test to verify they fail**

Run: `pytest tests/test_analysis.py -v`
Expected: Import errors or assertion failures reveal exact API differences.

**Step 3: Fix any import path issues**

The `cleaner.py` module should be importable as `src.analysis.cleaner`. If tests fail due to function signatures differing from what's documented, adjust test expectations.

**Step 4: Run test to verify all pass**

Run: `pytest tests/test_analysis.py -v`
Expected: All tests passed

**Step 5: Commit**

```bash
git add tests/test_analysis.py
git commit -m "test: add P1 tests for analysis modules (cleaner, hotspots, keywords)"
```

---

### Task 7: Replace bare except Exception with specific exceptions

**Files:**
- Modify: `src/database/connection.py` (replace `except Exception: pass` in `_ensure_compat_views`)
- Modify: `api/main.py` (replace generic `except Exception as e` with specific types)

**Context:** Grep found multiple bare `except Exception: pass` blocks. We replace them with specific exceptions from our new hierarchy, or at minimum log them.

**Step 1: Write the failing test**

```python
# tests/test_error_handling.py
"""Verify that bare 'except Exception: pass' patterns are eliminated."""
import ast
import os
from pathlib import Path

import pytest

# Files that should NOT have bare except Exception: pass
CHECKED_FILES = [
    "src/database/connection.py",
    "src/analysis/cleaner.py",
    "src/analysis/sentiment.py",
    "src/analysis/anomaly.py",
    "src/ai_engine/llm_analyzer.py",
]

PROJECT_ROOT = Path(__file__).parent.parent


def _find_bare_except_pass(filepath: Path) -> list[int]:
    """Find line numbers where 'except Exception: pass' or 'except: pass' occurs."""
    bare_lines = []
    try:
        source = filepath.read_text()
    except FileNotFoundError:
        return []

    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, ast.ExceptHandler):
            # Check if body is just 'pass'
            if (
                len(node.body) == 1
                and isinstance(node.body[0], ast.Pass)
                and node.type is not None
                and isinstance(node.type, ast.Name)
                and node.type.id == "Exception"
            ):
                bare_lines.append(node.lineno)
    return bare_lines


@pytest.mark.parametrize("filepath", CHECKED_FILES)
def test_no_bare_except_exception_pass(filepath):
    full_path = PROJECT_ROOT / filepath
    bare_lines = _find_bare_except_pass(full_path)
    assert bare_lines == [], (
        f"{filepath} has bare 'except Exception: pass' at lines: {bare_lines}. "
        "Replace with specific exception types or add logging."
    )
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_error_handling.py -v`
Expected: FAIL for files that have bare `except Exception: pass`

**Step 3: Fix the violations**

In `src/database/connection.py`, find each `except Exception: pass` and replace:

```python
# Before:
try:
    _create_or_replace_view(conn, "ts_weekly", "SELECT ...")
except Exception:
    pass

# After:
try:
    _create_or_replace_view(conn, "ts_weekly", "SELECT ...")
except (sqlite3.OperationalError, sqlite3.DatabaseError):
    pass  # View creation is best-effort for backwards compatibility
```

Repeat for each instance. The key principle: use the most specific exception type that makes sense.

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_error_handling.py -v`
Expected: All parametrized tests pass

**Step 5: Commit**

```bash
git add src/database/connection.py tests/test_error_handling.py
# Add any other modified files
git commit -m "fix: replace bare except Exception:pass with specific exception types"
```

---

### Task 8: Add API exception middleware

**Files:**
- Create: `api/middleware.py`
- Modify: `api/main.py` (register middleware)
- Test: `tests/test_api_middleware.py`

**Step 1: Write the failing test**

```python
# tests/test_api_middleware.py
"""API exception middleware tests."""
import pytest
from unittest.mock import patch
from httpx import AsyncClient, ASGITransport
from fastapi import FastAPI

from api.middleware import register_exception_handlers
from src.exceptions import AppError, DataFetchError, DatabaseError


@pytest.fixture
def test_app():
    """Create a minimal FastAPI app with exception handlers."""
    app = FastAPI()
    register_exception_handlers(app)

    @app.get("/trigger-app-error")
    async def trigger_app():
        raise AppError("general app error")

    @app.get("/trigger-data-error")
    async def trigger_data():
        raise DataFetchError("tushare down", source="tushare", code="000001.SZ")

    @app.get("/trigger-db-error")
    async def trigger_db():
        raise DatabaseError("insert failed", table="ts_daily")

    @app.get("/trigger-unexpected")
    async def trigger_unexpected():
        raise RuntimeError("unexpected crash")

    return app


@pytest.mark.asyncio
async def test_app_error_returns_400(test_app):
    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        resp = await c.get("/trigger-app-error")
        assert resp.status_code == 400
        data = resp.json()
        assert "error" in data
        assert data["error"] == "general app error"


@pytest.mark.asyncio
async def test_data_fetch_error_returns_502(test_app):
    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        resp = await c.get("/trigger-data-error")
        assert resp.status_code == 502
        data = resp.json()
        assert data["source"] == "tushare"


@pytest.mark.asyncio
async def test_database_error_returns_503(test_app):
    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        resp = await c.get("/trigger-db-error")
        assert resp.status_code == 503
        data = resp.json()
        assert data["table"] == "ts_daily"


@pytest.mark.asyncio
async def test_unexpected_error_returns_500(test_app):
    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        resp = await c.get("/trigger-unexpected")
        assert resp.status_code == 500
        data = resp.json()
        assert "error" in data
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_api_middleware.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'api.middleware'`

**Step 3: Write minimal implementation**

```python
# api/middleware.py
"""Unified exception handling middleware for FastAPI."""
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from src.exceptions import AppError, DataFetchError, AnalysisError, DatabaseError
from src.logging import get_logger

logger = get_logger("api.middleware")


def register_exception_handlers(app: FastAPI) -> None:
    """Register exception handlers on the FastAPI app."""

    @app.exception_handler(DataFetchError)
    async def data_fetch_handler(request: Request, exc: DataFetchError):
        logger.error("data_fetch_error", error=str(exc), source=exc.source, code=exc.code)
        return JSONResponse(
            status_code=502,
            content={"error": str(exc), "type": "DataFetchError", "source": exc.source, "code": exc.code},
        )

    @app.exception_handler(DatabaseError)
    async def database_handler(request: Request, exc: DatabaseError):
        logger.error("database_error", error=str(exc), table=exc.table)
        return JSONResponse(
            status_code=503,
            content={"error": str(exc), "type": "DatabaseError", "table": exc.table},
        )

    @app.exception_handler(AnalysisError)
    async def analysis_handler(request: Request, exc: AnalysisError):
        logger.error("analysis_error", error=str(exc), module=exc.module)
        return JSONResponse(
            status_code=500,
            content={"error": str(exc), "type": "AnalysisError", "module": exc.module},
        )

    @app.exception_handler(AppError)
    async def app_error_handler(request: Request, exc: AppError):
        logger.error("app_error", error=str(exc))
        return JSONResponse(
            status_code=400,
            content={"error": str(exc), "type": "AppError"},
        )

    @app.exception_handler(Exception)
    async def catch_all_handler(request: Request, exc: Exception):
        logger.error("unexpected_error", error=str(exc), type=type(exc).__name__)
        return JSONResponse(
            status_code=500,
            content={"error": "Internal server error", "type": type(exc).__name__},
        )
```

Then register in `api/main.py` — add after `app = FastAPI(...)`:

```python
from api.middleware import register_exception_handlers
register_exception_handlers(app)
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_api_middleware.py -v`
Expected: 4 passed

**Step 5: Commit**

```bash
git add api/middleware.py api/main.py tests/test_api_middleware.py
git commit -m "feat: add unified API exception handling middleware"
```

---

### Task 9: Add GitHub Actions CI workflow

**Files:**
- Create: `.github/workflows/ci.yml`

**Step 1: Write the CI workflow**

```yaml
# .github/workflows/ci.yml
name: CI

on:
  push:
    branches: [main]
  pull_request:
    branches: [main]

jobs:
  lint:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.11"
      - run: pip install ruff
      - run: ruff check .
      - run: ruff format --check .

  test:
    runs-on: ubuntu-latest
    needs: lint
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.11"
          cache: pip
      - run: pip install -r requirements.txt
      - run: pip install pytest pytest-asyncio pytest-cov httpx structlog
      - name: Run tests with coverage
        run: pytest --cov=src --cov=api --cov-report=term-missing -v
        env:
          TUSHARE_TOKEN: "fake_token_for_ci"
          OPENAI_API_KEY: "fake_key_for_ci"
```

**Step 2: Verify the file is valid YAML**

Run: `python -c "import yaml; yaml.safe_load(open('.github/workflows/ci.yml'))"`
(Or just verify with `cat` — YAML parsing is optional)

**Step 3: Commit**

```bash
git add .github/workflows/ci.yml
git commit -m "ci: add GitHub Actions workflow for linting and testing"
```

---

### Task 10: Add pre-commit hooks

**Files:**
- Create: `.pre-commit-config.yaml`

**Step 1: Write the config**

```yaml
# .pre-commit-config.yaml
repos:
  - repo: https://github.com/astral-sh/ruff-pre-commit
    rev: v0.9.0
    hooks:
      - id: ruff
        args: [--fix]
      - id: ruff-format
```

**Step 2: Install and test**

Run:
```bash
pip install pre-commit
pre-commit install
pre-commit run --all-files
```

Expected: ruff may find issues to fix. Fix any blocking issues.

**Step 3: Commit**

```bash
git add .pre-commit-config.yaml
git commit -m "ci: add pre-commit hooks with ruff linter and formatter"
```

---

### Task 11: Add Pydantic response models to API endpoints

**Files:**
- Create: `api/schemas.py`
- Modify: `api/main.py` (add `response_model` to key endpoints)
- Test: `tests/test_api_schemas.py`

**Step 1: Write the failing test**

```python
# tests/test_api_schemas.py
"""API response schema tests."""
import pytest
from api.schemas import (
    HealthResponse,
    NewsListResponse,
    NewsItem,
    WebhookResponse,
    ErrorResponse,
)


def test_health_response_fields():
    resp = HealthResponse(status="running", db="connected", scheduler="active", version="2.0.0")
    assert resp.status == "running"
    assert resp.version == "2.0.0"


def test_news_list_response():
    item = NewsItem(
        id=1,
        title="Test",
        content="Content",
        content_html="<p>Content</p>",
        received_at="2026-03-01T00:00:00",
    )
    resp = NewsListResponse(total=1, data=[item])
    assert resp.total == 1
    assert len(resp.data) == 1


def test_webhook_response():
    resp = WebhookResponse(status="success", message="saved", news_id=42)
    assert resp.news_id == 42


def test_error_response():
    resp = ErrorResponse(error="not found", type="NotFoundError")
    assert resp.error == "not found"
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_api_schemas.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'api.schemas'`

**Step 3: Write minimal implementation**

```python
# api/schemas.py
"""Pydantic response models for API documentation."""
from typing import Optional
from pydantic import BaseModel


class HealthResponse(BaseModel):
    status: str
    db: str
    scheduler: str
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


class SentimentStatsResponse(BaseModel):
    total: int
    data: list[dict]


class AnomalyListResponse(BaseModel):
    total: int
    data: list[dict]
```

Then update key endpoints in `api/main.py`:

```python
from api.schemas import HealthResponse, NewsListResponse, WebhookResponse

@app.get("/health", response_model=HealthResponse)
async def health_check():
    ...

@app.get("/api/news", response_model=NewsListResponse)
async def get_news(...):
    ...

@app.post("/webhook/receive", response_model=WebhookResponse)
async def receive_webhook(...):
    ...
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_api_schemas.py -v`
Expected: 4 passed

**Step 5: Commit**

```bash
git add api/schemas.py api/main.py tests/test_api_schemas.py
git commit -m "feat: add Pydantic response models for API documentation"
```

---

### Task 12: Run full test suite and measure coverage

**Files:** None (verification only)

**Step 1: Run all tests with coverage**

```bash
pytest --cov=src --cov=api --cov-report=term-missing -v
```

**Step 2: Verify P0 coverage targets**

Check output for:
- `src/database/connection.py` — target >= 80%
- `src/data_ingestion/tushare/client.py` — target >= 80% (decorator coverage)
- `api/main.py` — target >= 60% (key endpoints tested)

**Step 3: Verify P1 coverage**

- `src/analysis/cleaner.py` — target >= 60%
- `utils/rate_limiter.py` — target >= 60%
- `utils/retry.py` — target >= 60%

**Step 4: Fix any failing tests**

If any test fails, fix it before proceeding.

**Step 5: Commit if any fixes were needed**

```bash
git add -u
git commit -m "fix: resolve test failures from full suite run"
```

---

### Task 13: Final verification — ruff + pytest green

**Step 1: Run ruff linter**

```bash
ruff check src/ api/ tests/
```

Fix any issues found.

**Step 2: Run ruff formatter**

```bash
ruff format --check src/ api/ tests/
```

Fix any formatting issues.

**Step 3: Run full test suite**

```bash
pytest --cov=src --cov=api -v
```

Verify all tests pass.

**Step 4: Final commit**

```bash
git add -u
git commit -m "chore: phase 1 complete — all tests pass, lint clean"
```

---

## Phase 1 DoD Checklist

After completing all 13 tasks, verify:

- [ ] `src/exceptions.py` — exception hierarchy defined
- [ ] `src/logging.py` — structlog integration working
- [ ] `api/middleware.py` — unified exception handling
- [ ] `api/schemas.py` — Pydantic response models
- [ ] `.github/workflows/ci.yml` — CI pipeline
- [ ] `.pre-commit-config.yaml` — linting hooks
- [ ] P0 module coverage >= 80%
- [ ] P1 module coverage >= 60%
- [ ] `pytest` all green
- [ ] `ruff check` clean
- [ ] All bare `except Exception: pass` eliminated from checked files
