"""Database-agnostic upsert utilities using SQLAlchemy dialects."""
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.dialects.postgresql import insert as pg_insert


def upsert_row(session, table, data: dict) -> bool:
    """Upsert a single row. Works with SQLite and PostgreSQL.

    Uses dialect-specific INSERT ... ON CONFLICT statements to perform
    an insert-or-update operation atomically.

    Args:
        session: SQLAlchemy session (must be bound to an engine).
        table: SQLAlchemy Table object.
        data: Dictionary of column_name -> value for the row.

    Returns:
        True if the statement was executed successfully.
    """
    dialect = session.bind.dialect.name
    pk_cols = [c.name for c in table.primary_key.columns]
    update_cols = {k: v for k, v in data.items() if k not in pk_cols}

    if dialect == "postgresql":
        stmt = pg_insert(table).values(**data)
    else:
        stmt = sqlite_insert(table).values(**data)

    if update_cols:
        stmt = stmt.on_conflict_do_update(
            index_elements=pk_cols,
            set_=update_cols,
        )
    else:
        stmt = stmt.on_conflict_do_nothing()

    session.execute(stmt)
    return True


def upsert_batch(session, table, rows: list[dict], commit_every: int = 100) -> int:
    """Upsert multiple rows.

    Iterates over the list of row dicts and upserts each one.
    Flushes periodically according to commit_every to manage memory
    on large batches.

    Args:
        session: SQLAlchemy session (must be bound to an engine).
        table: SQLAlchemy Table object.
        rows: List of dictionaries, each representing a row.
        commit_every: Flush interval (default 100 rows).

    Returns:
        Number of rows processed.
    """
    count = 0
    for i, row in enumerate(rows):
        if upsert_row(session, table, row):
            count += 1
        if (i + 1) % commit_every == 0:
            session.flush()
    return count
