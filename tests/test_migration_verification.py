"""Tests for migration verification gates."""

from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import create_engine, text

# ---------------------------------------------------------------------------
# Helpers: create a pair of SQLite databases that act as "sqlite" and "pg"
# ---------------------------------------------------------------------------


def _create_tables(engine):
    """Create a simple schema in the given engine."""
    with engine.connect() as conn:
        conn.execute(
            text(
                "CREATE TABLE IF NOT EXISTS articles ("
                "  id INTEGER PRIMARY KEY, "
                "  title TEXT NOT NULL, "
                "  body TEXT"
                ")"
            )
        )
        conn.execute(
            text("CREATE TABLE IF NOT EXISTS tags (  id INTEGER PRIMARY KEY,   name TEXT NOT NULL)")
        )
        conn.commit()


def _insert_rows(engine, table, rows):
    """Insert rows (list of dicts) into a table."""
    with engine.connect() as conn:
        for row in rows:
            cols = ", ".join(row.keys())
            placeholders = ", ".join(f":{k}" for k in row.keys())
            conn.execute(text(f"INSERT INTO {table} ({cols}) VALUES ({placeholders})"), row)
        conn.commit()


@pytest.fixture()
def identical_dbs(tmp_path):
    """Two SQLite databases with identical schema and data."""
    sqlite_path = str(tmp_path / "source.db")
    pg_path = str(tmp_path / "target.db")

    sqlite_url = f"sqlite:///{sqlite_path}"
    pg_url = f"sqlite:///{pg_path}"

    sqlite_engine = create_engine(sqlite_url)
    pg_engine = create_engine(pg_url)

    _create_tables(sqlite_engine)
    _create_tables(pg_engine)

    articles = [
        {"id": 1, "title": "Hello", "body": "World"},
        {"id": 2, "title": "Foo", "body": "Bar"},
        {"id": 3, "title": "Baz", "body": "Qux"},
    ]
    tags = [
        {"id": 1, "name": "python"},
        {"id": 2, "name": "sql"},
    ]

    for engine in (sqlite_engine, pg_engine):
        _insert_rows(engine, "articles", articles)
        _insert_rows(engine, "tags", tags)

    sqlite_engine.dispose()
    pg_engine.dispose()

    return sqlite_url, pg_url


@pytest.fixture()
def mismatched_dbs(tmp_path):
    """Two SQLite databases with different row counts and data."""
    sqlite_path = str(tmp_path / "source.db")
    pg_path = str(tmp_path / "target.db")

    sqlite_url = f"sqlite:///{sqlite_path}"
    pg_url = f"sqlite:///{pg_path}"

    sqlite_engine = create_engine(sqlite_url)
    pg_engine = create_engine(pg_url)

    _create_tables(sqlite_engine)
    _create_tables(pg_engine)

    # SQLite side: 3 articles
    _insert_rows(
        sqlite_engine,
        "articles",
        [
            {"id": 1, "title": "Hello", "body": "World"},
            {"id": 2, "title": "Foo", "body": "Bar"},
            {"id": 3, "title": "Baz", "body": "Qux"},
        ],
    )
    _insert_rows(
        sqlite_engine,
        "tags",
        [
            {"id": 1, "name": "python"},
        ],
    )

    # PG side: only 2 articles, and different data for id=2
    _insert_rows(
        pg_engine,
        "articles",
        [
            {"id": 1, "title": "Hello", "body": "World"},
            {"id": 2, "title": "CHANGED", "body": "CHANGED"},
        ],
    )
    _insert_rows(
        pg_engine,
        "tags",
        [
            {"id": 1, "name": "python"},
        ],
    )

    sqlite_engine.dispose()
    pg_engine.dispose()

    return sqlite_url, pg_url


# ===================================================================
# Gate 1: Row count comparison
# ===================================================================


class TestRowCounts:
    def test_row_count_passes_identical(self, identical_dbs):
        from scripts.verify_migration import check_row_counts

        sqlite_url, pg_url = identical_dbs
        result = check_row_counts(sqlite_url, pg_url)
        assert result["passed"] is True
        for table_info in result["details"].values():
            assert table_info["match"] is True

    def test_row_count_fails_mismatch(self, mismatched_dbs):
        from scripts.verify_migration import check_row_counts

        sqlite_url, pg_url = mismatched_dbs
        result = check_row_counts(sqlite_url, pg_url)
        assert result["passed"] is False
        assert result["details"]["articles"]["match"] is False


# ===================================================================
# Gate 2: Random sample comparison
# ===================================================================


class TestSampleData:
    def test_sample_data_passes_identical(self, identical_dbs):
        from scripts.verify_migration import check_sample_data

        sqlite_url, pg_url = identical_dbs
        result = check_sample_data(sqlite_url, pg_url, sample_size=10)
        assert result["passed"] is True
        for table_info in result["details"].values():
            assert table_info["mismatches"] == 0

    def test_sample_data_fails_mismatch(self, mismatched_dbs):
        from scripts.verify_migration import check_sample_data

        sqlite_url, pg_url = mismatched_dbs
        result = check_sample_data(sqlite_url, pg_url, sample_size=10)
        assert result["passed"] is False
        # articles table should have mismatches (id=2 has different data)
        assert result["details"]["articles"]["mismatches"] > 0


# ===================================================================
# Gate 3: API endpoint regression
# ===================================================================


class TestApiRegression:
    def test_api_regression_passes(self):
        from scripts.verify_migration import check_api_regression

        mock_response = MagicMock()
        mock_response.status_code = 200

        with patch("scripts.verify_migration.httpx") as mock_httpx:
            mock_httpx.get.return_value = mock_response
            result = check_api_regression("http://localhost:8000")

        assert result["passed"] is True
        for endpoint_info in result["details"].values():
            assert endpoint_info["ok"] is True
            assert endpoint_info["status"] == 200

    def test_api_regression_fails(self):
        from scripts.verify_migration import check_api_regression

        def mock_get(url, **kwargs):
            resp = MagicMock()
            if url.endswith("/health"):
                resp.status_code = 200
            else:
                resp.status_code = 500
            return resp

        with patch("scripts.verify_migration.httpx") as mock_httpx:
            mock_httpx.get.side_effect = mock_get
            result = check_api_regression("http://localhost:8000")

        assert result["passed"] is False


# ===================================================================
# Gate 4: Query performance
# ===================================================================


class TestQueryPerformance:
    def test_query_performance_passes_within_baseline(self, identical_dbs):
        from scripts.verify_migration import check_query_performance

        _, pg_url = identical_dbs
        result = check_query_performance(pg_url, baseline_ms=5000.0)
        assert result["passed"] is True
        assert len(result["details"]) > 0

    def test_query_performance_fails_over_baseline(self, identical_dbs):
        from scripts.verify_migration import check_query_performance

        _, pg_url = identical_dbs
        # Impossibly tight baseline should cause failure
        result = check_query_performance(pg_url, baseline_ms=0.0001)
        assert result["passed"] is False


# ===================================================================
# run_all_gates aggregation
# ===================================================================


class TestRunAllGates:
    def test_run_all_gates_aggregates(self, identical_dbs):
        from scripts.verify_migration import run_all_gates

        sqlite_url, pg_url = identical_dbs
        result = run_all_gates(sqlite_url, pg_url)
        assert result["all_passed"] is True
        assert "row_counts" in result["gates"]
        assert "sample_data" in result["gates"]
        assert "query_performance" in result["gates"]

    def test_run_all_gates_fails_if_any_fails(self, mismatched_dbs):
        from scripts.verify_migration import run_all_gates

        sqlite_url, pg_url = mismatched_dbs
        result = run_all_gates(sqlite_url, pg_url)
        assert result["all_passed"] is False
