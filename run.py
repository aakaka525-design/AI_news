#!/usr/bin/env python3
"""
主入口脚本

用法：
    python run.py api          # 启动 FastAPI 服务
    python run.py fetch        # 运行数据抓取
    python run.py analyze      # 运行分析
    python run.py migrate      # 运行数据库迁移
"""

import sys
import os

# 添加项目根目录到 PYTHONPATH
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def run_api():
    """启动 FastAPI 服务"""
    import uvicorn
    uvicorn.run(
        "api.main:app",
        host="0.0.0.0",
        port=8000,
        reload=True
    )


def run_fetch():
    """运行数据抓取"""
    from src.data_ingestion.tushare.daily import main
    main()


def run_analyze():
    """运行分析"""
    import asyncio
    from src.ai_engine.sentiment import analyze_pending_news, get_sentiment_stats

    print("📊 运行 AI 分析（RSS 情感）...")

    try:
        before = get_sentiment_stats()
        result = asyncio.run(analyze_pending_news(limit=20))
        after = get_sentiment_stats()
    except Exception as exc:  # noqa: BLE001
        print(f"❌ analyze 执行失败: {exc}")
        raise SystemExit(1) from exc

    print(
        "   分析结果: "
        f"analyzed={result.get('analyzed', 0)}, pending={result.get('pending', 0)}"
    )
    if result.get("error"):
        print(f"   ⚠️ {result['error']}")
    print(
        "   统计变化: "
        f"analyzed {before.get('analyzed_count', 0)} -> {after.get('analyzed_count', 0)}, "
        f"pending {before.get('pending_count', 0)} -> {after.get('pending_count', 0)}"
    )

    return {"before": before, "result": result, "after": after}


def run_migrate():
    """运行数据库迁移"""
    from src.database.migrations.migrate_to_tushare import main
    main()


def show_help():
    print(__doc__)


if __name__ == "__main__":
    commands = {
        "api": run_api,
        "fetch": run_fetch,
        "analyze": run_analyze,
        "migrate": run_migrate,
        "help": show_help,
        "-h": show_help,
        "--help": show_help,
    }
    
    if len(sys.argv) < 2:
        show_help()
        sys.exit(0)
    
    cmd = sys.argv[1]
    if cmd in commands:
        commands[cmd]()
    else:
        print(f"❌ 未知命令: {cmd}")
        show_help()
        sys.exit(1)
