# 优化路线图执行计划

- 来源：`docs/ai-handoff/2026-03-08-shared-optimization-proposal.md`（13 项共识）
- 日期：2026-03-08
- 执行约束：DoD 驱动、profiling 先行、试点止损

---

## 第 1 周 — 产品化已有能力

### 目标

将已实现的 RPS 筛选和潜力筛选能力从 CLI 工具升级为可通过 API 访问、前端展示的产品功能。

### 任务清单

#### 1.1 创建快照数据表

**文件**: `src/database/models.py`

新增 3 个 ORM 模型：

```python
class ScreenRpsSnapshot(Base, TimestampMixin):
    __tablename__ = "screen_rps_snapshot"
    id = Column(Integer, primary_key=True)
    snapshot_date = Column(Date, nullable=False)
    source_trade_date = Column(Date, nullable=False)
    generated_at = Column(DateTime, nullable=False)
    generator_version = Column(String(16), nullable=False)
    ts_code = Column(String(12), nullable=False)
    stock_name = Column(String(20))
    rps_20 = Column(RATIO)
    rps_50 = Column(RATIO)
    rps_120 = Column(RATIO)
    rank = Column(Integer)
    __table_args__ = (UniqueConstraint("snapshot_date", "ts_code"),)

class ScreenPotentialSnapshot(Base, TimestampMixin):
    __tablename__ = "screen_potential_snapshot"
    id = Column(Integer, primary_key=True)
    snapshot_date = Column(Date, nullable=False)
    source_trade_date = Column(Date, nullable=False)
    generated_at = Column(DateTime, nullable=False)
    generator_version = Column(String(16), nullable=False)
    ts_code = Column(String(12), nullable=False)
    stock_name = Column(String(20))
    total_score = Column(RATIO)
    capital_score = Column(RATIO)
    trading_score = Column(RATIO)
    fundamental_score = Column(RATIO)
    technical_score = Column(RATIO)
    signals = Column(Text)  # JSON: ["MACD金叉", "量价齐升"]
    rank = Column(Integer)
    __table_args__ = (UniqueConstraint("snapshot_date", "ts_code"),)

class AnalysisFullSnapshot(Base, TimestampMixin):
    __tablename__ = "analysis_full_snapshot"
    id = Column(Integer, primary_key=True)
    snapshot_date = Column(Date, nullable=False)
    source_trade_date = Column(Date, nullable=False)
    generated_at = Column(DateTime, nullable=False)
    generator_version = Column(String(16), nullable=False)
    ts_code = Column(String(12), nullable=False)
    stock_name = Column(String(20))
    analysis_json = Column(Text, nullable=False)  # 完整分析结果 JSON
    __table_args__ = (UniqueConstraint("snapshot_date", "ts_code"),)
```

**测试**: 验证表创建、唯一约束冲突处理

#### 1.2 快照生成服务

**新文件**: `src/strategies/snapshot_service.py`

```python
def generate_rps_snapshot(date=None) -> int:
    """调用 rps_screener，将结果写入 screen_rps_snapshot。返回写入条数。"""

def generate_potential_snapshot(date=None) -> int:
    """调用 potential_screener.run_screening()，将结果写入 screen_potential_snapshot。返回写入条数。"""

def cleanup_old_snapshots(max_trading_days=60, max_analysis_days=14):
    """清理超过保留期的快照。"""
```

**依赖**: `src/strategies/rps_screener.py`, `src/strategies/potential_screener.py`
**测试**: mock screener 输出，验证写入和清理逻辑

#### 1.3 注册快照定时任务

**文件**: `api/scheduler.py`

在 `TASK_CONFIGS` 中新增：

```python
{
    "id": "screen_snapshot",
    "name": "筛选器日快照生成",
    "trigger": "cron",
    "day_of_week": "mon-fri",
    "hour": 17,
    "minute": 15,  # 在 fund_flow (17:00) 之后
}
```

注册函数调用 `generate_rps_snapshot()` + `generate_potential_snapshot()` + `cleanup_old_snapshots()`

#### 1.4 筛选器 API 端点

**文件**: `api/main.py`

新增端点：

```
GET /api/screens/rps
    Query: date (可选, YYYY-MM-DD), limit (默认 50)
    Response: { snapshot_date, source_trade_date, generated_at, items: [...] }

GET /api/screens/potential
    Query: date (可选, YYYY-MM-DD), limit (默认 20)
    Response: { snapshot_date, source_trade_date, generated_at, items: [...] }
```

**Pydantic response models**:
- `ScreenRpsResponse`
- `ScreenPotentialResponse`

#### 1.5 前端筛选器结果页

**新文件**: `frontend/app/screens/page.tsx`

页面内容：
- 标签切换：RPS 强势股 / 潜力筛选
- 数据表格：排名、代码、名称、核心指标
- 顶部显示：数据日期 + 生成时间（freshness 元数据）
- 点击行跳转个股详情页

**新类型** (`frontend/lib/types.ts`):
- `ScreenRpsItem`, `ScreenRpsResponse`
- `ScreenPotentialItem`, `ScreenPotentialResponse`

#### 1.6 K 线图指标叠加

**文件**: `frontend/components/charts/kline-chart.tsx`

扩展 Props：
```typescript
interface KlineChartProps {
  // ... 现有 props
  showMACD?: boolean
  showRSI?: boolean
  showBollinger?: boolean
}
```

实现：
- MACD 面板：DIF 线 + DEA 线 + 柱状图（独立子图，占底部 15%）
- RSI 面板：RSI14 线 + 超买(70)/超卖(30) 参考线（独立子图）
- 布林带：叠加在主图上（上轨、中轨、下轨）
- 切换按钮组：MA | MACD | RSI | BOLL

**数据来源**: 后端 `GET /api/stocks/{ts_code}/daily` 已返回 OHLCV，前端本地计算指标（避免新增后端接口）

#### 1.7 核心端点补 response_model

**文件**: `api/main.py`

为以下端点添加 Pydantic `response_model`：
- `GET /api/stocks` → `StockListResponse`
- `GET /api/stocks/{ts_code}/profile` → `StockProfileResponse`
- `GET /api/stocks/{ts_code}/daily` → `StockDailyResponse`
- `GET /api/screens/rps` → `ScreenRpsResponse`（新增）
- `GET /api/screens/potential` → `ScreenPotentialResponse`（新增）
- `GET /api/market/overview` → `MarketOverviewResponse`

### 完成标准 (DoD)

- [ ] `screen_rps_snapshot` / `screen_potential_snapshot` 表存在并可写入
- [ ] `GET /api/screens/rps` 返回带 `snapshot_date` 和 `source_trade_date` 的快照数据
- [ ] `GET /api/screens/potential` 返回带完整评分和信号的快照数据
- [ ] 前端筛选器页面可展示快照结果，且顶部显示数据日期
- [ ] K 线图支持 MACD/RSI/布林带至少一种指标切换
- [ ] 6 个核心端点有 `response_model` 定义

### 修改文件范围

| 文件 | 修改类型 |
|------|---------|
| `src/database/models.py` | 新增 3 个 ORM 模型 |
| `src/strategies/snapshot_service.py` | 新建 |
| `api/scheduler.py` | 新增任务配置 |
| `api/main.py` | 新增 2 端点 + 6 个 response_model |
| `frontend/app/screens/page.tsx` | 新建 |
| `frontend/components/charts/kline-chart.tsx` | 扩展指标面板 |
| `frontend/lib/types.ts` | 新增筛选器类型 |
| `frontend/lib/api.ts` | 新增 API 调用函数 |
| `frontend/components/layout/header.tsx` | 导航新增"筛选"入口 |

### 测试策略

- 后端：`tests/test_snapshot_service.py`（mock screener 输出，验证写入/清理/幂等性）
- 后端：`tests/test_api.py` 扩展（验证新端点返回格式）
- 前端：`frontend/__tests__/components/kline-chart.test.tsx`（验证指标切换渲染）

### 回滚点

- 快照表独立于现有表，删表即可回滚
- 新端点不影响现有 API
- K 线图指标切换默认关闭，不影响现有功能

---

## 第 2 周 — 性能与基础抽象

### 目标

建立性能观测能力，基于数据驱动优化；完成缓存抽象和 full_analysis 快照化。

### 任务清单

#### 2.1 接口耗时中间件

**文件**: `api/middleware.py`

```python
perf_logger = logging.getLogger("api.perf")

class PerfMiddleware:
    async def __call__(self, request, call_next):
        start = time.perf_counter()
        response = await call_next(request)
        elapsed = time.perf_counter() - start
        if elapsed > 0.5:
            perf_logger.warning("SLOW %s %s %.3fs", request.method, request.url.path, elapsed)
        else:
            perf_logger.info("%s %s %.3fs", request.method, request.url.path, elapsed)
        response.headers["X-Response-Time"] = f"{elapsed:.3f}s"
        return response
```

#### 2.2 基于 profiling 补复合索引

**前提**: 第 1 周慢查询日志已运行，收集到 Top 10 慢 SQL

**候选索引**（需 profiling 确认后再决定）：
- `ts_daily(ts_code, trade_date DESC)` — 个股日线查询
- `ts_daily(trade_date)` — 全市场截面查询
- `screen_rps_snapshot(snapshot_date, rank)` — 快照排名查询
- `screen_potential_snapshot(snapshot_date, rank)` — 快照排名查询

**约束**: 没有 profiling 证据，不加索引。

#### 2.3 CacheService 抽象层

**新文件**: `src/utils/cache.py`

```python
from abc import ABC, abstractmethod

class CacheService(ABC):
    @abstractmethod
    def get(self, key: str) -> Optional[Any]: ...
    @abstractmethod
    def set(self, key: str, value: Any, ttl: int = 300): ...
    @abstractmethod
    def invalidate(self, key: str): ...
    @abstractmethod
    def invalidate_prefix(self, prefix: str): ...

class MemoryCacheService(CacheService):
    """基于 cachetools.TTLCache 的内存实现"""

# 全局单例
cache = MemoryCacheService(maxsize=1024, default_ttl=300)
```

接入 1-2 个高频端点（如 `/api/stocks`、`/api/market/overview`）验证。

#### 2.4 full_analysis 快照化

**扩展文件**: `src/strategies/snapshot_service.py`

```python
def generate_full_analysis_snapshots() -> int:
    """预计算热门股票的完整分析。
    集合 = RPS Top 20 ∪ Potential Top 20 ∪ 涨跌幅榜 Top 10 → 去重后 30-40 只。
    结果写入 analysis_full_snapshot。
    """

def get_or_generate_full_analysis(ts_code: str) -> dict:
    """懒生成：先查快照，无则现场生成并缓存 24h。
    并发限制：同时最多 3 个生成任务（asyncio.Semaphore）。
    """
```

**API 端点** (`api/main.py`):
```
GET /api/analysis/full/{ts_code}
    Response: { snapshot_date, source_trade_date, generated_at, analysis: {...} }
    行为: 快照存在 → 直接返回; 不存在 → 懒生成 → 缓存 → 返回
```

#### 2.5 开发种子数据

**新文件**: `scripts/create_seed_data.py`

从现有 `stocks.db` 导出 50 只代表性股票：
- 覆盖沪深京三市、大中小盘
- 包含：`ts_stock_basic`, `ts_daily`（近 1 年）, `stock_technicals`, `stock_rps`, `ts_hk_hold`, `margin_trading`, `ts_daily_basic`
- 输出：`data/dev_seed.sql.gz`

**使用方式**: `zcat data/dev_seed.sql.gz | sqlite3 stocks.db`

#### 2.6 自选股功能

**新文件**: `frontend/lib/watchlist.ts`

```typescript
interface WatchlistService {
    getAll(): string[]             // 返回 ts_code 列表
    add(tsCode: string): void
    remove(tsCode: string): void
    has(tsCode: string): boolean
    onChange(cb: () => void): () => void  // 订阅变化
}

// 第一版实现: localStorage
class LocalStorageWatchlist implements WatchlistService { ... }

export const watchlist: WatchlistService = new LocalStorageWatchlist()
```

**前端集成**:
- 个股页：添加"加入自选"按钮
- 新建 `frontend/app/watchlist/page.tsx`：自选股列表页
- 导航栏添加"自选"入口

### 完成标准 (DoD)

- [ ] 慢查询日志在运行中产生真实输出（>500ms 的请求有 WARNING 日志）
- [ ] `X-Response-Time` header 出现在所有 API 响应中
- [ ] CacheService 抽象层已实现，至少 1 个端点接入
- [ ] `GET /api/analysis/full/{ts_code}` 可返回预计算或懒生成的分析结果
- [ ] `data/dev_seed.sql.gz` 存在且可导入空 SQLite
- [ ] 自选股功能可添加/删除/展示

### 修改文件范围

| 文件 | 修改类型 |
|------|---------|
| `api/middleware.py` | 新增 PerfMiddleware |
| `src/utils/cache.py` | 新建 |
| `src/strategies/snapshot_service.py` | 扩展 full_analysis |
| `api/main.py` | 新增 1 端点 + 缓存接入 |
| `scripts/create_seed_data.py` | 新建 |
| `frontend/lib/watchlist.ts` | 新建 |
| `frontend/app/watchlist/page.tsx` | 新建 |
| `frontend/components/layout/header.tsx` | 新增自选入口 |

### 测试策略

- `tests/test_cache.py`（get/set/invalidate/TTL 过期）
- `tests/test_snapshot_service.py` 扩展（full_analysis 快照 + 懒生成 + 并发限制）
- `frontend/__tests__/lib/watchlist.test.ts`（localStorage mock）

### 回滚点

- PerfMiddleware 可独立移除
- CacheService 接入点少，可快速回退
- 自选股纯前端功能，不影响后端

---

## 第 3 周 — 搜索与导出

### 目标

实现统一搜索能力和数据导出，完成 full_analysis 的前端展示。

### 任务清单

#### 3.1 搜索语义定义

固定搜索行为（来自讨论共识）：

| 场景 | 触发条件 | 行为 | 排序 |
|------|---------|------|------|
| 股票代码精确 | 输入 6 位数字 | 精确匹配 ts_code | 市值降序 |
| 股票名称模糊 | 输入中文 | 前缀匹配 stock_name | 市值降序 |
| 新闻全文搜索 | 输入关键词 | 搜索标题+摘要 | 时间倒序 |

路由规则：由输入内容特征自动判断（数字 → 代码匹配，中文 → 名称+新闻）。

#### 3.2 SearchService 抽象层

**新文件**: `src/utils/search.py`

```python
class SearchService(ABC):
    @abstractmethod
    def search_stocks(self, query: str, limit: int = 20) -> list: ...
    @abstractmethod
    def search_news(self, query: str, limit: int = 50) -> list: ...

class SqliteSearchService(SearchService):
    """FTS5 实现。tokenizer 选型需用中文样本验证效果后确定。"""

class PostgresSearchService(SearchService):
    """tsvector + GIN 实现"""
```

**搜索实现分层**：
1. **能力目标**（必须达成）：股票代码精确匹配 + 股票名称可靠模糊匹配 + 新闻标题/摘要关键词搜索
2. **实现验证**（需实测）：FTS5 中文搜索效果需用真实新闻样本验证召回率和排序质量。若 `simple tokenizer` 效果不稳定，阶段 1 可先用标题/摘要 `LIKE` 匹配作为保守方案，不阻塞搜索功能上线

#### 3.3 搜索 API 端点

**文件**: `api/main.py`

```
GET /api/search
    Query: q (必填), type (stocks|news|all, 默认 all), limit
    Response: { stocks: [...], news: [...] }
```

#### 3.4 前端搜索 UI

**文件**: `frontend/components/layout/stock-search.tsx`

增强现有搜索组件：
- 输入框支持股票代码和新闻关键词
- 下拉分组显示：股票结果 / 新闻结果
- 键盘导航（↑↓ 选择，Enter 跳转）

#### 3.5 个股页 AI 综合分析展示

**文件**: `frontend/app/market/[code]/page.tsx`（或对应个股详情页）

- 新增"AI 综合分析"标签页/卡片
- 读取 `GET /api/analysis/full/{ts_code}` 快照数据
- 展示：技术形态、支撑阻力、板块排名、大盘环境
- 数据日期标注（freshness 元数据）

#### 3.6 CSV 导出端点

**文件**: `api/main.py`

```
GET /api/stocks/{ts_code}/daily/export
    Query: start_date, end_date, format (csv)
    Response: StreamingResponse with Content-Disposition

GET /api/screens/rps/export
    Response: CSV 格式的 RPS 快照

GET /api/screens/potential/export
    Response: CSV 格式的潜力筛选快照
```

#### 3.7 CI 契约测试

**文件**: `.github/workflows/ci.yml` 扩展

新增步骤：
- 检查核心端点是否有 `response_model`
- 运行现有测试 + 新增的快照/搜索/导出测试

### 完成标准 (DoD)

- [ ] `GET /api/search?q=000001` 返回精确匹配的股票
- [ ] `GET /api/search?q=芯片` 返回相关新闻和股票
- [ ] 前端搜索框输入后显示分组下拉结果
- [ ] 个股页可展示 AI 综合分析（快照或懒生成）
- [ ] CSV 导出端点返回可被 Excel 打开的 UTF-8 BOM CSV
- [ ] CI 流水线包含契约测试

### 修改文件范围

| 文件 | 修改类型 |
|------|---------|
| `src/utils/search.py` | 新建 |
| `api/main.py` | 新增搜索 + 导出端点 |
| `frontend/components/layout/stock-search.tsx` | 增强搜索 |
| `frontend/app/market/[code]/page.tsx` | 新增分析展示 |
| `.github/workflows/ci.yml` | 新增契约测试步骤 |

### 测试策略

- `tests/test_search.py`（FTS5 创建、精确匹配、模糊匹配、空结果）
- `tests/test_api.py` 扩展（搜索端点、CSV 导出）
- 前端：搜索组件交互测试

### 回滚点

- 搜索功能独立，移除端点和前端组件即可
- CSV 导出无副作用
- FTS5 虚拟表可单独删除

---

## 第 4 周 — 盘中试点 + 收尾

### 目标

验证盘中准实时数据能力的可行性和性价比；完成 CI 和基础设施收尾。

### 任务清单

#### 4.1 盘中快照表

**文件**: `src/database/models.py`

```python
class IntradaySnapshot(Base):
    __tablename__ = "intraday_snapshot"
    id = Column(Integer, primary_key=True)
    ts_code = Column(String(12), nullable=False)
    price = Column(PRICE)
    change_pct = Column(RATIO)
    volume = Column(VOLUME)
    amount = Column(MARKET_VALUE)
    update_time = Column(DateTime, nullable=False)
    __table_args__ = (UniqueConstraint("ts_code", "update_time"),)
```

#### 4.2 盘中轮询任务

**新文件**: `fetchers/intraday.py`

```python
INTRADAY_POOL_SIZE = 50  # 最大轮询股票数

def get_intraday_pool() -> list[str]:
    """获取盘中轮询股票池 = RPS 快照 Top 30 ∪ Potential Top 20 → 去重后 ≤50"""

def fetch_intraday_snapshot():
    """调用 ak.stock_zh_a_spot_em()，过滤股票池，写入 intraday_snapshot。
    熔断：连续 5 次失败暂停 30 分钟。
    """
```

**调度**: 盘中（9:30-15:00）每 10 分钟执行，仅交易日。

#### 4.3 SQLite WAL 配置

**文件**: `src/database/connection.py`（主落点）+ `src/database/engine.py`（SQLAlchemy 层）

注意：项目大量读写路径通过 `get_connection()` / `sqlite3.connect()` 直连，不经过 SQLAlchemy engine。WAL 配置必须覆盖两条路径。

**connection.py**（已有部分 PRAGMA，需确认完整性）：
```python
# 在 get_connection() 中确保每次连接都设置：
conn.execute("PRAGMA journal_mode=WAL")
conn.execute("PRAGMA busy_timeout=5000")
```

**engine.py**（SQLAlchemy 层，使用 connect event）：
```python
from sqlalchemy import event

@event.listens_for(engine, "connect")
def set_sqlite_pragma(dbapi_connection, connection_record):
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA busy_timeout=5000")
    cursor.close()
```

**不使用** `engine.execute()`（已废弃于 SQLAlchemy 2.x）。

#### 4.4 前端盘中数据条件渲染

**文件**: 个股详情页、市场概览页

- 判断当前是否盘中时段（9:30-15:00 交易日）
- 盘中：优先读 `intraday_snapshot`，显示实时价格和更新时间
- 盘后：读日线数据，显示收盘价

#### 4.5 response_model 覆盖率检查

**文件**: `.github/workflows/ci.yml`

新增脚本检查所有 `@app.get` / `@app.post` 路由是否有 `response_model` 参数。
目标：核心端点覆盖率 > 60%。

#### 4.6 盘中试点评估报告

第 4 周末产出评估文档 `docs/intraday-pilot-evaluation.md`：

- AkShare 调用成功率
- 平均响应时间
- SQLite 写入冲突次数
- 用户价值判断（是否值得继续）
- 结论：扩张 / 维持 / 停止

### 完成标准 (DoD)

- [ ] 盘中轮询任务在交易时段正常执行（日志可见）
- [ ] 熔断机制在模拟 5 次连续失败后暂停轮询
- [ ] SQLite WAL 模式已启用（`PRAGMA journal_mode` 返回 `wal`）
- [ ] 前端盘中时段显示实时价格，盘后显示收盘价
- [ ] CI 包含 response_model 覆盖率检查
- [ ] 试点评估报告已产出

### 修改文件范围

| 文件 | 修改类型 |
|------|---------|
| `src/database/models.py` | 新增 IntradaySnapshot |
| `fetchers/intraday.py` | 新建 |
| `src/database/connection.py` | SQLite WAL/busy_timeout 确认 |
| `src/database/engine.py` | SQLAlchemy connect event WAL 配置 |
| `api/scheduler.py` | 新增盘中轮询任务 |
| `api/main.py` | 新增盘中数据端点 |
| `.github/workflows/ci.yml` | 新增覆盖率检查 |

### 测试策略

- `tests/test_intraday.py`（轮询逻辑、熔断、股票池生成）
- `tests/test_engine.py`（WAL 模式验证）
- 手动测试：交易时段观察日志

### 回滚点

- `intraday_snapshot` 表独立，删表即可
- 轮询任务可通过调度器暂停/删除
- WAL 模式可切回 DELETE 模式

---

## Backlog（本轮不做）

| 功能 | 原因 |
|------|------|
| 深色模式 | 低优先级，有余量再做 |
| Prometheus 指标 | 先用慢查询日志，后续再评估 |
| WebSocket 实时推送 | 依赖盘中试点结论 |
| openapi-typescript | 等 response_model 覆盖率足够 |
| 价格提醒（Telegram）| 依赖自选股后端化 |
| north_money_holding 命名收敛 | 维护性重构，不紧急 |

---

## 风险登记

| 风险 | 影响 | 缓解措施 |
|------|------|---------|
| RPS/potential screener 计算耗时超预期 | 快照生成延迟 | 限制计算范围，异步执行 |
| AkShare 接口变动 | full_analysis 批量失败 | 预计算范围限制 30-40 只，加重试 |
| SQLite FTS5 中文分词质量差 | 搜索体验不达标 | 用中文样本验证效果，不达标则先用 LIKE 保底，后续切 PostgreSQL tsvector |
| 盘中轮询触发 AkShare 限流 | IP 被封 | 熔断机制 + 低频率（10 分钟） |
| 前端指标计算性能 | K 线图卡顿 | 限制计算数据量（最近 250 个交易日） |
