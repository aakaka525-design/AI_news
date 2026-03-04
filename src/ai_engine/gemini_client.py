"""
共享 Gemini 客户端工厂

提供单例 genai.Client 和默认模型配置。
"""

import os
from typing import Optional

from google import genai

_client: Optional[genai.Client] = None


def get_gemini_client() -> Optional[genai.Client]:
    """获取共享 Gemini 客户端（单例）"""
    global _client

    api_key = os.getenv("GEMINI_API_KEY", "")
    if not api_key:
        return None

    if _client is None:
        _client = genai.Client(api_key=api_key)

    return _client


def get_default_model() -> str:
    """获取默认 Gemini 模型名称"""
    return os.getenv("GEMINI_MODEL", "gemini-2.0-flash")
