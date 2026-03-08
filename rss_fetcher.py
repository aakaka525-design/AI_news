"""
RSS 订阅模块 - 从 RSS 源获取新闻数据

功能：
1. 订阅多个 RSS 源
2. 解析文章标题、摘要、链接
3. 存入 Dashboard 数据库
4. 支持定时拉取
"""

import logging
import os
import json
import sqlite3
import asyncio
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional
from dataclasses import dataclass

import feedparser
import httpx

logger = logging.getLogger(__name__)

# ============================================================
# 配置
# ============================================================

# 默认 RSS 源列表
DEFAULT_FEEDS = [
    # === 科技 ===
    {"name": "36氪", "url": "https://36kr.com/feed", "category": "科技"},
    {"name": "少数派", "url": "https://sspai.com/feed", "category": "科技"},
    {"name": "Hacker News", "url": "https://hnrss.org/frontpage", "category": "科技"},
    {"name": "极客公园", "url": "https://www.geekpark.net/rss", "category": "科技"},
    {"name": "The Verge", "url": "https://www.theverge.com/rss/index.xml", "category": "科技"},
    {"name": "TechCrunch", "url": "https://techcrunch.com/feed/", "category": "科技"},
    {"name": "Wired", "url": "https://www.wired.com/feed/rss", "category": "科技"},

    # === AI / 机器学习 ===
    {"name": "AI News (英)", "url": "https://buttondown.email/ainews/rss", "category": "AI"},
    {"name": "MIT AI News", "url": "https://news.mit.edu/topic/mitartificial-intelligence2-rss.xml", "category": "AI"},
    {"name": "OpenAI Blog", "url": "https://openai.com/blog/rss/", "category": "AI"},
    {"name": "Hugging Face Blog", "url": "https://huggingface.co/blog/feed.xml", "category": "AI"},
    {"name": "机器之心", "url": "https://www.jiqizhixin.com/rss", "category": "AI"},

    # === 财经 ===
    {"name": "华尔街见闻", "url": "https://wallstreetcn.com/rss/news/global", "category": "财经"},
    {"name": "Bloomberg", "url": "https://feeds.bloomberg.com/markets/news.rss", "category": "财经"},
    {"name": "Reuters", "url": "https://www.reutersagency.com/feed/", "category": "财经"},

    # === 国际新闻 ===
    {"name": "BBC中文", "url": "https://feeds.bbci.co.uk/zhongwen/simp/rss.xml", "category": "国际"},
    {"name": "纽约时报中文", "url": "https://cn.nytimes.com/rss/", "category": "国际"},
    {"name": "端传媒", "url": "https://theinitium.com/newsfeed/", "category": "国际"},

    # === 产品/创业 ===
    {"name": "Product Hunt", "url": "https://www.producthunt.com/feed", "category": "产品"},
    {"name": "Indie Hackers", "url": "https://www.indiehackers.com/feed.xml", "category": "创业"},

    # === 设计 ===
    {"name": "Dribbble", "url": "https://dribbble.com/shots/popular.rss", "category": "设计"},
]

# RSSHub 本地实例订阅源
# 启动方式：docker compose up rsshub -d
# 本地访问：http://localhost:1200
RSSHUB_BASE = os.environ.get("RSSHUB_URL", "http://localhost:1200")
RSSHUB_FEEDS = [
    # === 政策 ===
    {"name": "发改委新闻", "url": f"{RSSHUB_BASE}/gov/ndrc/xwdt", "category": "政策"},
    {"name": "工信部政策解读", "url": f"{RSSHUB_BASE}/gov/miit/zcjd", "category": "政策"},
    {"name": "证监会新闻", "url": f"{RSSHUB_BASE}/gov/csrc/news", "category": "政策"},
    {"name": "商务部新闻", "url": f"{RSSHUB_BASE}/gov/mofcom/article/xwfb", "category": "政策"},

    # === 财经 ===
    {"name": "东方财富研报", "url": f"{RSSHUB_BASE}/eastmoney/report/strategyreport", "category": "财经"},
    {"name": "雪球热帖", "url": f"{RSSHUB_BASE}/xueqiu/today", "category": "财经"},
    {"name": "华尔街见闻", "url": f"{RSSHUB_BASE}/wallstreetcn/news/global", "category": "财经"},

    # === 科技 ===
    {"name": "虎嗅", "url": f"{RSSHUB_BASE}/huxiu/article", "category": "科技"},
    {"name": "36氪快讯", "url": f"{RSSHUB_BASE}/36kr/newsflashes", "category": "科技"},
    {"name": "掘金热门", "url": f"{RSSHUB_BASE}/juejin/trending/all/weekly", "category": "科技"},
]


# 数据库路径
DB_PATH = Path(__file__).parent / "data" / "news.db"


# ============================================================
# 数据结构
# ============================================================

@dataclass
class RSSItem:
    """RSS 条目"""
    title: str
    link: str
    summary: str
    published: Optional[str]
    source: str
    category: str


# ============================================================
# RSS 抓取
# ============================================================

async def fetch_feed(feed_url: str, timeout: int = 10) -> Optional[str]:
    """异步获取 RSS 内容"""
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(feed_url, timeout=timeout, follow_redirects=True)
            resp.raise_for_status()
            return resp.text
    except Exception as e:
        logger.warning("获取失败 %s: %s", feed_url, e)
        return None


def parse_feed(content: str, source_name: str, category: str) -> list[RSSItem]:
    """解析 RSS 内容"""
    items = []
    feed = feedparser.parse(content)

    for entry in feed.entries[:20]:  # 限制每个源20条
        items.append(RSSItem(
            title=entry.get("title", ""),
            link=entry.get("link", ""),
            summary=entry.get("summary", "")[:500],  # 截断摘要
            published=entry.get("published", None),
            source=source_name,
            category=category
        ))

    return items


async def fetch_all_feeds(feeds: list[dict] = None, include_rsshub: bool = False) -> list[RSSItem]:
    """并发抓取所有 RSS 源

    Args:
        feeds: 自定义源列表，默认使用 DEFAULT_FEEDS
        include_rsshub: 是否包含本地 RSSHub 源
    """
    if feeds is None:
        feeds = DEFAULT_FEEDS.copy()

    if include_rsshub:
        feeds = feeds + RSSHUB_FEEDS
        logger.info("启用 RSSHub 源 (%d 个)", len(RSSHUB_FEEDS))

    all_items = []

    tasks = []
    for feed in feeds:
        tasks.append(fetch_feed(feed["url"]))

    results = await asyncio.gather(*tasks, return_exceptions=True)

    for feed, content in zip(feeds, results):
        if isinstance(content, str) and content:
            items = parse_feed(content, feed["name"], feed["category"])
            all_items.extend(items)
            logger.info("%s: %d 条", feed['name'], len(items))
        else:
            logger.warning("%s: 抓取失败", feed['name'])

    return all_items


# ============================================================
# 相似度去重（Levenshtein 编辑距离）
# ============================================================

def levenshtein_distance(s1: str, s2: str) -> int:
    """计算 Levenshtein 编辑距离"""
    if len(s1) < len(s2):
        s1, s2 = s2, s1

    if len(s2) == 0:
        return len(s1)

    prev_row = range(len(s2) + 1)
    for i, c1 in enumerate(s1):
        curr_row = [i + 1]
        for j, c2 in enumerate(s2):
            insertions = prev_row[j + 1] + 1
            deletions = curr_row[j] + 1
            substitutions = prev_row[j] + (c1 != c2)
            curr_row.append(min(insertions, deletions, substitutions))
        prev_row = curr_row

    return prev_row[-1]


def levenshtein_similarity(s1: str, s2: str) -> float:
    """计算 Levenshtein 相似度（0-1）"""
    if not s1 or not s2:
        return 0.0

    distance = levenshtein_distance(s1, s2)
    max_len = max(len(s1), len(s2))
    return 1 - (distance / max_len) if max_len > 0 else 0.0


def get_recent_titles(hours: int = 24) -> list[str]:
    """获取时间窗口内的标题列表"""
    init_rss_table()
    cutoff = (datetime.now() - timedelta(hours=hours)).strftime("%Y-%m-%d %H:%M:%S")
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.execute(
            "SELECT title FROM rss_items WHERE fetched_at > ?",
            (cutoff,)
        )
        titles = [row[0] for row in cursor.fetchall()]
    return titles


def is_duplicate(title: str, existing_titles: list[str], threshold: float = 0.85) -> bool:
    """
    检查标题是否与现有标题相似

    使用 Levenshtein 相似度，阈值 0.85（更保守，减少误删）
    """
    for existing in existing_titles:
        if levenshtein_similarity(title, existing) >= threshold:
            return True
    return False


# ============================================================
# 数据库操作
# ============================================================

def init_rss_table():
    """初始化 RSS 表"""
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS rss_items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                link TEXT UNIQUE,
                summary TEXT,
                published TEXT,
                source TEXT,
                category TEXT,
                fetched_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_rss_fetched ON rss_items(fetched_at DESC)")
        conn.commit()


def save_rss_items(items: list[RSSItem], dedup_hours: int = 24, similarity_threshold: float = 0.6) -> tuple[int, int]:
    """
    保存 RSS 条目（支持 URL 去重 + 时间窗口内相似度去重）

    Args:
        items: RSS 条目列表
        dedup_hours: 相似度检查的时间窗口（小时）
        similarity_threshold: Jaccard 相似度阈值 (0-1)

    Returns:
        (saved, skipped): 保存数量和跳过数量
    """
    init_rss_table()

    # 获取时间窗口内的已有标题
    existing_titles = get_recent_titles(hours=dedup_hours)

    saved = 0
    skipped = 0

    with sqlite3.connect(DB_PATH) as conn:
        batch_count = 0
        for item in items:
            # 1. 相似度去重检查
            if is_duplicate(item.title, existing_titles, threshold=similarity_threshold):
                skipped += 1
                continue

            # 2. URL 去重 (数据库层面)
            try:
                cursor = conn.execute(
                    "INSERT OR IGNORE INTO rss_items (title, link, summary, published, source, category) VALUES (?, ?, ?, ?, ?, ?)",
                    (item.title, item.link, item.summary, item.published, item.source, item.category)
                )
                if cursor.rowcount > 0:
                    saved += 1
                    batch_count += 1
                    # 添加到已有标题列表，避免同批次重复
                    existing_titles.append(item.title)
            except Exception as e:
                logger.warning("保存失败: %s", e)

            # 每 100 条批量 commit
            if batch_count >= 100:
                conn.commit()
                batch_count = 0

        conn.commit()
    return saved, skipped


def get_recent_rss(limit: int = 50) -> list[dict]:
    """获取最近的 RSS 条目"""
    init_rss_table()
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.execute(
            "SELECT * FROM rss_items ORDER BY fetched_at DESC LIMIT ?",
            (limit,)
        )
        rows = cursor.fetchall()
    return [dict(r) for r in rows]


# ============================================================
# 主函数
# ============================================================

async def run_rss_fetch(feeds: list[dict] = None, save: bool = True, include_rsshub: bool = False):
    """运行 RSS 抓取"""
    logger.info("开始抓取 RSS...")

    items = await fetch_all_feeds(feeds, include_rsshub=include_rsshub)
    logger.info("共获取 %d 条数据", len(items))

    if save and items:
        saved, skipped = save_rss_items(items)
        logger.info("新增保存 %d 条", saved)
        if skipped > 0:
            logger.info("相似度过滤 %d 条", skipped)

    return items


def main():
    """命令行入口"""
    import argparse
    parser = argparse.ArgumentParser(description="RSS 订阅抓取")
    parser.add_argument("--list", action="store_true", help="列出默认订阅源")
    parser.add_argument("--no-save", action="store_true", help="不保存到数据库")
    parser.add_argument("--rsshub", action="store_true", help="包含 RSSHub 源")
    args = parser.parse_args()

    if args.list:
        print("📋 默认订阅源:")
        for f in DEFAULT_FEEDS:
            print(f"   [{f['category']}] {f['name']}: {f['url']}")
        if args.rsshub:
            print("\n📡 RSSHub 源:")
            for f in RSSHUB_FEEDS:
                print(f"   [{f['category']}] {f['name']}: {f['url']}")
        return

    asyncio.run(run_rss_fetch(save=not args.no_save, include_rsshub=args.rsshub))


if __name__ == "__main__":
    main()
