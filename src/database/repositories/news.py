"""
News repository — SQLAlchemy ORM replacement for all raw SQL in api/main.py.

Covers tables: news, analysis_results, rss_items.
Works with both SQLite and PostgreSQL.

Usage:
    from src.database.engine import create_engine_from_url, get_session_factory
    from src.database.repositories.news import NewsRepository

    engine = create_engine_from_url(database_url)
    Session = get_session_factory(engine)
    repo = NewsRepository(Session)
    repo.create_tables(engine)

    news_id = repo.insert_news("Title", "Content")
    items = repo.get_news_list(limit=50)
"""

from __future__ import annotations

import json
from collections import Counter
from datetime import datetime, timedelta, timezone
from typing import Any, Optional


def _utcnow() -> datetime:
    """Return the current UTC time (timezone-aware)."""
    return datetime.now(timezone.utc)

from sqlalchemy import (
    Column,
    DateTime,
    Float,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.orm import DeclarativeBase, sessionmaker


# ------------------------------------------------------------------
# ORM models (local to the news database — NOT the stocks database)
# ------------------------------------------------------------------

class _Base(DeclarativeBase):
    """Private declarative base for news-database tables."""
    pass


class News(_Base):
    """Webhook-received news articles."""

    __tablename__ = "news"

    id = Column(Integer, primary_key=True, autoincrement=True)
    title = Column(Text, nullable=False)
    content = Column(Text, nullable=False)
    cleaned_data = Column(Text, nullable=True)
    hotspots = Column(Text, nullable=True)
    keywords = Column(Text, nullable=True)
    received_at = Column(DateTime, default=_utcnow)

    __table_args__ = (
        Index("idx_received_at", received_at.desc()),
    )


class AnalysisResult(_Base):
    """AI analysis results."""

    __tablename__ = "analysis_results"

    id = Column(Integer, primary_key=True, autoincrement=True)
    date = Column(Text, nullable=False)
    input_count = Column(Integer, nullable=True)
    analysis_summary = Column(Text, nullable=True)
    opportunities = Column(Text, nullable=True)
    analyzed_at = Column(DateTime, default=_utcnow)

    __table_args__ = (
        Index("idx_analysis_date", "date"),
    )


class RssItem(_Base):
    """RSS feed items."""

    __tablename__ = "rss_items"

    id = Column(Integer, primary_key=True, autoincrement=True)
    title = Column(Text, nullable=False)
    link = Column(Text, nullable=True, unique=True)
    summary = Column(Text, nullable=True)
    published = Column(Text, nullable=True)
    source = Column(Text, nullable=True)
    category = Column(Text, nullable=True)
    fetched_at = Column(DateTime, default=_utcnow)
    # Sentiment analysis fields (populated later by the sentiment module)
    sentiment_score = Column(Float, nullable=True)
    ai_summary = Column(Text, nullable=True)
    analyzed_at = Column(DateTime, nullable=True)

    __table_args__ = (
        Index("idx_rss_fetched", fetched_at.desc()),
    )


# ------------------------------------------------------------------
# Repository
# ------------------------------------------------------------------

class NewsRepository:
    """Data-access layer for the news dashboard database.

    Every public method opens (and closes) its own session, so the
    repository is safe for use across async tasks and threads.

    All public methods return plain ``dict`` / ``list`` / ``int``
    values so that callers never depend on ORM identity maps.
    """

    def __init__(self, session_factory: sessionmaker) -> None:
        self.Session = session_factory

    # ----------------------------------------------------------
    # DDL
    # ----------------------------------------------------------

    def create_tables(self, engine) -> None:
        """Create all tables managed by this repository (idempotent)."""
        _Base.metadata.create_all(engine)

    # ----------------------------------------------------------
    # news table
    # ----------------------------------------------------------

    def insert_news(
        self,
        title: str,
        content: str,
        cleaned_data: Optional[str] = None,
        hotspots: Optional[str] = None,
        keywords: Optional[str] = None,
    ) -> int:
        """Insert a news record and return its id."""
        with self.Session() as session:
            row = News(
                title=title,
                content=content,
                cleaned_data=cleaned_data,
                hotspots=hotspots,
                keywords=keywords,
            )
            session.add(row)
            session.commit()
            return row.id

    def get_news_list(self, limit: int = 50) -> list[dict[str, Any]]:
        """Return the most recent news, newest first.

        Each dict contains: id, title, content, cleaned_data (parsed
        JSON or ``None``), received_at (ISO string).
        """
        with self.Session() as session:
            rows = (
                session.query(News)
                .order_by(News.received_at.desc(), News.id.desc())
                .limit(limit)
                .all()
            )
            results = []
            for r in rows:
                parsed_cleaned = None
                if r.cleaned_data:
                    try:
                        parsed_cleaned = json.loads(r.cleaned_data)
                    except (json.JSONDecodeError, TypeError):
                        pass
                results.append({
                    "id": r.id,
                    "title": r.title,
                    "content": r.content,
                    "cleaned_data": parsed_cleaned,
                    "received_at": r.received_at.isoformat() if r.received_at else None,
                })
            return results

    def get_news_count(self) -> int:
        """Return total number of news rows."""
        with self.Session() as session:
            return session.query(func.count(News.id)).scalar() or 0

    def get_news_by_id(self, news_id: int) -> Optional[dict[str, Any]]:
        """Return a single news record (with parsed cleaned_data) or ``None``."""
        with self.Session() as session:
            r = session.get(News, news_id)
            if r is None:
                return None
            parsed_cleaned = None
            if r.cleaned_data:
                try:
                    parsed_cleaned = json.loads(r.cleaned_data)
                except (json.JSONDecodeError, TypeError):
                    pass
            return {
                "id": r.id,
                "title": r.title,
                "content": r.content,
                "cleaned_data": parsed_cleaned,
                "hotspots": r.hotspots,
                "keywords": r.keywords,
                "received_at": r.received_at.isoformat() if r.received_at else None,
            }

    def update_cleaned_data(
        self,
        news_id: int,
        cleaned_data: str,
        hotspots: Optional[str] = None,
        keywords: Optional[str] = None,
    ) -> bool:
        """Update the cleaned_data (and optionally hotspots/keywords) for a news row.

        Returns ``True`` if the row was found and updated.
        """
        with self.Session() as session:
            r = session.get(News, news_id)
            if r is None:
                return False
            r.cleaned_data = cleaned_data
            if hotspots is not None:
                r.hotspots = hotspots
            if keywords is not None:
                r.keywords = keywords
            session.commit()
            return True

    def get_news_by_date(self, date: str, limit: int = 20) -> list[dict[str, Any]]:
        """Return news whose ``received_at`` starts with *date* (YYYY-MM-DD).

        Used by the AI analysis pipeline.
        """
        with self.Session() as session:
            rows = (
                session.query(News)
                .filter(func.cast(News.received_at, Text).like(f"{date}%"))
                .order_by(News.id.desc())
                .limit(limit)
                .all()
            )
            return [
                {"id": r.id, "title": r.title, "content": r.content}
                for r in rows
            ]

    def get_recent_news_for_task(self, limit: int = 20) -> list[dict[str, Any]]:
        """Return the latest news rows (id, title, content[:200]) for the scheduled task."""
        with self.Session() as session:
            rows = (
                session.query(News)
                .order_by(News.id.desc())
                .limit(limit)
                .all()
            )
            return [
                {"id": r.id, "title": r.title, "content": (r.content or "")[:200]}
                for r in rows
            ]

    def get_hotspot_stats(self, top_n: int = 20) -> list[tuple[str, int]]:
        """Aggregate hotspot keywords across all news and return the *top_n* most common."""
        with self.Session() as session:
            rows = (
                session.query(News.hotspots)
                .filter(News.hotspots.isnot(None))
                .all()
            )
        counter: Counter = Counter()
        for (hotspots_str,) in rows:
            if hotspots_str:
                for kw in hotspots_str.split(","):
                    kw = kw.strip()
                    if kw:
                        counter[kw] += 1
        return counter.most_common(top_n)

    # ----------------------------------------------------------
    # analysis_results table
    # ----------------------------------------------------------

    def insert_analysis(
        self,
        date: str,
        input_count: int,
        analysis_summary: str = "",
        opportunities: Optional[list | str] = None,
    ) -> int:
        """Insert an analysis result and return its id.

        *opportunities* may be a Python list (will be JSON-serialised)
        or a pre-serialised JSON string.
        """
        if isinstance(opportunities, list):
            opps_json = json.dumps(opportunities, ensure_ascii=False)
        elif opportunities is None:
            opps_json = "[]"
        else:
            opps_json = opportunities

        with self.Session() as session:
            row = AnalysisResult(
                date=date,
                input_count=input_count,
                analysis_summary=analysis_summary,
                opportunities=opps_json,
            )
            session.add(row)
            session.commit()
            return row.id

    def get_analysis_by_id(self, analysis_id: int) -> Optional[dict[str, Any]]:
        """Return a single analysis result or ``None``."""
        with self.Session() as session:
            r = session.get(AnalysisResult, analysis_id)
            if r is None:
                return None
            opps: list = []
            if r.opportunities:
                try:
                    opps = json.loads(r.opportunities)
                except (json.JSONDecodeError, TypeError):
                    pass
            return {
                "id": r.id,
                "date": r.date,
                "input_count": r.input_count,
                "analysis_summary": r.analysis_summary,
                "opportunities": opps,
                "analyzed_at": r.analyzed_at.isoformat() if r.analyzed_at else None,
            }

    # ----------------------------------------------------------
    # rss_items table
    # ----------------------------------------------------------

    def insert_rss_item(
        self,
        title: str,
        link: Optional[str] = None,
        summary: Optional[str] = None,
        published: Optional[str] = None,
        source: Optional[str] = None,
        category: Optional[str] = None,
    ) -> Optional[int]:
        """Insert an RSS item.  Returns the id, or ``None`` if the link already exists."""
        with self.Session() as session:
            # Check for duplicate link at the application level so we can
            # return None gracefully instead of raising an IntegrityError.
            if link:
                exists = (
                    session.query(RssItem.id)
                    .filter(RssItem.link == link)
                    .first()
                )
                if exists:
                    return None
            row = RssItem(
                title=title,
                link=link,
                summary=summary,
                published=published,
                source=source,
                category=category,
            )
            session.add(row)
            session.commit()
            return row.id

    def get_rss_items(self, limit: int = 50) -> list[dict[str, Any]]:
        """Return the most recent RSS items, newest first."""
        with self.Session() as session:
            rows = (
                session.query(RssItem)
                .order_by(RssItem.fetched_at.desc(), RssItem.id.desc())
                .limit(limit)
                .all()
            )
            return [
                {
                    "id": r.id,
                    "title": r.title,
                    "link": r.link,
                    "summary": r.summary,
                    "published": r.published,
                    "source": r.source,
                    "category": r.category,
                    "fetched_at": r.fetched_at.isoformat() if r.fetched_at else None,
                    "sentiment_score": r.sentiment_score,
                    "ai_summary": r.ai_summary,
                    "analyzed_at": r.analyzed_at.isoformat() if r.analyzed_at else None,
                }
                for r in rows
            ]

    def get_rss_recent_titles(self, hours: int = 24) -> list[str]:
        """Return RSS titles fetched within the last *hours* hours.

        Works with both SQLite (``datetime('now', ...)`` ) and
        PostgreSQL (``now() - interval``).  We use the
        database-agnostic approach of computing the cutoff in Python.
        """
        cutoff = _utcnow() - timedelta(hours=hours)
        with self.Session() as session:
            rows = (
                session.query(RssItem.title)
                .filter(RssItem.fetched_at > cutoff)
                .all()
            )
            return [r.title for r in rows]

    def update_rss_sentiment(
        self,
        rss_id: int,
        sentiment_score: float,
        ai_summary: Optional[str] = None,
    ) -> bool:
        """Update sentiment fields on an RSS item.  Returns ``True`` if the row existed."""
        with self.Session() as session:
            r = session.get(RssItem, rss_id)
            if r is None:
                return False
            r.sentiment_score = sentiment_score
            r.ai_summary = ai_summary
            r.analyzed_at = _utcnow()
            session.commit()
            return True

    def get_unanalyzed_rss(self, limit: int = 10) -> list[dict[str, Any]]:
        """Return RSS items that have not yet been sentiment-analysed."""
        with self.Session() as session:
            rows = (
                session.query(RssItem)
                .filter(RssItem.sentiment_score.is_(None))
                .order_by(RssItem.fetched_at.desc())
                .limit(limit)
                .all()
            )
            return [
                {
                    "id": r.id,
                    "title": r.title,
                    "summary": r.summary,
                    "source": r.source,
                    "category": r.category,
                    "published": r.published,
                }
                for r in rows
            ]

    def get_rss_sentiment_stats(self) -> dict[str, Any]:
        """Return sentiment analysis statistics for RSS items."""
        with self.Session() as session:
            analyzed = (
                session.query(func.count(RssItem.id))
                .filter(RssItem.sentiment_score.isnot(None))
                .scalar() or 0
            )
            pending = (
                session.query(func.count(RssItem.id))
                .filter(RssItem.sentiment_score.is_(None))
                .scalar() or 0
            )

            # Distribution: positive / neutral / negative
            distribution: dict[str, int] = {}
            rows = (
                session.query(RssItem.sentiment_score)
                .filter(RssItem.sentiment_score.isnot(None))
                .all()
            )
            for (score,) in rows:
                if score > 0.3:
                    label = "positive"
                elif score < -0.3:
                    label = "negative"
                else:
                    label = "neutral"
                distribution[label] = distribution.get(label, 0) + 1

            return {
                "analyzed_count": analyzed,
                "pending_count": pending,
                "distribution": distribution,
            }

    # ----------------------------------------------------------
    # Health check
    # ----------------------------------------------------------

    def health_check(self) -> bool:
        """Return ``True`` if the database is reachable."""
        try:
            with self.Session() as session:
                session.execute(text("SELECT 1"))
            return True
        except Exception:
            return False
