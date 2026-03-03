#!/usr/bin/env python3
"""Tests for run.py command wrappers."""

import run


def test_run_analyze_executes_ai_pipeline(monkeypatch, capsys):
    import src.ai_engine.sentiment as sentiment_module

    calls = {"limit": None}

    async def _fake_analyze_pending_news(limit: int = 20):
        calls["limit"] = limit
        return {"analyzed": 2, "pending": 0}

    stats = [
        {"analyzed_count": 1, "pending_count": 3},
        {"analyzed_count": 3, "pending_count": 1},
    ]

    def _fake_stats():
        return stats.pop(0)

    monkeypatch.setattr(sentiment_module, "analyze_pending_news", _fake_analyze_pending_news)
    monkeypatch.setattr(sentiment_module, "get_sentiment_stats", _fake_stats)

    result = run.run_analyze()
    output = capsys.readouterr().out

    assert calls["limit"] == 20
    assert result["result"]["analyzed"] == 2
    assert "运行 AI 分析" in output
