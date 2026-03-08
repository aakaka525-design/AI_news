# Codex 整理的 Phase 2 文档提交清单

- 作者：Codex
- 日期：2026-03-09
- 目的：把 `docs/ai-handoff/` 中和 Phase 2 相关的文档整理成可提交清单，避免把无关讨论一起带入一次提交。

---

## 1. 推荐提交方式

我建议分成两种选择：

### 方案 A：最小提交集

适合你只想保留：

- Phase 2 的设计输入
- Claude 的执行报告
- Codex 的最终复核结论

推荐文件：

1. `docs/ai-handoff/README.md`
2. `docs/ai-handoff/2026-03-08-claude-phase2-pre-implementation-questions.md`
3. `docs/ai-handoff/2026-03-08-codex-review-phase1-and-answer-phase2.md`
4. `docs/ai-handoff/2026-03-09-claude-phase2-execution-report.md`
5. `docs/ai-handoff/2026-03-09-codex-review-phase2-progress.md`
6. `docs/ai-handoff/2026-03-09-codex-review-phase2-completion-claim.md`
7. `docs/ai-handoff/2026-03-09-codex-close-phase2-review.md`
8. `docs/ai-handoff/2026-03-09-codex-phase2-doc-set.md`

这个集合的特点是：

- 能看清 Phase 2 从设计确认到最终关闭的主线
- 不把更早期的执行计划争论、优化路线讨论一起混进来
- 足够给后续维护者理解“为什么这么做”和“最后是怎么验收通过的”

---

### 方案 B：完整追溯集

适合你希望仓库里完整保留 Phase 2 前后的设计讨论链。

推荐文件：

1. `docs/ai-handoff/README.md`
2. `docs/ai-handoff/2026-03-08-claude-confirm-design-decisions.md`
3. `docs/ai-handoff/2026-03-08-codex-confirm-phase1-design.md`
4. `docs/ai-handoff/2026-03-08-claude-phase2-pre-implementation-questions.md`
5. `docs/ai-handoff/2026-03-08-codex-answer-pre-implementation-questions.md`
6. `docs/ai-handoff/2026-03-08-codex-review-phase1-and-answer-phase2.md`
7. `docs/ai-handoff/2026-03-09-claude-phase2-execution-report.md`
8. `docs/ai-handoff/2026-03-09-codex-review-phase2-progress.md`
9. `docs/ai-handoff/2026-03-09-codex-review-phase2-completion-claim.md`
10. `docs/ai-handoff/2026-03-09-codex-close-phase2-review.md`
11. `docs/ai-handoff/2026-03-09-codex-phase2-doc-set.md`

这个集合的特点是：

- 设计锁定点更完整
- 更适合以后复盘“为什么 Phase 2 选了这些边界和取舍”
- 提交体积会比最小集更大，但仍然只围绕 Phase 2，不会把所有历史讨论塞进去

---

## 2. 不建议纳入本次 Phase 2 提交的文档

以下文件不是无价值，而是它们更偏：

- Phase 1 之前的审计往返
- 执行计划早期争论
- 优化路线讨论
- 已被后续文档覆盖的中间态意见

不建议放进本次 Phase 2 文档提交：

1. `docs/ai-handoff/2026-03-08-codex-full-audit.md`
2. `docs/ai-handoff/2026-03-08-codex-reply-to-claude.md`
3. `docs/ai-handoff/2026-03-08-codex-final-followup-to-claude.md`
4. `docs/ai-handoff/2026-03-08-shared-optimization-proposal.md`
5. `docs/ai-handoff/2026-03-08-codex-review-execution-plan.md`
6. `docs/ai-handoff/2026-03-08-codex-review-claude-execution-report.md`
7. `docs/ai-handoff/2026-03-08-codex-close-execution-review.md`
8. `docs/ai-handoff/2026-03-08-codex-final-closure-summary.md`
9. `docs/ai-handoff/2026-03-08-codex-response-to-fourth-round-proposal.md`
10. `docs/ai-handoff/2026-03-08-codex-reply-to-fourth-round-followup.md`
11. `docs/ai-handoff/2026-03-09-codex-final-phase2-close-review.md`

其中最后这个：

- `2026-03-09-codex-final-phase2-close-review.md`

我建议视为**已被后续的** `2026-03-09-codex-close-phase2-review.md` **覆盖**，不需要两份都提交。

---

## 3. 我给你的直接建议

如果你想让这次提交干净、信息密度高，我建议用：

- **方案 A：最小提交集**

如果你想把整个 Phase 2 设计-实现-复核链都留在仓库里，用：

- **方案 B：完整追溯集**

---

## 4. 可直接执行的 git add 清单

### 方案 A

```bash
git add \
  docs/ai-handoff/README.md \
  docs/ai-handoff/2026-03-08-claude-phase2-pre-implementation-questions.md \
  docs/ai-handoff/2026-03-08-codex-review-phase1-and-answer-phase2.md \
  docs/ai-handoff/2026-03-09-claude-phase2-execution-report.md \
  docs/ai-handoff/2026-03-09-codex-review-phase2-progress.md \
  docs/ai-handoff/2026-03-09-codex-review-phase2-completion-claim.md \
  docs/ai-handoff/2026-03-09-codex-close-phase2-review.md \
  docs/ai-handoff/2026-03-09-codex-phase2-doc-set.md
```

### 方案 B

```bash
git add \
  docs/ai-handoff/README.md \
  docs/ai-handoff/2026-03-08-claude-confirm-design-decisions.md \
  docs/ai-handoff/2026-03-08-codex-confirm-phase1-design.md \
  docs/ai-handoff/2026-03-08-claude-phase2-pre-implementation-questions.md \
  docs/ai-handoff/2026-03-08-codex-answer-pre-implementation-questions.md \
  docs/ai-handoff/2026-03-08-codex-review-phase1-and-answer-phase2.md \
  docs/ai-handoff/2026-03-09-claude-phase2-execution-report.md \
  docs/ai-handoff/2026-03-09-codex-review-phase2-progress.md \
  docs/ai-handoff/2026-03-09-codex-review-phase2-completion-claim.md \
  docs/ai-handoff/2026-03-09-codex-close-phase2-review.md \
  docs/ai-handoff/2026-03-09-codex-phase2-doc-set.md
```
