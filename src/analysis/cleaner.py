"""
数据清洗模块 - 从原始热点数据中提取结构化事实

功能：
1. 去除噪音（格式代码、无关信息）
2. 提取核心事实（时间、地点、人物、事件）
3. 识别热点信号（关键词匹配、频次统计）
"""

import re
import json
from datetime import datetime
from typing import Optional
from dataclasses import dataclass, asdict
from collections import Counter


# ============================================================ 
# 数据结构
# ============================================================ 

@dataclass
class ExtractedFact:
    """提取的事实"""
    time: Optional[str] = None       # 时间
    location: Optional[str] = None   # 地点
    person: Optional[str] = None     # 人物
    event: str = ""                  # 核心事件
    source: Optional[str] = None     # 来源平台
    rank: Optional[int] = None       # 排名
    url: Optional[str] = None        # 链接
    
    def to_dict(self):
        return asdict(self)


@dataclass
class CleanedData:
    """清洗后的数据"""
    title: str                       # 标题
    summary: str                     # 摘要
    facts: list[ExtractedFact]       # 事实列表
    hotspots: list[str]              # 热点关键词
    keywords: list[str]              # 提取的关键词
    cleaned_at: str                  # 清洗时间
    
    def to_dict(self):
        return {
            "title": self.title,
            "summary": self.summary,
            "facts": [f.to_dict() for f in self.facts],
            "hotspots": self.hotspots,
            "keywords": self.keywords,
            "cleaned_at": self.cleaned_at
        }


# ============================================================ 
# 噪音清除 (预编译正则 P1 优化)
# ============================================================ 

# 常见噪音模式 - 预编译
NOISE_PATTERNS = [
    re.compile(r'\*\*'),                           # Markdown 加粗
    re.compile(r'#{1,6}\s*'),                      # Markdown 标题
    re.compile(r'\[([^\]]+)\]\([^\)]+\)'),         # Markdown 链接 -> 保留文本
    re.compile(r'!\ \[.*?\].*?\)'),                # Markdown 图片
    re.compile(r'<[^>]+>'),                        # HTML 标签
    re.compile(r'```[\s\S]*?```'),                 # 代码块
    re.compile(r'`[^`]+`'),                        # 行内代码
    re.compile(r'^\s*[-*+]\s+'),                   # 列表符号
    re.compile(r'^\s*\d+\.\s+'),                   # 有序列表
    re.compile(r'━+'),                             # 分隔线
    re.compile(r'─+'),                             # 分隔线
    re.compile(r'═+'),                             # 分隔线
    re.compile(r'\n{3,}'),                         # 多余空行
]

# 单独的链接匹配正则，用于 extract_url 或特殊处理
LINK_PATTERN = re.compile(r'\[([^\]]+)\]\([^\)]+\)')
WHITESPACE_PATTERN = re.compile(r'\s+')

def remove_noise(text: str) -> str:
    """去除文本中的噪音"""
    cleaned = text
    
    # 保留 Markdown 链接的文本部分
    cleaned = LINK_PATTERN.sub(r'\1', cleaned)
    
    # 链接在上面已做保留文本替换，这里跳过链接模式避免重复处理。
    for pattern in NOISE_PATTERNS:
        if pattern.pattern == r'\[([^\]]+)\]\([^\)]+\)':
            continue
        cleaned = pattern.sub('', cleaned)
    
    # 清理多余空白
    cleaned = WHITESPACE_PATTERN.sub(' ', cleaned)
    cleaned = cleaned.strip()
    
    return cleaned


# ============================================================ 
# 事实提取 (预编译正则 P1 优化)
# ============================================================ 

# 时间模式
TIME_PATTERNS = [
    re.compile(r'(\d{4}[-/]\d{1,2}[-/]\d{1,2})'),                    # 2026-01-16
    re.compile(r'(\d{1,2}月\d{1,2}日)'),                              # 1月16日
    re.compile(r'(今[日天]|昨[日天]|前[日天]|明[日天])'),              # 今日/昨天
    re.compile(r'(\d{1,2}:\d{2})'),                                   # 22:30
    re.compile(r'(上午|下午|晚间|凌晨)'),                              # 时段
]

# 地点模式
LOCATION_PATTERNS = [
    re.compile(r'(北京|上海|广州|深圳|杭州|成都|武汉|南京|西安|重庆)'),  # 城市
    re.compile(r'(中国|美国|日本|韩国|俄罗斯|英国|法国|德国)'),          # 国家
    re.compile(r'(亚洲|欧洲|北美|非洲)'),                               # 地区
    re.compile(r'([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)'),                  # 英文地名
]

# 人物模式（常见称谓后跟名字）
PERSON_PATTERNS = [
    re.compile(r'(马斯克|马云|雷军|刘强东|张一鸣|黄仁勋)'),              # 知名人物
    re.compile(r'([A-Z][a-z]+\s+[A-Z][a-z]+)'),                        # 英文名
    re.compile(r'(总[统裁理书记]|主席|CEO|创始人)\s*([^\s,，。]+)'),    # 职位+名字
]

# 来源平台模式
PLATFORM_PATTERNS = [
    re.compile(r'(微博|知乎|抖音|B站|百度|头条|贴吧|凤凰|澎湃|财联社|华尔街)'),
    re.compile(r'#(\d+)'),  # 排名
]

URL_PATTERN = re.compile(r'https?://[^\s\)]+')
WORD_SPLIT_PATTERN = re.compile(r'[\u4e00-\u9fff]{2,}|[a-zA-Z]{3,}')

def extract_time(text: str) -> Optional[str]:
    """提取时间"""
    for pattern in TIME_PATTERNS:
        match = pattern.search(text)
        if match:
            return match.group(1)
    return None

def extract_location(text: str) -> Optional[str]:
    """提取地点"""
    for pattern in LOCATION_PATTERNS:
        match = pattern.search(text)
        if match:
            return match.group(1)
    return None

def extract_person(text: str) -> Optional[str]:
    """提取人物"""
    for pattern in PERSON_PATTERNS:
        match = pattern.search(text)
        if match:
            return match.group(0)
    return None

def extract_source_and_rank(text: str) -> tuple[Optional[str], Optional[int]]:
    """提取来源平台和排名"""
    source = None
    rank = None
    
    for pattern in PLATFORM_PATTERNS:
        match = pattern.search(text)
        if match:
            if pattern.pattern == r'#(\d+)':
                rank = int(match.group(1))
            else:
                source = match.group(1)
    
    return source, rank

def extract_url(text: str) -> Optional[str]:
    """提取 URL"""
    match = URL_PATTERN.search(text)
    return match.group(0) if match else None


# ============================================================ 
# 热点信号识别
# ============================================================ 

# 热点关键词权重
HOTSPOT_KEYWORDS = {
    # 科技
    "AI": 10, "人工智能": 10, "ChatGPT": 9, "OpenAI": 9, "Gemini": 8,
    "大模型": 8, "芯片": 7, "5G": 6, "量子": 6,
    # 财经
    "股市": 8, "暴跌": 9, "暴涨": 9, "A股": 7, "美股": 7,
    "比特币": 8, "加密货币": 7, "房价": 7,
    # 社会
    "官方": 6, "通报": 7, "辟谣": 8, "热搜": 5,
    "突发": 9, "紧急": 8, "重大": 7,
    # 娱乐
    "明星": 5, "演员": 5, "导演": 5,
}

def identify_hotspots(text: str) -> list[str]:
    """识别热点信号"""
    found = []
    # 简单字符串匹配无需正则优化，除非列表极大
    text_lower = text.lower()
    for keyword, weight in HOTSPOT_KEYWORDS.items():
        if keyword.lower() in text_lower:
            found.append((keyword, weight))
    
    # 按权重排序
    found.sort(key=lambda x: x[1], reverse=True)
    return [k for k, w in found[:5]]  # 返回前5个热点

def extract_keywords(text: str) -> list[str]:
    """提取关键词（简单词频统计）"""
    # 移除常见停用词
    stopwords = {"的", "了", "是", "在", "和", "与", "或", "等", "被", "将", "已", "于", "为"}
    
    # 分词 (使用预编译正则)
    words = WORD_SPLIT_PATTERN.findall(text)
    
    # 过滤停用词和短词
    words = [w for w in words if w not in stopwords and len(w) >= 2]
    
    # 统计词频
    counter = Counter(words)
    
    # 返回高频词
    return [word for word, count in counter.most_common(10) if count >= 1]


# ============================================================ 
# 核心清洗函数
# ============================================================ 

def parse_news_item(line: str) -> ExtractedFact:
    """解析单条新闻"""
    cleaned = remove_noise(line)
    source, rank = extract_source_and_rank(line)
    
    return ExtractedFact(
        time=extract_time(line),
        location=extract_location(line),
        person=extract_person(line),
        event=cleaned[:200],  # 限制长度
        source=source,
        rank=rank,
        url=extract_url(line)
    )

def clean_raw_data(title: str, content: str) -> CleanedData:
    """
    清洗原始数据
    
    Args:
        title: 原始标题
        content: 原始内容（Markdown 格式）
    
    Returns:
        CleanedData: 结构化的清洗结果
    """
    # 按行分割
    lines = content.split('\n')
    
    # 提取事实
    facts = []
    for line in lines:
        line = line.strip()
        if len(line) > 10:  # 过滤短行
            fact = parse_news_item(line)
            if fact.event:  # 有效事实
                facts.append(fact)
    
    # 生成摘要
    cleaned_content = remove_noise(content)
    summary = cleaned_content[:300] + "..." if len(cleaned_content) > 300 else cleaned_content
    
    # 识别热点
    hotspots = identify_hotspots(content)
    
    # 提取关键词
    keywords = extract_keywords(cleaned_content)
    
    return CleanedData(
        title=remove_noise(title),
        summary=summary,
        facts=facts,
        hotspots=hotspots,
        keywords=keywords,
        cleaned_at=datetime.now().isoformat()
    )


# ============================================================ 
# 导出函数
# ============================================================ 

def clean_and_export(title: str, content: str, output_path: Optional[str] = None) -> dict:
    """
    清洗数据并导出
    
    Args:
        title: 原始标题
        content: 原始内容
        output_path: 可选，导出 JSON 文件路径
    
    Returns:
        dict: 清洗后的结构化数据
    """
    result = clean_raw_data(title, content)
    data = result.to_dict()
    
    if output_path:
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    
    return data
