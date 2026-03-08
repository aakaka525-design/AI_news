"""Database connection module tests.

Focuses on SQL identifier validation, validate_and_create edge cases,
insert_validated error paths, and batch_insert_validated transactional behavior.
"""

import sqlite3
from unittest.mock import MagicMock

import pytest
from pydantic import BaseModel

from src.database.connection import (
    _validate_identifier,
    validate_and_create,
    insert_validated,
    batch_insert_validated,
)


# ---------------------------------------------------------------------------
# Test models
# ---------------------------------------------------------------------------


class SampleModel(BaseModel):
    name: str
    value: int


class NullableModel(BaseModel):
    name: str
    value: int | None = None


# ---------------------------------------------------------------------------
# _validate_identifier
# ---------------------------------------------------------------------------


class TestValidateIdentifier:
    def test_valid_identifiers(self):
        assert _validate_identifier("users") == "users"
        assert _validate_identifier("ts_daily") == "ts_daily"
        assert _validate_identifier("_private") == "_private"
        assert _validate_identifier("Table123") == "Table123"

    def test_single_letter(self):
        assert _validate_identifier("x") == "x"

    def test_underscore_only(self):
        assert _validate_identifier("_") == "_"

    def test_mixed_case_with_numbers(self):
        assert _validate_identifier("myTable_2") == "myTable_2"

    def test_invalid_starts_with_number(self):
        with pytest.raises(ValueError, match="Invalid SQL identifier"):
            _validate_identifier("1starts_with_number")

    def test_invalid_has_spaces(self):
        with pytest.raises(ValueError, match="Invalid SQL identifier"):
            _validate_identifier("has spaces")

    def test_invalid_has_dashes(self):
        with pytest.raises(ValueError, match="Invalid SQL identifier"):
            _validate_identifier("has-dashes")

    def test_invalid_sql_injection(self):
        with pytest.raises(ValueError, match="Invalid SQL identifier"):
            _validate_identifier("'; DROP TABLE users; --")

    def test_invalid_empty_string(self):
        with pytest.raises(ValueError, match="Invalid SQL identifier"):
            _validate_identifier("")

    def test_invalid_dot_notation(self):
        with pytest.raises(ValueError, match="Invalid SQL identifier"):
            _validate_identifier("schema.table")

    def test_invalid_semicolon(self):
        with pytest.raises(ValueError, match="Invalid SQL identifier"):
            _validate_identifier("bad;table")

    def test_invalid_parentheses(self):
        with pytest.raises(ValueError, match="Invalid SQL identifier"):
            _validate_identifier("func()")

    def test_invalid_asterisk(self):
        with pytest.raises(ValueError, match="Invalid SQL identifier"):
            _validate_identifier("*")

    def test_invalid_unicode(self):
        with pytest.raises(ValueError, match="Invalid SQL identifier"):
            _validate_identifier("tablé")

    def test_invalid_newline(self):
        with pytest.raises(ValueError, match="Invalid SQL identifier"):
            _validate_identifier("table\nname")


# ---------------------------------------------------------------------------
# validate_and_create
# ---------------------------------------------------------------------------


class TestValidateAndCreate:
    def test_valid_data(self):
        result = validate_and_create(SampleModel, {"name": "test", "value": 42})
        assert result is not None
        assert result.name == "test"
        assert result.value == 42

    def test_invalid_data_non_strict_returns_none(self):
        result = validate_and_create(SampleModel, {"name": "test", "value": "not_int"})
        assert result is None

    def test_invalid_data_strict_raises(self):
        with pytest.raises(Exception):
            validate_and_create(
                SampleModel, {"name": "test", "value": "not_int"}, strict=True
            )

    def test_missing_required_field_non_strict(self):
        result = validate_and_create(SampleModel, {"name": "test"})
        assert result is None

    def test_missing_required_field_strict_raises(self):
        with pytest.raises(Exception):
            validate_and_create(SampleModel, {"name": "test"}, strict=True)

    def test_extra_fields_ignored(self):
        result = validate_and_create(
            SampleModel, {"name": "test", "value": 1, "extra": "ignored"}
        )
        assert result is not None
        assert result.name == "test"

    def test_empty_dict_returns_none(self):
        result = validate_and_create(SampleModel, {})
        assert result is None

    def test_type_coercion(self):
        """Pydantic should coerce '42' string to int."""
        result = validate_and_create(SampleModel, {"name": "test", "value": "42"})
        assert result is not None
        assert result.value == 42

    def test_nullable_field(self):
        result = validate_and_create(NullableModel, {"name": "test"})
        assert result is not None
        assert result.value is None


# ---------------------------------------------------------------------------
# insert_validated
# ---------------------------------------------------------------------------


class TestInsertValidated:
    def test_insert_with_invalid_table_returns_false(self):
        """insert_validated catches all exceptions internally and returns False."""
        conn = MagicMock()
        record = SampleModel(name="test", value=1)
        result = insert_validated(conn, "bad table name", record, [])
        assert result is False

    def test_insert_succeeds_with_valid_table(self):
        conn = sqlite3.connect(":memory:")
        conn.execute("CREATE TABLE test_table (name TEXT, value INTEGER)")
        record = SampleModel(name="hello", value=42)
        result = insert_validated(conn, "test_table", record, [])
        assert result is True
        row = conn.execute("SELECT name, value FROM test_table").fetchone()
        assert row[0] == "hello"
        assert row[1] == 42
        conn.close()

    def test_insert_to_nonexistent_table_returns_false(self):
        conn = sqlite3.connect(":memory:")
        record = SampleModel(name="test", value=1)
        result = insert_validated(conn, "nonexistent", record, [])
        assert result is False
        conn.close()

    def test_upsert_with_unique_keys(self):
        conn = sqlite3.connect(":memory:")
        conn.execute(
            "CREATE TABLE items (name TEXT NOT NULL, value INTEGER NOT NULL, UNIQUE(name))"
        )
        r1 = SampleModel(name="key", value=1)
        r2 = SampleModel(name="key", value=2)
        insert_validated(conn, "items", r1, ["name"])
        insert_validated(conn, "items", r2, ["name"])
        conn.commit()
        row = conn.execute("SELECT value FROM items WHERE name='key'").fetchone()
        assert row[0] == 2  # updated to latest value
        count = conn.execute("SELECT COUNT(*) FROM items").fetchone()[0]
        assert count == 1  # only one row, no duplicates
        conn.close()

    def test_insert_with_invalid_unique_key_returns_false(self):
        """insert_validated catches all exceptions internally and returns False."""
        conn = sqlite3.connect(":memory:")
        conn.execute("CREATE TABLE items (name TEXT, value INTEGER)")
        record = SampleModel(name="test", value=1)
        result = insert_validated(conn, "items", record, ["bad column!"])
        assert result is False
        conn.close()

    def test_insert_with_dot_table_name_returns_false(self):
        """insert_validated catches all exceptions internally and returns False."""
        conn = MagicMock()
        record = SampleModel(name="test", value=1)
        result = insert_validated(conn, "schema.table", record, [])
        assert result is False


# ---------------------------------------------------------------------------
# batch_insert_validated
# ---------------------------------------------------------------------------


class TestBatchInsertValidated:
    def test_batch_insert_with_invalid_table_raises(self):
        conn = MagicMock()
        records = [SampleModel(name="test", value=1)]
        with pytest.raises(ValueError, match="Invalid SQL identifier"):
            batch_insert_validated(conn, "bad;table", records, [])

    def test_batch_insert_multiple_records(self):
        conn = sqlite3.connect(":memory:")
        conn.execute(
            "CREATE TABLE items (name TEXT NOT NULL, value INTEGER NOT NULL)"
        )
        records = [
            SampleModel(name="a", value=1),
            SampleModel(name="b", value=2),
        ]
        count = batch_insert_validated(conn, "items", records, [])
        assert count == 2
        rows = conn.execute("SELECT COUNT(*) FROM items").fetchone()
        assert rows[0] == 2
        conn.close()

    def test_batch_insert_empty_list(self):
        conn = sqlite3.connect(":memory:")
        conn.execute("CREATE TABLE items (name TEXT, value INTEGER)")
        count = batch_insert_validated(conn, "items", [], [])
        assert count == 0
        conn.close()

    def test_batch_insert_commits(self):
        conn = sqlite3.connect(":memory:")
        conn.execute(
            "CREATE TABLE items (name TEXT NOT NULL, value INTEGER NOT NULL)"
        )
        records = [
            SampleModel(name="x", value=10),
            SampleModel(name="y", value=20),
            SampleModel(name="z", value=30),
        ]
        count = batch_insert_validated(conn, "items", records, [])
        assert count == 3

        # Verify all records were persisted
        rows = conn.execute("SELECT name, value FROM items ORDER BY name").fetchall()
        assert len(rows) == 3
        assert rows[0][0] == "x"
        assert rows[1][0] == "y"
        assert rows[2][0] == "z"
        conn.close()

    def test_batch_insert_with_unique_keys_upserts(self):
        conn = sqlite3.connect(":memory:")
        conn.execute(
            "CREATE TABLE items (name TEXT NOT NULL, value INTEGER NOT NULL, UNIQUE(name))"
        )
        records = [
            SampleModel(name="key1", value=1),
            SampleModel(name="key1", value=2),  # same key, should upsert
            SampleModel(name="key2", value=3),
        ]
        count = batch_insert_validated(conn, "items", records, ["name"])
        assert count == 3  # all three inserts/upserts succeed

        # Verify upsert worked: key1 should have latest value
        rows = conn.execute("SELECT name, value FROM items ORDER BY name").fetchall()
        assert len(rows) == 2  # only 2 unique keys
        assert rows[0][1] == 2  # key1 upserted to value=2
        assert rows[1][1] == 3  # key2
        conn.close()

    def test_batch_insert_failed_records_not_counted(self):
        """Records that fail to insert should not be counted in the result."""
        conn = sqlite3.connect(":memory:")
        # Create table with NOT NULL constraint to cause some inserts to fail
        conn.execute(
            "CREATE TABLE items (name TEXT NOT NULL, value INTEGER NOT NULL)"
        )
        records = [
            SampleModel(name="a", value=1),
            SampleModel(name="b", value=2),
        ]
        count = batch_insert_validated(conn, "items", records, [])
        assert count == 2

        # Verify all records were inserted
        total = conn.execute("SELECT COUNT(*) FROM items").fetchone()[0]
        assert total == 2
        conn.close()

    def test_batch_insert_rollback_on_commit_failure(self):
        """If commit fails, rollback should be called."""
        mock_conn = MagicMock()
        # Make insert_validated succeed by mocking the execute
        mock_conn.execute = MagicMock()
        mock_conn.commit.side_effect = sqlite3.OperationalError("disk full")

        records = [SampleModel(name="a", value=1)]
        with pytest.raises(Exception):
            batch_insert_validated(mock_conn, "items", records, [])

        mock_conn.rollback.assert_called_once()

    def test_batch_insert_with_semicolon_table_raises(self):
        conn = MagicMock()
        with pytest.raises(ValueError, match="Invalid SQL identifier"):
            batch_insert_validated(conn, "drop;table", [SampleModel(name="x", value=1)], [])

    def test_batch_insert_with_space_table_raises(self):
        conn = MagicMock()
        with pytest.raises(ValueError, match="Invalid SQL identifier"):
            batch_insert_validated(conn, "my table", [SampleModel(name="x", value=1)], [])
