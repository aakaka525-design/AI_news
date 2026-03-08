# Codex 对执行计划文档的复核

- 作者：Codex
- 日期：2026-03-08
- 范围：复核 `docs/execution-plan-week1-4.md`
- 上游文档：
  - `docs/ai-handoff/2026-03-08-shared-optimization-proposal.md`
  - `docs/execution-plan-week1-4.md`

---

## 结论

这份执行计划已经和共享路线图的大方向基本一致，可以作为执行底稿。  
但当前还有 4 个执行级偏差需要先修正，否则进入实施后会在第 1-4 周不同阶段撞到实际仓库结构。

我把问题分成：

- `1` 个高优先级执行偏差
- `3` 个中低优先级修正项

---

## 问题清单

| # | 位置 | 严重级别 | 问题描述 | 建议修正 |
|---|---|---|---|---|
| 1 | `docs/execution-plan-week1-4.md` 第 4 周 `4.3 SQLite WAL 配置` | 🔴 严重 | 计划写的是改 `src/database/engine.py` 并调用 `engine.execute("PRAGMA ...")`，但当前项目大量读写路径并不经过 SQLAlchemy engine，而是直接走 `src.database.connection.get_connection()` 或 `sqlite3.connect(...)`。只改 `engine.py` 覆盖不到主路径；同时 `engine.execute` 也不适合当前 SQLAlchemy 2.x 用法。 | 把 SQLite PRAGMA 配置的主落点改到 `src/database/connection.py` 及相关直连封装；若要在 SQLAlchemy engine 层生效，用 connect event，而不是 `engine.execute(...)`。 |
| 2 | `docs/execution-plan-week1-4.md` 第 3 周 `3.5 个股页 AI 综合分析展示` | 🟡 建议 | 文档写的是 `frontend/app/stocks/[code]/page.tsx`，但当前实际个股详情页路径是 `frontend/app/market/[code]/page.tsx`。如果按现文档执行，修改文件范围会直接偏掉。 | 把目标文件统一改成当前真实路由 `frontend/app/market/[code]/page.tsx`，并同步所有周计划中的文件范围引用。 |
| 3 | `docs/execution-plan-week1-4.md` 第 3 周 `3.2 SearchService` | 🟡 建议 | 文档把 `SQLite FTS5 (simple tokenizer)` 当成中文新闻搜索正式方案，但这对中文分词并不稳，容易把“实现完成”和“搜索效果可用”混为一谈。 | 把第 1 阶段搜索目标收窄为“股票代码/名称可靠搜索 + 新闻标题/摘要可用搜索”；中文全文搜索质量单独做验证项，不要在计划里默认 `simple tokenizer` 已满足效果。 |
| 4 | `docs/execution-plan-week1-4.md` 第 2 周 `2.4 full_analysis 快照化` | 🟢 优化 | 预计算集合里写了“首页展示股”，但这是 UI 概念，不是稳定的数据源定义。执行时容易出现“到底按哪个首页模块取”的歧义。 | 把“首页展示股”改成可计算的后端集合定义，例如“dashboard 核心榜单股票集”或配置化列表，避免执行层依赖前端页面结构。 |

---

## 详细说明

### 问题 1（🔴 严重）：WAL 配置落点不对，且 API 用法不适配当前结构

当前代码事实：

- `src/database/engine.py` 只负责 SQLAlchemy engine 工厂
- 但项目大量路径仍然走：
  - `src.database.connection.get_connection()`
  - `fetchers/db.py`
  - 直接 `sqlite3.connect(...)`

已确认的现状证据：

- `src/database/connection.py:410-411` 已有 `PRAGMA journal_mode=WAL` / `busy_timeout`
- 仓库中仍有大量 `get_connection()` / `sqlite3.connect(...)` 直接调用

这意味着：

- 如果只按执行计划改 `src/database/engine.py`
- 那么 ORM/repository 路径可能生效
- 但大量策略、抓取器、分析脚本路径不会同步生效

这会造成一个很糟的状态：

- 文档以为“WAL 已开启”
- 实际只有部分连接生效

建议修正为：

1. 把 SQLite 连接语义的“单一真相”放在 `src/database/connection.py`
2. 所有非 ORM 直连都尽量汇聚到统一连接工厂
3. SQLAlchemy engine 层若仍需补充，使用 connect hook，而不是 `engine.execute`

### 问题 2（🟡 建议）：个股页路径和当前仓库不一致

当前真实路径：

- `frontend/app/market/[code]/page.tsx`

执行计划当前写法：

- `frontend/app/stocks/[code]/page.tsx`

这不是小问题，因为它会影响：

- 实际修改文件
- 组件集成位置
- 测试文件引用
- 页面导航理解

建议直接把执行计划里的目标页统一改成当前真实路由，避免后续实现时又回头对照目录。

### 问题 3（🟡 建议）：中文搜索方案写得太乐观

当前计划已经很好地定义了“搜索语义先行”，这点是对的。  
但底层实现那里直接写成：

- `SQLite FTS5 实现（simple tokenizer）`

这在中文新闻搜索上风险较高。  
问题不在于“能不能跑”，而在于：

- 跑出来的结果可能看起来是全文搜索
- 实际召回和排序效果并不稳定

建议把计划改成两层：

1. **能力目标**
   - 股票代码精确匹配
   - 股票名称可靠模糊匹配
   - 新闻标题/摘要关键词搜索

2. **实现验证**
   - FTS5 方案需要用中文样本验证效果
   - 若效果不稳定，阶段 1 可先用更保守的标题/摘要匹配策略

这样执行计划会更诚实，也更容易验收。

### 问题 4（🟢 优化）：`首页展示股` 不是稳定的执行对象

“首页展示股”适合讨论文档，不适合执行计划。  
执行计划里更适合写成：

- “由 dashboard 逻辑明确产出的股票集合”
- 或“后端配置定义的展示股票池”

否则一到实施阶段，就会出现：

- 首页到底指主 dashboard 还是市场页
- 用哪个模块的数据
- 如果首页布局变了，这个集合还算不算“首页展示股”

建议把它收敛成一个后端可计算、可测试的集合定义。

---

## 建议处理顺序

1. 先修正执行计划中的 `WAL` 落点描述
2. 再修正个股页真实路径
3. 然后收窄搜索实现表述
4. 最后把 `首页展示股` 改成稳定集合定义

---

## 当前判断

这份执行计划不需要推倒重写。  
更合适的做法是：

- 保留当前周计划结构
- 只修正上述 4 个执行级偏差

修完后，这份文档就可以作为下一阶段实现的直接底稿。

本文档由 Codex 编写，用于回应 `docs/execution-plan-week1-4.md` 的当前版本。
