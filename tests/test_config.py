"""Configuration tests."""
from unittest.mock import patch
import importlib


def test_database_url_defaults_to_sqlite():
    with patch.dict("os.environ", {}, clear=False):
        import config.settings as s
        importlib.reload(s)
        assert "sqlite" in s.DATABASE_URL


def test_database_url_reads_from_env():
    with patch.dict("os.environ", {"DATABASE_URL": "postgresql://user:pass@localhost:5432/ainews"}):
        import config.settings as s
        importlib.reload(s)
        assert s.DATABASE_URL == "postgresql://user:pass@localhost:5432/ainews"


def test_news_database_url_defaults():
    with patch.dict("os.environ", {}, clear=False):
        import config.settings as s
        importlib.reload(s)
        assert "sqlite" in s.NEWS_DATABASE_URL
        assert "news" in s.NEWS_DATABASE_URL
