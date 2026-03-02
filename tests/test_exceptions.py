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
