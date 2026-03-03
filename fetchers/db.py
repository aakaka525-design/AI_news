"""Database compatibility wrapper for legacy fetcher scripts."""

from src.database.connection import (  # noqa: F401
    STOCKS_DB_PATH,
    batch_insert_validated,
    get_connection,
    insert_validated,
    validate_and_create,
)
