"""
Report repository — SQLAlchemy ORM for research_report table.

Usage:
    from src.database.engine import create_engine_from_url, get_session_factory
    from src.database.repositories.report import ReportRepository

    engine = create_engine_from_url(database_url)
    Session = get_session_factory(engine)
    repo = ReportRepository(Session)
    repo.create_tables(engine)
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import BigInteger, func, text
from sqlalchemy.orm import sessionmaker

from src.database.models import ResearchReport


# SQLite only auto-increments columns declared as exactly ``INTEGER``
# (not ``BIGINT``).  Register a dialect-level compile rule so that
# ``BigInteger`` renders as ``INTEGER`` on SQLite, which enables the
# implicit rowid alias / autoincrement behaviour.
try:
    from sqlalchemy.ext.compiler import compiles as _compiles

    @_compiles(BigInteger, "sqlite")
    def _bi_sqlite(element, compiler, **kw):  # noqa: N802
        return "INTEGER"
except Exception:  # pragma: no cover – defensive
    pass


class ReportRepository:
    """CRUD operations for the research_report table."""

    def __init__(self, session_factory: sessionmaker):
        self._Session = session_factory

    def create_tables(self, engine) -> None:
        """Create the research_report table if it doesn't exist."""
        ResearchReport.__table__.create(bind=engine, checkfirst=True)

    def upsert_report(self, data: dict[str, Any]) -> None:
        """Insert or update a research report.

        Uniqueness is determined by (ts_code, publish_date, institution).
        """
        with self._Session() as session:
            existing = (
                session.query(ResearchReport)
                .filter_by(
                    ts_code=data.get("ts_code"),
                    publish_date=data.get("publish_date"),
                    institution=data.get("institution"),
                )
                .first()
            )
            if existing:
                for key, value in data.items():
                    if hasattr(existing, key) and value is not None:
                        setattr(existing, key, value)
            else:
                report = ResearchReport(
                    **{k: v for k, v in data.items() if hasattr(ResearchReport, k)}
                )
                session.add(report)
            session.commit()

    def get_reports(
        self,
        ts_code: str | None = None,
        limit: int = 20,
    ) -> list[dict[str, Any]]:
        """Get reports, optionally filtered by stock code."""
        with self._Session() as session:
            query = session.query(ResearchReport)
            if ts_code:
                query = query.filter(ResearchReport.ts_code == ts_code)
            query = query.order_by(ResearchReport.publish_date.desc()).limit(limit)
            return [self._to_dict(r) for r in query.all()]

    def get_rating_stats(self) -> dict[str, int]:
        """Get rating distribution."""
        with self._Session() as session:
            rows = (
                session.query(ResearchReport.rating, func.count())
                .filter(ResearchReport.rating.isnot(None))
                .filter(ResearchReport.rating != "")
                .group_by(ResearchReport.rating)
                .all()
            )
            return {rating: count for rating, count in rows}

    def save_analysis(
        self,
        ts_code: str,
        publish_date: str,
        institution: str,
        analysis: dict[str, Any],
    ) -> bool:
        """Persist analysis results to structured fields."""
        with self._Session() as session:
            report = (
                session.query(ResearchReport)
                .filter_by(
                    ts_code=ts_code,
                    publish_date=publish_date,
                    institution=institution,
                )
                .first()
            )
            if not report:
                return False

            if analysis.get("target_price") is not None:
                report.target_price = analysis["target_price"]
            if analysis.get("rating_change"):
                report.rating_change = analysis["rating_change"]
            if analysis.get("key_points"):
                report.key_points = analysis["key_points"]
            if analysis.get("summary"):
                report.summary = analysis["summary"]
            if analysis.get("sentiment_score") is not None:
                report.sentiment_score = analysis["sentiment_score"]

            session.commit()
            return True

    @staticmethod
    def _to_dict(report: ResearchReport) -> dict[str, Any]:
        """Convert a ResearchReport ORM object to a dict."""
        return {
            "id": report.id,
            "ts_code": report.ts_code,
            "stock_name": report.stock_name,
            "title": report.title,
            "institution": report.institution,
            "analyst": report.analyst,
            "rating": report.rating,
            "rating_change": report.rating_change,
            "target_price": float(report.target_price) if report.target_price else None,
            "target_price_change": float(report.target_price_change) if report.target_price_change else None,
            "content": report.content,
            "summary": report.summary,
            "key_points": report.key_points,
            "sentiment_score": float(report.sentiment_score) if report.sentiment_score else None,
            "publish_date": report.publish_date,
        }
