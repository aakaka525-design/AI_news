"""
统一调度器模块 - 管理所有定时任务

功能：
1. 定时执行 RSS 抓取、金融数据更新等任务
2. 提供 API 接口查看/管理任务
3. 任务执行日志记录
"""

import asyncio
import logging
import os
from datetime import datetime
from typing import Callable, Optional
from dataclasses import dataclass, field

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger
from apscheduler.jobstores.memory import MemoryJobStore

# ============================================================
# 配置
# ============================================================

logger = logging.getLogger(__name__)

# 任务配置
TASK_CONFIGS = {
    "rss_fetch": {
        "name": "RSS 抓取",
        "trigger": "interval",
        "minutes": 30,
        "enabled": True,
        "description": "从 RSS 源和 RSSHub 抓取新闻"
    },
    "stock_indicators": {
        "name": "技术指标更新",
        "trigger": "cron",
        "hour": 16,
        "minute": 30,
        "day_of_week": "mon-fri",
        "enabled": True,
        "description": "收盘后更新技术指标、RPS 等"
    },
    "fund_flow": {
        "name": "资金流向更新",
        "trigger": "cron",
        "hour": 17,
        "minute": 0,
        "day_of_week": "mon-fri",
        "enabled": True,
        "description": "更新沪深股通、龙虎榜数据"
    },
    "macro_data": {
        "name": "宏观数据更新",
        "trigger": "cron",
        "hour": 8,
        "minute": 0,
        "enabled": True,
        "description": "更新 M1/M2、CPI、GDP 等宏观指标"
    },
    "ai_analysis": {
        "name": "AI 热点分析",
        "trigger": "cron",
        "hour": 9,
        "minute": 0,
        "enabled": True,
        "description": "每日早间 AI 热点分析"
    },
    "polymarket_fetch": {
        "name": "Polymarket 预测市场",
        "trigger": "interval",
        "minutes": None,  # Filled at import time from settings
        "enabled": None,  # Filled at import time from settings
        "description": "从 Polymarket 拉取预测市场数据，检测概率波动"
    },
    "screen_snapshot": {
        "name": "筛选器日快照生成",
        "trigger": "cron",
        "hour": 17,
        "minute": 15,
        "day_of_week": "mon-fri",
        "enabled": True,
        "description": "生成 RPS/潜力筛选日快照，清理过期数据"
    },
    "intraday_snapshot": {
        "name": "盘中快照轮询",
        "trigger": "interval",
        "minutes": 10,
        "enabled": True,
        "description": "盘中拉取实时行情快照（9:30-15:00 交易日）"
    },
    "composite_score": {
        "name": "综合评分计算",
        "trigger": "cron",
        "hour": 17,
        "minute": 30,
        "day_of_week": "mon-fri",
        "enabled": True,
        "description": "收盘后全市场综合评分批量计算"
    },
}

# Static mapping: task_id -> expected (source_key, dataset_key, db_name) tuples.
# Used to synthesize error telemetry when a task fails before returning datasets.
TASK_EXPECTED_DATASETS: dict[str, list[tuple[str, str, str]]] = {
    "rss_fetch": [("rss", "rss_items", "news")],
    "ai_analysis": [("ai", "analysis", "news"), ("ai", "rss_sentiment", "news")],
    "stock_indicators": [
        ("tushare", "ts_daily", "stocks"),
        ("tushare", "ts_weekly", "stocks"),
        ("tushare", "ts_weekly_valuation", "stocks"),
    ],
    "fund_flow": [("tushare", "ts_moneyflow", "stocks"), ("tushare", "ts_hsgt_top10", "stocks")],
    "macro_data": [
        ("tushare", "ts_daily_basic", "stocks"),
        ("tushare", "ts_hk_hold", "stocks"),
        ("tushare", "ts_top10_holders", "stocks"),
        ("tushare", "ts_cyq_perf", "stocks"),
    ],
    "screen_snapshot": [
        ("derived", "screen_rps", "stocks"),
        ("derived", "screen_potential", "stocks"),
    ],
    "composite_score": [
        ("derived", "composite_score", "stocks"),
    ],
}

# Fill Polymarket config from centralized settings
from config.settings import POLYMARKET_ENABLED, POLYMARKET_FETCH_INTERVAL, SCHEDULER_TIMEZONE
TASK_CONFIGS["polymarket_fetch"]["minutes"] = POLYMARKET_FETCH_INTERVAL
TASK_CONFIGS["polymarket_fetch"]["enabled"] = POLYMARKET_ENABLED


# ============================================================
# 数据结构
# ============================================================

@dataclass
class TaskResult:
    """任务执行结果"""
    task_id: str
    success: bool
    start_time: datetime
    end_time: datetime
    message: str = ""
    error: Optional[str] = None


@dataclass
class TaskStatus:
    """任务状态"""
    task_id: str
    name: str
    description: str
    enabled: bool
    next_run: Optional[datetime]
    last_run: Optional[datetime] = None
    last_result: Optional[str] = None
    run_count: int = 0


# ============================================================
# 调度器管理器
# ============================================================

class SchedulerManager:
    """统一调度器管理"""
    
    def __init__(self):
        self.scheduler = AsyncIOScheduler(
            jobstores={"default": MemoryJobStore()},
            timezone=SCHEDULER_TIMEZONE
        )
        self._task_history: dict[str, list[TaskResult]] = {}
        self._task_funcs: dict[str, Callable] = {}
        self._running = False
    
    def register_task(self, task_id: str, func: Callable):
        """注册任务执行函数"""
        self._task_funcs[task_id] = func
        logger.info(f"注册任务: {task_id}")
    
    def _create_trigger(self, config: dict):
        """根据配置创建触发器"""
        trigger_type = config.get("trigger", "interval")
        
        if trigger_type == "interval":
            return IntervalTrigger(
                minutes=config.get("minutes", 30),
                seconds=config.get("seconds", 0)
            )
        elif trigger_type == "cron":
            return CronTrigger(
                hour=config.get("hour", 0),
                minute=config.get("minute", 0),
                day_of_week=config.get("day_of_week", "*")
            )
        else:
            raise ValueError(f"未知触发器类型: {trigger_type}")
    
    async def _execute_task(self, task_id: str):
        """执行任务并记录结果"""
        start_time = datetime.now()
        result = TaskResult(
            task_id=task_id,
            success=False,
            start_time=start_time,
            end_time=start_time
        )
        task_return = None

        try:
            func = self._task_funcs.get(task_id)
            if not func:
                raise ValueError(f"任务 {task_id} 未注册执行函数")

            logger.info(f"▶️ 开始执行任务: {task_id}")

            # 执行任务（支持同步和异步函数），带超时保护
            task_timeout = 3600  # 1 小时超时
            if asyncio.iscoroutinefunction(func):
                task_return = await asyncio.wait_for(func(), timeout=task_timeout)
            else:
                task_return = await asyncio.wait_for(
                    asyncio.get_event_loop().run_in_executor(None, func),
                    timeout=task_timeout,
                )

            result.success = True
            result.message = "执行成功"
            logger.info(f"✅ 任务完成: {task_id}")

        except Exception as e:
            result.error = str(e)
            result.message = f"执行失败: {e}"
            logger.error(f"❌ 任务失败: {task_id} - {e}")

        finally:
            result.end_time = datetime.now()

            # 记录历史
            if task_id not in self._task_history:
                self._task_history[task_id] = []
            self._task_history[task_id].append(result)

            # 只保留最近 20 条记录（避免内存膨胀）
            if len(self._task_history[task_id]) > 20:
                self._task_history[task_id] = self._task_history[task_id][-20:]

            # Persist telemetry (best-effort, never fails the task)
            try:
                from src.telemetry.models import DatasetTelemetry, TaskExecutionTelemetry
                from src.telemetry.recorder import record_telemetry

                datasets = None
                if isinstance(task_return, list) and task_return and isinstance(task_return[0], DatasetTelemetry):
                    datasets = task_return
                elif not result.success and task_id in TASK_EXPECTED_DATASETS:
                    # Task failed before returning datasets — synthesize error entries
                    datasets = [
                        DatasetTelemetry(
                            source_key=src, dataset_key=ds, db_name=db,
                            record_count=0, status="error",
                            error_message=result.error,
                        )
                        for src, ds, db in TASK_EXPECTED_DATASETS[task_id]
                    ]

                if datasets:
                    tel = TaskExecutionTelemetry(
                        task_id=task_id,
                        started_at=start_time,
                        finished_at=result.end_time,
                        success=result.success,
                        error=result.error,
                        datasets=datasets,
                    )
                    record_telemetry(tel)
            except Exception as tel_err:
                logger.warning(f"Telemetry recording failed for {task_id}: {tel_err}")

        return result
    
    def start(self):
        """启动调度器"""
        if self._running:
            return
        
        # 添加所有启用的任务
        for task_id, config in TASK_CONFIGS.items():
            if not config.get("enabled", True):
                continue
            
            if task_id not in self._task_funcs:
                logger.warning(f"任务 {task_id} 未注册执行函数，跳过")
                continue
            
            trigger = self._create_trigger(config)
            # For interval triggers, fire immediately on startup
            kwargs: dict = {}
            if config.get("trigger") == "interval":
                kwargs["next_run_time"] = datetime.now()
            self.scheduler.add_job(
                self._execute_task,
                trigger=trigger,
                id=task_id,
                args=[task_id],
                name=config.get("name", task_id),
                replace_existing=True,
                **kwargs,
            )
            logger.info(f"📅 添加定时任务: {config.get('name', task_id)}")
        
        self.scheduler.start()
        self._running = True
        logger.info("🚀 调度器已启动")
    
    def stop(self):
        """停止调度器（等待进行中的任务完成）"""
        if self._running:
            self.scheduler.shutdown(wait=True)
            self._running = False
            logger.info("⏹️ 调度器已停止")
    
    def get_jobs(self) -> list[TaskStatus]:
        """获取所有任务状态"""
        jobs = []
        
        for task_id, config in TASK_CONFIGS.items():
            job = self.scheduler.get_job(task_id)
            history = self._task_history.get(task_id, [])
            last_result = history[-1] if history else None
            
            status = TaskStatus(
                task_id=task_id,
                name=config.get("name", task_id),
                description=config.get("description", ""),
                enabled=config.get("enabled", True) and job is not None,
                next_run=job.next_run_time if job else None,
                last_run=last_result.end_time if last_result else None,
                last_result="成功" if last_result and last_result.success else ("失败" if last_result else None),
                run_count=len(history)
            )
            jobs.append(status)
        
        return jobs
    
    async def trigger_job(self, task_id: str) -> TaskResult:
        """手动触发任务"""
        if task_id not in TASK_CONFIGS:
            raise ValueError(f"未知任务: {task_id}")
        
        return await self._execute_task(task_id)
    
    def pause_job(self, task_id: str) -> bool:
        """暂停任务"""
        job = self.scheduler.get_job(task_id)
        if job:
            self.scheduler.pause_job(task_id)
            logger.info(f"⏸️ 暂停任务: {task_id}")
            return True
        return False
    
    def resume_job(self, task_id: str) -> bool:
        """恢复任务"""
        job = self.scheduler.get_job(task_id)
        if job:
            self.scheduler.resume_job(task_id)
            logger.info(f"▶️ 恢复任务: {task_id}")
            return True
        return False
    
    def get_task_history(self, task_id: str, limit: int = 10) -> list[dict]:
        """获取任务执行历史"""
        history = self._task_history.get(task_id, [])
        return [
            {
                "start_time": r.start_time.isoformat(),
                "end_time": r.end_time.isoformat(),
                "success": r.success,
                "message": r.message,
                "duration": (r.end_time - r.start_time).total_seconds()
            }
            for r in history[-limit:]
        ]


# 全局实例
scheduler_manager = SchedulerManager()


# ============================================================
# 任务注册辅助函数
# ============================================================

def register_default_tasks():
    """注册默认任务"""
    import sys
    import os

    from src.telemetry.models import DatasetTelemetry

    # 添加项目根目录到路径
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    if project_root not in sys.path:
        sys.path.insert(0, project_root)

    # ------------------------------------------------------------------
    # RSS 抓取（async，带 telemetry）
    # ------------------------------------------------------------------
    from rss_fetcher import run_rss_fetch

    async def rss_task():
        items = await run_rss_fetch(include_rsshub=True)
        count = len(items) if items else 0
        return [
            DatasetTelemetry(
                source_key="rss",
                dataset_key="rss_items",
                db_name="news",
                record_count=count,
                status="ok" if count > 0 else "empty",
            )
        ]

    scheduler_manager.register_task("rss_fetch", rss_task)

    # ------------------------------------------------------------------
    # AI 分析（async，带 telemetry）
    # ------------------------------------------------------------------
    from src.ai_engine.llm_analyzer import create_analyzer_from_env
    from src.ai_engine.sentiment import analyze_pending_news
    from rss_fetcher import get_recent_rss
    from api.db import news_session as _ai_session
    from src.database.repositories.news import NewsRepository as _AINewsRepo

    _ai_repo = _AINewsRepo(_ai_session)

    async def ai_task():
        analysis_count = 0
        sentiment_count = 0

        # 1. 热点分析
        analyzer = create_analyzer_from_env()
        if not analyzer:
            raise RuntimeError("AI 分析器未启用")
        items = get_recent_rss(limit=20)
        if not items:
            logger.info("无可分析 RSS 数据，跳过本轮 AI 分析")
            return [
                DatasetTelemetry(source_key="ai", dataset_key="analysis", db_name="news", record_count=0, status="empty"),
                DatasetTelemetry(source_key="ai", dataset_key="rss_sentiment", db_name="news", record_count=0, status="empty"),
            ]
        payload = [
            {"id": r.get("id"), "title": r.get("title", ""), "content": r.get("summary", "")}
            for r in items
        ]
        analysis = await analyzer.analyze_opportunities(payload)

        if "error" not in analysis:
            from datetime import datetime as _dt
            _ai_repo.insert_analysis(
                date=_dt.now().strftime("%Y-%m-%d"),
                input_count=len(payload),
                analysis_summary=analysis.get("analysis_summary", ""),
                opportunities=analysis.get("opportunities", []),
            )
            analysis_count = len(analysis.get("opportunities", []))
            logger.info(f"AI 热点分析完成，已保存 {analysis_count} 个机会")
        else:
            logger.warning(f"AI 热点分析返回错误: {analysis.get('error')}")

        # 2. 情感分析
        sentiment_result = await analyze_pending_news(_ai_repo)
        if isinstance(sentiment_result, dict):
            sentiment_count = sentiment_result.get("analyzed", 0)
        logger.info(f"情感分析: {sentiment_result}")

        return [
            DatasetTelemetry(source_key="ai", dataset_key="analysis", db_name="news", record_count=analysis_count),
            DatasetTelemetry(source_key="ai", dataset_key="rss_sentiment", db_name="news", record_count=sentiment_count),
        ]

    scheduler_manager.register_task("ai_analysis", ai_task)

    # ------------------------------------------------------------------
    # 技术指标（直接 import，替代 subprocess）
    # ------------------------------------------------------------------
    from scripts.fetch_history import run_stock_indicators

    def indicators_task():
        results = run_stock_indicators()
        return [
            DatasetTelemetry(
                source_key="tushare", dataset_key=r["dataset"], db_name="stocks", record_count=r["count"],
            )
            for r in results
        ]

    scheduler_manager.register_task("stock_indicators", indicators_task)

    # ------------------------------------------------------------------
    # 资金流向（直接 import，替代 subprocess）
    # ------------------------------------------------------------------
    from src.data_ingestion.tushare.moneyflow import run_fund_flow

    def fund_flow_task():
        results = run_fund_flow()
        return [
            DatasetTelemetry(
                source_key="tushare", dataset_key=r["dataset"], db_name="stocks", record_count=r["count"],
            )
            for r in results
        ]

    scheduler_manager.register_task("fund_flow", fund_flow_task)

    # ------------------------------------------------------------------
    # 宏观数据（直接 import，替代 subprocess）
    # ------------------------------------------------------------------
    from scripts.fetch_advanced_data import run_macro_data

    def macro_task():
        results = run_macro_data()
        return [
            DatasetTelemetry(
                source_key="tushare", dataset_key=r["dataset"], db_name="stocks", record_count=r["count"],
            )
            for r in results
        ]

    scheduler_manager.register_task("macro_data", macro_task)

    # ------------------------------------------------------------------
    # Polymarket 预测市场
    # ------------------------------------------------------------------
    if POLYMARKET_ENABLED:
        from src.data_ingestion.polymarket.fetcher import PolymarketFetcher
        from src.data_ingestion.polymarket.models import PolymarketBase
        from api.db import news_engine, news_session
        from src.database.repositories.news import NewsRepository

        pm_Session = news_session
        pm_repo = NewsRepository(pm_Session)
        PolymarketBase.metadata.create_all(news_engine)

        pm_fetcher = PolymarketFetcher(pm_Session, pm_repo)

        def polymarket_task():
            pm_fetcher.run()

        scheduler_manager.register_task("polymarket_fetch", polymarket_task)

    # ------------------------------------------------------------------
    # 筛选器日快照（带 telemetry）
    # ------------------------------------------------------------------
    from src.strategies.snapshot_service import run_daily_snapshots

    def screen_snapshot_task():
        result = run_daily_snapshots()
        rps_count = result.get("rps", 0) if isinstance(result, dict) else 0
        potential_count = result.get("potential", 0) if isinstance(result, dict) else 0
        return [
            DatasetTelemetry(source_key="derived", dataset_key="screen_rps", db_name="stocks", record_count=rps_count),
            DatasetTelemetry(source_key="derived", dataset_key="screen_potential", db_name="stocks", record_count=potential_count),
        ]

    scheduler_manager.register_task("screen_snapshot", screen_snapshot_task)

    # ------------------------------------------------------------------
    # 盘中快照轮询
    # ------------------------------------------------------------------
    from fetchers.intraday import fetch_intraday_snapshot

    def intraday_task():
        # 仅在交易时段执行 (9:25-15:05 留余量)
        from datetime import datetime as _dt
        now = _dt.now()
        hour_min = now.hour * 100 + now.minute
        weekday = now.weekday()
        if weekday >= 5 or hour_min < 925 or hour_min > 1505:
            logger.debug("非交易时段，跳过盘中快照")
            return
        fetch_intraday_snapshot()

    scheduler_manager.register_task("intraday_snapshot", intraday_task)

    # ------------------------------------------------------------------
    # 综合评分（带 telemetry）
    # ------------------------------------------------------------------
    from src.scoring.engine import compute_all_scores
    from fetchers.trading_calendar import get_recent_trading_days

    def composite_score_task():
        # 使用最近交易日作为评分日期
        recent = get_recent_trading_days(1)
        if not recent:
            logger.warning("无可用交易日，跳过综合评分")
            return [
                DatasetTelemetry(
                    source_key="derived", dataset_key="composite_score",
                    db_name="stocks", record_count=0, status="empty",
                )
            ]

        trade_date = recent[0].replace("-", "")
        summary = compute_all_scores(trade_date)

        return [
            DatasetTelemetry(
                source_key="derived",
                dataset_key="composite_score",
                db_name="stocks",
                record_count=summary.scored,
                latest_record_date=trade_date,
                status="ok" if summary.scored > 0 else "empty",
            )
        ]

    scheduler_manager.register_task("composite_score", composite_score_task)

    logger.info("✅ 默认任务注册完成")
