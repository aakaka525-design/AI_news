"""
研报 AI 观点提取模块

功能：
1. 分析研报标题和内容
2. 提取目标价、评级、核心逻辑
3. 生成 AI 摘要
"""

import json
import os
import re
from datetime import datetime
from typing import Optional

from src.database.connection import get_connection

try:
    from openai import AsyncOpenAI
except ImportError:
    AsyncOpenAI = None  # type: ignore[assignment,misc]


def log(msg: str):
    """格式化输出日志信息。"""
    ts = datetime.now().strftime("%H:%M:%S")
    print(f"[{ts}] {msg}", flush=True)


def _resolve_report_table(conn) -> str:
    """Resolve available report table and create a default table if missing."""
    if conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='research_reports'"
    ).fetchone():
        return "research_reports"
    if conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='research_report'"
    ).fetchone():
        return "research_report"

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS research_reports (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            stock_code TEXT,
            stock_name TEXT,
            report_title TEXT,
            rating TEXT,
            institution TEXT,
            publish_date TEXT,
            ai_summary TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_research_reports_code_date ON research_reports(stock_code, publish_date)"
    )
    conn.commit()
    return "research_reports"


# ============================================================
# 规则提取（不需要 LLM）
# ============================================================


def extract_target_price_from_title(title: str) -> Optional[float]:
    """
    从研报标题提取目标价

    Args:
        title: 研报标题

    Returns:
        目标价（元）或 None
    """
    if not title:
        return None

    # 常见目标价模式
    patterns = [
        r"目标价[：:]\s*(\d+\.?\d*)\s*元",
        r"目标[：:]\s*(\d+\.?\d*)\s*元",
        r"(\d+\.?\d*)\s*元目标",
        r"上调目标价至\s*(\d+\.?\d*)",
        r"目标价\s*(\d+\.?\d*)",
    ]

    for pattern in patterns:
        match = re.search(pattern, title)
        if match:
            try:
                return float(match.group(1))
            except ValueError:
                pass

    return None


def extract_rating_change(title: str) -> Optional[str]:
    """
    从研报标题提取评级变化

    Returns:
        评级变化描述或 None
    """
    if not title:
        return None

    # 评级变化模式
    patterns = [
        (r"首次覆盖", "首次覆盖"),
        (r"上调.*评级", "上调评级"),
        (r"下调.*评级", "下调评级"),
        (r"维持.*?买入", "维持买入"),
        (r"维持.*?增持", "维持增持"),
        (r"重申.*?买入", "重申买入"),
    ]

    for pattern, result in patterns:
        if re.search(pattern, title):
            return result

    return None


def extract_key_points(title: str) -> list[str]:
    """
    从研报标题提取关键点
    """
    if not title:
        return []

    points = []

    # 业绩相关
    if re.search(r"业绩.*?(超预期|符合|略低)", title):
        points.append("业绩点评")
    if re.search(r"(增长|高增|翻倍)", title):
        points.append("增长亮点")

    # 事件相关
    if re.search(r"(募资|定增|并购|收购)", title):
        points.append("资本运作")
    if re.search(r"(新品|新产品|新项目)", title):
        points.append("新品发布")
    if re.search(r"(订单|签约|中标)", title):
        points.append("订单获取")

    # 估值相关
    if re.search(r"(低估|估值底|价值)", title):
        points.append("估值分析")

    return points


def extract_risk_factors(title: str) -> list[str]:
    """
    从研报标题提取风险因素

    Args:
        title: 研报标题

    Returns:
        风险因素列表
    """
    if not title:
        return []

    factors = []

    if re.search(r"政策.*?风险|监管.*?风险", title):
        factors.append("政策风险")
    if re.search(r"竞争.*?(加剧|风险|压力)", title):
        factors.append("竞争风险")
    if re.search(r"(需求|下游).*?(不及|下滑|放缓|风险)", title):
        factors.append("需求风险")
    if re.search(r"(成本|原材料).*?(上升|上涨|压力|风险)", title):
        factors.append("成本风险")
    if re.search(r"(汇率|汇兑).*?(波动|风险)", title):
        factors.append("汇率风险")
    if re.search(r"(技术|研发).*?(风险|不确定)", title):
        factors.append("技术风险")

    return factors


def analyze_report_rule_based(report: dict) -> dict:
    """
    基于规则分析研报（不需要 LLM）

    Args:
        report: 研报数据字典

    Returns:
        分析结果
    """
    title = report.get("report_title", "")
    rating = report.get("rating", "")

    analysis = {
        "target_price": extract_target_price_from_title(title),
        "rating_change": extract_rating_change(title),
        "key_points": extract_key_points(title),
        "risk_factors": extract_risk_factors(title),
        "rating": rating,
        "sentiment": "positive"
        if rating in ["买入", "增持"]
        else ("neutral" if rating in ["持有", "中性"] else "negative"),
    }

    return analysis


# ============================================================
# LLM 分析（需要 API）
# ============================================================

REPORT_ANALYSIS_PROMPT = """你是一个专业的证券分析师助手。请分析以下研报标题，提取关键信息。

研报标题：{title}
机构：{institution}
评级：{rating}

请提取并返回 JSON 格式的分析结果：
{{
  "core_logic": "核心投资逻辑（一句话）",
  "catalysts": ["催化剂1", "催化剂2"],
  "risks": ["风险点1"],
  "sentiment_score": 0.8  // 情感分 0-1
}}

只返回 JSON，不要其他内容。"""


async def analyze_report_with_llm(report: dict) -> Optional[dict]:
    """
    使用 LLM 分析研报

    Requires:
        DEEPSEEK_API_KEY 或 OPENAI_API_KEY 环境变量
    """
    if AsyncOpenAI is None:
        log("   ⚠️ 需要安装 openai: pip install openai")
        return None

    api_key = os.getenv("DEEPSEEK_API_KEY") or os.getenv("OPENAI_API_KEY")
    if not api_key:
        log("   ⚠️ 未设置 API Key")
        return None

    base_url = "https://api.deepseek.com" if os.getenv("DEEPSEEK_API_KEY") else None

    client = AsyncOpenAI(api_key=api_key, base_url=base_url)

    prompt = REPORT_ANALYSIS_PROMPT.format(
        title=report.get("report_title", ""),
        institution=report.get("institution", ""),
        rating=report.get("rating", ""),
    )

    try:
        response = await client.chat.completions.create(
            model="deepseek-chat" if base_url else "gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3,
            max_tokens=500,
        )

        content = response.choices[0].message.content.strip()
        # 提取 JSON
        if content.startswith("{"):
            return json.loads(content)
        else:
            match = re.search(r"\{.*\}", content, re.DOTALL)
            if match:
                return json.loads(match.group())
    except Exception as e:
        log(f"   ⚠️ LLM 分析失败: {e}")

    return None


# ============================================================
# 批量分析
# ============================================================


def analyze_and_save_reports(
    repo,
    limit: int = 20,
) -> list[dict]:
    """
    Analyze reports using rule-based extraction and save results via repository.

    Args:
        repo: ReportRepository instance
        limit: Number of reports to analyze

    Returns:
        List of analysis results
    """
    reports = repo.get_reports(limit=limit)

    results = []
    for report in reports:
        analysis = analyze_report_rule_based(
            {
                "report_title": report.get("title", ""),
                "rating": report.get("rating", ""),
            }
        )

        # Map sentiment to numeric score
        sentiment_score = (
            0.8
            if analysis["sentiment"] == "positive"
            else 0.5
            if analysis["sentiment"] == "neutral"
            else 0.2
        )

        # Save structured fields
        repo.save_analysis(
            ts_code=report["ts_code"],
            publish_date=report["publish_date"],
            institution=report["institution"],
            analysis={
                "target_price": analysis["target_price"],
                "rating_change": analysis["rating_change"],
                "key_points": analysis["key_points"],
                "summary": None,
                "sentiment_score": sentiment_score,
            },
        )

        analysis["ts_code"] = report["ts_code"]
        analysis["stock_name"] = report["stock_name"]
        analysis["title"] = report["title"]
        analysis["institution"] = report["institution"]
        analysis["publish_date"] = report["publish_date"]
        results.append(analysis)

    return results


def analyze_recent_reports(limit: int = 20) -> list[dict]:
    """
    分析最新研报

    Args:
        limit: 分析数量

    Returns:
        分析结果列表
    """
    log(f"📊 分析最新 {limit} 条研报...")

    conn = get_connection()
    table = _resolve_report_table(conn)
    cursor = conn.execute(
        f"SELECT * FROM {table} ORDER BY publish_date DESC LIMIT ?",
        (limit,),
    )

    reports = [dict(row) for row in cursor.fetchall()]
    conn.close()

    results = []
    for report in reports:
        analysis = analyze_report_rule_based(report)
        analysis["stock_code"] = report.get("stock_code")
        analysis["stock_name"] = report.get("stock_name")
        analysis["report_title"] = report.get("report_title")
        analysis["institution"] = report.get("institution")
        analysis["publish_date"] = report.get("publish_date")
        results.append(analysis)

    log(f"   ✅ 分析完成 {len(results)} 条")
    return results


def save_report_analysis(stock_code: str, analysis: dict) -> bool:
    """保存分析结果到数据库"""
    conn = get_connection()
    try:
        # 更新 ai_summary 字段
        summary = json.dumps(analysis, ensure_ascii=False)
        table = _resolve_report_table(conn)
        conn.execute(
            f"""
            UPDATE {table}
            SET ai_summary = ?
            WHERE stock_code = ? AND publish_date = (
                SELECT MAX(publish_date) FROM {table} WHERE stock_code = ?
            )
            """,
            (summary, stock_code, stock_code),
        )
        conn.commit()
        return True
    except Exception as e:
        log(f"   ⚠️ 保存失败: {e}")
        return False
    finally:
        conn.close()


def get_reports_with_target_price() -> list[dict]:
    """获取包含目标价的研报"""
    log("📈 提取包含目标价的研报...")

    conn = get_connection()
    table = _resolve_report_table(conn)
    cursor = conn.execute(
        f"""
        SELECT stock_code, stock_name, report_title, rating, institution, publish_date
        FROM {table}
        WHERE report_title LIKE '%目标%'
        ORDER BY publish_date DESC
        LIMIT 50
        """
    )

    reports = [dict(row) for row in cursor.fetchall()]
    conn.close()

    results = []
    for report in reports:
        target_price = extract_target_price_from_title(report["report_title"])
        if target_price:
            report["target_price"] = target_price
            results.append(report)

    log(f"   ✅ 找到 {len(results)} 条含目标价研报")
    return results


# ============================================================
# 主函数
# ============================================================


def main():
    log("=" * 50)
    log("研报 AI 观点提取")
    log("=" * 50)

    # 1. 基于规则分析最新研报
    results = analyze_recent_reports(limit=10)

    log("\n📋 分析结果:")
    for r in results:
        log(f"   {r['stock_code']} {r['stock_name']}: {r['rating']} | {r['key_points']}")
        if r["target_price"]:
            log(f"      目标价: {r['target_price']} 元")

    # 2. 提取目标价
    target_reports = get_reports_with_target_price()

    log("\n🎯 目标价汇总:")
    for r in target_reports[:5]:
        log(f"   {r['stock_code']} {r['stock_name']}: {r['target_price']} 元 ({r['institution']})")

    log("\n✅ 完成!")


if __name__ == "__main__":
    main()
