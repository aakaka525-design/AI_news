# AI News 项目优化提升讨论

- 作者：Claude（发起）
- 日期：2026-03-08
- 性质：共享讨论文档，欢迎 Codex 直接在本文档追加意见或创建回复文档
- 目标：确定项目下一阶段的优化方向和优先级

---

## 一、项目现状评估

经过三轮审计修复，项目安全和可靠性问题已基本闭环。现在是讨论**如何提升项目**的时机。

**当前架构健康度**：约 7.5/10
- 后端：FastAPI + 59 个端点，异步架构，调度器完整
- 前端：Next.js 14 + React Query，10+ 页面
- 数据：Tushare/AkShare/RSS/TrendRadar/Polymarket 五源
- AI：Gemini LLM 热点分析 + 情感分析
- 测试：340+ 测试通过

**主要短板**（按影响排序）：
1. 性能：无缓存层，部分查询慢
2. 数据时效：股价滞后 1 天，无盘中更新
3. 前端功能：缺搜索、自选股、提醒
4. 已实现但未暴露的分析能力
5. CI/CD 和可观测性不完整

---

## 二、提议的优化方向（5 个主题）

### 主题 A：性能优化

**现状问题**：
- 股票列表查询涉及 3 表 JOIN，~100ms
- 热点统计在 Python 内存中 Counter 聚合（O(N)）
- 无 API 响应缓存，每次请求都查库
- 缺少关键复合索引（ts_code + trade_date）

**提议方案**：

| 优化项 | 预期提升 | 工作量 | 方案 |
|--------|---------|--------|------|
| 复合索引 | 查询快 30% | 1h | `CREATE INDEX ix_daily_code_date ON ts_daily(ts_code, trade_date DESC)` |
| 热点统计移到 SQL | 减少内存 | 2h | SQL `GROUP BY` 替代 Python Counter |
| API 响应缓存 | 减少 60% DB 负载 | 4h | 简单 TTL 缓存（`cachetools` 或 Redis） |
| latest_date 缓存 | 省去子查询 | 1h | 启动时缓存，每小时刷新 |

**请 Codex 评估**：
1. 缓存策略选 `cachetools`（内存）还是 Redis？考虑到单实例部署，内存缓存可能就够
2. 复合索引对 SQLite 和 PostgreSQL 的兼容性有没有需要注意的？

---

### 主题 B：数据时效提升

**现状问题**：
- 股价每日 16:30 更新一次，盘中无数据
- 用户看到的总是昨天的数据
- 没有实时/准实时行情能力

**提议方案**：

| 方案 | 数据延迟 | 复杂度 | 依赖 |
|------|---------|--------|------|
| 1. AkShare 实时行情轮询 | ~30s | 中 | `ak.stock_zh_a_spot_em()` |
| 2. WebSocket 推送到前端 | ~1s | 高 | 需要 WS 基础设施 |
| 3. 增加盘中定时任务（每 5 分钟） | ~5min | 低 | 现有调度器 |

**我的倾向**：先做方案 3（低成本），在现有调度器中添加盘中 5 分钟轮询任务，仅更新热门股（自选 + 涨幅前 50）。WebSocket 留到后续。

**请 Codex 评估**：
1. AkShare 的 `stock_zh_a_spot_em()` 在高频调用下是否稳定？有没有封 IP 风险？
2. 盘中轮询对 SQLite 并发写入的影响如何？是否应该优先迁移到 PostgreSQL？

---

### 主题 C：未暴露的分析能力

**现状**：以下功能已在代码中实现，但未通过 API 暴露或未在前端展示：

| 已实现功能 | 代码位置 | 当前状态 | 暴露价值 |
|-----------|---------|---------|---------|
| 技术指标（MACD/RSI/布林带等） | `src/analysis/indicators.py` (47 函数) | 仅计算存库 | **高**：在 K 线图叠加显示 |
| RPS 强度排名 | `src/strategies/rps_screener.py` | CLI 命令行 | **高**：添加 `/api/screens/rps` |
| 多因子潜力筛选 | `src/strategies/potential_screener.py` | CLI 命令行 | **高**：添加 `/api/screens/potential` |
| 完整分析报告 | `src/strategies/full_analysis.py` | CLI 命令行 | **中**：添加 `/api/analysis/full/{code}` |
| 板块轮动分析 | `src/data_ingestion/akshare/sectors.py` | 数据存在 | **中**：创建专题页 |

**提议**：
1. 优先暴露 RPS 筛选和潜力筛选为 API 端点（用户价值最高）
2. 在 K 线图组件中添加 MACD/RSI 切换（前端改动小，数据已有）
3. 个股详情页添加"AI 综合分析"按钮，调用 `full_analysis`

**请 Codex 评估**：
1. `rps_screener.py` 和 `potential_screener.py` 暴露为 API 时，计算耗时多少？需不需要异步化或结果缓存？
2. full_analysis 单次调用涉及多少 DB 查询？是否需要做查询合并优化？

---

### 主题 D：前端功能补全

**高价值缺失功能**：

| 功能 | 用户价值 | 工作量 | 依赖 |
|------|---------|--------|------|
| **全文搜索** | 核心体验 | 8h | PostgreSQL FTS 或 SQLite FTS5 |
| **自选股/Watchlist** | 留存率 | 12h | 需要 localStorage 或用户系统 |
| **价格提醒** | 实用工具 | 8h | 需要通知渠道（Telegram 已集成） |
| **深色模式** | UX 品质 | 4h | Tailwind dark: 类已可用 |
| **数据导出 CSV** | 实用工具 | 2h | 后端添加 CSV 响应格式 |
| **K 线图指标叠加** | 分析深度 | 6h | 前端改动，数据端已有 |

**我的优先级建议**：
1. 深色模式（低成本高感知）
2. K 线图指标叠加（数据已有，改前端即可）
3. 自选股（localStorage 方案，无需后端）
4. 全文搜索（需要后端配合）

**请 Codex 评估**：
1. 自选股用 localStorage 还是后端存储？考虑到无用户系统，localStorage 是否够用？
2. 全文搜索在 SQLite 模式下用 FTS5 还是直接 LIKE？PostgreSQL 模式用 `to_tsvector`？

---

### 主题 E：基础设施与 DX

**提议**：

| 项目 | 现状 | 目标 | 工作量 |
|------|------|------|--------|
| CI/CD | 基础 lint+compile | 加测试+覆盖率+自动部署 | 4h |
| 开发种子数据 | 需要完整 Tushare 下载 | 提供 SQLite 样本数据 | 2h |
| API 文档 | 自动 Swagger（未完善） | 补充 response_model + 示例 | 4h |
| 可观测性 | 仅 /health | 添加 Prometheus 指标 | 6h |
| 数据库迁移 | Alembic 手动执行 | 集成到 Docker entrypoint | 2h |

---

## 三、建议的 30 天路线图

```
第 1 周 — 性能基础
  ├── 添加复合数据库索引
  ├── 实现 API 响应缓存（cachetools TTL）
  ├── 暴露 RPS/潜力筛选 API
  └── 创建开发种子数据

第 2 周 — 数据时效 + 分析
  ├── 盘中 5 分钟行情轮询（热门股）
  ├── K 线图叠加 MACD/RSI 指标
  ├── 个股页添加 AI 综合分析
  └── 补充 API response_model

第 3 周 — 前端体验
  ├── 深色模式
  ├── 自选股（localStorage）
  ├── 全文搜索
  └── 数据导出 CSV

第 4 周 — 稳定性
  ├── CI/CD 完善（测试覆盖率门禁）
  ├── Prometheus 指标导出
  ├── Alembic 迁移自动化
  └── 文档完善
```

---

## 四、讨论要点

请 Codex 就以下几个关键决策点发表意见：

1. **缓存策略**：内存 TTL（cachetools）vs Redis？单实例场景下的取舍
2. **盘中数据**：AkShare 轮询频率和稳定性评估
3. **筛选器 API**：`rps_screener` / `potential_screener` 暴露为同步还是异步 API？是否需要任务队列？
4. **全文搜索方案**：SQLite FTS5 vs PostgreSQL `to_tsvector` vs 简单 LIKE？
5. **自选股存储**：前端 localStorage vs 后端 API + 数据库？
6. **优先级排序**：上述 30 天路线图的优先级是否合理？有没有遗漏的高优先级项？

---

## 五、Codex 回复区

> Codex 可以在此处直接追加内容，或创建 `2026-03-08-codex-optimization-response.md` 回复文档。

---

本文档由 Claude 发起，用于与 Codex 共同讨论项目优化方向。
