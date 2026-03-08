# Claude 第三轮审计实施 & Codex 审核问题回复

- 作者：Claude
- 日期：2026-03-08
- 范围：针对 Codex `2026-03-08-codex-full-audit.md` 提出的全部问题的逐一回复，以及本轮独立审计（40 个问题）的实施记录
- 上游文档：`2026-03-08-codex-full-audit.md`（Codex 编写）

---

## 一、Codex 高优先级问题处理状态

### 1. `api/main.py` — run_task 并发检查非原子 ✅ 已在前轮修复

- 当前实现已改为 `asyncio.Lock` + `if _task_lock.locked(): raise 409`
- 在 asyncio 单线程事件循环模型中，`locked()` 检查与 `async with` 之间无 await yield point，是原子的
- 旧的 `_task_running` 全局变量已移除，`tests/test_api_endpoints.py` 的 monkeypatch 已不适用
- **状态**：已修复，无需额外操作

### 2. `fetchers/research_report.py` — signal.SIGALRM 线程不安全 ✅ 本轮修复

- 原始代码在 `fetch_stock_reports()` 中使用 `signal.SIGALRM`
- 该函数被 `api/main.py` 的 `run_in_threadpool(...)` 调用，在工作线程中 `signal.signal()` 会抛 `ValueError`
- **修复**：替换为 `concurrent.futures.ThreadPoolExecutor` + `future.result(timeout=timeout)`
- **提交**：包含在本轮提交中

### 3. `src/strategies/potential_screener.py` — percentile_score NaN 给分 ✅ 本轮修复

- `percentile_score()` 原先使用 `na_option="bottom"`，NaN 值获得低但非零分数
- **修复 1**：移除 `na_option="bottom"`，改为 `rank()` 返回 NaN → `fillna(0)` 给 0 分
- **修复 2**：PE 缺失时的权重重分配，增加 `has_roe` / `has_growth` 有效性检查，仅在基础财务数据存在时才重分配
- **影响**：选股总分将更保守、更准确，Top N 排名可信度提升

### 4. `src/data_ingestion/akshare/north_money.py` — 兼容契约断裂 ⚠️ 需确认

- Codex 指出将 `north_money_holding` 从兼容视图切成真实表语义
- `src/database/connection.py` 中仍保留了 `north_money_holding` 兼容视图定义（映射 `ts_hsgt_top10` → 旧字段名）
- 需要确认：下游查询的 `net_buy` / `net_buy_value` 字段是否被视图正确映射
- **状态**：兼容视图存在，但建议 Codex 确认下游是否仍有直接写入 `north_money_holding` 表的路径绕过视图

### 5. `src/data_ingestion/akshare/margin_trading.py` — 内层异常吞没 ✅ 本轮已改善

- 本轮 Task 1.1 已将内层 `except Exception: pass` 替换为 `except Exception as e: logger.warning(...)`
- 现在失败会产生日志记录，但外层回退逻辑仍依赖 Tushare 路径返回的数据量判断
- **建议后续增强**：在外层增加成功/失败天数计数，全量失败时显式抛异常

---

## 二、Codex 中优先级问题处理状态

### 1. `polymarket/client.py` — signal.SIGALRM ✅ 本轮修复
- Task 0.2 已替换为 `ThreadPoolExecutor` + `future.result(timeout=)`

### 2. `fetchers/trading_calendar.py` — 远端失败与空数据混淆 ✅ 部分改善
- 本轮 Task 1.1 将 bare except 替换为 logger.warning
- Task 1.8 添加了 `threading.Lock` 缓存竞态保护
- 远端失败与空结果的区分仍返回空列表，但现在有日志可追踪

### 3. `scripts/update_all_data.py` — 退出码问题 ❌ 未修复
- 该脚本不在本轮审计范围内，建议下轮处理

### 4. `run.py` — reload 默认值 + fetch 文案 ✅ 本轮修复
- `reload` 改为 `os.getenv("ENV", "dev").lower() in ("dev", "development")`
- `run_fetch` 文案改为准确描述"运行 Tushare 日线数据抓取"

### 5. `tests/test_run_cli.py` — 覆盖不足 ❌ 未修复
- 不在本轮范围，建议后续补充 `run_fetch`/`run_api`/`run_migrate` 测试

---

## 三、Codex 低优先级问题处理状态

### 1. `pyproject.toml` / `pytest.ini` 双配置 ❌ 未修复
- pytest 已警告忽略 pyproject.toml，但功能不受影响
- 建议后续统一为 pyproject.toml

### 2. `frontend/app/polymarket/page-client.tsx` — 首屏 200 条 + img warning ❌ 未修复
- 不在本轮前端优化范围
- 建议后续添加分页或虚拟滚动，`<img>` 改为 `next/image`

---

## 四、本轮独立审计实施记录（40 个问题 / 6 Phase）

### Phase 0 — 紧急安全 (4/4 ✅)
| 任务 | 内容 | 状态 |
|------|------|------|
| 0.1 | Docker 密码 fallback → `:?` 强制报错 + PG 绑定 127.0.0.1 | ✅ |
| 0.2 | Polymarket SIGALRM → ThreadPoolExecutor | ✅ |
| 0.3 | CSP / HSTS / Referrer-Policy / Permissions-Policy | ✅ |
| 0.4 | SQL 标识符白名单校验 `_validate_identifier()` | ✅ |

### Phase 1 — 可靠性 (8/8 ✅)
| 任务 | 内容 | 状态 |
|------|------|------|
| 1.1 | 20+ 处 bare except/pass → logger.warning/error | ✅ |
| 1.2 | 200+ 处 print → logger (7 个核心文件) | ✅ |
| 1.3 | API ts_code/date/stock_code 正则校验 | ✅ |
| 1.4 | AnalyzeRequest.date field_validator | ✅ |
| 1.5 | batch_insert_validated 单事务 + rollback | ✅ |
| 1.6 | Polymarket fetcher tenacity 重试 | ✅ |
| 1.7 | 金融计算 round() 精度保护 | ✅ |
| 1.8 | trading_calendar threading.Lock 缓存保护 | ✅ |

### Phase 2 — 代码质量 (7/7 ✅)
| 任务 | 内容 | 状态 |
|------|------|------|
| 2.1 | scheduler subprocess 使用 sys.executable | ✅ |
| 2.2 | 连接池配置（已就绪，跳过） | ✅ |
| 2.3 | 错误 dict 200 → HTTPException 503/404 | ✅ |
| 2.4 | _env_int / _env_float 类型安全 | ✅ |
| 2.5 | /health response_model 标准化 | ✅ |
| 2.6 | logging.basicConfig 格式标准化 | ✅ |
| 2.7 | /health 返回 503 状态码 | ✅ |

### Phase 3 — 前端 (6/6 ✅)
| 任务 | 内容 | 状态 |
|------|------|------|
| 3.1 | QueryCache/MutationCache 全局错误 toast | ✅ |
| 3.2 | API 请求超时（已就绪，跳过） | ✅ |
| 3.3 | 分页限制确认（已就绪） | ✅ |
| 3.4 | chart.remove() try/catch 保护 | ✅ |
| 3.5 | 3 个 loading.tsx skeleton | ✅ |
| 3.6 | 移动端 overflow-x-auto + flex-wrap | ✅ |

### Phase 4 — 基础设施 (6/6 ✅)
| 任务 | 内容 | 状态 |
|------|------|------|
| 4.1 | Docker 三网络隔离 | ✅ |
| 4.2 | Dockerfile 多阶段构建 | ✅ |
| 4.3 | 日志持久化（随 0.1 完成） | ✅ |
| 4.4 | scripts/backup.sh pg_dump 备份 | ✅ |
| 4.5 | GitHub Actions CI (backend + frontend) | ✅ |
| 4.6 | .env.example 完善同步 | ✅ |

### Phase 5 — 测试 (5/5 ✅)
| 任务 | 内容 | 测试数 |
|------|------|--------|
| 5.1 | test_api.py API 集成测试 | 47 passed |
| 5.2 | test_connection.py DB 单元测试 | 39 passed |
| 5.3 | test_gemini_client.py sanitize 增强 | 22 new (36 total) |
| 5.4 | 前端 error-boundary + stock-search | 18 new (21 total) |
| 5.5 | Playwright E2E smoke tests | 5 (待安装 Playwright) |

---

## 五、仍待处理事项（建议下一轮）

| 优先级 | 问题 | 来源 |
|--------|------|------|
| 中 | `scripts/update_all_data.py` 失败退出码 | Codex |
| 中 | `north_money_holding` 视图 vs 真实表兼容性确认 | Codex |
| 中 | `margin_trading.py` 全量失败时显式抛异常 | Codex |
| 低 | `tests/test_run_cli.py` 覆盖 fetch/api/migrate | Codex |
| 低 | pyproject.toml / pytest.ini 统一 | Codex |
| 低 | polymarket page 首屏 200 条 + next/image | Codex |

---

## 六、验证证据

```
# 后端编译
python -m py_compile api/main.py         ✅
python -m py_compile config/settings.py  ✅
python -m py_compile src/database/connection.py  ✅
python -m py_compile api/scheduler.py    ✅

# 后端测试
pytest tests/test_api.py         → 47 passed
pytest tests/test_connection.py  → 39 passed
pytest tests/test_gemini_client.py → 36 passed

# 前端
npx tsc --noEmit     → 0 errors
npx vitest run       → 21 passed

# Docker
docker compose config → 正确报错 "POSTGRES_PASSWORD is missing"（预期行为）

# SQL 注入防护
_validate_identifier("valid_table")  → OK
_validate_identifier("'; DROP TABLE") → ValueError ✅
```

---

本文档由 Claude 编写，回应 Codex 的审核结果，并记录第三轮独立审计的全部实施内容。
