#!/usr/bin/env python3
"""
RSS 新闻情感分析模块

功能：
1. 批量分析 RSS 新闻的情感倾向
2. 生成 AI 摘要
3. 通过 NewsRepository 存储结果（SQLAlchemy ORM）
"""

import logging
from typing import Optional

from google import genai
from google.genai.types import GenerateContentConfig

from src.ai_engine.gemini_client import (
    get_gemini_client,
    get_default_model,
    call_with_retry,
    parse_json_response,
)

logger = logging.getLogger(__name__)

# ============================================================
# 配置
# ============================================================

BATCH_SIZE = 10  # 每批分析数量

SENTIMENT_PROMPT = """你是一个金融新闻情感分析专家。分析以下新闻的情感倾向和市场影响。

对于每条新闻，输出 JSON 数组，每个元素包含：
- id: 新闻 ID
- sentiment_score: 情感分数 (-1.0 到 1.0，负面到正面)
- ai_summary: 一句话摘要（20字以内）
- market_impact: 市场影响标签（利好/利空/中性）
- related_sectors: 相关板块列表

严格输出 JSON 数组，不要包含任何其他文字。"""


# ============================================================
# 情感分析器
# ============================================================

class SentimentAnalyzer:
    """新闻情感分析器"""

    def __init__(
        self,
        client: genai.Client,
        model: str = "gemini-3.1-flash-lite-preview",
    ):
        self.client = client
        self.model = model

    async def analyze_batch(self, news_items: list[dict]) -> list[dict]:
        """批量分析新闻情感"""
        if not news_items:
            return []

        user_content = self._build_prompt(news_items)
        prompt = f"{SENTIMENT_PROMPT}\n\n{user_content}"

        try:
            result_text = await call_with_retry(
                prompt,
                model=self.model,
                config=GenerateContentConfig(
                    temperature=0.3,
                    max_output_tokens=2000,
                ),
            )
            result = parse_json_response(result_text)
            # 确保返回列表
            if isinstance(result, dict):
                return [result]
            return result

        except ValueError as e:
            logger.error(f"情感分析 JSON 解析失败: {e}")
            return []
        except Exception as e:
            logger.error(f"情感分析 API 调用失败: {e}")
            return []

    def _build_prompt(self, items: list[dict]) -> str:
        """构建分析请求"""
        lines = ["请分析以下新闻的情感倾向：\n"]

        for item in items:
            lines.append(f"[ID={item['id']}] {item['title']}")
            if item.get("summary"):
                lines.append(f"  摘要: {item['summary'][:100]}")
            lines.append("")

        return "\n".join(lines)


# ============================================================
# 工厂函数
# ============================================================

def create_sentiment_analyzer() -> Optional[SentimentAnalyzer]:
    """从环境变量创建分析器"""
    client = get_gemini_client()
    if not client:
        logger.warning("GEMINI_API_KEY 未配置，无法创建情感分析器")
        return None

    model = get_default_model()
    return SentimentAnalyzer(client=client, model=model)


# ============================================================
# 主函数（使用 NewsRepository）
# ============================================================

async def analyze_pending_news(repo, limit: int = BATCH_SIZE) -> dict:
    """
    分析待处理的新闻

    Args:
        repo: NewsRepository 实例
        limit: 每批分析数量

    Returns:
        dict: 分析结果统计
    """
    logger.info("RSS 新闻情感分析开始")

    # 通过 ORM 获取未分析的新闻
    news = repo.get_unanalyzed_rss(limit)
    if not news:
        logger.info("无待分析新闻")
        return {"analyzed": 0, "pending": 0}

    logger.info(f"待分析: {len(news)} 条")

    # 创建分析器
    analyzer = create_sentiment_analyzer()
    if not analyzer:
        return {"error": "分析器创建失败", "pending": len(news)}

    # 执行分析
    results = await analyzer.analyze_batch(news)

    # 通过 ORM 保存结果
    saved = 0
    for r in results:
        rss_id = r.get("id")
        score = r.get("sentiment_score")
        summary = r.get("ai_summary")
        if rss_id is not None and score is not None:
            if repo.update_rss_sentiment(rss_id, score, summary):
                saved += 1

    logger.info(f"情感分析完成: {saved}/{len(news)} 条")
    return {"analyzed": saved, "pending": len(news) - saved}


def get_sentiment_stats(repo) -> dict:
    """
    获取情感分析统计

    Args:
        repo: NewsRepository 实例

    Returns:
        dict: 统计数据
    """
    return repo.get_rss_sentiment_stats()
