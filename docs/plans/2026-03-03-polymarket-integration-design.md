# Polymarket 预测市场新闻信号源 — 实现计划

> **状态：已完成**
> `src/data_ingestion/polymarket/*`、调度注册、API 端点、前端页面及集成测试（`tests/test_polymarket_integration.py`）均已落地并通过。

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 将 Polymarket 预测市场接入 AI 新闻平台，当市场概率大幅波动时自动生成 NewsFlash 进入 AI 分析管线。

**Architecture:** 使用 `py-clob-client` 官方 SDK 定时拉取活跃市场数据，存入 news.db 的 Polymarket 表，与上次快照对比检测概率波动，超过阈值时写入 News 表触发 AI 分析。

**Tech Stack:** py-clob-client (Polymarket SDK), SQLAlchemy, APScheduler, FastAPI

---

### Task 1: 添加 py-clob-client 依赖

**Files:**
- Modify: `requirements.txt:46` (末尾追加)

**Step 1: 添加依赖**

在 `requirements.txt` 末尾添加：
```
# 预测市场
py-clob-client>=0.34.0
```

**Step 2: 验证安装**

Run: `pip install py-clob-client`
Expected: Successfully installed

**Step 3: Commit**

```bash
git add requirements.txt
git commit -m "chore: add py-clob-client dependency for Polymarket integration"
```

---

### Task 2: 创建 Polymarket ORM 模型

**Files:**
- Create: `src/data_ingestion/polymarket/__init__.py`
- Create: `src/data_ingestion/polymarket/models.py`
- Create: `tests/test_polymarket_models.py`

**Step 1: 创建包目录和 `__init__.py`**

```python
# src/data_ingestion/polymarket/__init__.py
"""Polymarket prediction market data ingestion."""
```

**Step 2: 写 models.py 的失败测试**

```python
# tests/test_polymarket_models.py
"""Tests for Polymarket ORM models."""

import json
import pytest
from sqlalchemy import create_engine, inspect
from sqlalchemy.orm import sessionmaker

from src.data_ingestion.polymarket.models import (
    PolymarketBase,
    PolymarketMarket,
    PolymarketSnapshot,
)


@pytest.fixture()
def engine():
    eng = create_engine("sqlite:///:memory:")
    PolymarketBase.metadata.create_all(eng)
    yield eng
    eng.dispose()


@pytest.fixture()
def session(engine):
    Session = sessionmaker(bind=engine, expire_on_commit=False)
    with Session() as s:
        yield s


class TestPolymarketMarket:
    def test_tables_created(self, engine):
        tables = inspect(engine).get_table_names()
        assert "polymarket_markets" in tables
        assert "polymarket_snapshots" in tables

    def test_insert_market(self, session):
        m = PolymarketMarket(
            condition_id="0xabc123",
            question="Will BTC reach $100k?",
            description="Test market",
            tags=json.dumps(["crypto"]),
            outcomes=json.dumps(["Yes", "No"]),
            clob_token_ids=json.dumps(["token1", "token2"]),
            image="https://example.com/img.png",
            end_date="2026-12-31T00:00:00Z",
            active=True,
            closed=False,
        )
        session.add(m)
        session.commit()

        result = session.get(PolymarketMarket, "0xabc123")
        assert result is not None
        assert result.question == "Will BTC reach $100k?"
        assert json.loads(result.tags) == ["crypto"]

    def test_upsert_market_updates_on_conflict(self, session):
        m = PolymarketMarket(
            condition_id="0xabc123",
            question="Old question",
            active=True,
            closed=False,
        )
        session.add(m)
        session.commit()

        session.merge(PolymarketMarket(
            condition_id="0xabc123",
            question="New question",
            active=False,
            closed=True,
        ))
        session.commit()

        result = session.get(PolymarketMarket, "0xabc123")
        assert result.question == "New question"
        assert result.active is False


class TestPolymarketSnapshot:
    def test_insert_snapshot(self, session):
        m = PolymarketMarket(
            condition_id="0xabc123",
            question="Test",
            active=True,
            closed=False,
        )
        session.add(m)
        session.commit()

        snap = PolymarketSnapshot(
            market_id="0xabc123",
            outcome_prices=json.dumps([0.65, 0.35]),
        )
        session.add(snap)
        session.commit()

        assert snap.id is not None
        assert json.loads(snap.outcome_prices) == [0.65, 0.35]
        assert snap.snapshot_time is not None
```

**Step 3: 运行测试验证失败**

Run: `python -m pytest tests/test_polymarket_models.py -v`
Expected: FAIL (ModuleNotFoundError)

**Step 4: 实现 models.py**

```python
# src/data_ingestion/polymarket/models.py
"""Polymarket ORM models for the news database."""

from datetime import datetime, timezone

from sqlalchemy import (
    Column, String, Text, Boolean, Integer, BigInteger,
    DateTime, Index,
)
from sqlalchemy.orm import DeclarativeBase


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class PolymarketBase(DeclarativeBase):
    """Declarative base for Polymarket tables (lives in news.db)."""
    pass


class PolymarketMarket(PolymarketBase):
    """Polymarket prediction market metadata."""

    __tablename__ = "polymarket_markets"

    condition_id = Column(String(256), primary_key=True)
    question = Column(Text, nullable=False)
    description = Column(Text, nullable=True)
    tags = Column(Text, nullable=True)          # JSON string: ["crypto", "politics"]
    outcomes = Column(Text, nullable=True)       # JSON string: ["Yes", "No"]
    clob_token_ids = Column(Text, nullable=True) # JSON string: ["token1", "token2"]
    image = Column(String(512), nullable=True)
    end_date = Column(String(64), nullable=True)
    active = Column(Boolean, default=True)
    closed = Column(Boolean, default=False)
    created_at = Column(DateTime, default=_utcnow)
    updated_at = Column(DateTime, default=_utcnow, onupdate=_utcnow)


class PolymarketSnapshot(PolymarketBase):
    """Price snapshot for volatility detection."""

    __tablename__ = "polymarket_snapshots"

    id = Column(BigInteger().with_variant(Integer, "sqlite"), primary_key=True, autoincrement=True)
    market_id = Column(String(256), nullable=False, index=True)
    outcome_prices = Column(Text, nullable=False)  # JSON string: [0.65, 0.35]
    snapshot_time = Column(DateTime, default=_utcnow)

    __table_args__ = (
        Index("idx_snap_market_time", "market_id", "snapshot_time"),
    )
```

**Step 5: 运行测试验证通过**

Run: `python -m pytest tests/test_polymarket_models.py -v`
Expected: ALL PASS

**Step 6: Commit**

```bash
git add src/data_ingestion/polymarket/ tests/test_polymarket_models.py
git commit -m "feat(polymarket): add ORM models for markets and snapshots"
```

---

### Task 3: 创建 Polymarket Client（SDK 封装 + 分页）

**Files:**
- Create: `src/data_ingestion/polymarket/client.py`
- Create: `tests/test_polymarket_client.py`

**Step 1: 写 client 的失败测试**

```python
# tests/test_polymarket_client.py
"""Tests for PolymarketClient (SDK wrapper with pagination)."""

import pytest
from unittest.mock import MagicMock, patch

from src.data_ingestion.polymarket.client import PolymarketClient


@pytest.fixture()
def client():
    return PolymarketClient()


class TestGetActiveMarkets:
    def test_returns_list_of_markets(self, client):
        """Mock SDK to return one page of data."""
        fake_market = {
            "condition_id": "0xabc",
            "question": "Test?",
            "description": "desc",
            "tags": ["crypto"],
            "tokens": [
                {"token_id": "t1", "outcome": "Yes", "price": 0.7},
                {"token_id": "t2", "outcome": "No", "price": 0.3},
            ],
            "active": True,
            "closed": False,
            "image": "https://img.png",
            "end_date_iso": "2026-12-31T00:00:00Z",
        }
        mock_sdk = MagicMock()
        mock_sdk.get_sampling_markets.return_value = {
            "data": [fake_market],
            "next_cursor": "DONE",
            "count": 1,
        }
        client._sdk = mock_sdk

        markets = client.get_active_markets()

        assert len(markets) == 1
        assert markets[0]["condition_id"] == "0xabc"
        assert markets[0]["outcomes"] == ["Yes", "No"]
        assert markets[0]["prices"] == [0.7, 0.3]

    def test_pagination_fetches_all_pages(self, client):
        """Mock SDK to return two pages."""
        page1_market = {"condition_id": "0x1", "question": "Q1", "tokens": [
            {"token_id": "t1", "outcome": "Yes", "price": 0.5},
        ], "active": True, "closed": False, "tags": [], "description": "", "image": "", "end_date_iso": ""}
        page2_market = {"condition_id": "0x2", "question": "Q2", "tokens": [
            {"token_id": "t2", "outcome": "Yes", "price": 0.6},
        ], "active": True, "closed": False, "tags": [], "description": "", "image": "", "end_date_iso": ""}

        call_count = 0
        def fake_get(cursor="MA=="):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return {"data": [page1_market], "next_cursor": "PAGE2", "count": 1}
            return {"data": [page2_market], "next_cursor": "DONE", "count": 1}

        mock_sdk = MagicMock()
        mock_sdk.get_sampling_markets.side_effect = fake_get
        client._sdk = mock_sdk

        markets = client.get_active_markets()
        assert len(markets) == 2

    def test_empty_response(self, client):
        mock_sdk = MagicMock()
        mock_sdk.get_sampling_markets.return_value = {
            "data": [], "next_cursor": "DONE", "count": 0
        }
        client._sdk = mock_sdk

        markets = client.get_active_markets()
        assert markets == []
```

**Step 2: 运行测试验证失败**

Run: `python -m pytest tests/test_polymarket_client.py -v`
Expected: FAIL (ModuleNotFoundError)

**Step 3: 实现 client.py**

```python
# src/data_ingestion/polymarket/client.py
"""Polymarket SDK wrapper with pagination support."""

import logging
from typing import Any

from py_clob_client.client import ClobClient

logger = logging.getLogger(__name__)

CLOB_HOST = "https://clob.polymarket.com"
# Cursor indicating no more pages
END_CURSOR = "DONE"


class PolymarketClient:
    """Wraps py-clob-client SDK, handles pagination, normalizes data."""

    def __init__(self, host: str = CLOB_HOST):
        self._sdk = ClobClient(host)

    def get_active_markets(self) -> list[dict[str, Any]]:
        """Fetch all active (sampling) markets, auto-paginating.

        Returns a list of normalized market dicts with keys:
          condition_id, question, description, tags, outcomes, prices,
          clob_token_ids, image, end_date, active, closed
        """
        all_markets: list[dict[str, Any]] = []
        cursor = "MA=="  # default first-page cursor

        while True:
            resp = self._sdk.get_sampling_markets(cursor)
            data = resp.get("data", [])
            if not data:
                break

            for raw in data:
                all_markets.append(self._normalize(raw))

            cursor = resp.get("next_cursor", END_CURSOR)
            if cursor == END_CURSOR or not cursor:
                break

        logger.info(f"Polymarket: fetched {len(all_markets)} active markets")
        return all_markets

    @staticmethod
    def _normalize(raw: dict) -> dict[str, Any]:
        """Extract and flatten relevant fields from SDK response."""
        tokens = raw.get("tokens", [])
        return {
            "condition_id": raw.get("condition_id", ""),
            "question": raw.get("question", ""),
            "description": raw.get("description", ""),
            "tags": raw.get("tags", []),
            "outcomes": [t.get("outcome", "") for t in tokens],
            "prices": [t.get("price", 0) for t in tokens],
            "clob_token_ids": [t.get("token_id", "") for t in tokens],
            "image": raw.get("image", ""),
            "end_date": raw.get("end_date_iso", ""),
            "active": raw.get("active", False),
            "closed": raw.get("closed", False),
        }
```

**Step 4: 运行测试验证通过**

Run: `python -m pytest tests/test_polymarket_client.py -v`
Expected: ALL PASS

**Step 5: Commit**

```bash
git add src/data_ingestion/polymarket/client.py tests/test_polymarket_client.py
git commit -m "feat(polymarket): add SDK client wrapper with pagination"
```

---

### Task 4: 创建波动检测器

**Files:**
- Create: `src/data_ingestion/polymarket/detector.py`
- Create: `tests/test_polymarket_detector.py`

**Step 1: 写 detector 的失败测试**

```python
# tests/test_polymarket_detector.py
"""Tests for Polymarket volatility detector."""

import json
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.data_ingestion.polymarket.models import (
    PolymarketBase, PolymarketMarket, PolymarketSnapshot,
)
from src.data_ingestion.polymarket.detector import VolatilityDetector


@pytest.fixture()
def engine():
    eng = create_engine("sqlite:///:memory:")
    PolymarketBase.metadata.create_all(eng)
    yield eng
    eng.dispose()


@pytest.fixture()
def Session(engine):
    return sessionmaker(bind=engine, expire_on_commit=False)


@pytest.fixture()
def detector(Session):
    return VolatilityDetector(Session, threshold=0.10)


class TestDetectVolatility:
    def test_no_previous_snapshot_no_alert(self, detector, Session):
        """First snapshot ever — no alert."""
        market_data = {
            "condition_id": "0xabc",
            "question": "Test?",
            "outcomes": ["Yes", "No"],
            "prices": [0.7, 0.3],
        }
        alerts = detector.detect([market_data])
        assert alerts == []

    def test_small_change_no_alert(self, detector, Session):
        """5% change — below threshold, no alert."""
        # Insert previous snapshot
        with Session() as s:
            s.add(PolymarketMarket(condition_id="0xabc", question="Test?", active=True, closed=False))
            s.add(PolymarketSnapshot(
                market_id="0xabc",
                outcome_prices=json.dumps([0.70, 0.30]),
            ))
            s.commit()

        alerts = detector.detect([{
            "condition_id": "0xabc",
            "question": "Test?",
            "outcomes": ["Yes", "No"],
            "prices": [0.75, 0.25],  # 5% change
        }])
        assert alerts == []

    def test_large_change_triggers_alert(self, detector, Session):
        """15% change — above threshold, should alert."""
        with Session() as s:
            s.add(PolymarketMarket(condition_id="0xabc", question="Will X happen?", active=True, closed=False))
            s.add(PolymarketSnapshot(
                market_id="0xabc",
                outcome_prices=json.dumps([0.50, 0.50]),
            ))
            s.commit()

        alerts = detector.detect([{
            "condition_id": "0xabc",
            "question": "Will X happen?",
            "outcomes": ["Yes", "No"],
            "prices": [0.65, 0.35],  # 15% change
        }])
        assert len(alerts) == 1
        assert "Will X happen?" in alerts[0]["title"]
        assert "Yes" in alerts[0]["content"]

    def test_snapshot_is_saved(self, detector, Session):
        """After detection, new snapshot should be persisted."""
        detector.detect([{
            "condition_id": "0xnew",
            "question": "New market?",
            "outcomes": ["Yes", "No"],
            "prices": [0.80, 0.20],
        }])

        with Session() as s:
            snaps = s.query(PolymarketSnapshot).filter_by(market_id="0xnew").all()
            assert len(snaps) == 1
            assert json.loads(snaps[0].outcome_prices) == [0.80, 0.20]
```

**Step 2: 运行测试验证失败**

Run: `python -m pytest tests/test_polymarket_detector.py -v`
Expected: FAIL (ModuleNotFoundError)

**Step 3: 实现 detector.py**

```python
# src/data_ingestion/polymarket/detector.py
"""Volatility detector — compares snapshots to detect big price moves."""

import json
import logging
from typing import Any

from sqlalchemy.orm import sessionmaker

from src.data_ingestion.polymarket.models import (
    PolymarketMarket,
    PolymarketSnapshot,
)

logger = logging.getLogger(__name__)


class VolatilityDetector:
    """Compares current prices with the last snapshot to detect volatility."""

    def __init__(self, session_factory: sessionmaker, threshold: float = 0.10):
        self.Session = session_factory
        self.threshold = threshold

    def detect(self, markets: list[dict[str, Any]]) -> list[dict[str, str]]:
        """Process market data, save snapshots, return alerts for big moves.

        Each alert dict has keys: title, content, source.
        """
        alerts: list[dict[str, str]] = []

        with self.Session() as session:
            for m in markets:
                cid = m["condition_id"]
                prices = m["prices"]
                outcomes = m["outcomes"]
                question = m["question"]

                # Get latest previous snapshot
                prev = (
                    session.query(PolymarketSnapshot)
                    .filter_by(market_id=cid)
                    .order_by(PolymarketSnapshot.snapshot_time.desc())
                    .first()
                )

                prev_prices = json.loads(prev.outcome_prices) if prev else None

                # Save new snapshot
                snap = PolymarketSnapshot(
                    market_id=cid,
                    outcome_prices=json.dumps(prices),
                )
                session.add(snap)

                # Upsert market record
                session.merge(PolymarketMarket(
                    condition_id=cid,
                    question=question,
                    description=m.get("description", ""),
                    tags=json.dumps(m.get("tags", [])),
                    outcomes=json.dumps(outcomes),
                    clob_token_ids=json.dumps(m.get("clob_token_ids", [])),
                    image=m.get("image", ""),
                    end_date=m.get("end_date", ""),
                    active=m.get("active", True),
                    closed=m.get("closed", False),
                ))

                # Compare
                if prev_prices and len(prev_prices) == len(prices):
                    for i, outcome in enumerate(outcomes):
                        delta = prices[i] - prev_prices[i]
                        if abs(delta) >= self.threshold:
                            direction = "↑" if delta > 0 else "↓"
                            alerts.append({
                                "title": f"预测市场波动: {question}",
                                "content": (
                                    f"'{outcome}' 概率从 {prev_prices[i]:.0%} "
                                    f"变为 {prices[i]:.0%} ({direction}{abs(delta):.0%})"
                                ),
                                "source": "polymarket",
                            })
                            logger.info(
                                f"Polymarket alert: {question} "
                                f"{outcome} {prev_prices[i]:.0%}->{prices[i]:.0%}"
                            )

            session.commit()

        return alerts
```

**Step 4: 运行测试验证通过**

Run: `python -m pytest tests/test_polymarket_detector.py -v`
Expected: ALL PASS

**Step 5: Commit**

```bash
git add src/data_ingestion/polymarket/detector.py tests/test_polymarket_detector.py
git commit -m "feat(polymarket): add volatility detector with snapshot comparison"
```

---

### Task 5: 创建 Fetcher（定时任务入口）

**Files:**
- Create: `src/data_ingestion/polymarket/fetcher.py`
- Create: `tests/test_polymarket_fetcher.py`

**Step 1: 写 fetcher 的失败测试**

```python
# tests/test_polymarket_fetcher.py
"""Tests for PolymarketFetcher (scheduler task entry point)."""

import json
import pytest
from unittest.mock import MagicMock, patch
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.data_ingestion.polymarket.models import PolymarketBase, PolymarketSnapshot
from src.data_ingestion.polymarket.fetcher import PolymarketFetcher


@pytest.fixture()
def engine():
    eng = create_engine("sqlite:///:memory:")
    PolymarketBase.metadata.create_all(eng)
    yield eng
    eng.dispose()


@pytest.fixture()
def Session(engine):
    return sessionmaker(bind=engine, expire_on_commit=False)


class TestFetcher:
    @patch("src.data_ingestion.polymarket.fetcher.PolymarketClient")
    def test_fetch_and_detect_writes_news(self, MockClient, Session):
        """When volatility detected, insert_news is called."""
        mock_client = MagicMock()
        mock_client.get_active_markets.return_value = [{
            "condition_id": "0xabc",
            "question": "Test?",
            "outcomes": ["Yes", "No"],
            "prices": [0.80, 0.20],
            "description": "",
            "tags": [],
            "clob_token_ids": [],
            "image": "",
            "end_date": "",
            "active": True,
            "closed": False,
        }]
        MockClient.return_value = mock_client

        mock_repo = MagicMock()
        fetcher = PolymarketFetcher(Session, mock_repo, threshold=0.0)  # threshold=0 so first fetch triggers
        # First run — no previous snapshot, no alert
        fetcher.run()
        mock_repo.insert_news.assert_not_called()

        # Second run — same price, no alert
        fetcher.run()
        mock_repo.insert_news.assert_not_called()

    @patch("src.data_ingestion.polymarket.fetcher.PolymarketClient")
    def test_fetch_disabled_does_nothing(self, MockClient, Session):
        """When disabled via env, run() is a no-op."""
        mock_repo = MagicMock()
        fetcher = PolymarketFetcher(Session, mock_repo, enabled=False)
        fetcher.run()
        MockClient.return_value.get_active_markets.assert_not_called()
```

**Step 2: 运行测试验证失败**

Run: `python -m pytest tests/test_polymarket_fetcher.py -v`
Expected: FAIL

**Step 3: 实现 fetcher.py**

```python
# src/data_ingestion/polymarket/fetcher.py
"""Polymarket fetcher — entry point for the scheduler task."""

import logging
import os

from sqlalchemy.orm import sessionmaker

from src.data_ingestion.polymarket.client import PolymarketClient
from src.data_ingestion.polymarket.detector import VolatilityDetector
from src.data_ingestion.polymarket.models import PolymarketBase

logger = logging.getLogger(__name__)


class PolymarketFetcher:
    """Orchestrates: fetch markets → detect volatility → write news."""

    def __init__(
        self,
        session_factory: sessionmaker,
        news_repo,
        threshold: float | None = None,
        enabled: bool | None = None,
    ):
        self.news_repo = news_repo
        self.enabled = enabled if enabled is not None else (
            os.getenv("POLYMARKET_ENABLED", "true").lower() == "true"
        )
        _threshold = threshold if threshold is not None else float(
            os.getenv("POLYMARKET_VOLATILITY_THRESHOLD", "0.10")
        )
        self.client = PolymarketClient()
        self.detector = VolatilityDetector(session_factory, threshold=_threshold)

    def ensure_tables(self, engine) -> None:
        """Create Polymarket tables if they don't exist (idempotent)."""
        PolymarketBase.metadata.create_all(engine)

    def run(self) -> int:
        """Fetch, detect, and write alerts. Returns count of alerts generated."""
        if not self.enabled:
            logger.info("Polymarket fetcher is disabled, skipping")
            return 0

        markets = self.client.get_active_markets()
        if not markets:
            logger.info("Polymarket: no active markets found")
            return 0

        alerts = self.detector.detect(markets)

        for alert in alerts:
            self.news_repo.insert_news(
                title=alert["title"],
                content=alert["content"],
                hotspots="polymarket,预测市场",
                keywords=alert.get("source", "polymarket"),
            )

        if alerts:
            logger.info(f"Polymarket: generated {len(alerts)} news alerts")
        return len(alerts)
```

**Step 4: 运行测试验证通过**

Run: `python -m pytest tests/test_polymarket_fetcher.py -v`
Expected: ALL PASS

**Step 5: Commit**

```bash
git add src/data_ingestion/polymarket/fetcher.py tests/test_polymarket_fetcher.py
git commit -m "feat(polymarket): add fetcher orchestrator for scheduler integration"
```

---

### Task 6: 注册调度任务 + 数据库表创建

**Files:**
- Modify: `api/scheduler.py:28-70` (TASK_CONFIGS 中添加)
- Modify: `api/scheduler.py:293-343` (register_default_tasks 中添加)
- Modify: `api/main.py:49-51` (表创建区域)

**Step 1: 在 TASK_CONFIGS 中添加 polymarket_fetch**

在 `api/scheduler.py` 的 `TASK_CONFIGS` 字典末尾添加：

```python
    "polymarket_fetch": {
        "name": "Polymarket 预测市场",
        "trigger": "interval",
        "minutes": int(os.getenv("POLYMARKET_FETCH_INTERVAL", "5")),
        "enabled": os.getenv("POLYMARKET_ENABLED", "true").lower() == "true",
        "description": "从 Polymarket 拉取预测市场数据，检测概率波动"
    },
```

需要在文件顶部 import os：确认已有或添加 `import os`。

**Step 2: 在 register_default_tasks 中注册执行函数**

在 `api/scheduler.py` 的 `register_default_tasks()` 函数末尾（`logger.info("✅ 默认任务注册完成")` 之前）添加：

```python
    # 注册 Polymarket 预测市场任务
    if os.getenv("POLYMARKET_ENABLED", "true").lower() == "true":
        from src.data_ingestion.polymarket.fetcher import PolymarketFetcher
        from src.data_ingestion.polymarket.models import PolymarketBase

        # 获取 news db 引擎和仓储（复用 main.py 的）
        from config.settings import NEWS_DATABASE_URL
        from src.database.engine import create_engine_from_url, get_session_factory
        from src.database.repositories.news import NewsRepository

        pm_engine = create_engine_from_url(NEWS_DATABASE_URL)
        pm_Session = get_session_factory(pm_engine)
        pm_repo = NewsRepository(pm_Session)

        # 确保 Polymarket 表存在
        PolymarketBase.metadata.create_all(pm_engine)

        pm_fetcher = PolymarketFetcher(pm_Session, pm_repo)

        def polymarket_task():
            pm_fetcher.run()

        scheduler_manager.register_task("polymarket_fetch", polymarket_task)
```

**Step 3: 验证启动不报错**

Run: `python -c "from api.scheduler import register_default_tasks; print('OK')"`
Expected: OK (or import errors to fix)

**Step 4: Commit**

```bash
git add api/scheduler.py
git commit -m "feat(polymarket): register scheduler task for periodic market fetching"
```

---

### Task 7: 添加 Polymarket 配置到 .env.example

**Files:**
- Modify: `.env` 或 `.env.example` (如存在)

**Step 1: 添加配置说明**

在 `.env` 文件末尾追加：

```env
# Polymarket 预测市场
POLYMARKET_ENABLED=true
POLYMARKET_FETCH_INTERVAL=5
POLYMARKET_VOLATILITY_THRESHOLD=0.10
```

**Step 2: Commit**

```bash
git add .env.example  # 或对应的文件
git commit -m "chore: add Polymarket env configuration"
```

---

### Task 8: 端到端集成测试

**Files:**
- Create: `tests/test_polymarket_integration.py`

**Step 1: 写集成测试**

```python
# tests/test_polymarket_integration.py
"""End-to-end integration test for Polymarket pipeline."""

import json
import pytest
from unittest.mock import MagicMock, patch
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.database.engine import get_session_factory
from src.database.repositories.news import NewsRepository, _Base as NewsBase
from src.data_ingestion.polymarket.models import PolymarketBase, PolymarketSnapshot
from src.data_ingestion.polymarket.fetcher import PolymarketFetcher


@pytest.fixture()
def engine():
    eng = create_engine("sqlite:///:memory:")
    NewsBase.metadata.create_all(eng)
    PolymarketBase.metadata.create_all(eng)
    yield eng
    eng.dispose()


@pytest.fixture()
def Session(engine):
    return get_session_factory(engine)


@pytest.fixture()
def repo(Session):
    return NewsRepository(Session)


class TestE2E:
    @patch("src.data_ingestion.polymarket.fetcher.PolymarketClient")
    def test_full_pipeline_detects_volatility_and_writes_news(self, MockClient, Session, repo):
        """Simulate two fetches: first creates baseline, second detects volatility."""
        mock_client = MagicMock()
        MockClient.return_value = mock_client

        # First fetch: 50/50 market
        mock_client.get_active_markets.return_value = [{
            "condition_id": "0xe2e",
            "question": "Will AI surpass humans by 2030?",
            "outcomes": ["Yes", "No"],
            "prices": [0.50, 0.50],
            "description": "Test", "tags": ["tech"], "clob_token_ids": ["t1", "t2"],
            "image": "", "end_date": "2030-01-01T00:00:00Z", "active": True, "closed": False,
        }]

        fetcher = PolymarketFetcher(Session, repo, threshold=0.10)
        count1 = fetcher.run()
        assert count1 == 0  # first fetch, no baseline to compare

        # Second fetch: big move to 75/25
        mock_client.get_active_markets.return_value = [{
            "condition_id": "0xe2e",
            "question": "Will AI surpass humans by 2030?",
            "outcomes": ["Yes", "No"],
            "prices": [0.75, 0.25],
            "description": "Test", "tags": ["tech"], "clob_token_ids": ["t1", "t2"],
            "image": "", "end_date": "2030-01-01T00:00:00Z", "active": True, "closed": False,
        }]

        count2 = fetcher.run()
        assert count2 == 1  # should detect 25% move

        # Verify news was written
        news = repo.get_news_list(limit=10)
        assert len(news) == 1
        assert "Will AI surpass humans" in news[0]["title"]
        assert "Yes" in news[0]["content"]

    @patch("src.data_ingestion.polymarket.fetcher.PolymarketClient")
    def test_disabled_fetcher_writes_nothing(self, MockClient, Session, repo):
        fetcher = PolymarketFetcher(Session, repo, enabled=False)
        count = fetcher.run()
        assert count == 0
        assert repo.get_news_list() == []
```

**Step 2: 运行集成测试**

Run: `python -m pytest tests/test_polymarket_integration.py -v`
Expected: ALL PASS

**Step 3: 运行全部测试确保无回归**

Run: `python -m pytest tests/ -v --tb=short`
Expected: ALL PASS

**Step 4: Commit**

```bash
git add tests/test_polymarket_integration.py
git commit -m "test(polymarket): add end-to-end integration tests"
```

---

### Task 9: 最终验证

**Step 1: 确认所有文件都已就绪**

```bash
ls -la src/data_ingestion/polymarket/
# Expected: __init__.py, client.py, detector.py, fetcher.py, models.py
```

**Step 2: 运行全部 Polymarket 测试**

Run: `python -m pytest tests/test_polymarket_*.py -v`
Expected: ALL PASS

**Step 3: 手动冒烟测试（可选，需联网）**

```python
from src.data_ingestion.polymarket.client import PolymarketClient
client = PolymarketClient()
markets = client.get_active_markets()
print(f"Fetched {len(markets)} markets")
print(f"Sample: {markets[0]['question']}" if markets else "No markets")
```

**Step 4: Final commit**

```bash
git add -A
git commit -m "feat(polymarket): complete Polymarket prediction market integration"
```
