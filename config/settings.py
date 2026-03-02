"""
AI News - 统一配置模块
"""

import os
from pathlib import Path
from dotenv import load_dotenv

# 加载 .env 文件
load_dotenv()

# 项目根目录
PROJECT_ROOT = Path(__file__).parent.parent

# 数据目录
DATA_DIR = PROJECT_ROOT / "data"
STOCKS_DB_PATH = DATA_DIR / "stocks.db"
LOGS_DIR = DATA_DIR / "logs"

# Database URL (supports SQLite and PostgreSQL)
DATABASE_URL = os.getenv(
    "DATABASE_URL",
    f"sqlite:///{STOCKS_DB_PATH}"
)
NEWS_DATABASE_URL = os.getenv(
    "NEWS_DATABASE_URL",
    f"sqlite:///{DATA_DIR / 'news.db'}"
)

# 确保目录存在
DATA_DIR.mkdir(exist_ok=True)
LOGS_DIR.mkdir(exist_ok=True)

# 代理配置（不提供硬编码默认密钥，避免误用和泄露）
PROXY_API_KEY = os.getenv("PROXY_API_KEY", "")
PROXY_API_PWD = os.getenv("PROXY_API_PWD", "")
PROXY_TTL = 100  # 代理有效期（秒）

# API 配置
SINA_API = "https://quotes.sina.cn/cn/api/openapi.php/CompanyFinanceService.getFinanceReport2022"
EM_API = "https://push2.eastmoney.com/api/qt/stock/get"

# 并发配置
DEFAULT_WORKERS = 50
MAX_WORKERS = 100

# AI 配置
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
OPENAI_BASE_URL = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")

# Telegram 配置
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")
