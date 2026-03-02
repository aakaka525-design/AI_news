"""Database engine factory tests."""
import pytest
from src.database.engine import create_engine_from_url, get_session_factory, is_postgresql


def test_create_engine_sqlite(tmp_path):
    url = f"sqlite:///{tmp_path / 'test.db'}"
    engine = create_engine_from_url(url)
    assert engine is not None
    assert "sqlite" in str(engine.url)


def test_create_engine_sqlite_memory():
    engine = create_engine_from_url("sqlite:///:memory:")
    assert engine is not None


def test_is_postgresql_false_for_sqlite():
    assert is_postgresql("sqlite:///test.db") is False


def test_is_postgresql_true_for_pg():
    assert is_postgresql("postgresql://localhost/ainews") is True


def test_get_session_factory(tmp_path):
    url = f"sqlite:///{tmp_path / 'test.db'}"
    engine = create_engine_from_url(url)
    SessionFactory = get_session_factory(engine)
    with SessionFactory() as session:
        assert session is not None
        session.execute(
            __import__("sqlalchemy").text("SELECT 1")
        )
