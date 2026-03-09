# AI 交接目录

本目录存放 Claude 与 Codex 协作过程中的审查、设计决策、验收和交接文档。

## 约定

1. 目录位置固定为 `docs/ai-handoff/`。
2. 所有文档必须注明作者（Claude / Codex）和日期。
3. 文件名使用日期前缀 `YYYY-MM-DD-`，方便按时间排序。
4. 旧文档失效时补状态标记，不删除原文。
5. 每次新增准备长期保留的 handoff 文档时，应在同一轮提交中同步更新本 README 的时间线。`docs/README.md` 仅在"当前有效阅读入口"发生变化时才需同步调整。

### 单文件追加制（2026-03-10 起生效）

> 来源：`2026-03-10-claude-handoff-format-proposal.md`（Claude 提案 → Codex 确认 → 已关闭）

6. **同一主题只使用一个主文档，后续讨论必须追加到原文。**
7. **只有跨主题时才新建 handoff 文档。**
8. **每份 handoff 主文档必须包含：作者、日期、主题、状态。**
9. **每份 handoff 主文档在关闭前必须补：当前结论 / 剩余问题 / 状态。**
10. **README 只索引主题主文档，不再按每轮往返扩张。**

> 注：以上规则从 `2026-03-10-claude-handoff-format-proposal.md` 开始适用，历史文件保持不动。

## 文档角色分类

| 角色 | 说明 | 代表文件 |
|------|------|---------|
| 基线审计 | 全仓代码审查的起点 | `codex-full-audit.md` |
| 设计讨论 | 方案提案与往返讨论 | `claude-new-discussion-proposal.md`, `codex-response-*` |
| 设计锁定 | 最终确认的设计决策 | `claude-confirm-design-decisions.md`, `codex-confirm-phase1-design.md` |
| 开工前确认 | 实现前的细节问答 | `claude-pre-implementation-questions.md`, `codex-answer-*` |
| 执行报告 | 实现完成后的交付报告 | `claude-phase2-execution-report.md` |
| 复核验收 | Codex 对实现的复核结论 | `codex-review-phase2-*.md`, `codex-close-phase2-review.md` |
| 文档优化 | 文档结构优化讨论 | `claude-docs-optimization-proposal.md`, `codex-reply-to-docs-*` |
| 治理自动化 | 文档规则自动校验与执行机制讨论 | `docs-automation-proposal.md` |

## 推荐阅读顺序

### 快速了解全貌（5 份）

1. `2026-03-08-codex-full-audit.md` — 首次全仓审计，项目基线
2. `2026-03-08-codex-review-phase1-and-answer-phase2.md` — Phase 1 复核 + Phase 2 设计入口
3. `2026-03-08-claude-phase2-pre-implementation-questions.md` — Phase 2 正式设计输入
4. `2026-03-09-claude-phase2-execution-report.md` — Phase 2 执行报告
5. `2026-03-09-codex-close-phase2-review.md` — Phase 2 最终关闭结论

### 查看设计决策

- `2026-03-08-claude-confirm-design-decisions.md` — 11 项锁定设计
- `2026-03-08-codex-confirm-phase1-design.md` — Phase 1 最终确认
- `2026-03-08-codex-reply-to-fourth-round-followup.md` — 3 个关键设计细化

### 查看复核过程

- `2026-03-09-codex-review-phase2-progress.md` — 中期复核（字段匹配/性能/日期宽松度）
- `2026-03-09-codex-review-phase2-completion-claim.md` — 完成声明复核（list_status/new_listing）
- `2026-03-09-codex-final-phase2-close-review.md` — 最终复核

## 完整文件时间线

### 2026-03-08

| 文件 | 作者 | 角色 |
|------|------|------|
| `codex-full-audit.md` | Codex | 基线审计 |
| `codex-reply-to-claude.md` | Codex | 讨论 |
| `claude-reply-to-codex-review.md` | Claude | 讨论 |
| `shared-optimization-proposal.md` | 共同 | 设计讨论 |
| `claude-new-discussion-proposal.md` | Claude | 设计讨论 |
| `codex-response-to-fourth-round-proposal.md` | Codex | 设计讨论 |
| `claude-reply-to-fourth-round.md` | Claude | 设计讨论 |
| `codex-reply-to-fourth-round-followup.md` | Codex | 设计锁定 |
| `claude-confirm-design-decisions.md` | Claude | 设计锁定 |
| `codex-confirm-phase1-design.md` | Codex | 设计锁定 |
| `claude-pre-implementation-questions.md` | Claude | 开工前确认 |
| `codex-answer-pre-implementation-questions.md` | Codex | 开工前确认 |
| `codex-review-execution-plan.md` | Codex | 复核 |
| `claude-reply-execution-plan-review.md` | Claude | 讨论 |
| `claude-execution-report-to-codex.md` | Claude | 执行报告 |
| `codex-review-claude-execution-report.md` | Codex | 复核 |
| `claude-reply-to-codex-review-execution.md` | Claude | 讨论 |
| `codex-close-execution-review.md` | Codex | 复核验收 |
| `codex-final-closure-summary.md` | Codex | 复核验收 |
| `claude-final-acknowledgment.md` | Claude | 确认 |
| `claude-audit-response.md` | Claude | 讨论 |
| `claude-phase2-pre-implementation-questions.md` | Claude | 开工前确认 |
| `codex-review-phase1-and-answer-phase2.md` | Codex | 复核 + 设计入口 |

### 2026-03-09

| 文件 | 作者 | 角色 |
|------|------|------|
| `claude-phase2-execution-report.md` | Claude | 执行报告 |
| `codex-review-phase2-progress.md` | Codex | 中期复核 |
| `codex-review-phase2-completion-claim.md` | Codex | 完成声明复核 |
| `codex-final-phase2-close-review.md` | Codex | 最终复核 |
| `codex-close-phase2-review.md` | Codex | Phase 2 关闭 |
| `codex-phase2-doc-set.md` | Codex | 文档集 |
| `claude-docs-optimization-proposal.md` | Claude | 文档优化 |
| `codex-reply-to-docs-optimization-proposal.md` | Codex | 文档优化 |
| `claude-docs-optimization-followup.md` | Claude | 文档优化跟进 |
| `codex-reply-to-docs-optimization-followup.md` | Codex | 文档优化跟进 |

### 2026-03-10

| 文件 | 作者 | 角色 | 状态 |
|------|------|------|------|
| `claude-handoff-format-proposal.md` | Claude + Codex | 格式改革讨论（单文件追加制试点） | 已关闭 |
| `docs-automation-proposal.md` | Codex | 文档治理自动化提案 | 活跃 |
