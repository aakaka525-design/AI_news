"""SearchService — 统一搜索抽象层。

第一版使用 LIKE 匹配，后续可替换为 FTS5 或 PostgreSQL tsvector。
"""

import logging
import re
from typing import Optional

from src.database.connection import get_connection

logger = logging.getLogger(__name__)

# 输入特征判断
_CODE_PATTERN = re.compile(r"^\d{6}$")
_TSCODE_PATTERN = re.compile(r"^\d{6}\.[A-Z]{2}$")


def _is_code_query(q: str) -> bool:
    return bool(_CODE_PATTERN.match(q) or _TSCODE_PATTERN.match(q))


def search_stocks(query: str, limit: int = 20) -> list[dict]:
    """搜索股票：代码精确匹配 or 名称前缀匹配。"""
    conn = get_connection()
    try:
        query = query.strip()
        if not query:
            return []

        if _is_code_query(query):
            # 代码精确匹配
            code = query.split(".")[0]  # 去掉 .SH/.SZ 后缀
            rows = conn.execute(
                "SELECT code, name, industry, market FROM stocks "
                "WHERE code = ? OR code LIKE ? LIMIT ?",
                (code, f"{code}%", limit),
            ).fetchall()
        else:
            # 名称前缀匹配
            rows = conn.execute(
                "SELECT code, name, industry, market FROM stocks "
                "WHERE name LIKE ? LIMIT ?",
                (f"{query}%", limit),
            ).fetchall()

        return [
            {"ts_code": r[0], "name": r[1], "industry": r[2], "market": r[3]}
            for r in rows
        ]
    except Exception as e:
        logger.error("search_stocks failed: %s", e)
        return []
    finally:
        conn.close()


def search_news(query: str, limit: int = 50) -> list[dict]:
    """搜索新闻：标题/摘要 LIKE 匹配。"""
    from sqlalchemy import text as sa_text
    from api.db import news_session

    try:
        query = query.strip()
        if not query:
            return []

        session = news_session()
        try:
            rows = session.execute(
                sa_text(
                    "SELECT id, title, received_at FROM news_items "
                    "WHERE title LIKE :q OR content LIKE :q "
                    "ORDER BY received_at DESC LIMIT :lim"
                ),
                {"q": f"%{query}%", "lim": limit},
            ).fetchall()

            return [
                {"id": r[0], "title": r[1], "received_at": str(r[2])}
                for r in rows
            ]
        finally:
            session.close()
    except Exception as e:
        logger.error("search_news failed: %s", e)
        return []


def search(query: str, search_type: str = "all", limit: int = 20) -> dict:
    """统一搜索入口。

    Args:
        query: 搜索关键词
        search_type: "stocks" | "news" | "all"
        limit: 每类最大结果数

    Returns:
        {"stocks": [...], "news": [...]}
    """
    result: dict = {"stocks": [], "news": []}

    if search_type in ("stocks", "all"):
        result["stocks"] = search_stocks(query, limit)

    if search_type in ("news", "all"):
        # 纯数字代码搜索时跳过新闻
        if not _is_code_query(query):
            result["news"] = search_news(query, limit)

    return result
