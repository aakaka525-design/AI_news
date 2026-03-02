# AI_news 项目演进设计方案

> 日期：2026-03-02
> 状态：已批准
> 方案：渐进式演进（方案 A）

## 背景

AI_news 是一个 A股全维度数据系统，v2.0.0 已完成 Clean Architecture 重构。当前具备完整的数据采集管道（Tushare）、FastAPI 服务（30+ 端点）、AI/LLM 集成（DeepSeek/OpenAI）和基础分析模块。

主要缺口：测试覆盖率极低、部分模块为 stub、无 CI/CD、SQLite 扩展性有限、无前端可视化。

## 总体策略

四阶段渐进式演进，先稳后扩，每阶段独立可交付：

1. 生产化加固
2. 数据库迁移（SQLite → PostgreSQL）
3. 功能完善（拆分 3A/3B/3C）
4. 前端可视化（Next.js + shadcn/ui）

部署方式：本地 Docker Compose 一键部署。

---

## 阶段 1：生产化加固

### 1.1 测试体系 — 分层优先级

| 优先级 | 模块 | 理由 |
|--------|------|------|
| P0 | `src/database/connection.py` | 核心数据链路，upsert 正确性关乎全局 |
| P0 | `src/data_ingestion/tushare/client.py` | 数据入口，速率限制和错误处理 |
| P0 | `api/main.py` 关键端点 (webhook, analyze, news) | 面向用户的核心路径 |
| P1 | `src/analysis/` (cleaner, sentiment, anomaly) | 分析准确性 |
| P1 | `utils/rate_limiter.py`, `utils/retry.py` | 基础设施 |
| P2 | 其余端点、fetchers | 外围功能 |

工具链：`pytest` + `pytest-asyncio` + `pytest-cov` + `httpx.AsyncClient`

### 1.2 CI/CD

- GitHub Actions：PR 自动运行 `pytest` + `ruff check`；主分支推送构建 Docker 镜像
- pre-commit hooks：`ruff check` + `ruff format`

### 1.3 结构化日志

- 引入 `structlog`，统一 JSON 格式（request_id、时间戳、模块名）
- 关键路径日志覆盖（数据采集、API 请求、AI 分析）

### 1.4 错误处理

- 异常层次：`AppError → DataFetchError / AnalysisError / DatabaseError`
- API 统一异常处理中间件，标准化错误响应
- 消除泛型 `except Exception`

### 1.5 API 文档

- 启用 FastAPI Swagger UI + ReDoc
- 所有端点添加 Pydantic response model
- 添加 API 版本前缀 `/api/v1/`

### DoD（完成定义）

- [ ] P0 模块覆盖率 >= 80%，P1 >= 60%
- [ ] CI 通过：pytest 全绿 + ruff check 无 error
- [ ] 所有 API 端点有 Pydantic response model
- [ ] structlog 集成，关键路径有日志覆盖
- [ ] 异常层次定义完毕，泛型 except Exception 消除

---

## 阶段 2：数据库迁移（SQLite → PostgreSQL）

### 关键认知

当前项目大量使用 `sqlite3` + 原生 SQL（不在 ORM 层），迁移工作量远大于纯 ORM 项目。需先做 SQL 审计再评估。

### 迁移步骤

**Step 1：SQL 审计与分类**
- 全面扫描所有 `.py` 文件中的原生 SQL 语句
- 分类：可直接迁移（标准 SQL）/ 需改写（SQLite 特有语法）/ 需重构（绕过 ORM 的复杂查询）
- 输出：SQL 迁移清单 + 工作量评估

**Step 2：数据访问层统一**
- 散落的原生 SQL 收归 Repository 层
- 逐模块替换，每替换一个做回归测试
- 保留双后端支持（SQLite / PostgreSQL），通过 `DATABASE_URL` 切换

**Step 3：PostgreSQL 适配**
- 逐条改写不兼容 SQL
- Alembic 管理 schema 版本
- Docker Compose 添加 PostgreSQL 15

**Step 4：数据迁移 + 验证**

### 数据分区

- `public` schema：核心交易数据（daily、basic、moneyflow）
- `analytics` schema：分析结果（sentiment、anomaly、analysis）
- `content` schema：内容数据（news、research_reports）

### 切换闸门标准（全部通过才可切换）

| 检查项 | 标准 | 验证方式 |
|--------|------|---------|
| 行数对账 | 所有表行数一致（容差 0） | 自动化脚本比对 |
| 关键指标 | 随机抽 100 条，所有字段值一致 | 抽样校验脚本 |
| API 回归 | 所有 API 端点返回结果一致 | pytest 双数据库对比测试 |
| 性能基线 | 关键查询延迟 <= SQLite 基线 120% | benchmark 脚本 |
| 灰度运行 | 双写模式 >= 3 个交易日无异常 | 日志监控 |

### 回退方案

保留 SQLite 连接器作为备选，通过 `DATABASE_URL` 环境变量一键切换。

### DoD

- [ ] SQL 审计清单完成，所有原生 SQL 已分类
- [ ] Repository 层统一，无散落的原生 SQL
- [ ] 闸门 5 项全部通过
- [ ] PostgreSQL 成为主库，SQLite 降级为备份

---

## 阶段 3：功能完善

拆分为 3A / 3B / 3C，明确依赖关系。

### 阶段 3A：技术指标 + 趋势分析

依赖关系：先指标后趋势。

**技术指标 (`src/analysis/indicators.py`)：**
- 趋势类：MA(5/10/20/60/120/250)、EMA、MACD
- 动量类：RSI(6/12/24)、KDJ、威廉指标
- 波动类：布林带、ATR
- 成交量：OBV、量比
- pandas/numpy 向量化计算，批量入库

**趋势分析 (`src/analysis/trend.py`)：**
- 趋势识别：上升/下降/盘整，基于均线排列
- 支撑/阻力位计算
- 趋势强度评分（0-100）
- 多周期趋势共振（日线 + 周线）

**DoD：** 指标计算结果与同花顺/东方财富对比误差 < 0.1%

### 阶段 3B：研报解析（可与 3A 并行）

**`src/ai_engine/report_parser.py`：**
- PDF/HTML 研报内容提取
- LLM 辅助提取：目标价、评级、核心观点、风险提示
- 结构化存储到 research_reports 表
- 支持东方财富、同花顺等来源

**DoD：** 成功解析 >= 3 个来源研报，结构化字段完整率 >= 90%

### 阶段 3C：策略增强 + 回测（依赖 3A）

- RPS 行业相对强度
- 板块轮动检测
- 基础回测框架

**DoD：** 回测结果可复现，提供 Sharpe Ratio 等基础指标

---

## 阶段 4：前端可视化

### 技术栈

| 层 | 选型 | 理由 |
|----|------|------|
| 框架 | Next.js 14 (App Router) | SSR + API Routes |
| UI | shadcn/ui + Tailwind CSS | 美观、可定制 |
| K 线图 | TradingView Lightweight Charts | 专业轻量 |
| 通用图表 | ECharts (echarts-for-react) | 资金流、热力图 |
| 数据管理 | TanStack Query | 缓存、轮询 |
| 类型 | 全量 TypeScript | 类型安全 |

### 页面结构

```
frontend/
├── app/
│   ├── page.tsx                    # Dashboard 首页
│   ├── market/page.tsx             # 市场总览
│   ├── stock/[code]/page.tsx       # 个股详情
│   ├── strategy/
│   │   ├── limit-up/page.tsx       # 涨停分析
│   │   ├── rps/page.tsx            # RPS 筛选
│   │   └── anomaly/page.tsx        # 异常信号
│   ├── news/page.tsx               # 新闻舆情
│   └── settings/page.tsx           # 系统设置
```

### 核心页面

**Dashboard 首页：** 市场情绪卡片、异常信号列表、北向资金趋势、板块 Top10、AI 摘要

**个股详情：** TradingView K 线（支持 MA/MACD/RSI 叠加）、资金流向图、AI 报告、龙虎榜、异常信号时间线

**策略页面：** 涨停股 + 连板统计、RPS 筛选器、异常信号看板

### Docker 网络（修正方案）

```yaml
services:
  api:
    build: .
    ports:
      - "8000:8000"  # 暴露到宿主机
    networks:
      - app-net

  frontend:
    build: ./frontend
    ports:
      - "3000:3000"
    environment:
      - API_URL=http://api:8000              # SSR 用（容器间）
      - NEXT_PUBLIC_API_URL=http://localhost:8000  # 浏览器用（宿主机）
    depends_on:
      - api
    networks:
      - app-net

  postgres:
    image: postgres:15
    ports:
      - "5432:5432"
    volumes:
      - pgdata:/var/lib/postgresql/data
    networks:
      - app-net

networks:
  app-net:
    driver: bridge

volumes:
  pgdata:
```

双 URL 策略：
- `API_URL`（服务端）：Next.js SSR/API Routes 容器内调用 `http://api:8000`
- `NEXT_PUBLIC_API_URL`（客户端）：浏览器通过 `http://localhost:8000` 访问

### DoD

- [ ] Dashboard 首页加载 < 2s
- [ ] K 线图流畅渲染 1000+ 根 K 线
- [ ] 移动端响应式适配
- [ ] 所有页面有 loading/error/empty 状态处理
- [ ] Docker Compose 一键启动全套服务
