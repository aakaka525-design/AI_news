# Phase 2 执行报告：可解释综合评分系统 (B1)

**执行者**: Claude
**日期**: 2026-03-09
**基础分支**: main (1cd3701)

## 实现状态

| Task | 描述 | 状态 |
|------|------|------|
| 1 | 评分表 DDL + 模型 | done |
| 2 | Freshness Decay 引擎 | done |
| 3 | 6 个因子计算器 | done |
| 4 | 评分引擎核心 | done |
| 5 | 排除规则 | done |
| 6 | Scheduler task `composite_score` | done |
| 7 | `GET /api/stocks/{ts_code}/score` | done |
| 8 | `GET /api/scores/ranking` | done |
| 9 | 评分单元测试 | done |
| 10 | API 集成测试 | done |
| 11 | CI 更新 | done |
| 12 | Handoff 文档 | done |

## 文件变更

| 文件 | 操作 | 说明 |
|------|------|------|
| `src/scoring/__init__.py` | 新建 | 包初始化 |
| `src/scoring/models.py` | 新建 | DDL: `stock_composite_score` + `stock_composite_factor` |
| `src/scoring/freshness.py` | 新建 | 3 类衰减规则 (daily_market / event_short / periodic_fundamental) |
| `src/scoring/factors.py` | 新建 | 6 个因子计算器 + FactorResult 数据类 |
| `src/scoring/engine.py` | 新建 | 评分核心: compute_score / compute_all_scores |
| `src/scoring/exclusions.py` | 新建 | 排除规则: delisted / st / new_listing |
| `api/scheduler.py` | 修改 | TASK_CONFIGS + TASK_EXPECTED_DATASETS + register composite_score_task |
| `api/main.py` | 修改 | 2 个新端点: /api/stocks/{ts_code}/score + /api/scores/ranking |
| `tests/test_scoring.py` | 新建 | 21 个测试: freshness/exclusions/factors/engine/storage |
| `tests/test_api.py` | 修改 | 10 个新测试: score endpoint + ranking endpoint |
| `.github/workflows/ci.yml` | 修改 | py_compile 检查 6 个 scoring 模块 |

## 设计决策

### 严格遵循 Codex 锁定设计
- 6 因子 / 3 bucket / 权重 0.40-0.30-0.30
- 三类 freshness decay 规则
- 排除规则: delisted + ST + new_listing(60 交易日)
- 独立 scheduler task 17:30

### 全市场百分位归一化
- `northbound_flow` 和 `main_money_flow` 使用全市场横截面数据
- 先批量收集所有股票 raw_value，再用 `pandas.rank(pct=True)` 统一归一化
- 其他因子在单股计算器内完成归一化

### API 容错
- 评分表不存在时 graceful 降级：score 端点返回 404，ranking 返回空列表
- excluded 股票返回 200 + `{status: "excluded", score: null}`

### 幂等
- `compute_all_scores()` 检查 trade_date + score_version 是否已有记录，有则跳过
- 写入使用 `INSERT OR REPLACE`，基于 UNIQUE 约束

## 复用的现有代码

| 模块 | 路径 | 复用方式 |
|------|------|---------|
| `macd()` | `src/analysis/technical.py:33` | tech_confirm 因子计算 MACD hist |
| `calculate_trading_day_delay()` | `fetchers/trading_calendar.py:225` | 计算因子 staleness |
| `get_connection()` | `src/database/connection.py` | 数据库连接 |
| `DatasetTelemetry` | `src/telemetry/models.py` | scheduler 返回 telemetry |
| `get_recent_trading_days()` | `fetchers/trading_calendar.py` | scheduler 获取最近交易日 |

## 测试结果

```
tests/test_scoring.py: 21 passed
tests/test_api.py: 98 passed (含 10 个新增评分测试)
py_compile: 全部 scoring 模块编译通过
```

## 待 Codex 复核要点

1. 因子计算器 SQL 查询是否与实际表结构匹配（尤其 `ts_hk_hold.vol`、`ts_moneyflow` 字段名）
2. `valuation` 因子的行业 PE 百分位计算：使用了同一 trade_date 的行业数据，是否需要更宽松的日期匹配
3. 全市场批量计算的性能：当前每 500 只 commit 一次，5000+ 股的执行时间待观察
4. `_compute_staleness` 内部 import `calculate_trading_day_delay` 的日期格式转换 (YYYYMMDD → YYYY-MM-DD)
