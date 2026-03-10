# P0 AkShare 迁移执行报告

**执行日期:** 2026-03-10
**执行者:** Claude Opus 4.6
**设计文档:** `docs/ai-handoff/2026-03-10-self-built-datasource-proposal.md`

## 概要

用 AkShare（免费）替换 Tushare（token 过期）的 6 个核心 dataset producer，恢复全部 P0 数据采集能力。

## 实现的 6 个 Producer

| Producer | 文件 | AkShare API | 目标表 | 模式 |
|----------|------|-------------|--------|------|
| stock_basic | `producers/stock_basic.py` | `stock_info_a_code_name()` + `stock_board_industry_cons_em()` + `stock_individual_info_em()` | `ts_stock_basic` | 全量更新 |
| daily | `producers/daily.py` | `stock_zh_a_hist()` (不复权+前复权) | `ts_daily` | 逐股日增量 |
| daily_basic | `producers/daily_basic.py` | `stock_zh_a_spot_em()` | `ts_daily_basic` | 全市场批量 |
| moneyflow | `producers/moneyflow.py` | `stock_individual_fund_flow()` | `ts_moneyflow` | 逐股日增量 |
| hk_hold | `producers/hk_hold.py` | `stock_hsgt_hold_stock_em()` | `ts_hk_hold` | 全市场批量 |
| fina_indicator | `producers/fina_indicator.py` | `stock_financial_analysis_indicator()` | `ts_fina_indicator` | 逐股季度 |

## Scheduler 替换

**移除 3 个 Tushare 任务:**
- `stock_indicators` (16:30 mon-fri)
- `fund_flow` (17:00 mon-fri)
- `macro_data` (08:00 daily)

**新增 6 个 AkShare 任务:**
- `akshare_stock_basic` (08:00 daily)
- `akshare_daily` (16:30 mon-fri)
- `akshare_daily_basic` (16:35 mon-fri)
- `akshare_moneyflow` (17:00 mon-fri)
- `akshare_hk_hold` (08:30 mon-fri)
- `akshare_fina_indicator` (18:00 mon-fri)

## 非 P0 降级表

以下数据集在 Tushare token 过期后已停更，P0 不为其创建 producer：

| 数据集 | 原任务 | P0 状态 | 后续计划 |
|--------|--------|---------|---------|
| `ts_weekly` | stock_indicators | 不调度 | P1 |
| `ts_hsgt_top10` | fund_flow | 不调度 | P1 |
| `ts_top10_holders` | macro_data | 不调度 | P2 |
| `ts_cashflow` | macro_data | 不调度 | P2 |
| `ts_cyq_perf` | macro_data | 不调度 | P3 |

## 测试结果

- `tests/test_akshare_producers.py`: 19 个单元测试全部通过
- `tests/test_api.py::TestSchedulerTaskConfigs`: 3 个配置验证测试通过
- 全部 7 个 producer 文件编译检查通过

## 已知限制

1. **stock_basic list_date**: 需通过 `stock_individual_info_em()` 逐股查询上市日期，首次运行耗时较长（~5000 次 API 调用）；后续增量运行只查新股
2. **moneyflow**: AkShare 只提供 `net_mf_amount`（主力净流入净额），buy/sell 分档字段写 NULL
3. **fina_indicator**: 字段映射覆盖 14 个核心指标，原 Tushare 29 字段中部分不可用（如 netprofit_yoy 等增长率指标需要额外计算）
4. **daily adj_factor**: 通过 qfq_close / raw_close 计算，精度可能与 Tushare 原生 adj_factor 有微小差异

## 文件变更汇总

| 文件 | 操作 |
|------|------|
| `src/data_ingestion/akshare/producers/__init__.py` | 新建 |
| `src/data_ingestion/akshare/producers/utils.py` | 新建 |
| `src/data_ingestion/akshare/producers/stock_basic.py` | 新建 |
| `src/data_ingestion/akshare/producers/daily.py` | 新建 |
| `src/data_ingestion/akshare/producers/daily_basic.py` | 新建 |
| `src/data_ingestion/akshare/producers/moneyflow.py` | 新建 |
| `src/data_ingestion/akshare/producers/hk_hold.py` | 新建 |
| `src/data_ingestion/akshare/producers/fina_indicator.py` | 新建 |
| `src/data_ingestion/akshare/__init__.py` | 修改 |
| `api/scheduler.py` | 修改 |
| `tests/test_akshare_producers.py` | 新建 |
| `tests/test_api.py` | 修改 |
| `.github/workflows/ci.yml` | 修改 |
