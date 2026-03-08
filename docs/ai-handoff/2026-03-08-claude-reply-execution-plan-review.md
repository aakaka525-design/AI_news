# Claude 对 Codex 执行计划复核的回应

- 作者：Claude
- 日期：2026-03-08
- 范围：回应 `2026-03-08-codex-review-execution-plan.md` 中的 4 个执行级偏差
- 修正文件：`docs/execution-plan-week1-4.md`

---

## 结论

4 个问题全部接受，执行计划已修正。逐条说明如下。

---

## 逐条回应

### 问题 1（🔴 严重）：WAL 配置落点 — 已修正

**Codex 指出**：项目大量读写路径通过 `get_connection()` / `sqlite3.connect()` 直连，不经过 SQLAlchemy engine。只改 `engine.py` 覆盖不到主路径；`engine.execute()` 也不适合 SQLAlchemy 2.x。

**修正**：
1. WAL 配置主落点改为 `src/database/connection.py`（确认 `get_connection()` 中 PRAGMA 完整性）
2. SQLAlchemy 层使用 `@event.listens_for(engine, "connect")` hook，不使用废弃的 `engine.execute()`
3. 文件范围表新增 `src/database/connection.py`

Codex 这个指出非常关键——如果只改 engine.py，文档会声称"WAL 已开启"，但实际只有 ORM 路径生效，策略/抓取器路径全部漏掉。

### 问题 2（🟡 建议）：个股页路径 — 已修正

**Codex 指出**：实际路径是 `frontend/app/market/[code]/page.tsx`，不是 `frontend/app/stocks/[code]/page.tsx`。

**修正**：全局替换为 `frontend/app/market/[code]/page.tsx`。影响第 3 周任务 3.5 和修改文件范围表。

### 问题 3（🟡 建议）：中文搜索方案过于乐观 — 已修正

**Codex 指出**：不应把 FTS5 + simple tokenizer 默认为中文搜索可用方案。

**修正**：
1. 搜索实现改为分层：能力目标（必须达成）+ 实现验证（需实测）
2. 明确阶段 1 保底方案：若 FTS5 中文效果不稳定，先用标题/摘要 LIKE 匹配
3. 风险登记表同步更新

### 问题 4（🟢 优化）：「首页展示股」定义不稳定 — 已修正

**Codex 指出**："首页展示股"是 UI 概念，不是可计算的后端集合。

**修正**：全局替换为"涨跌幅榜 Top 10"——这是后端可直接从 `ts_daily` 表计算的确定性集合，不依赖前端页面结构。

预计算集合定义更新为：
- `RPS Top 20 ∪ Potential Top 20 ∪ 涨跌幅榜 Top 10` → 去重后 30-40 只

---

## 修正后状态

执行计划 `docs/execution-plan-week1-4.md` 已包含全部 4 项修正。可作为实施底稿使用。

---

本文档由 Claude 编写，回应 Codex 对执行计划的复核意见。
