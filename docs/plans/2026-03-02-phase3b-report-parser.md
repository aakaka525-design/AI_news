# Phase 3B: 研报解析增强 Implementation Plan

> **状态：部分完成**
> `src/ai_engine/report_parser.py` 及测试已存在并通过，但当前实现仍保留 `get_connection()` 直连痕迹，未完全达到计划中"repository 化"的目标。

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Modernize the research report parsing pipeline with full test coverage, SQLAlchemy repository, LLM integration, and structured field population.

**Architecture:** Replace raw sqlite3 in `report_parser.py` with SQLAlchemy repository pattern (matching `NewsRepository`). Keep pure rule-based extraction functions testable and DB-free. Wire async LLM analysis into the pipeline with proper mocking for tests. Consolidate legacy fetcher wrapper into modern code.

**Tech Stack:** SQLAlchemy ORM, pytest, openai (async), httpx, pydantic

---

### Existing Code Summary

**`src/ai_engine/report_parser.py`** (372 lines):
- `extract_target_price_from_title(title)` → regex, 5 patterns, returns `float | None`
- `extract_rating_change(title)` → regex, 6 patterns, returns `str | None`
- `extract_key_points(title)` → regex, 7 categories, returns `list[str]`
- `analyze_report_rule_based(report)` → aggregator, returns dict with target_price/rating_change/key_points/sentiment
- `analyze_report_with_llm(report)` → async, uses DeepSeek/OpenAI, returns dict with core_logic/catalysts/risks/sentiment_score
- `analyze_recent_reports(limit)` → batch, uses raw sqlite3, returns list[dict]
- `save_report_analysis(stock_code, analysis)` → raw sqlite3 UPDATE
- `get_reports_with_target_price()` → raw sqlite3 query
- Uses `src.database.connection.get_connection()` (raw sqlite3)

**`legacy_archive/fetchers/research_report.py`** (332 lines):
- `fetch_stock_reports(stock_code)` → AkShare `ak.stock_research_report_em()`, returns list[dict]
- `save_reports(reports)` → raw sqlite3 INSERT OR REPLACE
- `fetch_hot_stock_reports(limit)` → multi-source hot stock identification + batch fetch
- `get_latest_reports(limit)`, `get_stock_reports(stock_code, limit)`, `get_rating_stats()`
- Uses hardcoded sqlite3 path

**`fetchers/research_report.py`** — just a wrapper: `from legacy_archive.fetchers.research_report import *`

**`src/database/models.py:374-416`** — `ResearchReport` SQLAlchemy model with fields:
- `ts_code`, `stock_name`, `title`, `institution`, `analyst`
- `rating`, `rating_change`, `target_price`, `target_price_change`
- `content`, `summary`, `key_points` (JSON)
- `embedding` (JSON), `sentiment_score` (Numeric 4,3)
- `publish_date` (String 8)

**`src/database/engine.py`** — `create_engine_from_url()`, `get_session_factory()`

**`src/database/repositories/news.py`** — Reference pattern for repository implementation.

---

### Task 1: Unit Tests for Rule-Based Extraction

**Files:**
- Create: `tests/test_report_parser.py`

**Step 1: Write the failing tests**

```python
"""Tests for research report rule-based extraction."""

import pytest

from src.ai_engine.report_parser import (
    extract_target_price_from_title,
    extract_rating_change,
    extract_key_points,
    analyze_report_rule_based,
)


class TestExtractTargetPrice:
    def test_target_price_colon_yuan(self):
        assert extract_target_price_from_title("看好公司前景，目标价：35.5元") == 35.5

    def test_target_price_target_colon_yuan(self):
        assert extract_target_price_from_title("首次覆盖，目标：120元") == 120.0

    def test_target_price_yuan_suffix(self):
        assert extract_target_price_from_title("上调至88.8元目标") == 88.8

    def test_target_price_raise_to(self):
        assert extract_target_price_from_title("上调目标价至45.6") == 45.6

    def test_target_price_bare(self):
        assert extract_target_price_from_title("维持买入评级，目标价52") == 52.0

    def test_no_target_price(self):
        assert extract_target_price_from_title("业绩超预期，维持增持") is None

    def test_empty_string(self):
        assert extract_target_price_from_title("") is None

    def test_none_input(self):
        assert extract_target_price_from_title(None) is None


class TestExtractRatingChange:
    def test_first_coverage(self):
        assert extract_rating_change("首次覆盖：看好长期发展") == "首次覆盖"

    def test_upgrade(self):
        assert extract_rating_change("上调评级至买入") == "上调评级"

    def test_downgrade(self):
        assert extract_rating_change("下调评级至中性") == "下调评级"

    def test_maintain_buy(self):
        assert extract_rating_change("维持买入评级") == "维持买入"

    def test_maintain_overweight(self):
        assert extract_rating_change("维持增持评级") == "维持增持"

    def test_reiterate_buy(self):
        assert extract_rating_change("重申买入评级") == "重申买入"

    def test_no_rating_change(self):
        assert extract_rating_change("业绩快报点评") is None

    def test_none_input(self):
        assert extract_rating_change(None) is None


class TestExtractKeyPoints:
    def test_performance_beat(self):
        points = extract_key_points("业绩超预期，增长强劲")
        assert "业绩点评" in points

    def test_growth(self):
        points = extract_key_points("收入高增，毛利率提升")
        assert "增长亮点" in points

    def test_capital_operation(self):
        points = extract_key_points("拟定增募资20亿元")
        assert "资本运作" in points

    def test_new_product(self):
        points = extract_key_points("新品发布，打开增长空间")
        assert "新品发布" in points

    def test_order_win(self):
        points = extract_key_points("中标10亿元大订单")
        assert "订单获取" in points

    def test_valuation(self):
        points = extract_key_points("估值底部，投资价值凸显")
        assert "估值分析" in points

    def test_multiple_points(self):
        points = extract_key_points("业绩超预期，高增长，中标大订单")
        assert len(points) >= 2

    def test_no_points(self):
        assert extract_key_points("公司调研纪要") == []

    def test_none_input(self):
        assert extract_key_points(None) == []


class TestAnalyzeReportRuleBased:
    def test_positive_sentiment(self):
        report = {"report_title": "目标价：50元，业绩超预期", "rating": "买入"}
        result = analyze_report_rule_based(report)
        assert result["target_price"] == 50.0
        assert result["sentiment"] == "positive"
        assert "业绩点评" in result["key_points"]

    def test_neutral_sentiment(self):
        report = {"report_title": "符合预期", "rating": "持有"}
        result = analyze_report_rule_based(report)
        assert result["sentiment"] == "neutral"

    def test_negative_sentiment(self):
        report = {"report_title": "下调评级", "rating": "减持"}
        result = analyze_report_rule_based(report)
        assert result["sentiment"] == "negative"
        assert result["rating_change"] == "下调评级"

    def test_missing_fields(self):
        result = analyze_report_rule_based({})
        assert result["target_price"] is None
        assert result["rating_change"] is None
        assert result["key_points"] == []
        assert result["sentiment"] == "negative"  # empty rating → negative
```

**Step 2: Run tests to verify they pass** (these test existing code)

Run: `python -m pytest tests/test_report_parser.py -v`
Expected: ALL PASS (testing existing functions)

**Step 3: Commit**

```bash
git add tests/test_report_parser.py
git commit -m "test: add unit tests for rule-based report extraction"
```

---

### Task 2: Add Risk Extraction + Enhance Rule Patterns

**Files:**
- Modify: `src/ai_engine/report_parser.py:122-149`
- Modify: `tests/test_report_parser.py`

**Step 1: Write failing tests for risk extraction**

Add to `tests/test_report_parser.py`:

```python
from src.ai_engine.report_parser import extract_risk_factors


class TestExtractRiskFactors:
    def test_policy_risk(self):
        factors = extract_risk_factors("政策风险可控，维持买入")
        assert "政策风险" in factors

    def test_competition_risk(self):
        factors = extract_risk_factors("竞争加剧，关注盈利压力")
        assert "竞争风险" in factors

    def test_demand_risk(self):
        factors = extract_risk_factors("下游需求不及预期")
        assert "需求风险" in factors

    def test_cost_risk(self):
        factors = extract_risk_factors("原材料成本上升压力")
        assert "成本风险" in factors

    def test_no_risk(self):
        assert extract_risk_factors("业绩超预期") == []

    def test_none_input(self):
        assert extract_risk_factors(None) == []
```

**Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_report_parser.py::TestExtractRiskFactors -v`
Expected: FAIL with `ImportError: cannot import name 'extract_risk_factors'`

**Step 3: Implement extract_risk_factors**

Add to `src/ai_engine/report_parser.py` after `extract_key_points`:

```python
def extract_risk_factors(title: str) -> list[str]:
    """
    从研报标题提取风险因素

    Args:
        title: 研报标题

    Returns:
        风险因素列表
    """
    if not title:
        return []

    factors = []

    if re.search(r'政策.*?风险|监管.*?风险', title):
        factors.append('政策风险')
    if re.search(r'竞争.*?(加剧|风险|压力)', title):
        factors.append('竞争风险')
    if re.search(r'(需求|下游).*?(不及|下滑|放缓|风险)', title):
        factors.append('需求风险')
    if re.search(r'(成本|原材料).*?(上升|上涨|压力|风险)', title):
        factors.append('成本风险')
    if re.search(r'(汇率|汇兑).*?(波动|风险)', title):
        factors.append('汇率风险')
    if re.search(r'(技术|研发).*?(风险|不确定)', title):
        factors.append('技术风险')

    return factors
```

Also update `analyze_report_rule_based` to include risk_factors:

```python
def analyze_report_rule_based(report: dict) -> dict:
    title = report.get('report_title', '')
    rating = report.get('rating', '')

    analysis = {
        'target_price': extract_target_price_from_title(title),
        'rating_change': extract_rating_change(title),
        'key_points': extract_key_points(title),
        'risk_factors': extract_risk_factors(title),
        'rating': rating,
        'sentiment': 'positive' if rating in ['买入', '增持'] else ('neutral' if rating in ['持有', '中性'] else 'negative'),
    }

    return analysis
```

**Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_report_parser.py -v`
Expected: ALL PASS

**Step 5: Commit**

```bash
git add src/ai_engine/report_parser.py tests/test_report_parser.py
git commit -m "feat: add risk factor extraction to report parser"
```

---

### Task 3: Create ReportRepository (SQLAlchemy)

**Files:**
- Create: `src/database/repositories/report.py`
- Create: `tests/test_report_repository.py`

**Step 1: Write failing tests**

```python
"""Tests for ReportRepository."""

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.database.repositories.report import ReportRepository


@pytest.fixture()
def repo(tmp_path):
    """Create a ReportRepository backed by in-memory SQLite."""
    db_url = f"sqlite:///{tmp_path / 'test.db'}"
    engine = create_engine(db_url)
    Session = sessionmaker(bind=engine)
    repository = ReportRepository(Session)
    repository.create_tables(engine)
    return repository


class TestReportRepositoryUpsert:
    def test_upsert_single_report(self, repo):
        report = {
            "ts_code": "000001.SZ",
            "stock_name": "平安银行",
            "title": "业绩超预期，维持买入",
            "institution": "中信证券",
            "rating": "买入",
            "publish_date": "20260301",
        }
        repo.upsert_report(report)
        reports = repo.get_reports(ts_code="000001.SZ")
        assert len(reports) == 1
        assert reports[0]["title"] == "业绩超预期，维持买入"

    def test_upsert_updates_existing(self, repo):
        report = {
            "ts_code": "000001.SZ",
            "stock_name": "平安银行",
            "title": "旧标题",
            "institution": "中信证券",
            "rating": "增持",
            "publish_date": "20260301",
        }
        repo.upsert_report(report)
        report["title"] = "新标题"
        report["rating"] = "买入"
        repo.upsert_report(report)
        reports = repo.get_reports(ts_code="000001.SZ")
        assert len(reports) == 1
        assert reports[0]["title"] == "新标题"
        assert reports[0]["rating"] == "买入"


class TestReportRepositoryQuery:
    def test_get_reports_by_code(self, repo):
        for i in range(3):
            repo.upsert_report({
                "ts_code": "000001.SZ",
                "stock_name": "平安银行",
                "title": f"报告{i}",
                "institution": f"机构{i}",
                "rating": "买入",
                "publish_date": f"2026030{i+1}",
            })
        reports = repo.get_reports(ts_code="000001.SZ", limit=2)
        assert len(reports) == 2

    def test_get_latest_reports(self, repo):
        for code in ["000001.SZ", "600519.SH"]:
            repo.upsert_report({
                "ts_code": code,
                "stock_name": "测试",
                "title": f"{code}报告",
                "institution": "中信证券",
                "rating": "买入",
                "publish_date": "20260301",
            })
        reports = repo.get_reports(limit=10)
        assert len(reports) == 2

    def test_get_rating_stats(self, repo):
        for rating in ["买入", "买入", "增持", "中性"]:
            repo.upsert_report({
                "ts_code": "000001.SZ",
                "stock_name": "测试",
                "title": f"{rating}报告",
                "institution": f"{rating}机构",
                "rating": rating,
                "publish_date": "20260301",
            })
        stats = repo.get_rating_stats()
        assert stats["买入"] == 2
        assert stats["增持"] == 1


class TestReportRepositoryAnalysis:
    def test_save_analysis_fields(self, repo):
        repo.upsert_report({
            "ts_code": "000001.SZ",
            "stock_name": "平安银行",
            "title": "目标价：50元",
            "institution": "中信证券",
            "rating": "买入",
            "publish_date": "20260301",
        })
        repo.save_analysis(
            ts_code="000001.SZ",
            publish_date="20260301",
            institution="中信证券",
            analysis={
                "target_price": 50.0,
                "rating_change": None,
                "key_points": ["业绩点评"],
                "risk_factors": [],
                "sentiment": "positive",
                "summary": "看好长期发展",
                "sentiment_score": 0.85,
            },
        )
        reports = repo.get_reports(ts_code="000001.SZ")
        r = reports[0]
        assert r["target_price"] == 50.0
        assert r["key_points"] == ["业绩点评"]
        assert r["summary"] == "看好长期发展"
        assert float(r["sentiment_score"]) == pytest.approx(0.85, abs=0.01)
```

**Step 2: Run to verify it fails**

Run: `python -m pytest tests/test_report_repository.py -v`
Expected: FAIL with `ModuleNotFoundError`

**Step 3: Implement ReportRepository**

Create `src/database/repositories/report.py`:

```python
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

from typing import Any, Optional

from sqlalchemy import func, text
from sqlalchemy.orm import sessionmaker

from src.database.models import ResearchReport, Base


class ReportRepository:
    """CRUD operations for the research_report table."""

    def __init__(self, session_factory: sessionmaker):
        self._Session = session_factory

    def create_tables(self, engine) -> None:
        """Create the research_report table if it doesn't exist."""
        ResearchReport.__table__.create(bind=engine, checkfirst=True)

    def upsert_report(self, data: dict[str, Any]) -> None:
        """Insert or update a research report."""
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
                report = ResearchReport(**{
                    k: v for k, v in data.items()
                    if hasattr(ResearchReport, k)
                })
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
```

**Step 4: Run tests**

Run: `python -m pytest tests/test_report_repository.py -v`
Expected: ALL PASS

**Step 5: Commit**

```bash
git add src/database/repositories/report.py tests/test_report_repository.py
git commit -m "feat: add ReportRepository with SQLAlchemy ORM"
```

---

### Task 4: LLM Analysis Integration with Mock Tests

**Files:**
- Modify: `tests/test_report_parser.py`
- Modify: `src/ai_engine/report_parser.py`

**Step 1: Write failing tests for LLM integration**

Add to `tests/test_report_parser.py`:

```python
from unittest.mock import AsyncMock, MagicMock, patch

from src.ai_engine.report_parser import analyze_report_with_llm


class TestAnalyzeReportWithLLM:
    @pytest.mark.asyncio
    async def test_returns_none_without_api_key(self):
        with patch.dict("os.environ", {}, clear=True):
            result = await analyze_report_with_llm({"report_title": "test"})
            assert result is None

    @pytest.mark.asyncio
    async def test_successful_analysis(self):
        mock_response = MagicMock()
        mock_response.choices = [
            MagicMock(
                message=MagicMock(
                    content='{"core_logic": "增长强劲", "catalysts": ["新品"], "risks": ["竞争"], "sentiment_score": 0.8}'
                )
            )
        ]

        mock_client = AsyncMock()
        mock_client.chat.completions.create = AsyncMock(return_value=mock_response)

        with patch.dict("os.environ", {"DEEPSEEK_API_KEY": "test-key"}):
            with patch("src.ai_engine.report_parser.AsyncOpenAI", return_value=mock_client):
                result = await analyze_report_with_llm({
                    "report_title": "业绩超预期",
                    "institution": "中信证券",
                    "rating": "买入",
                })

        assert result is not None
        assert result["core_logic"] == "增长强劲"
        assert "新品" in result["catalysts"]
        assert result["sentiment_score"] == 0.8

    @pytest.mark.asyncio
    async def test_handles_api_error(self):
        mock_client = AsyncMock()
        mock_client.chat.completions.create = AsyncMock(side_effect=Exception("API error"))

        with patch.dict("os.environ", {"DEEPSEEK_API_KEY": "test-key"}):
            with patch("src.ai_engine.report_parser.AsyncOpenAI", return_value=mock_client):
                result = await analyze_report_with_llm({
                    "report_title": "test",
                    "institution": "test",
                    "rating": "买入",
                })
        assert result is None

    @pytest.mark.asyncio
    async def test_extracts_json_from_markdown(self):
        mock_response = MagicMock()
        mock_response.choices = [
            MagicMock(
                message=MagicMock(
                    content='```json\n{"core_logic": "test", "catalysts": [], "risks": [], "sentiment_score": 0.5}\n```'
                )
            )
        ]

        mock_client = AsyncMock()
        mock_client.chat.completions.create = AsyncMock(return_value=mock_response)

        with patch.dict("os.environ", {"DEEPSEEK_API_KEY": "test-key"}):
            with patch("src.ai_engine.report_parser.AsyncOpenAI", return_value=mock_client):
                result = await analyze_report_with_llm({
                    "report_title": "test",
                    "institution": "test",
                    "rating": "买入",
                })
        assert result is not None
        assert result["core_logic"] == "test"
```

**Step 2: Run tests**

Run: `python -m pytest tests/test_report_parser.py::TestAnalyzeReportWithLLM -v`
Expected: Some may FAIL if `AsyncOpenAI` import path differs

**Step 3: Fix import in report_parser.py for testability**

The existing `analyze_report_with_llm` does a lazy import `from openai import AsyncOpenAI` inside the function body. To make it mockable, move the import to module-level with a try/except:

At the top of `src/ai_engine/report_parser.py`, add:

```python
try:
    from openai import AsyncOpenAI
except ImportError:
    AsyncOpenAI = None  # type: ignore[assignment,misc]
```

Then update `analyze_report_with_llm` to check `if AsyncOpenAI is None:` instead of the try/except import block.

**Step 4: Run tests**

Run: `python -m pytest tests/test_report_parser.py -v`
Expected: ALL PASS

**Step 5: Commit**

```bash
git add src/ai_engine/report_parser.py tests/test_report_parser.py
git commit -m "feat: add LLM analysis mock tests and improve import structure"
```

---

### Task 5: Modernize report_parser.py — Replace Raw SQLite with Repository

**Files:**
- Modify: `src/ai_engine/report_parser.py:251-340`

**Goal:** Replace `analyze_recent_reports()`, `save_report_analysis()`, `get_reports_with_target_price()` to use `ReportRepository` instead of raw sqlite3. Keep backward compatibility by accepting either a `ReportRepository` instance or falling back to legacy behavior.

**Step 1: Write failing tests**

Add to `tests/test_report_parser.py`:

```python
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from src.database.repositories.report import ReportRepository
from src.ai_engine.report_parser import analyze_and_save_reports


class TestAnalyzeAndSave:
    @pytest.fixture()
    def repo(self, tmp_path):
        db_url = f"sqlite:///{tmp_path / 'test.db'}"
        engine = create_engine(db_url)
        Session = sessionmaker(bind=engine)
        repository = ReportRepository(Session)
        repository.create_tables(engine)
        return repository

    def test_analyze_and_save_populates_fields(self, repo):
        repo.upsert_report({
            "ts_code": "000001.SZ",
            "stock_name": "平安银行",
            "title": "目标价：50元，业绩超预期，维持买入",
            "institution": "中信证券",
            "rating": "买入",
            "publish_date": "20260301",
        })
        results = analyze_and_save_reports(repo)
        assert len(results) == 1
        assert results[0]["target_price"] == 50.0
        assert results[0]["sentiment"] == "positive"

        # Verify saved to DB
        reports = repo.get_reports(ts_code="000001.SZ")
        assert reports[0]["target_price"] == 50.0
        assert reports[0]["key_points"] == ["业绩点评"]

    def test_analyze_empty_repo(self, repo):
        results = analyze_and_save_reports(repo)
        assert results == []
```

**Step 2: Run to verify it fails**

Run: `python -m pytest tests/test_report_parser.py::TestAnalyzeAndSave -v`
Expected: FAIL with `ImportError: cannot import name 'analyze_and_save_reports'`

**Step 3: Implement analyze_and_save_reports**

Add to `src/ai_engine/report_parser.py`:

```python
def analyze_and_save_reports(
    repo: "ReportRepository",
    limit: int = 20,
) -> list[dict]:
    """
    Analyze reports using rule-based extraction and save results.

    Args:
        repo: ReportRepository instance
        limit: Number of reports to analyze

    Returns:
        List of analysis results
    """
    reports = repo.get_reports(limit=limit)

    results = []
    for report in reports:
        analysis = analyze_report_rule_based({
            "report_title": report.get("title", ""),
            "rating": report.get("rating", ""),
        })

        # Save structured fields
        repo.save_analysis(
            ts_code=report["ts_code"],
            publish_date=report["publish_date"],
            institution=report["institution"],
            analysis={
                "target_price": analysis["target_price"],
                "rating_change": analysis["rating_change"],
                "key_points": analysis["key_points"],
                "summary": None,
                "sentiment_score": 0.8 if analysis["sentiment"] == "positive"
                    else 0.5 if analysis["sentiment"] == "neutral"
                    else 0.2,
            },
        )

        analysis["ts_code"] = report["ts_code"]
        analysis["stock_name"] = report["stock_name"]
        analysis["title"] = report["title"]
        analysis["institution"] = report["institution"]
        analysis["publish_date"] = report["publish_date"]
        results.append(analysis)

    return results
```

**Step 4: Run tests**

Run: `python -m pytest tests/test_report_parser.py -v`
Expected: ALL PASS

**Step 5: Commit**

```bash
git add src/ai_engine/report_parser.py tests/test_report_parser.py
git commit -m "feat: add analyze_and_save_reports using ReportRepository"
```

---

### Task 6: Consolidate Legacy Fetcher

**Files:**
- Modify: `fetchers/research_report.py` (replace wrapper with modern code)
- Create: `tests/test_report_fetcher.py`

**Step 1: Write tests for the modernized fetcher**

```python
"""Tests for research report fetcher."""

import pytest
from unittest.mock import MagicMock, patch
import pandas as pd

from fetchers.research_report import parse_eastmoney_reports


class TestParseEastmoneyReports:
    def test_parse_valid_dataframe(self):
        df = pd.DataFrame({
            "股票简称": ["平安银行"],
            "报告名称": ["业绩超预期"],
            "东财评级": ["买入"],
            "机构": ["中信证券"],
            "行业": ["银行"],
            "日期": ["2026-03-01"],
        })
        reports = parse_eastmoney_reports("000001", df)
        assert len(reports) == 1
        assert reports[0]["ts_code"] == "000001.SZ"
        assert reports[0]["title"] == "业绩超预期"
        assert reports[0]["rating"] == "买入"
        assert reports[0]["institution"] == "中信证券"
        assert reports[0]["publish_date"] == "20260301"

    def test_parse_empty_dataframe(self):
        df = pd.DataFrame()
        assert parse_eastmoney_reports("000001", df) == []

    def test_parse_handles_missing_columns(self):
        df = pd.DataFrame({"报告名称": ["test"]})
        reports = parse_eastmoney_reports("000001", df)
        assert len(reports) == 1
        assert reports[0]["title"] == "test"

    def test_code_suffix_sh(self):
        df = pd.DataFrame({
            "报告名称": ["test"],
            "日期": ["2026-03-01"],
        })
        reports = parse_eastmoney_reports("600519", df)
        assert reports[0]["ts_code"] == "600519.SH"

    def test_date_normalization(self):
        df = pd.DataFrame({
            "报告名称": ["test"],
            "日期": ["2026-03-01"],
        })
        reports = parse_eastmoney_reports("000001", df)
        assert reports[0]["publish_date"] == "20260301"
```

**Step 2: Run to verify it fails**

Run: `python -m pytest tests/test_report_fetcher.py -v`
Expected: FAIL with `ImportError`

**Step 3: Replace fetchers/research_report.py with modern implementation**

```python
"""
Research report fetcher — fetches from AkShare (EastMoney source).

Produces dicts compatible with ReportRepository.upsert_report().
"""

from __future__ import annotations

import logging
from typing import Optional

import pandas as pd

logger = logging.getLogger(__name__)


def _stock_suffix(code: str) -> str:
    """Add exchange suffix: 6xx→SH, else→SZ."""
    code = code.strip()[:6]
    return f"{code}.SH" if code.startswith("6") else f"{code}.SZ"


def _normalize_date(date_str: str) -> str:
    """Convert 'YYYY-MM-DD' → 'YYYYMMDD'."""
    if not date_str:
        return ""
    return str(date_str)[:10].replace("-", "")


def parse_eastmoney_reports(stock_code: str, df: pd.DataFrame) -> list[dict]:
    """
    Parse an AkShare stock_research_report_em() DataFrame into report dicts.

    Args:
        stock_code: 6-digit stock code
        df: DataFrame from ak.stock_research_report_em()

    Returns:
        List of dicts ready for ReportRepository.upsert_report()
    """
    if df is None or df.empty:
        return []

    ts_code = _stock_suffix(stock_code)
    reports = []

    for _, row in df.iterrows():
        reports.append({
            "ts_code": ts_code,
            "stock_name": row.get("股票简称") or None,
            "title": row.get("报告名称") or "无标题",
            "rating": row.get("东财评级") or None,
            "institution": row.get("机构") or None,
            "publish_date": _normalize_date(str(row.get("日期", ""))),
        })

    return reports


def fetch_stock_reports(stock_code: str) -> list[dict]:
    """
    Fetch research reports for a single stock from AkShare.

    Args:
        stock_code: 6-digit stock code

    Returns:
        List of report dicts
    """
    try:
        import akshare as ak
        df = ak.stock_research_report_em(symbol=stock_code)
        return parse_eastmoney_reports(stock_code, df)
    except Exception as e:
        logger.warning("Failed to fetch reports for %s: %s", stock_code, e)
        return []
```

**Step 4: Run tests**

Run: `python -m pytest tests/test_report_fetcher.py -v`
Expected: ALL PASS

**Step 5: Commit**

```bash
git add fetchers/research_report.py tests/test_report_fetcher.py
git commit -m "feat: modernize research report fetcher with proper parsing"
```

---

### Task 7: Full Regression + Lint

**Files:** All Phase 3B files

**Step 1: Run ruff on all changed files**

```bash
ruff check src/ai_engine/report_parser.py src/database/repositories/report.py fetchers/research_report.py tests/test_report_parser.py tests/test_report_repository.py tests/test_report_fetcher.py --fix
ruff format src/ai_engine/report_parser.py src/database/repositories/report.py fetchers/research_report.py tests/test_report_parser.py tests/test_report_repository.py tests/test_report_fetcher.py
```

**Step 2: Run full test suite**

```bash
python -m pytest --tb=short -q
```

Expected: ~260+ tests, ALL PASS (no regressions)

**Step 3: Fix any failures, then commit**

```bash
git add -u
git commit -m "chore: lint fixes for Phase 3B"
```

---

## DoD Verification

| Requirement | Implementation |
|---|---|
| LLM 辅助提取：目标价 | `extract_target_price_from_title()` (rule) + `analyze_report_with_llm()` (LLM) |
| LLM 辅助提取：评级 | `extract_rating_change()` (rule) + LLM `core_logic` |
| LLM 辅助提取：核心观点 | `extract_key_points()` (rule) + LLM `catalysts` |
| LLM 辅助提取：风险提示 | `extract_risk_factors()` (rule) + LLM `risks` |
| 结构化存储到 research_reports 表 | `ReportRepository.save_analysis()` populates all fields |
| 支持东方财富来源 | `fetch_stock_reports()` via AkShare |
| 结构化字段完整率 >= 90% | target_price, rating_change, key_points, sentiment_score, summary all populated |
| 测试覆盖 | ~35+ new tests across 3 test files |
