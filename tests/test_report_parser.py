"""Tests for research report rule-based extraction."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from src.ai_engine.report_parser import (
    extract_target_price_from_title,
    extract_rating_change,
    extract_key_points,
    extract_risk_factors,
    analyze_report_rule_based,
    analyze_report_with_llm,
)


class TestExtractTargetPrice:
    def test_target_price_colon_yuan(self):
        assert extract_target_price_from_title("看好公司前景，目标价：35.5元") == 35.5

    def test_target_price_target_colon_yuan(self):
        assert extract_target_price_from_title("首次覆盖，目标：120元") == 120.0

    def test_target_price_yuan_suffix(self):
        assert extract_target_price_from_title("上调至88.8元目标") == 88.8

    def test_target_price_raise_to(self):
        assert extract_target_price_from_title("上调目标价至45.6") == 45.6

    def test_target_price_bare(self):
        assert extract_target_price_from_title("维持买入评级，目标价52") == 52.0

    def test_no_target_price(self):
        assert extract_target_price_from_title("业绩超预期，维持增持") is None

    def test_empty_string(self):
        assert extract_target_price_from_title("") is None

    def test_none_input(self):
        assert extract_target_price_from_title(None) is None


class TestExtractRatingChange:
    def test_first_coverage(self):
        assert extract_rating_change("首次覆盖：看好长期发展") == "首次覆盖"

    def test_upgrade(self):
        assert extract_rating_change("上调评级至买入") == "上调评级"

    def test_downgrade(self):
        assert extract_rating_change("下调评级至中性") == "下调评级"

    def test_maintain_buy(self):
        assert extract_rating_change("维持买入评级") == "维持买入"

    def test_maintain_overweight(self):
        assert extract_rating_change("维持增持评级") == "维持增持"

    def test_reiterate_buy(self):
        assert extract_rating_change("重申买入评级") == "重申买入"

    def test_no_rating_change(self):
        assert extract_rating_change("业绩快报点评") is None

    def test_none_input(self):
        assert extract_rating_change(None) is None


class TestExtractKeyPoints:
    def test_performance_beat(self):
        points = extract_key_points("业绩超预期，增长强劲")
        assert "业绩点评" in points

    def test_growth(self):
        points = extract_key_points("收入高增，毛利率提升")
        assert "增长亮点" in points

    def test_capital_operation(self):
        points = extract_key_points("拟定增募资20亿元")
        assert "资本运作" in points

    def test_new_product(self):
        points = extract_key_points("新品发布，打开增长空间")
        assert "新品发布" in points

    def test_order_win(self):
        points = extract_key_points("中标10亿元大订单")
        assert "订单获取" in points

    def test_valuation(self):
        points = extract_key_points("估值底部，投资价值凸显")
        assert "估值分析" in points

    def test_multiple_points(self):
        points = extract_key_points("业绩超预期，高增长，中标大订单")
        assert len(points) >= 2

    def test_no_points(self):
        assert extract_key_points("公司调研纪要") == []

    def test_none_input(self):
        assert extract_key_points(None) == []


class TestExtractRiskFactors:
    def test_policy_risk(self):
        factors = extract_risk_factors("政策风险可控，维持买入")
        assert "政策风险" in factors

    def test_competition_risk(self):
        factors = extract_risk_factors("竞争加剧，关注盈利压力")
        assert "竞争风险" in factors

    def test_demand_risk(self):
        factors = extract_risk_factors("下游需求不及预期")
        assert "需求风险" in factors

    def test_cost_risk(self):
        factors = extract_risk_factors("原材料成本上升压力")
        assert "成本风险" in factors

    def test_no_risk(self):
        assert extract_risk_factors("业绩超预期") == []

    def test_none_input(self):
        assert extract_risk_factors(None) == []


class TestAnalyzeReportRuleBased:
    def test_positive_sentiment(self):
        report = {"report_title": "目标价：50元，业绩超预期", "rating": "买入"}
        result = analyze_report_rule_based(report)
        assert result["target_price"] == 50.0
        assert result["sentiment"] == "positive"
        assert "业绩点评" in result["key_points"]

    def test_neutral_sentiment(self):
        report = {"report_title": "符合预期", "rating": "持有"}
        result = analyze_report_rule_based(report)
        assert result["sentiment"] == "neutral"

    def test_negative_sentiment(self):
        report = {"report_title": "下调评级", "rating": "减持"}
        result = analyze_report_rule_based(report)
        assert result["sentiment"] == "negative"
        assert result["rating_change"] == "下调评级"

    def test_missing_fields(self):
        result = analyze_report_rule_based({})
        assert result["target_price"] is None
        assert result["rating_change"] is None
        assert result["key_points"] == []
        assert result["sentiment"] == "negative"  # empty rating -> negative


from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from src.database.repositories.report import ReportRepository
from src.ai_engine.report_parser import analyze_and_save_reports


class TestAnalyzeAndSave:
    @pytest.fixture()
    def repo(self, tmp_path):
        db_url = f"sqlite:///{tmp_path / 'test.db'}"
        engine = create_engine(db_url)
        Session = sessionmaker(bind=engine)
        repository = ReportRepository(Session)
        repository.create_tables(engine)
        return repository

    def test_analyze_and_save_populates_fields(self, repo):
        repo.upsert_report({
            "ts_code": "000001.SZ",
            "stock_name": "平安银行",
            "title": "目标价：50元，业绩超预期，维持买入",
            "institution": "中信证券",
            "rating": "买入",
            "publish_date": "20260301",
        })
        results = analyze_and_save_reports(repo)
        assert len(results) == 1
        assert results[0]["target_price"] == 50.0
        assert results[0]["sentiment"] == "positive"

        # Verify saved to DB
        reports = repo.get_reports(ts_code="000001.SZ")
        assert reports[0]["target_price"] == 50.0
        assert reports[0]["key_points"] == ["业绩点评"]

    def test_analyze_empty_repo(self, repo):
        results = analyze_and_save_reports(repo)
        assert results == []


class TestAnalyzeReportWithLLM:
    @pytest.mark.asyncio
    async def test_returns_none_without_api_key(self):
        with patch.dict("os.environ", {}, clear=True):
            result = await analyze_report_with_llm({"report_title": "test"})
            assert result is None

    @pytest.mark.asyncio
    async def test_successful_analysis(self):
        mock_response = MagicMock()
        mock_response.choices = [
            MagicMock(
                message=MagicMock(
                    content='{"core_logic": "增长强劲", "catalysts": ["新品"], "risks": ["竞争"], "sentiment_score": 0.8}'
                )
            )
        ]

        mock_client = AsyncMock()
        mock_client.chat.completions.create = AsyncMock(return_value=mock_response)

        with patch.dict("os.environ", {"DEEPSEEK_API_KEY": "test-key"}):
            with patch("src.ai_engine.report_parser.AsyncOpenAI", return_value=mock_client):
                result = await analyze_report_with_llm({
                    "report_title": "业绩超预期",
                    "institution": "中信证券",
                    "rating": "买入",
                })

        assert result is not None
        assert result["core_logic"] == "增长强劲"
        assert "新品" in result["catalysts"]
        assert result["sentiment_score"] == 0.8

    @pytest.mark.asyncio
    async def test_handles_api_error(self):
        mock_client = AsyncMock()
        mock_client.chat.completions.create = AsyncMock(side_effect=Exception("API error"))

        with patch.dict("os.environ", {"DEEPSEEK_API_KEY": "test-key"}):
            with patch("src.ai_engine.report_parser.AsyncOpenAI", return_value=mock_client):
                result = await analyze_report_with_llm({
                    "report_title": "test",
                    "institution": "test",
                    "rating": "买入",
                })
        assert result is None

    @pytest.mark.asyncio
    async def test_extracts_json_from_markdown(self):
        mock_response = MagicMock()
        mock_response.choices = [
            MagicMock(
                message=MagicMock(
                    content='```json\n{"core_logic": "test", "catalysts": [], "risks": [], "sentiment_score": 0.5}\n```'
                )
            )
        ]

        mock_client = AsyncMock()
        mock_client.chat.completions.create = AsyncMock(return_value=mock_response)

        with patch.dict("os.environ", {"DEEPSEEK_API_KEY": "test-key"}):
            with patch("src.ai_engine.report_parser.AsyncOpenAI", return_value=mock_client):
                result = await analyze_report_with_llm({
                    "report_title": "test",
                    "institution": "test",
                    "rating": "买入",
                })
        assert result is not None
        assert result["core_logic"] == "test"
