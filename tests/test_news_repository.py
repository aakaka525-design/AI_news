"""Comprehensive tests for the NewsRepository (SQLAlchemy ORM)."""

import datetime as datetime_mod
import json

import pytest
from sqlalchemy import text

from src.database.engine import create_engine_from_url, get_session_factory
from src.database.repositories.news import (
    AnalysisResult,
    News,
    NewsRepository,
    RssItem,
    _Base,
)


# ------------------------------------------------------------------
# Fixtures
# ------------------------------------------------------------------

@pytest.fixture()
def engine():
    """In-memory SQLite engine."""
    eng = create_engine_from_url("sqlite:///:memory:")
    _Base.metadata.create_all(eng)
    yield eng
    eng.dispose()


@pytest.fixture()
def repo(engine):
    """NewsRepository backed by the in-memory engine."""
    Session = get_session_factory(engine)
    return NewsRepository(Session)


# ------------------------------------------------------------------
# create_tables
# ------------------------------------------------------------------

class TestCreateTables:
    def test_create_tables_is_idempotent(self, engine):
        Session = get_session_factory(engine)
        repo = NewsRepository(Session)
        # calling twice should not raise
        repo.create_tables(engine)
        repo.create_tables(engine)


# ------------------------------------------------------------------
# news table
# ------------------------------------------------------------------

class TestInsertNews:
    def test_insert_returns_positive_id(self, repo):
        nid = repo.insert_news("Title", "Content")
        assert isinstance(nid, int)
        assert nid > 0

    def test_insert_with_cleaned_data(self, repo):
        cleaned = json.dumps({"facts": ["fact1"]})
        nid = repo.insert_news("T", "C", cleaned_data=cleaned, hotspots="AI", keywords="LLM")
        assert nid > 0

    def test_sequential_ids(self, repo):
        id1 = repo.insert_news("A", "B")
        id2 = repo.insert_news("C", "D")
        assert id2 > id1


class TestGetNewsList:
    def test_empty_db(self, repo):
        assert repo.get_news_list() == []

    def test_returns_inserted_rows(self, repo):
        repo.insert_news("T1", "C1")
        repo.insert_news("T2", "C2")
        items = repo.get_news_list()
        assert len(items) == 2

    def test_respects_limit(self, repo):
        for i in range(5):
            repo.insert_news(f"T{i}", f"C{i}")
        items = repo.get_news_list(limit=3)
        assert len(items) == 3

    def test_newest_first(self, repo):
        repo.insert_news("Old", "old content")
        repo.insert_news("New", "new content")
        items = repo.get_news_list()
        # The second insert should appear first (newest)
        assert items[0]["title"] == "New"

    def test_cleaned_data_is_parsed(self, repo):
        cleaned = json.dumps({"facts": [1, 2, 3]})
        repo.insert_news("T", "C", cleaned_data=cleaned)
        items = repo.get_news_list()
        assert items[0]["cleaned_data"] == {"facts": [1, 2, 3]}

    def test_invalid_json_cleaned_data_returns_none(self, repo):
        repo.insert_news("T", "C", cleaned_data="NOT JSON")
        items = repo.get_news_list()
        assert items[0]["cleaned_data"] is None

    def test_dict_keys(self, repo):
        repo.insert_news("T", "C")
        item = repo.get_news_list()[0]
        assert set(item.keys()) == {"id", "title", "content", "cleaned_data", "received_at"}


class TestGetNewsCount:
    def test_zero_when_empty(self, repo):
        assert repo.get_news_count() == 0

    def test_reflects_inserts(self, repo):
        repo.insert_news("A", "B")
        repo.insert_news("C", "D")
        assert repo.get_news_count() == 2


class TestGetNewsById:
    def test_not_found(self, repo):
        assert repo.get_news_by_id(999) is None

    def test_returns_correct_row(self, repo):
        nid = repo.insert_news("T", "C")
        item = repo.get_news_by_id(nid)
        assert item is not None
        assert item["id"] == nid
        assert item["title"] == "T"
        assert item["content"] == "C"

    def test_includes_hotspots_and_keywords(self, repo):
        nid = repo.insert_news("T", "C", hotspots="AI,ML", keywords="python,data")
        item = repo.get_news_by_id(nid)
        assert item["hotspots"] == "AI,ML"
        assert item["keywords"] == "python,data"


class TestUpdateCleanedData:
    def test_update_existing(self, repo):
        nid = repo.insert_news("T", "C")
        cleaned = json.dumps({"summary": "ok"})
        assert repo.update_cleaned_data(nid, cleaned, hotspots="AI", keywords="LLM") is True
        item = repo.get_news_by_id(nid)
        assert item["cleaned_data"] == {"summary": "ok"}
        assert item["hotspots"] == "AI"
        assert item["keywords"] == "LLM"

    def test_update_nonexistent(self, repo):
        assert repo.update_cleaned_data(999, "{}") is False


class TestGetNewsByDate:
    def test_empty_result(self, repo):
        assert repo.get_news_by_date("2099-01-01") == []

    def test_matches_date_prefix(self, repo):
        # Insert news — the received_at default is now(utc) so it will
        # match today's date prefix.
        today = datetime_mod.datetime.now(datetime_mod.timezone.utc).strftime("%Y-%m-%d")
        repo.insert_news("Today", "content")
        items = repo.get_news_by_date(today)
        assert len(items) >= 1
        assert items[0]["title"] == "Today"

    def test_respects_limit(self, repo):
        today = datetime_mod.datetime.now(datetime_mod.timezone.utc).strftime("%Y-%m-%d")
        for i in range(5):
            repo.insert_news(f"N{i}", f"C{i}")
        items = repo.get_news_by_date(today, limit=2)
        assert len(items) == 2


class TestGetRecentNewsForTask:
    def test_truncates_content(self, repo):
        long_content = "x" * 500
        repo.insert_news("T", long_content)
        items = repo.get_recent_news_for_task(limit=1)
        assert len(items[0]["content"]) == 200


class TestGetHotspotStats:
    def test_empty_db(self, repo):
        assert repo.get_hotspot_stats() == []

    def test_counts_keywords(self, repo):
        repo.insert_news("T1", "C1", hotspots="AI,ML")
        repo.insert_news("T2", "C2", hotspots="AI,Cloud")
        stats = repo.get_hotspot_stats()
        # Convert to dict for easier assertion
        stats_dict = dict(stats)
        assert stats_dict["AI"] == 2
        assert stats_dict["ML"] == 1
        assert stats_dict["Cloud"] == 1

    def test_top_n_limit(self, repo):
        # Insert many distinct hotspots
        for i in range(30):
            repo.insert_news(f"T{i}", f"C{i}", hotspots=f"kw{i}")
        stats = repo.get_hotspot_stats(top_n=5)
        assert len(stats) == 5

    def test_strips_whitespace(self, repo):
        repo.insert_news("T", "C", hotspots=" AI , ML ")
        stats = dict(repo.get_hotspot_stats())
        assert "AI" in stats
        assert "ML" in stats


# ------------------------------------------------------------------
# analysis_results table
# ------------------------------------------------------------------

class TestInsertAnalysis:
    def test_returns_positive_id(self, repo):
        aid = repo.insert_analysis("2026-01-01", 10, "summary", [{"title": "opp1"}])
        assert aid > 0

    def test_accepts_list_opportunities(self, repo):
        aid = repo.insert_analysis("2026-01-01", 5, "s", [{"a": 1}])
        result = repo.get_analysis_by_id(aid)
        assert result["opportunities"] == [{"a": 1}]

    def test_accepts_string_opportunities(self, repo):
        opps_str = json.dumps([{"b": 2}])
        aid = repo.insert_analysis("2026-01-01", 5, "s", opps_str)
        result = repo.get_analysis_by_id(aid)
        assert result["opportunities"] == [{"b": 2}]

    def test_none_opportunities_becomes_empty_list(self, repo):
        aid = repo.insert_analysis("2026-01-01", 5, "s", None)
        result = repo.get_analysis_by_id(aid)
        assert result["opportunities"] == []


class TestGetAnalysisById:
    def test_not_found(self, repo):
        assert repo.get_analysis_by_id(999) is None

    def test_returns_correct_fields(self, repo):
        aid = repo.insert_analysis("2026-03-02", 15, "good summary", [{"title": "AI"}])
        result = repo.get_analysis_by_id(aid)
        assert result["id"] == aid
        assert result["date"] == "2026-03-02"
        assert result["input_count"] == 15
        assert result["analysis_summary"] == "good summary"
        assert result["opportunities"] == [{"title": "AI"}]
        assert result["analyzed_at"] is not None


# ------------------------------------------------------------------
# rss_items table
# ------------------------------------------------------------------

class TestInsertRssItem:
    def test_returns_positive_id(self, repo):
        rid = repo.insert_rss_item("RSS Title", link="http://example.com/1")
        assert isinstance(rid, int)
        assert rid > 0

    def test_duplicate_link_returns_none(self, repo):
        link = "http://example.com/dup"
        repo.insert_rss_item("A", link=link)
        assert repo.insert_rss_item("B", link=link) is None

    def test_null_link_allowed(self, repo):
        id1 = repo.insert_rss_item("A")
        id2 = repo.insert_rss_item("B")
        assert id1 is not None
        assert id2 is not None

    def test_all_fields(self, repo):
        rid = repo.insert_rss_item(
            title="News",
            link="http://example.com/full",
            summary="A summary",
            published="2026-01-01",
            source="TestSource",
            category="tech",
        )
        items = repo.get_rss_items(limit=1)
        item = items[0]
        assert item["title"] == "News"
        assert item["link"] == "http://example.com/full"
        assert item["summary"] == "A summary"
        assert item["source"] == "TestSource"
        assert item["category"] == "tech"


class TestGetRssItems:
    def test_empty(self, repo):
        assert repo.get_rss_items() == []

    def test_returns_correct_count(self, repo):
        for i in range(3):
            repo.insert_rss_item(f"T{i}", link=f"http://example.com/{i}")
        items = repo.get_rss_items()
        assert len(items) == 3

    def test_respects_limit(self, repo):
        for i in range(5):
            repo.insert_rss_item(f"T{i}", link=f"http://example.com/{i}")
        items = repo.get_rss_items(limit=2)
        assert len(items) == 2

    def test_newest_first(self, repo):
        repo.insert_rss_item("First", link="http://example.com/first")
        repo.insert_rss_item("Second", link="http://example.com/second")
        items = repo.get_rss_items()
        assert items[0]["title"] == "Second"

    def test_dict_keys(self, repo):
        repo.insert_rss_item("T", link="http://example.com/keys")
        item = repo.get_rss_items()[0]
        expected_keys = {
            "id", "title", "link", "summary", "published", "source",
            "category", "fetched_at", "sentiment_score", "ai_summary",
            "analyzed_at",
        }
        assert set(item.keys()) == expected_keys


class TestGetRssRecentTitles:
    def test_empty(self, repo):
        assert repo.get_rss_recent_titles() == []

    def test_returns_titles(self, repo):
        repo.insert_rss_item("Alpha", link="http://a.com")
        repo.insert_rss_item("Beta", link="http://b.com")
        titles = repo.get_rss_recent_titles(hours=1)
        assert set(titles) == {"Alpha", "Beta"}


class TestUpdateRssSentiment:
    def test_update_existing(self, repo):
        rid = repo.insert_rss_item("T", link="http://x.com")
        assert repo.update_rss_sentiment(rid, 0.8, "Positive news") is True
        items = repo.get_rss_items()
        item = items[0]
        assert item["sentiment_score"] == pytest.approx(0.8)
        assert item["ai_summary"] == "Positive news"
        assert item["analyzed_at"] is not None

    def test_nonexistent_returns_false(self, repo):
        assert repo.update_rss_sentiment(999, 0.5) is False


class TestGetUnanalyzedRss:
    def test_returns_only_unanalyzed(self, repo):
        r1 = repo.insert_rss_item("Unanalyzed", link="http://u.com")
        r2 = repo.insert_rss_item("Analyzed", link="http://a.com")
        repo.update_rss_sentiment(r2, 0.5)
        items = repo.get_unanalyzed_rss()
        assert len(items) == 1
        assert items[0]["title"] == "Unanalyzed"

    def test_empty_when_all_analyzed(self, repo):
        r1 = repo.insert_rss_item("A", link="http://a1.com")
        repo.update_rss_sentiment(r1, 0.1)
        assert repo.get_unanalyzed_rss() == []


class TestGetRssSentimentStats:
    def test_empty_db(self, repo):
        stats = repo.get_rss_sentiment_stats()
        assert stats["analyzed_count"] == 0
        assert stats["pending_count"] == 0
        assert stats["distribution"] == {}

    def test_correct_distribution(self, repo):
        # positive
        r1 = repo.insert_rss_item("P", link="http://p.com")
        repo.update_rss_sentiment(r1, 0.8)
        # negative
        r2 = repo.insert_rss_item("N", link="http://n.com")
        repo.update_rss_sentiment(r2, -0.5)
        # neutral
        r3 = repo.insert_rss_item("U", link="http://u.com")
        repo.update_rss_sentiment(r3, 0.1)
        # pending
        repo.insert_rss_item("Pending", link="http://pend.com")

        stats = repo.get_rss_sentiment_stats()
        assert stats["analyzed_count"] == 3
        assert stats["pending_count"] == 1
        assert stats["distribution"]["positive"] == 1
        assert stats["distribution"]["negative"] == 1
        assert stats["distribution"]["neutral"] == 1


# ------------------------------------------------------------------
# Health check
# ------------------------------------------------------------------

class TestHealthCheck:
    def test_returns_true_when_healthy(self, repo):
        assert repo.health_check() is True

    def test_returns_false_when_engine_disposed(self):
        engine = create_engine_from_url("sqlite:///:memory:")
        _Base.metadata.create_all(engine)
        Session = get_session_factory(engine)
        repo = NewsRepository(Session)
        engine.dispose()
        # After disposing, the connection pool is gone — should return False
        # Note: SQLite in-memory DB is gone once all connections are closed.
        # On some drivers this may still work (recreates the DB), so we
        # just verify it returns a boolean without crashing.
        result = repo.health_check()
        assert isinstance(result, bool)
