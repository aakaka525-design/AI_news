"""
AI 热点分析模块 - Strategic Opportunity Advisor

功能：
1. 接入 DeepSeek/OpenAI API
2. 分析热点数据，输出机会报告（JSON）
3. 硬限制 Top 20，防止 Token 爆炸
"""

import json
import os
import re
from typing import Optional
from openai import AsyncOpenAI

# ============================================================
# 配置
# ============================================================

MAX_ITEMS = 20  # Token 安全上限

# Prompt Injection 防护 (P1 安全修复)
DANGEROUS_PATTERNS = [
    re.compile(r'忽略.*指令', re.IGNORECASE),
    re.compile(r'ignore.*instruction', re.IGNORECASE),
    re.compile(r'system\s*:', re.IGNORECASE),
    re.compile(r'assistant\s*:', re.IGNORECASE),
    re.compile(r'user\s*:', re.IGNORECASE),
    re.compile(r'\{\{.*\}\}'),
    re.compile(r'\[\[.*\]\]'),
    re.compile(r'<\|.*\|>'),
    re.compile(r'###\s*(system|instruction)', re.IGNORECASE),
]

def sanitize_for_prompt(text: str) -> str:
    """清理可能的 Prompt Injection 载荷"""
    if not text:
        return ""
    result = text
    for pattern in DANGEROUS_PATTERNS:
        result = pattern.sub('[FILTERED]', result)
    return result

SYSTEM_PROMPT = """# Role
Strategic Opportunity Advisor (热点机会参谋)

# Objective
你是一个辅助内容创作者的智能决策系统。基于传入的热点数据，深度分析流量逻辑，输出 3 个具体的"机会切入点"及完整执行指南。

# Analysis Framework
1. **归因分析**：这事为什么火？（情绪宣泄 / 认知反差 / 利益相关 / 猎奇窥探）
2. **受众洞察**：不同人群（吃瓜群众 / 行业从业者 / 搞钱党）想看什么？
3. **行动决策**：做什么内容的性价比最高？时间窗口有多久？

# Output Format (JSON ONLY)
你必须只输出一个合法的 JSON 对象，不要包含任何 Markdown 标记。结构如下：

{
  "analysis_summary": "一句话锐评今日热点的核心价值和整体流量逻辑",
  "trending_keywords": ["关键词1", "关键词2", "关键词3"],
  "opportunities": [
    {
      "id": 1,
      "type": "类型标签（情绪共鸣 / 深度科普 / 反转打脸 / 消费避坑 / 行业揭秘）",
      "score": 85,
      "title": "建议的标题或话题方向",
      "reasoning": "为什么推荐这个方向？击中了什么心理？",
      "target_audience": "最适合的目标受众（如：职场白领 / 宝妈 / Z世代）",
      "timeliness": {
        "level": "紧急|今日|本周|长期",
        "window": "建议的发布时间窗口",
        "reason": "为什么这个时间窗口最佳"
      },
      "action_plan": {
        "format": "建议形式（短视频/图文/直播/长文章）",
        "platform": "最适合平台（抖音/小红书/公众号/B站）",
        "key_message": "核心话术/金句",
        "hook": "开头3秒/首句的抓人话术",
        "do_list": ["具体执行步骤1", "具体执行步骤2", "具体执行步骤3"]
      },
      "material_suggestions": {
        "visual": "建议的视觉素材类型（如：对比图表 / 实拍画面 / 表情包）",
        "reference": "可参考的同类爆款内容描述"
      },
      "related_topics": ["可关联的其他热点1", "可关联的热点2"],
      "monetization": {
        "direct": "直接变现方式（如：带货 / 引流 / 知识付费）",
        "indirect": "间接价值（如：涨粉 / 建立人设 / 行业资源）"
      },
      "risk_warning": "操作风险提示（如：版权 / 敏感话题 / 时效过期）"
    },
    { "id": 2, "...同上结构..." },
    { "id": 3, "...同上结构..." }
  ]
}"""


# ============================================================
# AI 分析器
# ============================================================

class AIAnalyzer:
    """AI 热点分析器"""
    
    def __init__(
        self,
        api_key: str,
        base_url: str = "https://api.deepseek.com/v1",
        model: str = "deepseek-chat"
    ):
        self.client = AsyncOpenAI(
            api_key=api_key,
            base_url=base_url
        )
        self.model = model
    
    async def analyze_opportunities(self, news_items: list[dict]) -> dict:
        """
        分析热点机会
        
        Args:
            news_items: 新闻数据列表，每项包含 title, content 等字段
            
        Returns:
            dict: 分析结果 JSON
        """
        # 硬限制：只取前 20 条
        truncated = news_items[:MAX_ITEMS]
        
        # 构建用户消息
        user_content = self._build_user_prompt(truncated)
        
        try:
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": user_content}
                ],
                temperature=0.7,
                max_tokens=4000  # 扩展结构需要更多 token
            )
            
            result_text = response.choices[0].message.content.strip()
            
            # 尝试解析 JSON
            # 处理可能的 Markdown 代码块包裹
            if result_text.startswith("```"):
                lines = result_text.split("\n")
                result_text = "\n".join(lines[1:-1])
            
            return json.loads(result_text)
            
        except json.JSONDecodeError as e:
            return {
                "error": "JSON 解析失败",
                "raw_response": result_text,
                "detail": str(e)
            }
        except Exception as e:
            return {
                "error": "API 调用失败",
                "detail": str(e)
            }
    
    def _build_user_prompt(self, items: list[dict]) -> str:
        """构建用户消息（带消毒）"""
        lines = ["以下是今日 Top 热点数据：\n"]
        
        for i, item in enumerate(items, 1):
            # P1 安全修复：消毒外部输入
            title = sanitize_for_prompt(item.get("title", ""))
            content = sanitize_for_prompt(item.get("content", "")[:200])
            lines.append(f"{i}. {title}")
            if content:
                lines.append(f"   摘要: {content[:100]}...")
        
        lines.append("\n请分析以上热点，输出 3 个最具潜力的机会切入点。")
        return "\n".join(lines)


# ============================================================
# 工厂函数
# ============================================================

def create_analyzer_from_env() -> Optional[AIAnalyzer]:
    """从环境变量创建分析器"""
    enabled = os.getenv("AI_ANALYSIS_ENABLED", "false").lower() == "true"
    if not enabled:
        return None
    
    api_key = os.getenv("AI_API_KEY")
    if not api_key:
        print("⚠️ AI_API_KEY 未配置")
        return None
    
    base_url = os.getenv("AI_BASE_URL", "https://api.deepseek.com/v1")
    model = os.getenv("AI_MODEL", "deepseek-chat")
    
    return AIAnalyzer(api_key=api_key, base_url=base_url, model=model)
