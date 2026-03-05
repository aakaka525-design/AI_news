# AI_news - A股智能数据平台

> 金融数据采集 + 量化策略 + LLM 分析 + 可视化前端

[![Python](https://img.shields.io/badge/Python-3.10+-blue.svg)](https://python.org)
[![Next.js](https://img.shields.io/badge/Next.js-14-black.svg)](https://nextjs.org)
[![License](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)

---

## 快速开始

```bash
# 1. 克隆项目
git clone https://github.com/your/AI_news.git
cd AI_news

# 2. 安装依赖（含 AI + Polymarket + 翻译组件）
pip install -e .

# 3. 配置环境变量
cp .env.example .env
# 编辑 .env 填写 TUSHARE_TOKEN

# 4. 初始化数据库
python run.py migrate

# 5. 抓取数据
python run.py fetch

# 6. 启动后端
python run.py api

# 7. 启动前端 (可选)
cd frontend && npm install && npm run dev
```

---

## 项目结构

```
AI_news/
├── run.py                      # 统一 CLI 入口
├── pyproject.toml              # 项目配置
├── requirements.txt            # Python 依赖
├── docker-compose.yml          # Docker 编排
├── .dockerignore               # 构建上下文过滤
├── rss_fetcher.py              # RSS 订阅抓取
│
├── src/                        # 核心源代码
│   ├── database/               # 数据库层
│   │   ├── connection.py       #   连接管理
│   │   ├── engine.py           #   引擎配置
│   │   ├── models.py           #   SQLAlchemy 模型
│   │   ├── upsert.py           #   幂等写入
│   │   ├── migrations/         #   迁移脚本
│   │   └── repositories/       #   数据仓库 (news, report, polymarket)
│   │
│   ├── data_ingestion/         # 数据采集层
│   │   ├── tushare/            #   Tinyshare 数据源
│   │   │   ├── client.py       #     API 客户端 (限流+重试)
│   │   │   ├── daily.py        #     日线行情
│   │   │   ├── financials.py   #     财务数据
│   │   │   ├── moneyflow.py    #     资金流向
│   │   │   ├── dragon_tiger.py #     龙虎榜
│   │   │   └── valuation.py    #     估值指标
│   │   ├── akshare/            #   AkShare 数据源 (板块/融资融券/北向)
│   │   ├── polymarket/         #   Polymarket 预测市场
│   │   │   ├── client.py       #     SDK 客户端 (分页)
│   │   │   ├── fetcher.py      #     数据采集编排
│   │   │   ├── detector.py     #     波动率检测
│   │   │   ├── translator.py   #     中文翻译
│   │   │   └── models.py       #     数据模型
│   │   └── compat.py           #   新旧表兼容层
│   │
│   ├── analysis/               # 分析层
│   │   ├── indicators.py       #   技术指标
│   │   ├── anomaly.py          #   异常检测
│   │   ├── sentiment.py        #   情绪分析
│   │   ├── trend.py            #   趋势预测
│   │   ├── cleaner.py          #   数据清洗
│   │   ├── backtest_engine.py  #   回测引擎
│   │   ├── backtest_metrics.py #   回测指标
│   │   ├── sector_rotation.py  #   板块轮动
│   │   └── strategies.py       #   策略模型
│   │
│   ├── strategies/             # 策略层
│   │   ├── limit_up_scanner.py #   涨停扫描
│   │   ├── rps_screener.py     #   RPS 筛选
│   │   └── full_analysis.py    #   综合分析
│   │
│   ├── ai_engine/              # AI 引擎
│   │   ├── llm_analyzer.py     #   LLM 分析器
│   │   ├── gemini_client.py    #   Gemini API 客户端
│   │   ├── report_parser.py    #   研报解析
│   │   └── sentiment.py        #   AI 情绪分析
│   │
│   └── utils/                  # 工具层
│       ├── rate_limiter.py     #   令牌桶限流
│       └── retry.py            #   重试装饰器
│
├── api/                        # FastAPI 后端
│   ├── main.py                 #   API 入口 (CORS)
│   ├── middleware.py           #   中间件
│   ├── scheduler.py            #   定时任务调度
│   ├── routers/                #   路由
│   ├── schemas/                #   请求/响应模型
│   └── templates/              #   管理面板模板
│
├── frontend/                   # Next.js 14 前端
│   ├── app/                    #   App Router 页面
│   │   ├── page.tsx            #     仪表盘 (健康/情绪/热点/异常/研报)
│   │   ├── news/               #     新闻中心 (推送/RSS)
│   │   ├── market/             #     行情中心 (个股详情/K线图/估值)
│   │   ├── polymarket/         #     预测市场
│   │   ├── strategy/anomaly/   #     异常信号
│   │   └── settings/           #     系统设置
│   ├── components/             #   React 组件 (shadcn/ui)
│   ├── lib/                    #   API 客户端 / hooks / 类型定义
│   └── Dockerfile              #   多阶段构建
│
├── fetchers/                   # 数据抓取模块
│   ├── main_money_flow.py      #   主力资金
│   ├── integrity_checker.py    #   数据完整性检查
│   ├── trading_calendar.py     #   交易日历
│   ├── valuation.py            #   估值数据
│   └── ...                     #   龙虎榜/财务/融资融券/北向
│
├── scripts/                    # 批量脚本 (14 个)
│   ├── fetch_history.py        #   历史数据回填
│   ├── fetch_all_stocks.py     #   全量股票抓取
│   ├── full_stock_analysis.py  #   综合分析
│   ├── rps_screener.py         #   RPS 筛选
│   ├── migrate_sqlite_to_pg.py #   SQLite → PostgreSQL 迁移
│   └── ...
│
├── tests/                      # 测试 (340+ passing)
├── config/                     # 配置 (settings.py)
├── data/                       # 数据存储 (gitignore)
├── alembic/                    # 数据库迁移
├── docker/                     # Docker 辅助文件
│   └── entrypoint.sh           #   容器启动脚本 (自动迁移)
└── docs/plans/                 # 实施计划文档
```

---

## 数据库架构

### 核心表

| 表名 | 用途 | 特殊字段 |
|:---|:---|:---|
| `stock_basic` | 股票基础信息 | market, industry |
| `stock_daily` | 日线行情 | **qfq_close**, **hfq_close** (预计算复权) |
| `stock_index` | 指数行情 | up_count, down_count |
| `block_daily` | 板块行情 | lead_stock |
| `news_flash` | 新闻快讯 | **embedding**, **sentiment_score** |
| `research_report` | 研究报告 | **embedding**, target_price |
| `money_flow` | 资金流向 | net_mf_amount, north_net |
| `dragon_tiger` | 龙虎榜 | inst_buy, inst_sell |
| `polymarket_markets` | 预测市场合约 | question, outcome_prices |
| `polymarket_snapshots` | 市场价格快照 | price, volume |

### 设计亮点

1. **预计算复权价** — `qfq_close`/`hfq_close` 避免运行时计算
2. **向量字段** — `embedding` 支持 LLM 语义检索
3. **情绪评分** — `sentiment_score` 直接落库
4. **幂等写入** — `upsert_data()` 防止重复插入

---

## 命令行接口

```bash
python run.py api          # 启动 FastAPI 服务 (端口 8000)
python run.py fetch        # 运行数据抓取
python run.py migrate      # 运行数据库迁移
python run.py analyze      # 运行 RSS 新闻 AI 情感分析
python run.py --help       # 帮助
```

---

## 环境变量

创建 `.env` 文件 (参考 `.env.example`)：

```env
# 数据源
TUSHARE_TOKEN=your_tinyshare_token

# 数据库 (默认 SQLite)
DATABASE_URL=sqlite:///data/stocks.db
NEWS_DATABASE_URL=sqlite:///data/news.db

# API 鉴权（生产建议开启）
DASHBOARD_API_KEY=
API_KEY_REQUIRED=false
WEBHOOK_SECRET=

# AI 分析 (可选)
AI_ANALYSIS_ENABLED=false
GEMINI_API_KEY=your_gemini_api_key
GEMINI_MODEL=gemini-3.1-flash-lite-preview

# 前端（可选）
NEXT_PUBLIC_API_URL=/api/proxy
# BFF 代理到后端服务（前端容器内）
DASHBOARD_INTERNAL_URL=http://dashboard:8000

# Telegram 推送 (可选)
TELEGRAM_BOT_TOKEN=
TELEGRAM_CHAT_ID=

# Polymarket 预测市场 (可选)
POLYMARKET_ENABLED=true
POLYMARKET_FETCH_INTERVAL=5
POLYMARKET_VOLATILITY_THRESHOLD=0.10

# TrendRadar 爬虫 (Docker 模式)
ENABLE_CRAWLER=true
CRON_SCHEDULE=*/30 * * * *

# Docker 数据库密码（请改成强密码）
POSTGRES_PASSWORD=change_me_ainews_db_password
NOCODB_META_PASSWORD=change_me_nocodb_meta_password
```

---

## Docker 部署

```bash
# 构建镜像
docker compose build

# 启动所有服务 (容器启动时自动运行 alembic 数据库迁移)
docker compose up -d

# 查看日志
docker compose logs -f dashboard

# 停止服务
docker compose down
```

### 服务列表

| 服务 | 端口 | 说明 |
|:---|:---|:---|
| dashboard | 8000 | FastAPI 后端 |
| frontend | 3000 | Next.js 前端 |
| rsshub | 1200 | RSS 聚合器 |
| trendradar | — | AI 新闻爬虫 |
| postgres | 5432 | PostgreSQL 数据库 |
| nocodb | 8180 | 数据库可视化 |

---

## 数据更新频率

| 数据类型 | 更新时间 | 说明 |
|:---|:---|:---|
| 日线行情 | 每日 15:30 | 收盘后自动抓取 |
| 财务数据 | 季度 | 财报发布后 |
| 龙虎榜 | 每日 18:00 | 交易所公布后 |
| 资金流向 | 每日 16:00 | 盘后统计 |
| 新闻快讯 | 实时 | RSS 订阅 + Webhook |
| Polymarket | 每 5 分钟 | 预测市场数据同步 |

---

## 测试

```bash
# 运行所有测试
pytest

# 运行特定测试
pytest tests/test_core.py -v

# 覆盖率报告
pytest --cov=src --cov-report=html
```

---

## 更新日志

### v3.1.0 (2026-03-04)
- 新增 Polymarket 预测市场集成（数据采集 + 波动率检测 + 前端页面）
- AI 引擎迁移至 Google Gemini（替代 OpenAI/DeepSeek）
- 前端新增行情中心（个股详情 + K线图 + 估值图表）
- 新增股票搜索功能
- Docker 优化（entrypoint 自动迁移 + .dockerignore）

### v3.0.0 (2026-03-03)
- 新增 Next.js 14 前端 (shadcn/ui + ECharts 可视化)
- 迁移数据源至 Tinyshare
- 新增回测引擎 + 板块轮动策略
- 新增研报解析模块
- 清理 legacy_archive、23 个过时脚本、345MB 损坏数据

### v2.0.0 (2026-01-22)
- 项目架构重构为 Clean Architecture
- 迁移至 Tushare 数据源
- 新增 AI-Ready 数据库模型 (向量字段)
- 新增统一入口 `run.py`

### v1.0.0 (2026-01-18)
- 初始版本
- AkShare 数据源
- FastAPI Dashboard

---

## License

MIT License - 详见 [LICENSE](LICENSE)
