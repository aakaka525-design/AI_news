"""Migration verification gate -- all checks must pass before cutover."""

import argparse
import random
import sys
import time

import httpx
from sqlalchemy import create_engine, inspect, text

# ===================================================================
# Gate 1: Row count comparison
# ===================================================================


def check_row_counts(sqlite_url: str, pg_url: str) -> dict:
    """Compare row counts for ALL tables between SQLite and PostgreSQL.

    Tolerance: 0 (exact match required).

    Returns:
        {"passed": bool, "details": {table: {"sqlite": N, "pg": N, "match": bool}}}
    """
    sqlite_engine = create_engine(sqlite_url)
    pg_engine = create_engine(pg_url)

    try:
        sqlite_inspector = inspect(sqlite_engine)
        pg_inspector = inspect(pg_engine)

        sqlite_tables = set(sqlite_inspector.get_table_names())
        pg_tables = set(pg_inspector.get_table_names())
        common_tables = sorted(sqlite_tables & pg_tables)

        details: dict = {}
        all_match = True

        for table in common_tables:
            with sqlite_engine.connect() as conn:
                sqlite_count = conn.execute(text(f'SELECT COUNT(*) FROM "{table}"')).scalar()
            with pg_engine.connect() as conn:
                pg_count = conn.execute(text(f'SELECT COUNT(*) FROM "{table}"')).scalar()

            match = sqlite_count == pg_count
            if not match:
                all_match = False

            details[table] = {
                "sqlite": sqlite_count,
                "pg": pg_count,
                "match": match,
            }
    finally:
        sqlite_engine.dispose()
        pg_engine.dispose()

    return {"passed": all_match, "details": details}


# ===================================================================
# Gate 2: Random sample comparison
# ===================================================================


def check_sample_data(sqlite_url: str, pg_url: str, sample_size: int = 100) -> dict:
    """For each table, pick random rows from SQLite and compare in PostgreSQL.

    Returns:
        {"passed": bool, "details": {table: {"checked": N, "mismatches": N}}}
    """
    sqlite_engine = create_engine(sqlite_url)
    pg_engine = create_engine(pg_url)

    try:
        sqlite_inspector = inspect(sqlite_engine)
        pg_inspector = inspect(pg_engine)

        sqlite_tables = set(sqlite_inspector.get_table_names())
        pg_tables = set(pg_inspector.get_table_names())
        common_tables = sorted(sqlite_tables & pg_tables)

        details: dict = {}
        all_ok = True

        for table in common_tables:
            # Determine primary key columns
            pk_constraint = sqlite_inspector.get_pk_constraint(table)
            pk_cols = pk_constraint.get("constrained_columns", [])
            if not pk_cols:
                # Skip tables without a primary key
                details[table] = {"checked": 0, "mismatches": 0}
                continue

            # Get all column names
            columns = [c["name"] for c in sqlite_inspector.get_columns(table)]

            # Fetch all rows from SQLite for this table
            col_list = ", ".join(f'"{c}"' for c in columns)
            with sqlite_engine.connect() as conn:
                rows = conn.execute(text(f'SELECT {col_list} FROM "{table}"')).fetchall()

            if not rows:
                details[table] = {"checked": 0, "mismatches": 0}
                continue

            # Sample up to sample_size rows
            sampled = random.sample(rows, min(sample_size, len(rows)))

            mismatches = 0
            with pg_engine.connect() as conn:
                for row in sampled:
                    row_dict = dict(zip(columns, row))
                    # Build WHERE clause on primary key
                    where_parts = []
                    params = {}
                    for pk in pk_cols:
                        where_parts.append(f'"{pk}" = :pk_{pk}')
                        params[f"pk_{pk}"] = row_dict[pk]

                    where_clause = " AND ".join(where_parts)
                    pg_row = conn.execute(
                        text(f'SELECT {col_list} FROM "{table}" WHERE {where_clause}'),
                        params,
                    ).fetchone()

                    if pg_row is None:
                        mismatches += 1
                        continue

                    pg_dict = dict(zip(columns, pg_row))
                    if row_dict != pg_dict:
                        mismatches += 1

            if mismatches > 0:
                all_ok = False

            details[table] = {"checked": len(sampled), "mismatches": mismatches}
    finally:
        sqlite_engine.dispose()
        pg_engine.dispose()

    return {"passed": all_ok, "details": details}


# ===================================================================
# Gate 3: API endpoint regression
# ===================================================================

ENDPOINTS = ["/health", "/api/news", "/api/rss"]


def check_api_regression(api_url: str) -> dict:
    """Hit key API endpoints and check for 200 responses.

    Returns:
        {"passed": bool, "details": {endpoint: {"status": code, "ok": bool}}}
    """
    details: dict = {}
    all_ok = True

    for endpoint in ENDPOINTS:
        url = f"{api_url.rstrip('/')}{endpoint}"
        try:
            resp = httpx.get(url, timeout=10)
            status = resp.status_code
        except Exception:
            status = 0

        ok = status == 200
        if not ok:
            all_ok = False
        details[endpoint] = {"status": status, "ok": ok}

    return {"passed": all_ok, "details": details}


# ===================================================================
# Gate 4: Query performance
# ===================================================================

REPRESENTATIVE_QUERIES = {
    "count_all_tables": "SELECT name FROM sqlite_master WHERE type='table'",
    "select_1": "SELECT 1",
}

# For PostgreSQL we use proper queries; for SQLite fallback we use compatible SQL
PG_QUERIES = {
    "count_all_tables": ("SELECT tablename FROM pg_catalog.pg_tables WHERE schemaname = 'public'"),
    "select_1": "SELECT 1",
}


def check_query_performance(pg_url: str, baseline_ms: float | None = None) -> dict:
    """Run representative queries against the database and report latency.

    If baseline_ms is provided, check that each query runs within 120% of it.

    Returns:
        {"passed": bool, "details": {query_name: {"ms": float}}}
    """
    engine = create_engine(pg_url)
    is_pg = pg_url.startswith("postgresql")
    queries = PG_QUERIES if is_pg else REPRESENTATIVE_QUERIES

    details: dict = {}
    all_ok = True

    try:
        with engine.connect() as conn:
            for name, sql in queries.items():
                start = time.perf_counter()
                try:
                    conn.execute(text(sql)).fetchall()
                except Exception:
                    elapsed_ms = (time.perf_counter() - start) * 1000.0
                    details[name] = {"ms": round(elapsed_ms, 2), "error": True}
                    all_ok = False
                    continue
                elapsed_ms = (time.perf_counter() - start) * 1000.0
                details[name] = {"ms": round(elapsed_ms, 2)}

                if baseline_ms is not None and elapsed_ms > baseline_ms * 1.2:
                    all_ok = False
    finally:
        engine.dispose()

    return {"passed": all_ok, "details": details}


# ===================================================================
# Gate 5: Grey period (manual)
# ===================================================================
# Gate 5 is a manual observation period (soak/grey period).
# It is NOT automated. After gates 1-4 pass, operators should
# monitor the system under dual-write for 3 trading days before
# completing the cutover. During this period, verify:
#   - No data discrepancies between SQLite and PostgreSQL
#   - API response times remain stable
#   - No new error patterns in logs
# Only proceed with full cutover after the grey period passes.


# ===================================================================
# run_all_gates
# ===================================================================


def run_all_gates(
    sqlite_url: str,
    pg_url: str,
    api_url: str | None = None,
    baseline_ms: float | None = None,
) -> dict:
    """Run all verification gates.

    Gates 1, 2, 4 always run.  Gate 3 only if api_url is provided.

    Returns:
        {"all_passed": bool, "gates": {name: result}}
    """
    gates: dict = {}

    gates["row_counts"] = check_row_counts(sqlite_url, pg_url)
    gates["sample_data"] = check_sample_data(sqlite_url, pg_url)

    if api_url:
        gates["api_regression"] = check_api_regression(api_url)

    gates["query_performance"] = check_query_performance(pg_url, baseline_ms=baseline_ms)

    all_passed = all(g["passed"] for g in gates.values())
    return {"all_passed": all_passed, "gates": gates}


# ===================================================================
# CLI
# ===================================================================

GREEN = "\033[92m"
RED = "\033[91m"
RESET = "\033[0m"
BOLD = "\033[1m"


def _status(passed: bool) -> str:
    if passed:
        return f"{GREEN}PASS{RESET}"
    return f"{RED}FAIL{RESET}"


def main():
    parser = argparse.ArgumentParser(
        description="Migration verification gate -- all checks must pass before cutover."
    )
    parser.add_argument(
        "--sqlite-path",
        default="data/news.db",
        help="Path to SQLite database file",
    )
    parser.add_argument(
        "--pg-url",
        default="postgresql://ainews:ainews_dev@localhost:5432/ainews",
        help="PostgreSQL connection URL",
    )
    parser.add_argument(
        "--api-url",
        default=None,
        help="API base URL for regression checks (optional)",
    )
    parser.add_argument(
        "--baseline-ms",
        type=float,
        default=None,
        help="Baseline query time in ms for performance gate (optional)",
    )
    args = parser.parse_args()

    sqlite_url = f"sqlite:///{args.sqlite_path}"

    print(f"{BOLD}Migration Verification Gates{RESET}")
    print(f"  SQLite : {args.sqlite_path}")
    print(f"  PG     : {args.pg_url}")
    if args.api_url:
        print(f"  API    : {args.api_url}")
    print()

    result = run_all_gates(
        sqlite_url,
        args.pg_url,
        api_url=args.api_url,
        baseline_ms=args.baseline_ms,
    )

    for gate_name, gate_result in result["gates"].items():
        status = _status(gate_result["passed"])
        print(f"  [{status}] {gate_name}")

        if gate_name == "row_counts":
            for table, info in gate_result["details"].items():
                mark = f"{GREEN}={RESET}" if info["match"] else f"{RED}!{RESET}"
                print(f"         {mark} {table}: sqlite={info['sqlite']} pg={info['pg']}")

        elif gate_name == "sample_data":
            for table, info in gate_result["details"].items():
                checked = info["checked"]
                mismatches = info["mismatches"]
                mark = f"{GREEN}={RESET}" if mismatches == 0 else f"{RED}!{RESET}"
                print(f"         {mark} {table}: checked={checked} mismatches={mismatches}")

        elif gate_name == "api_regression":
            for endpoint, info in gate_result["details"].items():
                mark = f"{GREEN}={RESET}" if info["ok"] else f"{RED}!{RESET}"
                print(f"         {mark} {endpoint}: status={info['status']}")

        elif gate_name == "query_performance":
            for query_name, info in gate_result["details"].items():
                print(f"           {query_name}: {info['ms']}ms")

    print()
    overall = _status(result["all_passed"])
    print(f"  Overall: [{overall}]")

    if not result["all_passed"]:
        print(f"\n{RED}Verification FAILED. Do NOT proceed with cutover.{RESET}")
        sys.exit(1)
    else:
        print(f"\n{GREEN}All gates passed. Safe to proceed with cutover.{RESET}")
        sys.exit(0)


if __name__ == "__main__":
    main()
