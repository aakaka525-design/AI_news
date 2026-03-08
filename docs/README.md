# AI News 项目文档索引

## 目录结构

| 目录 | 说明 |
|------|------|
| `docs/ai-handoff/` | AI 协作轨迹：审查、验收、设计决策、交接记录 |
| `docs/plans/` | 设计方案与实施计划（含历史草案） |
| `docs/execution-plan-week1-4.md` | 阶段性路线图执行计划 |

## 状态图例

文档顶部的状态标记含义：

| 标记 | 说明 |
|------|------|
| `状态：活跃` | 当前有效，可作为实施依据 |
| `状态：已完成` | 目标已达成，作为完成记录保留 |
| `状态：部分完成` | 部分目标被后续工作吸收，其余待定 |
| `状态：已搁置` | 暂时搁置，未来可能重启 |
| `状态：前提失效` | 设计前提已被否定，仅供历史参考 |

## 推荐阅读顺序

### 首次了解项目

1. `docs/plans/2026-03-02-project-evolution-design.md` — 项目演进总体设计
2. `docs/execution-plan-week1-4.md` — 阶段执行路线图
3. `docs/ai-handoff/README.md` — AI 协作文档导航

### 了解当前架构决策

1. `docs/ai-handoff/2026-03-08-codex-full-audit.md` — Codex 首次全仓审计基线
2. `docs/ai-handoff/2026-03-08-codex-review-phase1-and-answer-phase2.md` — Phase 1 复核 + Phase 2 设计锁定
3. `docs/ai-handoff/2026-03-09-codex-close-phase2-review.md` — Phase 2 最终关闭结论

### 了解评分系统设计

1. `docs/ai-handoff/2026-03-08-claude-phase2-pre-implementation-questions.md` — Phase 2 设计输入
2. `docs/ai-handoff/2026-03-09-claude-phase2-execution-report.md` — Phase 2 执行报告
3. `docs/ai-handoff/2026-03-09-codex-review-phase2-progress.md` — Codex 中期复核

## 维护规则

1. 新文档必须标明作者和日期
2. AI 协作/审查类文档放 `docs/ai-handoff/`，设计方案放 `docs/plans/`
3. 旧文档失效时，在顶部补状态标记，不直接删除或覆盖原文
4. 文件名使用日期前缀 `YYYY-MM-DD-` 便于排序
