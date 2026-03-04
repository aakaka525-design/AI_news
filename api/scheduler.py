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
}

# Fill Polymarket config from centralized settings
from config.settings import POLYMARKET_ENABLED, POLYMARKET_FETCH_INTERVAL
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
            timezone="Asia/Shanghai"
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
        
        try:
            func = self._task_funcs.get(task_id)
            if not func:
                raise ValueError(f"任务 {task_id} 未注册执行函数")
            
            logger.info(f"▶️ 开始执行任务: {task_id}")
            
            # 执行任务（支持同步和异步函数）
            if asyncio.iscoroutinefunction(func):
                await func()
            else:
                await asyncio.get_event_loop().run_in_executor(None, func)
            
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
            
            # 只保留最近 100 条记录
            if len(self._task_history[task_id]) > 100:
                self._task_history[task_id] = self._task_history[task_id][-100:]
        
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
        """停止调度器"""
        if self._running:
            self.scheduler.shutdown(wait=False)
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
    
    # 添加项目根目录到路径
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    if project_root not in sys.path:
        sys.path.insert(0, project_root)
    
    # 注册 RSS 抓取任务
    from rss_fetcher import run_rss_fetch
    async def rss_task():
        await run_rss_fetch(include_rsshub=True)
    scheduler_manager.register_task("rss_fetch", rss_task)
    
    # 注册 AI 分析任务
    from src.ai_engine.llm_analyzer import create_analyzer_from_env
    from src.ai_engine.sentiment import analyze_pending_news
    from rss_fetcher import get_recent_rss
    from api.db import news_session as _ai_session
    from src.database.repositories.news import NewsRepository as _AINewsRepo

    _ai_repo = _AINewsRepo(_ai_session)

    async def ai_task():
        # 1. 热点分析
        analyzer = create_analyzer_from_env()
        if not analyzer:
            raise RuntimeError("AI 分析器未启用")
        items = get_recent_rss(limit=20)
        if not items:
            logger.info("无可分析 RSS 数据，跳过本轮 AI 分析")
            return
        payload = [
            {"id": r.get("id"), "title": r.get("title", ""), "content": r.get("summary", "")}
            for r in items
        ]
        analysis = await analyzer.analyze_opportunities(payload)

        # 保存热点分析结果
        if "error" not in analysis:
            from datetime import datetime as _dt
            _ai_repo.insert_analysis(
                date=_dt.now().strftime("%Y-%m-%d"),
                input_count=len(payload),
                analysis_summary=analysis.get("analysis_summary", ""),
                opportunities=analysis.get("opportunities", []),
            )
            logger.info(f"AI 热点分析完成，已保存 {len(analysis.get('opportunities', []))} 个机会")
        else:
            logger.warning(f"AI 热点分析返回错误: {analysis.get('error')}")

        # 2. 情感分析
        sentiment_result = await analyze_pending_news(_ai_repo)
        logger.info(f"情感分析: {sentiment_result}")

    scheduler_manager.register_task("ai_analysis", ai_task)
    
    # 注册金融数据任务（同步函数）
    def indicators_task():
        import subprocess
        subprocess.run(["python3", f"{project_root}/scripts/fetch_history.py"], check=True)
    scheduler_manager.register_task("stock_indicators", indicators_task)
    
    def fund_flow_task():
        import subprocess
        subprocess.run(["python3", f"{project_root}/scripts/fetch_main_money.py"], check=True)
    scheduler_manager.register_task("fund_flow", fund_flow_task)
    
    def macro_task():
        import subprocess
        subprocess.run(["python3", f"{project_root}/scripts/fetch_advanced_data.py"], check=True)
    scheduler_manager.register_task("macro_data", macro_task)
    
    # 注册 Polymarket 预测市场任务
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

    logger.info("✅ 默认任务注册完成")
