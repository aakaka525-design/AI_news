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
