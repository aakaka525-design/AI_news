"""Shared database engines and session factories.

Both api/main.py and api/scheduler.py need access to the same databases.
This module creates each engine exactly once to avoid connection pool
fragmentation and SQLite lock contention.
"""

from src.database.engine import create_engine_from_url, get_session_factory
from config.settings import NEWS_DATABASE_URL, DATABASE_URL

# News database (polymarket, news, analysis, etc.)
news_engine = create_engine_from_url(NEWS_DATABASE_URL)
news_session = get_session_factory(news_engine)

# Stocks database (read-only)
stock_engine = create_engine_from_url(DATABASE_URL)
stock_session = get_session_factory(stock_engine)
