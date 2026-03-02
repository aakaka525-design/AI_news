# Phase 2: PostgreSQL Migration Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Migrate from SQLite to PostgreSQL while maintaining backwards compatibility, with a verified switch gate before cutover.

**Architecture:** Create a database abstraction layer (Repository pattern) that works with both SQLite and PostgreSQL. Use Alembic for schema management. Implement a switch gate with automated verification before cutover.

**Tech Stack:** PostgreSQL 15, SQLAlchemy 2.0 (unified), Alembic, asyncpg, psycopg2-binary

---

## Prerequisites

```bash
pip install psycopg2-binary alembic asyncpg
```

Docker Compose will provide PostgreSQL 15 for local development.

---

### Task 1: Add PostgreSQL to Docker Compose + DATABASE_URL config

**Files:**
- Modify: `docker-compose.yml`
- Modify: `config/settings.py`
- Test: `tests/test_config.py`

**Step 1: Write the failing test**

```python
# tests/test_config.py
"""Configuration tests."""
from unittest.mock import patch

def test_database_url_defaults_to_sqlite():
    with patch.dict("os.environ", {}, clear=True):
        from importlib import reload
        import config.settings as s
        reload(s)
        assert "sqlite" in s.DATABASE_URL or s.DATABASE_URL == ""

def test_database_url_reads_from_env():
    with patch.dict("os.environ", {"DATABASE_URL": "postgresql://user:pass@localhost:5432/ainews"}):
        from importlib import reload
        import config.settings as s
        reload(s)
        assert s.DATABASE_URL == "postgresql://user:pass@localhost:5432/ainews"
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_config.py -v`

**Step 3: Implement**

Add to `config/settings.py`:
```python
# Database configuration
DATABASE_URL = os.getenv(
    "DATABASE_URL",
    f"sqlite:///{STOCKS_DB_PATH}"
)
NEWS_DATABASE_URL = os.getenv(
    "NEWS_DATABASE_URL",
    f"sqlite:///{DATA_DIR / 'news.db'}"
)
```

Add PostgreSQL service to `docker-compose.yml`:
```yaml
  postgres:
    image: postgres:15
    ports:
      - "5432:5432"
    environment:
      POSTGRES_DB: ainews
      POSTGRES_USER: ainews
      POSTGRES_PASSWORD: ainews_dev
    volumes:
      - pgdata:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U ainews"]
      interval: 5s
      timeout: 5s
      retries: 5

volumes:
  pgdata:
```

**Step 4: Run tests, commit**

```bash
git commit -m "feat: add PostgreSQL to Docker Compose and DATABASE_URL config"
```

---

### Task 2: Create database engine factory

**Files:**
- Create: `src/database/engine.py`
- Test: `tests/test_database_engine.py`

**Step 1: Write the failing test**

```python
# tests/test_database_engine.py
"""Database engine factory tests."""
import pytest
from unittest.mock import patch
from src.database.engine import get_engine, get_session, is_postgresql


def test_get_engine_sqlite(tmp_path):
    url = f"sqlite:///{tmp_path / 'test.db'}"
    engine = get_engine(url)
    assert engine is not None
    assert "sqlite" in str(engine.url)


def test_get_engine_caches():
    url = "sqlite:///:memory:"
    e1 = get_engine(url)
    e2 = get_engine(url)
    assert e1 is e2


def test_is_postgresql_false_for_sqlite():
    with patch("src.database.engine._current_url", "sqlite:///test.db"):
        assert is_postgresql() is False


def test_is_postgresql_true_for_pg():
    with patch("src.database.engine._current_url", "postgresql://localhost/ainews"):
        assert is_postgresql() is True


def test_get_session_returns_session(tmp_path):
    url = f"sqlite:///{tmp_path / 'test.db'}"
    get_engine(url)
    with get_session() as session:
        assert session is not None
```

**Step 2: Implement**

```python
# src/database/engine.py
"""
Database engine factory — supports SQLite and PostgreSQL.

Usage:
    from src.database.engine import get_engine, get_session, is_postgresql
"""
from contextlib import contextmanager

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

_engines: dict[str, object] = {}
_current_url: str = ""
_SessionLocal = None


def get_engine(database_url: str = None):
    """Get or create a SQLAlchemy engine."""
    global _current_url, _SessionLocal

    if database_url is None:
        from config.settings import DATABASE_URL
        database_url = DATABASE_URL

    if database_url in _engines:
        return _engines[database_url]

    kwargs = {}
    if database_url.startswith("sqlite"):
        kwargs["connect_args"] = {"check_same_thread": False, "timeout": 30}
    else:
        kwargs["pool_size"] = 10
        kwargs["max_overflow"] = 20
        kwargs["pool_pre_ping"] = True

    engine = create_engine(database_url, **kwargs)
    _engines[database_url] = engine
    _current_url = database_url
    _SessionLocal = sessionmaker(bind=engine)
    return engine


def is_postgresql() -> bool:
    """Check if current database is PostgreSQL."""
    return _current_url.startswith("postgresql")


@contextmanager
def get_session():
    """Get a database session (context manager)."""
    if _SessionLocal is None:
        get_engine()
    session = _SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
```

**Step 3: Run tests, commit**

```bash
git commit -m "feat: add database engine factory with SQLite/PostgreSQL support"
```

---

### Task 3: Create news repository (extract SQL from api/main.py)

**Files:**
- Create: `src/database/repositories/news.py`
- Test: `tests/test_news_repository.py`

**Step 1: Write the failing test**

```python
# tests/test_news_repository.py
"""News repository tests."""
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.database.repositories.news import NewsRepository


@pytest.fixture
def repo(tmp_path):
    url = f"sqlite:///{tmp_path / 'test.db'}"
    engine = create_engine(url)
    # Create tables
    from src.database.repositories.news import Base
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    return NewsRepository(Session)


class TestNewsRepository:
    def test_insert_news(self, repo):
        news_id = repo.insert_news("Title", "Content", "<p>Content</p>")
        assert news_id > 0

    def test_get_news_list(self, repo):
        repo.insert_news("A", "Content A", "<p>A</p>")
        repo.insert_news("B", "Content B", "<p>B</p>")
        total, items = repo.get_news_list(limit=10)
        assert total == 2
        assert len(items) == 2

    def test_get_news_list_with_limit(self, repo):
        for i in range(5):
            repo.insert_news(f"Title {i}", f"Content {i}", f"<p>{i}</p>")
        total, items = repo.get_news_list(limit=3)
        assert total == 5
        assert len(items) == 3

    def test_update_cleaned_data(self, repo):
        news_id = repo.insert_news("T", "C", "<p>C</p>")
        repo.update_cleaned_data(news_id, {"summary": "test"}, ["AI"], ["tech"])
        item = repo.get_news_by_id(news_id)
        assert item is not None

    def test_get_hotspots(self, repo):
        repo.insert_news("T", "C", "<p>C</p>", hotspots="AI,股市")
        hotspots = repo.get_hotspot_stats()
        assert len(hotspots) > 0

    def test_insert_analysis(self, repo):
        aid = repo.insert_analysis("2026-03-02", 5, "summary", '{"opportunities": []}')
        assert aid > 0

    def test_get_analysis(self, repo):
        aid = repo.insert_analysis("2026-03-02", 5, "summary", '{}')
        result = repo.get_analysis_by_id(aid)
        assert result is not None
        assert result["date"] == "2026-03-02"
```

**Step 2: Implement**

Extract all news-related SQL from `api/main.py` into a repository class using SQLAlchemy ORM. The repository should work with both SQLite and PostgreSQL.

Key pattern:
- Define SQLAlchemy models (News, AnalysisResult) in the repository module
- Use `Session` for all database operations
- No raw SQL — use SQLAlchemy query API
- `insert_news()`, `get_news_list()`, `update_cleaned_data()`, `get_hotspot_stats()`, `insert_analysis()`, `get_analysis_by_id()`

**Step 3: Run tests, commit**

```bash
git commit -m "feat: create news repository with SQLAlchemy ORM"
```

---

### Task 4: Wire news repository into api/main.py

**Files:**
- Modify: `api/main.py` (replace raw SQL with repository calls)
- Test: Run existing `tests/test_api_endpoints.py` — all must still pass

**Step 1: Replace database operations in api/main.py**

Read `api/main.py` carefully. For each `sqlite3.connect(DB_PATH)` + raw SQL block, replace with the corresponding `NewsRepository` method call.

Key changes:
- Remove `import sqlite3` from api/main.py
- Replace `init_db()` with SQLAlchemy table creation
- Replace all `conn = sqlite3.connect(DB_PATH)` with repository calls
- Keep the same API response format

**Step 2: Run existing API tests**

Run: `pytest tests/test_api_endpoints.py -v`
All 17 existing tests must still pass.

**Step 3: Commit**

```bash
git commit -m "refactor: replace raw SQL in api/main.py with news repository"
```

---

### Task 5: Create upsert utility (database-agnostic)

**Files:**
- Create: `src/database/upsert.py`
- Test: `tests/test_upsert.py`

**Step 1: Write the failing test**

```python
# tests/test_upsert.py
"""Database-agnostic upsert tests."""
import pytest
from sqlalchemy import create_engine, Column, String, Float, MetaData, Table
from sqlalchemy.orm import sessionmaker

from src.database.upsert import upsert_row, upsert_batch


@pytest.fixture
def engine_and_table(tmp_path):
    url = f"sqlite:///{tmp_path / 'test.db'}"
    engine = create_engine(url)
    metadata = MetaData()
    table = Table("test_stocks", metadata,
        Column("ts_code", String, primary_key=True),
        Column("trade_date", String, primary_key=True),
        Column("close", Float),
    )
    metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    return engine, table, Session


def test_upsert_inserts_new(engine_and_table):
    engine, table, Session = engine_and_table
    with Session() as s:
        upsert_row(s, table, {"ts_code": "000001.SZ", "trade_date": "20260301", "close": 10.0})
        s.commit()
        row = s.execute(table.select()).fetchone()
        assert row.close == 10.0


def test_upsert_updates_existing(engine_and_table):
    engine, table, Session = engine_and_table
    with Session() as s:
        upsert_row(s, table, {"ts_code": "000001.SZ", "trade_date": "20260301", "close": 10.0})
        s.commit()
        upsert_row(s, table, {"ts_code": "000001.SZ", "trade_date": "20260301", "close": 11.0})
        s.commit()
        rows = s.execute(table.select()).fetchall()
        assert len(rows) == 1
        assert rows[0].close == 11.0


def test_upsert_batch(engine_and_table):
    engine, table, Session = engine_and_table
    data = [
        {"ts_code": "000001.SZ", "trade_date": f"2026030{i}", "close": 10.0 + i}
        for i in range(1, 6)
    ]
    with Session() as s:
        count = upsert_batch(s, table, data)
        s.commit()
        assert count == 5
```

**Step 2: Implement**

```python
# src/database/upsert.py
"""Database-agnostic upsert utilities using SQLAlchemy dialect."""
from sqlalchemy import inspect
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.dialects.postgresql import insert as pg_insert


def upsert_row(session, table, data: dict) -> bool:
    """Upsert a single row. Works with SQLite and PostgreSQL."""
    dialect = session.bind.dialect.name

    if dialect == "postgresql":
        stmt = pg_insert(table).values(**data)
        pk_cols = [c.name for c in table.primary_key.columns]
        update_cols = {k: v for k, v in data.items() if k not in pk_cols}
        if update_cols:
            stmt = stmt.on_conflict_do_update(
                index_elements=pk_cols,
                set_=update_cols,
            )
        else:
            stmt = stmt.on_conflict_do_nothing()
    else:  # sqlite
        stmt = sqlite_insert(table).values(**data)
        pk_cols = [c.name for c in table.primary_key.columns]
        update_cols = {k: v for k, v in data.items() if k not in pk_cols}
        if update_cols:
            stmt = stmt.on_conflict_do_update(
                index_elements=pk_cols,
                set_=update_cols,
            )
        else:
            stmt = stmt.on_conflict_do_nothing()

    session.execute(stmt)
    return True


def upsert_batch(session, table, rows: list[dict], commit_every: int = 100) -> int:
    """Upsert multiple rows."""
    count = 0
    for i, row in enumerate(rows):
        if upsert_row(session, table, row):
            count += 1
        if (i + 1) % commit_every == 0:
            session.flush()
    return count
```

**Step 3: Run tests, commit**

```bash
git commit -m "feat: add database-agnostic upsert utility"
```

---

### Task 6: Replace SQLite-specific syntax in connection.py

**Files:**
- Modify: `src/database/connection.py`
- Test: Existing `tests/test_database_connection.py` must still pass

**Step 1: Identify and fix SQLite-specific patterns**

Read `src/database/connection.py` and replace:

1. `INSERT OR REPLACE INTO` → `INSERT ... ON CONFLICT ... DO UPDATE` (already partially done)
2. `INSERT OR IGNORE INTO` → `INSERT ... ON CONFLICT ... DO NOTHING`
3. `PRAGMA journal_mode=WAL` → conditional (only for SQLite)
4. `PRAGMA busy_timeout=30000` → conditional (only for SQLite)
5. `sqlite_master` queries → use SQLAlchemy `inspect(engine).get_table_names()`

Add a `is_sqlite()` check:
```python
def get_connection(timeout: int = 30):
    """Get connection — returns SQLite connection for backwards compatibility."""
    ...
```

IMPORTANT: Keep backwards compatibility — the old API (returning sqlite3.Connection) must still work for code that hasn't been migrated yet. Add new functions that use SQLAlchemy alongside.

**Step 2: Run existing tests**

Run: `pytest tests/test_database_connection.py -v`
All must pass.

**Step 3: Commit**

```bash
git commit -m "refactor: make connection.py work with both SQLite and PostgreSQL"
```

---

### Task 7: Replace SQLite-specific syntax in analysis modules

**Files:**
- Modify: `src/analysis/sentiment.py`
- Modify: `src/analysis/anomaly.py`
- Test: Existing `tests/test_analysis.py` must still pass

**Step 1: Fix sentiment.py**

Replace:
- `INSERT OR REPLACE INTO market_sentiment` → standard upsert
- `SELECT 1 FROM sqlite_master WHERE type='table'` → use try/except or inspect
- Hardcoded `sqlite3.connect()` → use engine factory

**Step 2: Fix anomaly.py**

Replace:
- `INSERT OR REPLACE INTO technical_anomalies` → standard upsert
- `date('now', '-7 days')` → use Python datetime for the date calculation
- `SELECT 1 FROM sqlite_master` → use inspect or try/except

**Step 3: Run tests, commit**

```bash
git commit -m "refactor: remove SQLite-specific syntax from analysis modules"
```

---

### Task 8: Set up Alembic migrations

**Files:**
- Create: `alembic.ini`
- Create: `alembic/env.py`
- Create: `alembic/versions/001_initial_schema.py`

**Step 1: Initialize Alembic**

```bash
alembic init alembic
```

**Step 2: Configure alembic/env.py**

Point to `config.settings.DATABASE_URL` and import all models from `src/database/models.py`.

**Step 3: Generate initial migration**

```bash
alembic revision --autogenerate -m "initial schema"
```

**Step 4: Test migration runs**

```bash
# Against SQLite
alembic upgrade head

# Against PostgreSQL (Docker)
DATABASE_URL=postgresql://ainews:ainews_dev@localhost:5432/ainews alembic upgrade head
```

**Step 5: Commit**

```bash
git commit -m "feat: set up Alembic migrations with initial schema"
```

---

### Task 9: Create data migration script

**Files:**
- Create: `scripts/migrate_sqlite_to_pg.py`
- Test: Manual verification

**Step 1: Write migration script**

```python
# scripts/migrate_sqlite_to_pg.py
"""Migrate data from SQLite to PostgreSQL."""
import sqlite3
from sqlalchemy import create_engine, text

def migrate(sqlite_path, pg_url, tables=None):
    """Copy all data from SQLite to PostgreSQL."""
    sqlite_conn = sqlite3.connect(sqlite_path)
    sqlite_conn.row_factory = sqlite3.Row
    pg_engine = create_engine(pg_url)

    cursor = sqlite_conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'"
    )
    all_tables = [r[0] for r in cursor.fetchall()]
    target_tables = tables or all_tables

    for table in target_tables:
        rows = sqlite_conn.execute(f"SELECT * FROM {table}").fetchall()
        if not rows:
            continue
        columns = rows[0].keys()
        # Batch insert into PostgreSQL
        ...

    return report
```

**Step 2: Commit**

```bash
git commit -m "feat: add SQLite to PostgreSQL data migration script"
```

---

### Task 10: Create switch gate verification script

**Files:**
- Create: `scripts/verify_migration.py`
- Test: `tests/test_migration_verification.py`

**Step 1: Write verification script**

Implements the 5 gate checks from the design doc:

```python
# scripts/verify_migration.py
"""Migration verification gate — all checks must pass before cutover."""

def check_row_counts(sqlite_path, pg_url) -> dict:
    """Gate 1: Row count comparison (tolerance: 0)."""

def check_sample_data(sqlite_path, pg_url, sample_size=100) -> dict:
    """Gate 2: Random sample field-by-field comparison."""

def check_api_regression(api_url) -> dict:
    """Gate 3: API endpoint regression test."""

def check_query_performance(pg_url) -> dict:
    """Gate 4: Key query latency within 120% of baseline."""

def run_all_gates(sqlite_path, pg_url, api_url=None) -> dict:
    """Run all verification gates. Returns pass/fail for each."""
```

**Step 2: Write basic test**

```python
# tests/test_migration_verification.py
def test_row_count_check_passes_for_identical_data():
    ...

def test_row_count_check_fails_for_mismatch():
    ...
```

**Step 3: Commit**

```bash
git commit -m "feat: add migration verification gate script"
```

---

### Task 11: Update Docker Compose for full stack

**Files:**
- Modify: `docker-compose.yml`
- Modify: `.env.example`

**Step 1: Update docker-compose.yml**

Ensure the API service connects to PostgreSQL:
```yaml
  api:
    build: .
    environment:
      - DATABASE_URL=postgresql://ainews:ainews_dev@postgres:5432/ainews
      - NEWS_DATABASE_URL=postgresql://ainews:ainews_dev@postgres:5432/ainews
    depends_on:
      postgres:
        condition: service_healthy
```

**Step 2: Update .env.example**

```
# Database (default: SQLite, set for PostgreSQL)
DATABASE_URL=postgresql://ainews:ainews_dev@localhost:5432/ainews
```

**Step 3: Commit**

```bash
git commit -m "feat: update Docker Compose for PostgreSQL integration"
```

---

### Task 12: Full regression test + coverage verification

**Step 1:** Run all tests with SQLite (default)
```bash
pytest -v --cov=src --cov=api
```

**Step 2:** Start PostgreSQL via Docker
```bash
docker compose up -d postgres
```

**Step 3:** Run key tests against PostgreSQL
```bash
DATABASE_URL=postgresql://ainews:ainews_dev@localhost:5432/ainews pytest tests/test_database_engine.py tests/test_upsert.py tests/test_news_repository.py -v
```

**Step 4:** Verify no regressions

**Step 5:** Commit

```bash
git commit -m "chore: phase 2 complete — PostgreSQL migration ready"
```

---

## Phase 2 DoD Checklist

- [ ] PostgreSQL service in Docker Compose with healthcheck
- [ ] DATABASE_URL configuration in settings.py and .env.example
- [ ] Database engine factory (SQLite/PostgreSQL)
- [ ] News repository (replaces raw SQL in api/main.py)
- [ ] Database-agnostic upsert utility
- [ ] SQLite-specific syntax removed from connection.py and analysis modules
- [ ] Alembic migrations initialized
- [ ] Data migration script (SQLite → PostgreSQL)
- [ ] Switch gate verification script (5 checks)
- [ ] All existing tests still pass
- [ ] New repository/upsert tests pass on SQLite
