"""Database-agnostic upsert tests."""
import pytest
from sqlalchemy import create_engine, Column, String, Float, Integer
from sqlalchemy.orm import sessionmaker, DeclarativeBase

from src.database.upsert import upsert_row, upsert_batch


class Base(DeclarativeBase):
    pass


class TestStock(Base):
    __tablename__ = "test_stocks"
    ts_code = Column(String, primary_key=True)
    trade_date = Column(String, primary_key=True)
    close = Column(Float)
    vol = Column(Float, default=0)


@pytest.fixture
def session(tmp_path):
    url = f"sqlite:///{tmp_path / 'test.db'}"
    engine = create_engine(url)
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    with Session() as s:
        yield s


class TestUpsertRow:
    def test_inserts_new_row(self, session):
        result = upsert_row(session, TestStock.__table__,
            {"ts_code": "000001.SZ", "trade_date": "20260301", "close": 10.0, "vol": 100.0})
        session.commit()
        assert result is True
        row = session.execute(TestStock.__table__.select()).fetchone()
        assert row.close == 10.0

    def test_updates_existing_row(self, session):
        upsert_row(session, TestStock.__table__,
            {"ts_code": "000001.SZ", "trade_date": "20260301", "close": 10.0, "vol": 100.0})
        session.commit()
        upsert_row(session, TestStock.__table__,
            {"ts_code": "000001.SZ", "trade_date": "20260301", "close": 11.0, "vol": 200.0})
        session.commit()
        rows = session.execute(TestStock.__table__.select()).fetchall()
        assert len(rows) == 1
        assert rows[0].close == 11.0

    def test_different_keys_create_different_rows(self, session):
        upsert_row(session, TestStock.__table__,
            {"ts_code": "000001.SZ", "trade_date": "20260301", "close": 10.0})
        upsert_row(session, TestStock.__table__,
            {"ts_code": "000001.SZ", "trade_date": "20260302", "close": 11.0})
        session.commit()
        rows = session.execute(TestStock.__table__.select()).fetchall()
        assert len(rows) == 2


class TestUpsertBatch:
    def test_batch_inserts(self, session):
        data = [
            {"ts_code": "000001.SZ", "trade_date": f"2026030{i}", "close": 10.0 + i}
            for i in range(1, 6)
        ]
        count = upsert_batch(session, TestStock.__table__, data)
        session.commit()
        assert count == 5
        rows = session.execute(TestStock.__table__.select()).fetchall()
        assert len(rows) == 5

    def test_batch_with_duplicates(self, session):
        data = [
            {"ts_code": "000001.SZ", "trade_date": "20260301", "close": 10.0},
            {"ts_code": "000001.SZ", "trade_date": "20260301", "close": 11.0},
        ]
        count = upsert_batch(session, TestStock.__table__, data)
        session.commit()
        assert count == 2
        rows = session.execute(TestStock.__table__.select()).fetchall()
        assert len(rows) == 1
        assert rows[0].close == 11.0

    def test_empty_batch(self, session):
        count = upsert_batch(session, TestStock.__table__, [])
        assert count == 0
