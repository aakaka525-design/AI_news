"""
Migrate data from SQLite to PostgreSQL.

Usage:
    python scripts/migrate_sqlite_to_pg.py [--sqlite-path data/stocks.db] [--pg-url postgresql://...]

Copies all tables from SQLite to PostgreSQL, with progress reporting.
"""

import argparse
import sqlite3
import sys
import time
from pathlib import Path

from sqlalchemy import create_engine, inspect, text


def get_sqlite_tables(sqlite_path: str) -> list[str]:
    """Get all table names from SQLite database."""
    conn = sqlite3.connect(sqlite_path)
    cursor = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
    )
    tables = [row[0] for row in cursor.fetchall()]
    conn.close()
    return tables


def get_row_count(sqlite_path: str, table: str) -> int:
    """Get row count for a SQLite table."""
    conn = sqlite3.connect(sqlite_path)
    count = conn.execute(f"SELECT COUNT(*) FROM [{table}]").fetchone()[0]
    conn.close()
    return count


def migrate_table(sqlite_path: str, pg_engine, table: str, batch_size: int = 1000) -> dict:
    """Migrate a single table from SQLite to PostgreSQL."""
    conn = sqlite3.connect(sqlite_path)
    conn.row_factory = sqlite3.Row

    cursor = conn.execute(f"SELECT * FROM [{table}]")
    rows = cursor.fetchall()

    if not rows:
        conn.close()
        return {"table": table, "rows": 0, "status": "empty"}

    columns = rows[0].keys()
    total = len(rows)
    migrated = 0

    with pg_engine.connect() as pg_conn:
        for i in range(0, total, batch_size):
            batch = rows[i : i + batch_size]
            for row in batch:
                values = {col: row[col] for col in columns}
                placeholders = ", ".join(f":{col}" for col in columns)
                col_names = ", ".join(f'"{col}"' for col in columns)
                sql = (
                    f'INSERT INTO "{table}" ({col_names}) '
                    f"VALUES ({placeholders}) ON CONFLICT DO NOTHING"
                )
                try:
                    pg_conn.execute(text(sql), values)
                except Exception as e:
                    print(f"    Warning: row skip in {table}: {e}")
            pg_conn.commit()
            migrated += len(batch)
            print(f"    {table}: {migrated}/{total} rows", end="\r")

    conn.close()
    print(f"    {table}: {migrated}/{total} rows - done")
    return {"table": table, "rows": migrated, "status": "ok"}


def migrate(sqlite_path: str, pg_url: str, tables: list[str] = None) -> dict:
    """Migrate all tables from SQLite to PostgreSQL."""
    print(f"Source: {sqlite_path}")
    print(f"Target: {pg_url}")
    print()

    all_tables = get_sqlite_tables(sqlite_path)
    target_tables = tables or all_tables

    pg_engine = create_engine(pg_url)

    # Check which tables exist in PostgreSQL
    pg_inspector = inspect(pg_engine)
    pg_tables = pg_inspector.get_table_names()

    results = []
    start = time.time()

    for table in target_tables:
        if table not in pg_tables:
            print(f"  SKIP {table} (not in PostgreSQL schema)")
            results.append({"table": table, "rows": 0, "status": "skipped"})
            continue

        row_count = get_row_count(sqlite_path, table)
        print(f"  Migrating {table} ({row_count} rows)...")
        result = migrate_table(sqlite_path, pg_engine, table)
        results.append(result)

    elapsed = time.time() - start
    total_rows = sum(r["rows"] for r in results)

    print(f"\nMigration complete: {total_rows} rows in {elapsed:.1f}s")
    return {
        "tables": results,
        "total_rows": total_rows,
        "elapsed_seconds": round(elapsed, 1),
    }


def main():
    parser = argparse.ArgumentParser(description="Migrate SQLite to PostgreSQL")
    parser.add_argument("--sqlite-path", default="data/stocks.db", help="SQLite database path")
    parser.add_argument(
        "--pg-url",
        default="postgresql://ainews:ainews_dev@localhost:5432/ainews",
        help="PostgreSQL connection URL",
    )
    parser.add_argument("--tables", nargs="*", help="Specific tables to migrate (default: all)")
    args = parser.parse_args()

    if not Path(args.sqlite_path).exists():
        print(f"Error: SQLite file not found: {args.sqlite_path}")
        sys.exit(1)

    migrate(args.sqlite_path, args.pg_url, args.tables)


if __name__ == "__main__":
    main()
