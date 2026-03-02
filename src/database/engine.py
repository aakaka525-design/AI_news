"""
Database engine factory — supports SQLite and PostgreSQL.

Usage:
    from src.database.engine import create_engine_from_url, get_session_factory, is_postgresql

    engine = create_engine_from_url("postgresql://user:pass@localhost/ainews")
    Session = get_session_factory(engine)
    with Session() as session:
        ...
"""

from sqlalchemy import create_engine as _create_engine
from sqlalchemy.orm import sessionmaker


def create_engine_from_url(database_url: str, **kwargs):
    """Create a SQLAlchemy engine for the given URL.

    Automatically configures:
    - SQLite: check_same_thread=False, timeout=30
    - PostgreSQL: pool_size=10, max_overflow=20, pool_pre_ping=True
    """
    if database_url.startswith("sqlite"):
        defaults = {"connect_args": {"check_same_thread": False, "timeout": 30}}
    else:
        defaults = {
            "pool_size": 10,
            "max_overflow": 20,
            "pool_pre_ping": True,
        }
    defaults.update(kwargs)
    return _create_engine(database_url, **defaults)


def get_session_factory(engine):
    """Create a sessionmaker bound to the engine."""
    return sessionmaker(bind=engine, expire_on_commit=False)


def is_postgresql(database_url: str) -> bool:
    """Check if a database URL is for PostgreSQL."""
    return database_url.startswith("postgresql")
