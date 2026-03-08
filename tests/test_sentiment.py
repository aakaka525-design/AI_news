"""
情感分析模块单元测试

覆盖：SentimentAnalyzer、批量分析、工厂函数、统计
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch


class TestSentimentAnalyzer:
    """情感分析器测试"""

    def test_build_prompt_formats_correctly(self):
        from src.ai_engine.sentiment import SentimentAnalyzer

        analyzer = SentimentAnalyzer(client=MagicMock(), model="test-model")
        items = [
            {"id": 1, "title": "股市大涨", "summary": "A股全线上涨"},
            {"id": 2, "title": "经济数据", "summary": None},
        ]
        prompt = analyzer._build_prompt(items)
        assert "[ID=1]" in prompt
        assert "股市大涨" in prompt
        assert "[ID=2]" in prompt

    @pytest.mark.asyncio
    async def test_analyze_batch_empty_returns_empty(self):
        from src.ai_engine.sentiment import SentimentAnalyzer

        analyzer = SentimentAnalyzer(client=MagicMock(), model="test-model")
        result = await analyzer.analyze_batch([])
        assert result == []

    @pytest.mark.asyncio
    async def test_analyze_batch_returns_results(self):
        from src.ai_engine.sentiment import SentimentAnalyzer

        mock_json = '[{"id": 1, "sentiment_score": 0.8, "ai_summary": "利好", "market_impact": "利好", "related_sectors": ["科技"]}]'

        with patch("src.ai_engine.sentiment.call_with_retry", new_callable=AsyncMock, return_value=mock_json):
            analyzer = SentimentAnalyzer(client=MagicMock(), model="test-model")
            items = [{"id": 1, "title": "测试新闻", "summary": "内容"}]
            results = await analyzer.analyze_batch(items)
            assert len(results) == 1
            assert results[0]["sentiment_score"] == 0.8

    @pytest.mark.asyncio
    async def test_analyze_batch_handles_api_error(self):
        from src.ai_engine.sentiment import SentimentAnalyzer

        with patch("src.ai_engine.sentiment.call_with_retry", new_callable=AsyncMock, side_effect=Exception("API error")):
            analyzer = SentimentAnalyzer(client=MagicMock(), model="test-model")
            items = [{"id": 1, "title": "测试", "summary": ""}]
            results = await analyzer.analyze_batch(items)
            assert results == []

    @pytest.mark.asyncio
    async def test_analyze_batch_wraps_dict_in_list(self):
        from src.ai_engine.sentiment import SentimentAnalyzer

        mock_json = '{"id": 1, "sentiment_score": 0.5, "ai_summary": "中性", "market_impact": "中性", "related_sectors": []}'

        with patch("src.ai_engine.sentiment.call_with_retry", new_callable=AsyncMock, return_value=mock_json):
            analyzer = SentimentAnalyzer(client=MagicMock(), model="test-model")
            items = [{"id": 1, "title": "单条新闻", "summary": "内容"}]
            results = await analyzer.analyze_batch(items)
            assert isinstance(results, list)
            assert len(results) == 1


class TestCreateSentimentAnalyzer:
    """工厂函数测试"""

    def test_returns_none_without_client(self):
        with patch("src.ai_engine.sentiment.get_gemini_client", return_value=None):
            from src.ai_engine.sentiment import create_sentiment_analyzer
            result = create_sentiment_analyzer()
            assert result is None

    def test_returns_analyzer_with_client(self):
        mock_client = MagicMock()
        with patch("src.ai_engine.sentiment.get_gemini_client", return_value=mock_client), \
             patch("src.ai_engine.sentiment.get_default_model", return_value="test-model"):
            from src.ai_engine.sentiment import create_sentiment_analyzer
            result = create_sentiment_analyzer()
            assert result is not None


class TestAnalyzePendingNews:
    """主函数测试"""

    @pytest.mark.asyncio
    async def test_no_pending_news(self):
        from src.ai_engine.sentiment import analyze_pending_news

        mock_repo = MagicMock()
        mock_repo.get_unanalyzed_rss.return_value = []

        result = await analyze_pending_news(mock_repo)
        assert result["analyzed"] == 0

    @pytest.mark.asyncio
    async def test_analyzer_creation_fails(self):
        from src.ai_engine.sentiment import analyze_pending_news

        mock_repo = MagicMock()
        mock_repo.get_unanalyzed_rss.return_value = [{"id": 1, "title": "test", "summary": ""}]

        with patch("src.ai_engine.sentiment.create_sentiment_analyzer", return_value=None):
            result = await analyze_pending_news(mock_repo)
            assert "error" in result


class TestGetSentimentStats:
    """统计函数测试"""

    def test_delegates_to_repo(self):
        from src.ai_engine.sentiment import get_sentiment_stats

        mock_repo = MagicMock()
        mock_repo.get_rss_sentiment_stats.return_value = {"positive": 10, "negative": 5}

        result = get_sentiment_stats(mock_repo)
        assert result["positive"] == 10
        mock_repo.get_rss_sentiment_stats.assert_called_once()
