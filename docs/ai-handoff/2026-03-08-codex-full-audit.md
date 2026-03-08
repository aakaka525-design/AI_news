# 当前项目全量审核结果

- 作者：Codex
- 日期：2026-03-08
- 范围：当前工作树全量（含已提交代码、未提交修改、未跟踪源码/测试文件）
- 用途：供后续 AI/代理查阅和继续处理

## 审核结论

结论为 `REQUEST_CHANGES`。

本轮审查覆盖：

- 代码文件约 `204` 个
- 测试文件约 `46` 个
- FastAPI 路由约 `43` 个

已确认的自动化证据：

- `npm run lint --silent`：通过，存在 2 个 `<img>` warning
- `npm run build --silent`：通过
- `pytest -q tests/test_full_analysis.py tests/test_gemini_client.py tests/test_sentiment.py tests/test_tushare_daily.py`：`41 passed`
- `pytest -q tests/test_api_endpoints.py -x`：存在确定失败用例

## 高优先级问题

### 1. `api/main.py`

- `run_task` 的忙碌态检查不是原子操作。
- 当前实现使用 `_task_semaphore.locked()` 再进入 `async with _task_semaphore`，两个并发请求可能同时通过检查。
- 当前行为测试已经漂移：`tests/test_api_endpoints.py` 仍在 monkeypatch `_task_running`，会直接失败。

处理建议：

- 改为“状态位 + 短锁”的原子实现。
- 同步修复行为测试。

### 2. `fetchers/research_report.py`

- `fetch_stock_reports()` 使用 `signal.SIGALRM` 做超时。
- 该函数被 `api/main.py` 中的 `run_in_threadpool(...)` 调用。
- Python 在线程里不允许调用 `signal.signal(...)`，会触发 `ValueError: signal only works in main thread of the main interpreter`。
- 当前代码会吞掉异常并返回空列表，容易把“实现错误”伪装成“没有数据”。

处理建议：

- 不要在线程池函数里使用 `signal`。
- 将超时控制移到调用层，例如 `asyncio.wait_for(run_in_threadpool(...), timeout=...)`。

### 3. `src/strategies/potential_screener.py`

- `percentile_score()` 会给缺失值正分。
- 本地最小复现：
  - `percentile_score([None, None], 10) -> [7.5, 7.5]`
- `PE` 缺失时会直接给 `fund_roe +3`、`fund_growth +4`，即使 `ROE` 和 `netprofit_yoy` 本身也缺失。

影响：

- 选股总分会被错误抬高。
- Top N 排名不可信。

处理建议：

- 百分位只对非空值排名。
- 仅在“基础财务存在但 PE 缺失”时做权重重分配。

### 4. `src/data_ingestion/akshare/north_money.py`

- 将 `north_money_holding` 从兼容视图语义切成了真实表语义。
- 下游仍有代码依赖 `net_buy` / `net_buy_value` 字段。
- 兼容契约已断裂，可能导致排序、汇总或查询报错。

处理建议：

- 保留兼容视图，原始抓取写新表。
- 或者补齐旧字段并统一修改所有下游查询。

### 5. `src/data_ingestion/akshare/margin_trading.py`

- Tushare 路径内层循环吞掉异常。
- 外层“失败时回退到 akshare”逻辑经常不会触发。
- 最坏情况下会返回“0 条数据但看起来执行成功”。

处理建议：

- 记录成功天数与失败天数。
- 在全量失败时显式抛异常，驱动外层回退逻辑。

## 中优先级问题

### 1. `src/data_ingestion/polymarket/client.py`

- 同样使用 `signal.SIGALRM` 做超时。
- 这种实现依赖执行上下文，在线程或某些调度执行器下不稳。
- 当前实现会吞异常，只保留日志。

处理建议：

- 使用与线程上下文无关的 timeout 方案。

### 2. `fetchers/trading_calendar.py`

- 首次加载日历时会走远端拉取。
- 当前把“远端失败”和“无数据”都压成空列表。

处理建议：

- 分开处理超时、抓取失败和空结果。

### 3. `scripts/update_all_data.py`

- 某一步失败时，脚本仍可能以退出码 `0` 结束。

处理建议：

- 失败时显式 `SystemExit(1)`。

### 4. `run.py`

- `python run.py fetch` 文案像全量抓取，实际只调用 `tushare.daily.main()`。
- `run_api()` 默认 `reload=True`，更像开发模式默认值。

处理建议：

- 校正文案或调整命令行为。
- 用环境变量控制 `reload`，默认关闭。

### 5. `tests/test_run_cli.py`

- 目前只覆盖 `run_analyze()`。
- `run_fetch()`、`run_api()`、`run_migrate()` 缺少直接回归保护。

## 低优先级问题

### 1. `pyproject.toml` / `pytest.ini`

- 仓库存在两份 pytest 配置。
- 当前 `pytest` 已明确提示忽略 `pyproject.toml` 中的 pytest 配置。

### 2. `frontend/app/polymarket/page-client.tsx`

- 页面首屏一次拉取 200 条市场数据。
- 构建结果中 `/polymarket` 路由体积明显偏大。
- 仍有原生 `<img>` warning。

## 已检查但未发现明显问题的重点文件

- `api/middleware.py`
- `frontend/lib/api.ts`
- `frontend/lib/query-provider.tsx`
- `src/data_ingestion/compat.py`
- `src/data_ingestion/tushare/client.py`
- `src/database/engine.py`
- `tests/test_full_analysis.py`
- `tests/test_gemini_client.py`
- `tests/test_sentiment.py`
- `tests/test_tushare_daily.py`

## 适用度结论

### 本地开发

- 基本可用
- 前后端可构建
- 新增测试文件已被 pytest 收集

### 内部研究

- 有条件可用
- 先修选股器、北向资金、融资融券链路，否则分析结果不可靠

### 对外生产

- 暂不建议直接上线
- 需要先修复所有高优先级问题，再核查部署默认值和运行环境约束

## 备注

本文档由 Codex 编写，供后续 AI/代理查看、衔接与继续处理。
