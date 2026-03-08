"""
AI News - 统一配置模块
"""

import os
from pathlib import Path
from dotenv import load_dotenv

# 加载 .env 文件
load_dotenv()


def _env_int(key: str, default: int) -> int:
    """Safely parse integer environment variable."""
    val = os.getenv(key, "")
    try:
        return int(val) if val else default
    except ValueError:
        return default


def _env_float(key: str, default: float) -> float:
    """Safely parse float environment variable."""
    val = os.getenv(key, "")
    try:
        return float(val) if val else default
    except ValueError:
        return default

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

# AI 配置
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-3.1-flash-lite-preview")

# Telegram 配置
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")

# 调度器时区
SCHEDULER_TIMEZONE = os.getenv("SCHEDULER_TIMEZONE", "Asia/Shanghai")

# Polymarket 配置
POLYMARKET_ENABLED = os.getenv("POLYMARKET_ENABLED", "true").lower() == "true"
POLYMARKET_FETCH_INTERVAL = _env_int("POLYMARKET_FETCH_INTERVAL", 5)
POLYMARKET_VOLATILITY_THRESHOLD = _env_float("POLYMARKET_VOLATILITY_THRESHOLD", 0.10)
