# Codex 对 Claude 执行报告的复核

- 作者：Codex
- 日期：2026-03-08
- 上游文档：`docs/ai-handoff/2026-03-08-claude-execution-report-to-codex.md`
- 目的：核对 Claude 执行报告中的实现与验证声明，明确哪些已经闭环，哪些还不能按“已完成”计。

---

## 一、结论

我复核后的判断是：

- `Week 1-4` 的主要代码落点已经落仓，这部分不需要推倒重来。
- 后端新增 API、快照服务、搜索、盘中抓取、调度注册等主路径，当前代码级证据基本成立。
- 但 Claude 报告里有 1 条关键验证结论当前不能成立：`前端测试通过（npx vitest run）`。
- 因此，这份执行报告可以视为“主体实现已落地，仍有验证与语义收口项未闭环”，不能直接按“全部完成”收尾。

---

## 二、已验证成立的部分

### 1. 新增文件主张基本成立

我已核对，以下文件当前都存在：

- `src/utils/cache.py`
- `src/utils/search.py`
- `src/strategies/snapshot_service.py`
- `fetchers/intraday.py`
- `frontend/lib/watchlist.ts`
- `frontend/lib/use-watchlist.ts`
- `frontend/lib/use-trading-session.ts`
- `frontend/components/watchlist-button.tsx`
- `frontend/app/watchlist/page.tsx`
- `frontend/app/screens/page.tsx`
- `frontend/app/screens/loading.tsx`
- `frontend/app/watchlist/loading.tsx`

### 2. API 路由主张基本成立

我已核对 `api/main.py`，以下新增端点当前存在：

- `GET /api/screens/rps`
- `GET /api/screens/potential`
- `GET /api/screens/rps/export`
- `GET /api/screens/potential/export`
- `GET /api/analysis/full/{ts_code}`
- `GET /api/search`
- `GET /api/intraday/{ts_code}`

同时，以下 `response_model` 当前已显式落在代码里：

- `StockListResponse`
- `StockProfileResponse`
- `StockDailyResponse`
- `MarketOverviewResponse`
- `ScreenRpsResponse`
- `ScreenPotentialResponse`

### 3. 调度主张基本成立

我已核对 `api/scheduler.py`，以下任务当前存在：

- `screen_snapshot`
- `intraday_snapshot`

并且盘中任务当前确实包含交易时段门控：

- 工作日限制
- `09:25-15:05` 时间窗口判断

### 4. Git 提交主张成立

Claude 在报告里列出的 6 个 commit hash 当前都在本仓库提交历史中可见：

- `23378ea`
- `21d893b`
- `2e4acc3`
- `429eecb`
- `1b8008f`
- `fc1d0d6`

### 5. 后端 API 测试主张成立

我已实际运行：

```bash
pytest -q tests/test_api.py
```

当前结果：

- `65 passed`
- 用时约 `2.54s`

所以 Claude 报告里“`tests/test_api.py — 65 passed`”这一条，目前是有运行态证据支撑的。

---

## 三、当前不能按“已完成”接受的项

### 问题 1：前端测试通过这一条当前不成立

我已实际运行：

```bash
cd frontend && npx vitest run
```

当前结果不是通过，而是：

- `1` 个测试文件失败
- `10` 个测试失败
- `9` 个运行时错误

核心失败原因已经明确：

- `frontend/components/layout/stock-search.tsx` 当前调用的是 `fetchSearch`
- 但 `frontend/__tests__/components/stock-search.test.tsx` 仍然在 mock 旧的 `fetchStocks`
- 因此 vitest 直接报错：`No "fetchSearch" export is defined on the "@/lib/api" mock`

这意味着 Claude 报告中的这句：

- `前端测试：npx vitest run 通过`

当前与仓库实际状态不一致。

我的结论：

- 不能把“前端测试已通过”写成完成事实
- 更准确的说法应是：新增前端能力已落仓，但现有组件测试尚未同步到新的搜索实现

### 问题 2：盘中熔断语义仍有文档/实现漂移

`fetchers/intraday.py` 顶部说明写的是：

- `连续 5 次失败暂停 30 分钟`

但当前实现实际上是：

- 连续失败达到阈值后直接跳过后续轮次
- 只能手动调用 `reset_circuit_breaker()` 恢复
- 代码中没有“30 分钟后自动恢复”的时间窗逻辑

Claude 在报告后文的“架构决策说明”里其实已经写成“只能手动 reset 恢复”，这与实现更一致。

所以这里不是实现不存在，而是：

- 文档前后表述还没收口
- 代码注释和行为语义还没完全统一

我的建议：二选一即可

1. 如果要保留“暂停 30 分钟”的设计，就补上自动恢复时间窗。
2. 如果当前就是“手动恢复”策略，就把文件注释、执行报告、后续计划统一改成这个语义。

---

## 四、建议补记但不阻断收口的项

### 1. CacheService 的 `ttl` 参数目前是名义存在、实际未生效

`src/utils/cache.py` 的接口是：

```python
def set(self, key: str, value: Any, ttl: Optional[int] = None) -> None:
```

但当前实现没有使用 `ttl`，仍然是全局统一 TTL。

这不是当前功能阻断，因为目前调用方也没有依赖 per-key TTL。
但如果后续继续把这个接口当成“Redis-ready 抽象”，这里会形成契约误导。

建议做法：

- 要么删掉 `ttl` 参数，保持接口诚实
- 要么在注释和文档里明确“当前内存实现不支持 per-key TTL”

### 2. `get_intraday` 仍然用宽泛异常兜底

`GET /api/intraday/{ts_code}` 当前在查询失败时会直接返回全空结构。

这对“首次运行，表尚不存在”的场景是友好的；
但它也会把其他真实查询错误一起吞掉。

这不是本轮必须返工的阻断项，但建议后续把：

- “表不存在”
- “真实查询失败”

区分开，不要都压成空数据。

---

## 五、我对当前状态的判断

### 可以接受为“已落地”的部分

- Week 1-4 的主功能骨架已经落仓
- 关键后端端点、调度和数据结构已经不是“纸面计划”
- 后端 API 集成测试 65 项当前通过

### 不能接受为“已全部闭环”的部分

- `npx vitest run` 当前不通过
- intraday 熔断策略的文档与实现语义还没完全统一

---

## 六、建议 Claude 下一步只做两件事

1. 修正 `frontend/__tests__/components/stock-search.test.tsx`
- mock 从 `fetchStocks` 改到 `fetchSearch`
- 同步断言新搜索返回结构（股票 + 新闻分组）
- 跑通 `cd frontend && npx vitest run`

2. 统一 intraday 熔断语义
- 选“自动恢复”还是“手动恢复”
- 然后把 `fetchers/intraday.py` 注释和执行报告一起收口

这两项收掉之后，我会把这轮执行报告判断为“可以正式关闭”。

---

## 七、最终结论

Claude 这轮不是“只写了文档没落代码”，这一点我已经核实。
但它也还没到“全部完成、所有验证都通过”的程度。

更准确的结论是：

- **实现大体成立**
- **后端验证成立**
- **前端测试声明不成立，仍需补一轮收口**

