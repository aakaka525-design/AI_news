# AI_news - A股全维度数据系统

> **AI-Ready** 金融数据平台：Tushare 数据源 + 量化策略 + LLM 分析

[![Python](https://img.shields.io/badge/Python-3.10+-blue.svg)](https://python.org)
[![License](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)

---

## 🚀 快速开始

```bash
# 1. 克隆项目
git clone https://github.com/your/AI_news.git
cd AI_news

# 2. 安装依赖
pip install -e .

# 3. 配置环境变量
cp .env.example .env
# 编辑 .env 填写 TUSHARE_TOKEN

# 4. 初始化数据库
python run.py migrate

# 5. 抓取数据
python run.py fetch

# 6. 启动服务
python run.py api
```

---

## 📁 项目结构

```
AI_news/
├── run.py                  # 统一入口
├── pyproject.toml          # 项目配置
├── .env                    # 环境变量 (gitignore)
│
├── src/                    # 核心源代码
│   ├── database/           # 数据库层
│   │   ├── connection.py   # 连接管理
│   │   ├── models.py       # SQLAlchemy 模型 (AI-Ready)
│   │   └── migrations/     # 迁移脚本
│   │
│   ├── data_ingestion/     # 数据采集层
│   │   ├── tushare/        # Tushare 数据源
│   │   │   ├── client.py   # API 客户端 (限流+重试)
│   │   │   ├── daily.py    # 日线抓取
│   │   │   ├── financials.py
│   │   │   ├── moneyflow.py
│   │   │   └── dragon_tiger.py
│   │   ├── akshare/        # AkShare 数据源 (遗留)
│   │   └── compat.py       # 兼容层
│   │
│   ├── analysis/           # 分析层
│   │   ├── indicators.py   # 技术指标
│   │   ├── anomaly.py      # 异常检测
│   │   ├── sentiment.py    # 情绪分析
│   │   └── trend.py        # 趋势预测
│   │
│   ├── strategies/         # 策略层
│   │   ├── limit_up_scanner.py  # 涨停扫描
│   │   ├── rps_screener.py      # RPS 筛选
│   │   └── full_analysis.py     # 综合分析
│   │
│   ├── ai_engine/          # AI 引擎
│   │   ├── llm_analyzer.py # LLM 分析器
│   │   └── report_parser.py# 研报解析
│   │
│   └── utils/              # 工具层
│       ├── rate_limiter.py # 令牌桶限流
│       └── retry.py        # 重试装饰器
│
├── api/                    # FastAPI 服务
│   ├── main.py             # API 入口
│   ├── routers/            # 路由
│   ├── schemas/            # 请求/响应模型
│   └── templates/          # 前端模板
│
├── scripts/                # 执行脚本
├── tests/                  # 测试
├── data/                   # SQLite 数据 (gitignore)
└── config/                 # 配置文件
```

---

## 🗄️ 数据库架构 (AI-Ready)

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

### 设计亮点

1. **预计算复权价** - `qfq_close`/`hfq_close` 避免运行时计算
2. **向量字段** - `embedding` 支持 LLM 语义检索
3. **情绪分析** - `sentiment_score` 直接落库
4. **幂等性** - `upsert_data()` 防止重复插入

---

## 🔧 命令行接口

```bash
# 启动 FastAPI 服务
python run.py api

# 运行数据抓取
python run.py fetch

# 运行数据库迁移
python run.py migrate

# 运行分析
python run.py analyze

# 帮助
python run.py --help
```

---

## 📊 使用示例

### 获取 Tushare 数据

```python
from src.data_ingestion.tushare import get_tushare_client

client = get_tushare_client()

# 获取日线数据
df = client.daily(ts_code='600519.SH', start_date='20260101')

# 获取财务指标
df = client.fina_indicator(ts_code='600519.SH')
```

### 兼容层查询

```python
from src.data_ingestion import (
    to_ts_code, from_ts_code,
    query_daily, query_stock_info
)

# 代码转换
ts_code = to_ts_code('600519')  # -> 600519.SH

# 统一查询 (自动选择新旧表)
data = query_daily('600519', limit=10)
info = query_stock_info('000001')
```

### 策略筛选

```python
from src.strategies.rps_screener import screen_by_rps

# RPS 强势股筛选
stocks = screen_by_rps(min_rps=90, min_market_cap=50)
```

---

## 🔐 环境变量

创建 `.env` 文件：

```env
# Tushare
TUSHARE_TOKEN=your_token_here
TUSHARE_API_URL=https://jiaoch.site

# Database
DATABASE_URL=sqlite:///data/stocks.db

# API
API_HOST=0.0.0.0
API_PORT=8000
```

---

## 🐳 Docker 部署

```bash
# 启动所有服务
docker-compose up -d

# 查看日志
docker-compose logs -f dashboard

# 停止服务
docker-compose down
```

---

## 📈 数据更新频率

| 数据类型 | 更新时间 | 说明 |
|:---|:---|:---|
| 日线行情 | 每日 15:30 | 收盘后自动抓取 |
| 财务数据 | 季度 | 财报发布后 |
| 龙虎榜 | 每日 18:00 | 交易所公布后 |
| 资金流向 | 每日 16:00 | 盘后统计 |
| 新闻快讯 | 实时 | RSS 订阅 |

---

## 🧪 测试

```bash
# 运行所有测试
pytest

# 运行特定测试
pytest tests/test_tushare.py -v

# 覆盖率报告
pytest --cov=src --cov-report=html
```

---

## 📝 更新日志

### v2.0.0 (2026-01-22)
- 🏗️ 项目架构重构为 Clean Architecture
- 🔥 全面迁移至 Tushare 数据源
- 🤖 新增 AI-Ready 数据库模型 (向量字段)
- 📦 新增统一入口 `run.py`
- 🧹 清理遗留代码至 `legacy_archive/`

### v1.0.0 (2026-01-18)
- 🚀 初始版本
- AkShare 数据源
- FastAPI Dashboard

---

## 📄 License

MIT License - 详见 [LICENSE](LICENSE)
