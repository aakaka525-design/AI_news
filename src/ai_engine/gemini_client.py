"""
共享 Gemini 客户端工厂

提供单例 genai.Client、默认模型配置、重试机制和统一 JSON 解析。
"""

import json
import logging
import re
import time
from typing import Optional

from google import genai
from google.genai.types import GenerateContentConfig

from config.settings import GEMINI_API_KEY, GEMINI_MODEL

logger = logging.getLogger(__name__)

_client: Optional[genai.Client] = None

# ============================================================
# Token 用量追踪
# ============================================================

_usage_stats = {
    "total_calls": 0,
    "total_prompt_tokens": 0,
    "total_completion_tokens": 0,
    "total_tokens": 0,
    "errors": 0,
}


def get_usage_stats() -> dict:
    """返回累计 token 用量统计"""
    return dict(_usage_stats)


def _track_usage(response) -> None:
    """记录单次调用的 token 用量"""
    _usage_stats["total_calls"] += 1
    meta = getattr(response, "usage_metadata", None)
    if meta:
        prompt = getattr(meta, "prompt_token_count", 0) or 0
        completion = getattr(meta, "candidates_token_count", 0) or 0
        _usage_stats["total_prompt_tokens"] += prompt
        _usage_stats["total_completion_tokens"] += completion
        _usage_stats["total_tokens"] += prompt + completion


# ============================================================
# 客户端工厂
# ============================================================


def get_gemini_client() -> Optional[genai.Client]:
    """获取共享 Gemini 客户端（单例）"""
    global _client

    if not GEMINI_API_KEY:
        return None

    if _client is None:
        _client = genai.Client(api_key=GEMINI_API_KEY)

    return _client


def get_default_model() -> str:
    """获取默认 Gemini 模型名称"""
    return GEMINI_MODEL


# ============================================================
# 统一 JSON 解析
# ============================================================


def parse_json_response(text: str):
    """
    从 Gemini 响应文本中解析 JSON。

    尝试顺序：
    1. 直接 json.loads 整体解析
    2. 去除 markdown 代码块 ```json ... ```
    3. 非贪婪正则提取最后一个 JSON 对象/数组

    全部失败则抛出 ValueError。
    """
    if not text or not text.strip():
        raise ValueError("空响应文本，无法解析 JSON")

    text = text.strip()

    # 1. 直接解析
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # 2. 去除 markdown 代码块
    md_match = re.search(r"```(?:json)?\s*\n?([\s\S]*?)\n?```", text)
    if md_match:
        try:
            return json.loads(md_match.group(1).strip())
        except json.JSONDecodeError:
            pass

    # 3. 贪婪正则提取 JSON 对象或数组（贪婪匹配保留嵌套结构）
    # 先尝试数组
    array_match = re.search(r"\[[\s\S]*\]", text)
    if array_match:
        try:
            return json.loads(array_match.group())
        except json.JSONDecodeError:
            pass

    # 再尝试对象
    obj_match = re.search(r"\{[\s\S]*\}", text)
    if obj_match:
        try:
            return json.loads(obj_match.group())
        except json.JSONDecodeError:
            pass

    # 4. 回退：从最后一个 { 或 [ 尝试解析（处理多 JSON 块场景）
    last_brace = text.rfind("{")
    if last_brace >= 0:
        try:
            return json.loads(text[last_brace:])
        except json.JSONDecodeError:
            pass

    last_bracket = text.rfind("[")
    if last_bracket >= 0:
        try:
            return json.loads(text[last_bracket:])
        except json.JSONDecodeError:
            pass

    raise ValueError(f"无法从响应中解析 JSON: {text[:200]}")


# ============================================================
# 带重试的 API 调用
# ============================================================


async def call_with_retry(
    prompt: str,
    *,
    model: Optional[str] = None,
    config: Optional[GenerateContentConfig] = None,
    max_retries: int = 3,
    backoff: float = 2.0,
) -> str:
    """
    带指数退避重试的 Gemini API 调用。

    Args:
        prompt: 提示文本
        model: 模型名称，默认使用 get_default_model()
        config: 生成配置
        max_retries: 最大重试次数
        backoff: 退避基数（秒）

    Returns:
        响应文本

    Raises:
        Exception: 所有重试均失败后抛出最后一个异常
    """
    from src.utils.rate_limiter import GEMINI_BUCKET

    client = get_gemini_client()
    if not client:
        raise RuntimeError("GEMINI_API_KEY 未配置")

    model = model or get_default_model()
    last_error = None

    for attempt in range(max_retries):
        try:
            await GEMINI_BUCKET.acquire_async()

            response = await client.aio.models.generate_content(
                model=model,
                contents=prompt,
                config=config,
            )

            _track_usage(response)
            return (response.text or "").strip()

        except Exception as e:
            last_error = e
            _usage_stats["errors"] += 1

            if attempt < max_retries - 1:
                wait = backoff * (2 ** attempt)
                logger.warning(
                    f"Gemini API 调用失败 (尝试 {attempt + 1}/{max_retries}): {e}, "
                    f"{wait:.1f}s 后重试"
                )
                import asyncio
                await asyncio.sleep(wait)
            else:
                logger.error(
                    f"Gemini API 调用失败 (已达最大重试 {max_retries}): {e}"
                )

    raise last_error


async def call_and_parse_json(
    prompt: str,
    *,
    model: Optional[str] = None,
    config: Optional[GenerateContentConfig] = None,
    max_retries: int = 3,
    backoff: float = 2.0,
):
    """
    调用 Gemini API 并解析 JSON 响应。

    结合 call_with_retry 和 parse_json_response 的便捷方法。
    """
    text = await call_with_retry(
        prompt, model=model, config=config,
        max_retries=max_retries, backoff=backoff,
    )
    return parse_json_response(text)
