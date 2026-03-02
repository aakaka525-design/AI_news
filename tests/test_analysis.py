#!/usr/bin/env python3
"""
Analysis module tests - cleaner, hotspots, keywords, time/location extraction.

Covers:
- remove_noise: markdown/HTML stripping, link text preservation, whitespace collapse
- extract_time: YYYY-MM-DD, Chinese dates, missing dates
- extract_location: Chinese cities, missing locations
- identify_hotspots: tech/finance keyword detection
- extract_keywords: meaningful word extraction, stopword exclusion
- clean_raw_data: end-to-end structured output
"""

from datetime import datetime

import pytest

from src.analysis.cleaner import (
    CleanedData,
    ExtractedFact,
    clean_raw_data,
    extract_keywords,
    extract_location,
    extract_time,
    identify_hotspots,
    remove_noise,
)

# ============================================================
# TestRemoveNoise
# ============================================================


class TestRemoveNoise:
    """Tests for remove_noise()."""

    def test_removes_markdown_bold(self):
        text = "这是**加粗**文本"
        result = remove_noise(text)
        assert "**" not in result
        assert "加粗" in result

    def test_removes_html_tags(self):
        text = "<p>段落内容</p>"
        result = remove_noise(text)
        assert "<p>" not in result
        assert "</p>" not in result
        assert "段落内容" in result

    def test_preserves_link_text_from_markdown(self):
        text = "查看 [官方公告](https://example.com/notice) 获取详情"
        result = remove_noise(text)
        assert "官方公告" in result
        assert "https://example.com" not in result
        assert "[" not in result
        assert "]" not in result

    def test_collapses_whitespace(self):
        text = "词语之间   有    很多   空白"
        result = remove_noise(text)
        assert "   " not in result
        # Should be collapsed to single spaces
        assert "词语之间 有 很多 空白" == result

    def test_removes_markdown_headings(self):
        text = "## 标题内容"
        result = remove_noise(text)
        assert "#" not in result
        assert "标题内容" in result

    def test_empty_string_returns_empty(self):
        assert remove_noise("") == ""

    def test_removes_code_blocks(self):
        text = "正文 ```python\nprint('hello')\n``` 结尾"
        result = remove_noise(text)
        assert "```" not in result
        assert "print" not in result


# ============================================================
# TestExtractTime
# ============================================================


class TestExtractTime:
    """Tests for extract_time()."""

    def test_extracts_yyyy_mm_dd_format(self):
        text = "发布日期 2026-03-01 的公告"
        result = extract_time(text)
        assert result == "2026-03-01"

    def test_extracts_yyyy_slash_format(self):
        text = "发布日期 2026/01/16 的公告"
        result = extract_time(text)
        assert result == "2026/01/16"

    def test_extracts_chinese_date(self):
        text = "3月1日，市场出现波动"
        result = extract_time(text)
        assert result == "3月1日"

    def test_extracts_relative_date(self):
        text = "今日A股大幅上涨"
        result = extract_time(text)
        assert result == "今日"

    def test_returns_none_when_no_date(self):
        text = "这段文本里面没有任何日期信息"
        result = extract_time(text)
        assert result is None


# ============================================================
# TestExtractLocation
# ============================================================


class TestExtractLocation:
    """Tests for extract_location()."""

    def test_extracts_chinese_city_beijing(self):
        text = "北京市政府发布新政策"
        result = extract_location(text)
        assert result == "北京"

    def test_extracts_chinese_city_shanghai(self):
        text = "上海证券交易所公告"
        result = extract_location(text)
        assert result == "上海"

    def test_extracts_country(self):
        text = "美国宣布新的贸易政策"
        result = extract_location(text)
        assert result == "美国"

    def test_returns_none_when_no_location(self):
        text = "这条新闻没有提到任何地点"
        result = extract_location(text)
        assert result is None


# ============================================================
# TestIdentifyHotspots
# ============================================================


class TestIdentifyHotspots:
    """Tests for identify_hotspots()."""

    def test_identifies_ai_tech_hotspots(self):
        text = "OpenAI 发布了新的 AI 大模型"
        result = identify_hotspots(text)
        assert isinstance(result, list)
        assert "AI" in result or "人工智能" in result
        assert "OpenAI" in result

    def test_identifies_finance_hotspots(self):
        text = "A股暴涨，股市行情火爆"
        result = identify_hotspots(text)
        assert isinstance(result, list)
        assert "暴涨" in result
        assert "股市" in result
        assert "A股" in result

    def test_returns_empty_list_for_no_hotspots(self):
        text = "今天天气不错，适合散步"
        result = identify_hotspots(text)
        assert isinstance(result, list)
        assert len(result) == 0

    def test_returns_max_five_hotspots(self):
        text = "AI 人工智能 ChatGPT OpenAI 大模型 芯片 5G 量子 突发 紧急 暴涨 暴跌"
        result = identify_hotspots(text)
        assert len(result) <= 5

    def test_hotspots_sorted_by_weight(self):
        text = "5G 芯片 AI 技术"
        result = identify_hotspots(text)
        # AI (weight 10) should come before 芯片 (7) and 5G (6)
        if "AI" in result and "5G" in result:
            assert result.index("AI") < result.index("5G")


# ============================================================
# TestExtractKeywords
# ============================================================


class TestExtractKeywords:
    """Tests for extract_keywords()."""

    def test_extracts_meaningful_chinese_words(self):
        text = "人工智能技术在金融领域发展迅速"
        result = extract_keywords(text)
        assert isinstance(result, list)
        assert len(result) > 0
        # Should find multi-char Chinese words
        for kw in result:
            assert len(kw) >= 2

    def test_excludes_stopwords(self):
        text = "的了是在和与或等被将已于为"
        result = extract_keywords(text)
        stopwords = {"的", "了", "是", "在", "和", "与", "或", "等", "被", "将", "已", "于", "为"}
        for kw in result:
            assert kw not in stopwords

    def test_returns_empty_for_empty_text(self):
        result = extract_keywords("")
        assert result == []

    def test_extracts_english_words(self):
        text = "The OpenAI ChatGPT model is powerful"
        result = extract_keywords(text)
        assert isinstance(result, list)
        # Should find English words with >= 3 chars
        found_words = set(result)
        assert "OpenAI" in found_words or "ChatGPT" in found_words or "model" in found_words

    def test_max_ten_keywords(self):
        # Build a text with many distinct words
        text = "量子计算 人工智能 区块链 元宇宙 机器学习 深度学习 自然语言 计算机 大数据 云计算 物联网 虚拟现实"
        result = extract_keywords(text)
        assert len(result) <= 10


# ============================================================
# TestCleanRawData
# ============================================================


class TestCleanRawData:
    """Tests for clean_raw_data()."""

    def test_returns_cleaned_data_instance(self):
        result = clean_raw_data("测试标题", "这是一段足够长度的测试内容用来验证清洗流程")
        assert isinstance(result, CleanedData)

    def test_has_correct_structure(self):
        result = clean_raw_data(
            "AI **技术** 突破",
            "OpenAI 在北京发布了新的 AI 大模型，引发市场关注",
        )
        assert isinstance(result.title, str)
        assert isinstance(result.summary, str)
        assert isinstance(result.facts, list)
        assert isinstance(result.hotspots, list)
        assert isinstance(result.keywords, list)
        assert isinstance(result.cleaned_at, str)

    def test_title_is_cleaned(self):
        result = clean_raw_data("**加粗标题**", "内容文本用来充当正文的一段测试")
        assert "**" not in result.title
        assert "加粗标题" in result.title

    def test_facts_is_list_of_extracted_fact(self):
        content = "2026-03-01 北京发布AI政策\nOpenAI推出新产品引发关注"
        result = clean_raw_data("测试", content)
        assert isinstance(result.facts, list)
        for fact in result.facts:
            assert isinstance(fact, ExtractedFact)

    def test_hotspots_and_keywords_are_lists(self):
        result = clean_raw_data("AI新闻", "ChatGPT 引发人工智能革命")
        assert isinstance(result.hotspots, list)
        assert isinstance(result.keywords, list)

    def test_cleaned_at_is_iso_format(self):
        result = clean_raw_data("标题", "内容足够长度的正文文本用来生成事实")
        # Should be parseable as an ISO datetime
        parsed = datetime.fromisoformat(result.cleaned_at)
        assert isinstance(parsed, datetime)

    def test_to_dict_returns_dict(self):
        result = clean_raw_data("标题", "内容足够长度的正文文本用来验证")
        d = result.to_dict()
        assert isinstance(d, dict)
        assert "title" in d
        assert "summary" in d
        assert "facts" in d
        assert "hotspots" in d
        assert "keywords" in d
        assert "cleaned_at" in d


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
