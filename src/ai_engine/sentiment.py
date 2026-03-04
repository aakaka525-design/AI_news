#!/usr/bin/env python3
"""
RSS 新闻情感分析模块

功能：
1. 批量分析 RSS 新闻的情感倾向
2. 生成 AI 摘要
3. 存储结果到 news.db
"""

import json
import os
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Optional
from google import genai
from google.genai.types import GenerateContentConfig

from src.ai_engine.gemini_client import get_gemini_client, get_default_model

# ============================================================
# 配置
# ============================================================

NEWS_DB_PATH = Path(__file__).resolve().parents[2] / "data" / "news.db"
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
# 数据库操作
# ============================================================

def get_news_connection() -> sqlite3.Connection:
    """获取新闻数据库连接"""
    NEWS_DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(NEWS_DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS rss_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            summary TEXT,
            source TEXT,
            category TEXT,
            published TEXT,
            fetched_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            sentiment_score REAL,
            ai_summary TEXT,
            analyzed_at TIMESTAMP
        )
        """
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_rss_items_fetched_at ON rss_items(fetched_at)")
    conn.commit()
    return conn


def get_unanalyzed_news(limit: int = BATCH_SIZE) -> list[dict]:
    """获取未分析的新闻"""
    conn = get_news_connection()
    cursor = conn.execute("""
        SELECT id, title, summary, source, category, published
        FROM rss_items
        WHERE sentiment_score IS NULL
        ORDER BY fetched_at DESC
        LIMIT ?
    """, (limit,))
    
    news = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return news


def save_analysis_results(results: list[dict]) -> int:
    """保存分析结果"""
    if not results:
        return 0
    
    conn = get_news_connection()
    count = 0
    
    for r in results:
        try:
            conn.execute("""
                UPDATE rss_items 
                SET sentiment_score = ?,
                    ai_summary = ?,
                    analyzed_at = ?
                WHERE id = ?
            """, (
                r.get("sentiment_score"),
                r.get("ai_summary"),
                datetime.now().isoformat(),
                r.get("id")
            ))
            count += 1
        except Exception as e:
            print(f"  ⚠️ 保存失败 ID={r.get('id')}: {e}")
    
    conn.commit()
    conn.close()
    return count


# ============================================================
# 情感分析器
# ============================================================

class SentimentAnalyzer:
    """新闻情感分析器"""
    
    def __init__(
        self,
        client: genai.Client,
        model: str = "gemini-2.0-flash"
    ):
        self.client = client
        self.model = model
    
    async def analyze_batch(self, news_items: list[dict]) -> list[dict]:
        """批量分析新闻情感"""
        if not news_items:
            return []
        
        # 构建用户消息
        user_content = self._build_prompt(news_items)
        
        try:
            response = await self.client.aio.models.generate_content(
                model=self.model,
                contents=f"{SENTIMENT_PROMPT}\n\n{user_content}",
                config=GenerateContentConfig(
                    temperature=0.3,
                    max_output_tokens=2000,
                ),
            )

            result_text = (response.text or "").strip()
            
            # 处理可能的 Markdown 包裹
            if result_text.startswith("```"):
                lines = result_text.split("\n")
                result_text = "\n".join(lines[1:-1])
            
            return json.loads(result_text)
            
        except json.JSONDecodeError as e:
            print(f"  ⚠️ JSON 解析失败: {e}")
            return []
        except Exception as e:
            print(f"  ⚠️ API 调用失败: {e}")
            return []
    
    def _build_prompt(self, items: list[dict]) -> str:
        """构建分析请求"""
        lines = ["请分析以下新闻的情感倾向：\n"]
        
        for item in items:
            lines.append(f"[ID={item['id']}] {item['title']}")
            if item.get('summary'):
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
        print("⚠️ GEMINI_API_KEY 未配置")
        return None

    model = get_default_model()

    return SentimentAnalyzer(client=client, model=model)


# ============================================================
# 主函数
# ============================================================

async def analyze_pending_news(limit: int = BATCH_SIZE) -> dict:
    """分析待处理的新闻"""
    print("📊 RSS 新闻情感分析")
    print(f"   数据库: {NEWS_DB_PATH}")
    
    # 获取未分析的新闻
    news = get_unanalyzed_news(limit)
    if not news:
        print("   ✅ 无待分析新闻")
        return {"analyzed": 0, "pending": 0}
    
    print(f"   待分析: {len(news)} 条")
    
    # 创建分析器
    analyzer = create_sentiment_analyzer()
    if not analyzer:
        return {"error": "分析器创建失败", "pending": len(news)}
    
    # 执行分析
    results = await analyzer.analyze_batch(news)
    
    # 保存结果
    saved = save_analysis_results(results)
    print(f"   ✅ 已分析: {saved} 条")
    
    return {"analyzed": saved, "pending": len(news) - saved}


def get_sentiment_stats() -> dict:
    """获取情感分析统计"""
    conn = get_news_connection()
    
    stats = {}
    
    # 已分析数量
    cursor = conn.execute("SELECT COUNT(*) FROM rss_items WHERE sentiment_score IS NOT NULL")
    stats["analyzed_count"] = cursor.fetchone()[0]
    
    # 未分析数量
    cursor = conn.execute("SELECT COUNT(*) FROM rss_items WHERE sentiment_score IS NULL")
    stats["pending_count"] = cursor.fetchone()[0]
    
    # 情感分布
    cursor = conn.execute("""
        SELECT 
            CASE 
                WHEN sentiment_score > 0.3 THEN 'positive'
                WHEN sentiment_score < -0.3 THEN 'negative'
                ELSE 'neutral'
            END as sentiment,
            COUNT(*) as count
        FROM rss_items 
        WHERE sentiment_score IS NOT NULL
        GROUP BY sentiment
    """)
    stats["distribution"] = {row[0]: row[1] for row in cursor.fetchall()}
    
    conn.close()
    return stats


if __name__ == "__main__":
    import asyncio
    asyncio.run(analyze_pending_news())
