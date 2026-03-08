"""
AI News Dashboard - FastAPI 服务
接收 TrendRadar Webhook 推送，清洗、存储并展示热点新闻
"""

import csv
import hmac
import io
import json
import logging
import os
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path
from typing import Optional

logging.basicConfig(
    format='%(asctime)s %(levelname)s [%(name)s] %(message)s',
    level=os.getenv("LOG_LEVEL", "INFO"),
)
logger = logging.getLogger(__name__)

from dotenv import load_dotenv
load_dotenv(Path(__file__).parent.parent / ".env")

from fastapi import FastAPI, Request, Depends, HTTPException, Header, Query
from fastapi import Path as FastPath
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import HTMLResponse, StreamingResponse
from starlette.responses import JSONResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, field_validator
import bleach
import markdown

# 导入响应模型
from api.schemas import (
    HealthResponse,
    NewsListResponse,
    WebhookResponse,
    StockListResponse,
    StockProfileResponse,
    StockDailyResponse,
    MarketOverviewResponse,
    ScreenRpsResponse,
    ScreenPotentialResponse,
)

# 导入数据清洗模块
from src.analysis.cleaner import clean_raw_data, clean_and_export, CleanedData

# 导入 AI 分析模块
from src.ai_engine.llm_analyzer import AIAnalyzer, create_analyzer_from_env

# 导入调度器模块
from api.scheduler import scheduler_manager, register_default_tasks

# 导入数据库引擎和仓储层
from src.database.repositories.news import NewsRepository
from src.database.repositories.stock import StockRepository
from src.database.repositories.polymarket import PolymarketRepository
from src.data_ingestion.polymarket.models import PolymarketBase
from api.db import news_engine, news_session, stock_engine, stock_session

# ============================================================
# 配置
# ============================================================

TEMPLATES_DIR = Path(__file__).parent / "templates"

# 数据库引擎和仓储层（使用共享单例）
_engine = news_engine
_Session = news_session
_repo = NewsRepository(_Session)
_polymarket_repo = PolymarketRepository(_Session)

# Stocks database (read-only)
_stock_engine = stock_engine
_stock_Session = stock_session
_stock_repo = StockRepository(_stock_Session)

app = FastAPI(title="AI News Dashboard", version="2.0.0")

# ---- 请求体大小限制中间件 (P1 安全修复) ----
class LimitRequestSizeMiddleware:
    """拒绝超过 max_size 字节的请求体，防止大载荷攻击。"""

    def __init__(self, app, max_size: int = 10 * 1024 * 1024):
        self.app = app
        self.max_size = max_size

    async def __call__(self, scope, receive, send):
        if scope["type"] == "http":
            headers = dict(scope.get("headers", []))
            content_length = headers.get(b"content-length")
            if content_length and int(content_length) > self.max_size:
                response = JSONResponse(
                    status_code=413,
                    content={"detail": "Request body too large"},
                )
                await response(scope, receive, send)
                return
        await self.app(scope, receive, send)

app.add_middleware(LimitRequestSizeMiddleware)

from fastapi.middleware.cors import CORSMiddleware

_cors_origins = os.getenv("CORS_ORIGINS", "http://localhost:3000,http://frontend:3000").split(",")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in _cors_origins if o.strip()],
    allow_methods=["*"],
    allow_headers=["*"],
)

from api.middleware import register_exception_handlers
register_exception_handlers(app)

templates = Jinja2Templates(directory=str(TEMPLATES_DIR))
SCHEDULER_STATUS = {"running": False, "error": None}

MARKDOWN_ALLOWED_TAGS = [
    "p",
    "br",
    "ul",
    "ol",
    "li",
    "strong",
    "em",
    "code",
    "pre",
    "blockquote",
    "a",
]
MARKDOWN_ALLOWED_ATTRIBUTES = {
    "a": ["href", "title", "target", "rel"],
}


def _raise_internal_error(message: str, exc: Exception) -> None:
    raise HTTPException(status_code=500, detail=message) from exc


def render_markdown_safely(content: str) -> str:
    """Markdown 渲染后进行白名单清洗，避免 XSS。"""
    raw_html = markdown.markdown(content or "")
    return bleach.clean(
        raw_html,
        tags=MARKDOWN_ALLOWED_TAGS,
        attributes=MARKDOWN_ALLOWED_ATTRIBUTES,
        strip=True,
    )


# ============================================================
# 数据模型
# ============================================================

class WebhookPayload(BaseModel):
    """TrendRadar Webhook 数据格式"""
    title: str
    content: str


class NewsRecord(BaseModel):
    """新闻记录"""
    id: int
    title: str
    content: str
    content_html: str
    received_at: str
    cleaned_data: Optional[dict] = None
    source: Optional[str] = None


class CleanRequest(BaseModel):
    """清洗请求"""
    title: str
    content: str


class AnalyzeRequest(BaseModel):
    """AI 分析请求"""
    date: str  # 格式: 2026-01-16
    limit: int = 20  # 最多分析条数

    @field_validator('date')
    @classmethod
    def validate_date_format(cls, v: str) -> str:
        import re
        if not re.match(r'^\d{4}-\d{2}-\d{2}$', v):
            raise ValueError('日期格式必须为 YYYY-MM-DD')
        return v


# ============================================================
# 数据库操作 (通过 NewsRepository)
# ============================================================

def save_news(title: str, content: str, cleaned: Optional[CleanedData] = None) -> int:
    """保存新闻到数据库"""
    cleaned_json = None
    hotspots = None
    keywords = None

    if cleaned:
        cleaned_json = json.dumps(cleaned.to_dict(), ensure_ascii=False)
        hotspots = ",".join(cleaned.hotspots)
        keywords = ",".join(cleaned.keywords)

    return _repo.insert_news(
        title=title,
        content=content,
        cleaned_data=cleaned_json,
        hotspots=hotspots,
        keywords=keywords,
    )


def get_recent_news(limit: int = 50) -> list[NewsRecord]:
    """获取最近的新闻"""
    items = _repo.get_news_list(limit=limit)
    records = []
    for item in items:
        records.append(NewsRecord(
            id=item["id"],
            title=item["title"],
            content=item["content"],
            content_html=render_markdown_safely(item["content"]),
            received_at=item["received_at"] or "",
            cleaned_data=item["cleaned_data"],
            source=item.get("source"),
        ))
    return records


def get_news_count() -> int:
    """获取新闻总数"""
    return _repo.get_news_count()


def get_all_hotspots() -> list[tuple[str, int]]:
    """获取所有热点统计"""
    return _repo.get_hotspot_stats(top_n=20)


def get_news_by_date(date: str, limit: int = 20) -> list[dict]:
    """根据日期查询新闻数据（用于 AI 分析）"""
    return _repo.get_news_by_date(date, limit=limit)


def save_analysis_result(date: str, input_count: int, result: dict) -> int:
    """保存 AI 分析结果"""
    return _repo.insert_analysis(
        date=date,
        input_count=input_count,
        analysis_summary=result.get("analysis_summary", ""),
        opportunities=result.get("opportunities", []),
    )


# ============================================================
# API 鉴权 (P0 安全修复)
# ============================================================

DASHBOARD_API_KEY = os.getenv("DASHBOARD_API_KEY", "")
WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET", "").strip()
APP_ENV = os.getenv("ENV", os.getenv("APP_ENV", "dev")).strip().lower()
API_KEY_REQUIRED = (
    os.getenv("API_KEY_REQUIRED", "").strip().lower() in {"1", "true", "yes"}
    or APP_ENV in {"prod", "production", "staging"}
)

async def verify_api_key(x_api_key: str = Header(None, alias="X-API-Key")):
    """验证 API Key"""
    if not DASHBOARD_API_KEY:
        if API_KEY_REQUIRED:
            raise HTTPException(
                status_code=500,
                detail="Server misconfigured: DASHBOARD_API_KEY is required",
            )
        # 未配置 Key 时跳过验证（开发模式）
        return None
    if not hmac.compare_digest(x_api_key or "", DASHBOARD_API_KEY):
        raise HTTPException(status_code=401, detail="Invalid or missing API Key")
    return x_api_key


async def verify_webhook_token(x_webhook_token: str = Header(None, alias="X-Webhook-Token")):
    """可选 Webhook Token 校验。"""
    if not WEBHOOK_SECRET:
        return None
    if not hmac.compare_digest(x_webhook_token or "", WEBHOOK_SECRET):
        raise HTTPException(status_code=401, detail="Invalid webhook token")
    return x_webhook_token


# 任务执行锁 (P2 防重入) — 用 Lock 保证原子性
import asyncio
_task_lock = asyncio.Lock()


# ============================================================
# 生命周期
# ============================================================

async def startup():
    """启动时初始化数据库和调度器"""
    if API_KEY_REQUIRED and not DASHBOARD_API_KEY:
        raise RuntimeError("DASHBOARD_API_KEY is required in the current environment")

    _repo.create_tables(_engine)
    PolymarketBase.metadata.create_all(_engine)
    from config.settings import NEWS_DATABASE_URL as _news_db_url
    logger.info("数据库初始化完成: %s", _news_db_url)
    logger.info("数据清洗模块已加载")
    
    # 检查 AI 分析是否可用
    analyzer = create_analyzer_from_env()
    if analyzer:
        logger.info("AI 分析模块已启用")
    else:
        logger.warning("AI 分析模块未启用 (设置 AI_ANALYSIS_ENABLED=true)")
    
    # 启动调度器
    try:
        register_default_tasks()
        scheduler_manager.start()
        SCHEDULER_STATUS["running"] = True
        SCHEDULER_STATUS["error"] = None
        logger.info("调度器已启动")
    except Exception as e:
        SCHEDULER_STATUS["running"] = False
        SCHEDULER_STATUS["error"] = str(e)
        logger.warning("调度器启动失败: %s", e)
        if os.getenv("SCHEDULER_REQUIRED", "false").lower() == "true":
            raise


async def shutdown():
    """关闭时停止调度器"""
    scheduler_manager.stop()
    SCHEDULER_STATUS["running"] = False
    logger.info("调度器已停止")


@asynccontextmanager
async def app_lifespan(_: FastAPI):
    await startup()
    try:
        yield
    finally:
        await shutdown()


app.router.lifespan_context = app_lifespan


# ============================================================
# API 路由
# ============================================================


@app.post("/webhook/receive", response_model=WebhookResponse)
async def receive_webhook(
    payload: WebhookPayload,
    _: None = Depends(verify_webhook_token),
):
    """
    接收 TrendRadar Webhook 推送
    自动进行数据清洗
    """
    # 清洗数据
    cleaned = clean_raw_data(payload.title, payload.content)
    
    # 保存到数据库
    news_id = save_news(payload.title, payload.content, cleaned)
    received_at = datetime.now().isoformat()
    
    logger.info("收到推送 #%d: %s...", news_id, payload.title[:50])
    logger.info("   热点: %s", cleaned.hotspots)
    logger.info("   关键词: %s", cleaned.keywords[:5])
    
    return {
        "status": "ok",
        "message": f"Received at {received_at}",
        "news_id": news_id,
        "hotspots": cleaned.hotspots,
        "keywords": cleaned.keywords
    }


@app.post("/api/clean")
async def clean_data(request: CleanRequest, _: None = Depends(verify_api_key)):
    """
    清洗数据 API
    
    输入：原始数据
    输出：结构化事实清单
    """
    cleaned = clean_raw_data(request.title, request.content)
    return cleaned.to_dict()


@app.post("/api/analyze")
async def analyze_opportunities(request: AnalyzeRequest, _: None = Depends(verify_api_key)):
    """
    AI 热点分析 API
    
    输入：日期和条数限制
    输出：机会分析报告 JSON
    """
    # 创建分析器
    analyzer = create_analyzer_from_env()
    if not analyzer:
        raise HTTPException(
            status_code=503,
            detail="AI 分析未启用，请在 .env 中设置 AI_ANALYSIS_ENABLED=true 和 AI_API_KEY",
        )

    # 查询数据
    news_items = await run_in_threadpool(get_news_by_date, request.date, request.limit)
    if not news_items:
        raise HTTPException(
            status_code=404,
            detail=f"未找到 {request.date} 的新闻数据，请确认该日期有数据",
        )
    
    # 调用 AI 分析 (async + await)
    result = await analyzer.analyze_opportunities(news_items)
    
    # 保存结果
    if "error" not in result:
        analysis_id = await run_in_threadpool(
            save_analysis_result,
            request.date,
            len(news_items),
            result,
        )
        result["analysis_id"] = analysis_id
        result["input_count"] = len(news_items)
        result["date"] = request.date
    
    return result


@app.get("/api/analysis/{analysis_id}")
async def get_analysis(analysis_id: int):
    """获取历史分析结果"""
    row = await run_in_threadpool(_repo.get_analysis_by_id, analysis_id)
    if not row:
        raise HTTPException(status_code=404, detail="分析结果不存在")
    return row


@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    """首页 - 展示最近热点"""
    news_list = await run_in_threadpool(get_recent_news, 50)
    total_count = await run_in_threadpool(get_news_count)
    hotspots = await run_in_threadpool(get_all_hotspots)
    
    return templates.TemplateResponse(
        "index.html",
        {
            "request": request,
            "news_list": news_list,
            "total_count": total_count,
            "hotspots": hotspots,
            "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }
    )


@app.get("/console", response_class=HTMLResponse)
async def console(request: Request):
    """测试控制台"""
    return templates.TemplateResponse("console.html", {"request": request})


@app.get("/api/news", response_model=NewsListResponse)
async def api_news(limit: int = Query(50, ge=1, le=500)):
    """API - 获取新闻列表（含清洗数据）"""
    news_list = await run_in_threadpool(get_recent_news, limit)
    total = await run_in_threadpool(get_news_count)
    return {
        "total": total,
        "data": [n.model_dump() for n in news_list]
    }


@app.get("/api/hotspots")
async def api_hotspots():
    """API - 获取热点关键词统计"""
    hotspots = await run_in_threadpool(get_all_hotspots)
    return {
        "total": len(hotspots),
        "data": [{"keyword": k, "count": c} for k, c in hotspots]
    }


@app.get("/api/facts/{news_id}")
async def api_facts(news_id: int):
    """API - 获取单条新闻的结构化事实"""
    row = await run_in_threadpool(_repo.get_news_by_id, news_id)
    if not row or not row.get("cleaned_data"):
        raise HTTPException(status_code=404, detail="Not found or not cleaned")
    return row["cleaned_data"]


@app.get("/health", response_model=HealthResponse)
async def health():
    """健康检查 - 返回 503 当任何组件异常"""
    db_ok = True
    db_error = None
    try:
        db_ok = await run_in_threadpool(_repo.health_check)
    except Exception as e:
        db_ok = False
        db_error = str(e)

    scheduler_ok = bool(SCHEDULER_STATUS["running"])
    all_healthy = db_ok and scheduler_ok
    status = "healthy" if all_healthy else "degraded"
    payload = {
        "status": status,
        "db": {"ok": db_ok, "error": db_error},
        "scheduler": {
            "running": scheduler_ok,
            "error": SCHEDULER_STATUS["error"],
        },
        "version": "2.0.0",
    }
    return JSONResponse(content=payload, status_code=200 if all_healthy else 503)


# ============================================================
# RSS 订阅 API
# ============================================================

@app.post("/api/rss/fetch")
async def fetch_rss(_: None = Depends(verify_api_key)):
    """抓取 RSS 订阅源"""
    try:
        from rss_fetcher import run_rss_fetch, DEFAULT_FEEDS
        items = await run_rss_fetch(save=True)
        return {
            "status": "ok",
            "fetched": len(items),
            "sources": [f["name"] for f in DEFAULT_FEEDS]
        }
    except Exception as e:
        _raise_internal_error("rss fetch failed", e)


@app.get("/api/rss")
async def get_rss(limit: int = Query(50, ge=1, le=500)):
    """获取 RSS 条目列表"""
    try:
        from rss_fetcher import get_recent_rss
        items = await run_in_threadpool(get_recent_rss, limit)
        return {"total": len(items), "data": items}
    except Exception as e:
        _raise_internal_error("rss list failed", e)


@app.post("/api/rss/analyze")
async def analyze_rss_sentiment(
    limit: int = Query(10, ge=1, le=500),
    _: None = Depends(verify_api_key),
):
    """对 RSS 新闻进行情感分析"""
    try:
        from src.ai_engine.sentiment import analyze_pending_news, get_sentiment_stats
        result = await analyze_pending_news(_repo, limit=limit)
        stats = get_sentiment_stats(_repo)
        return {"analysis": result, "stats": stats}
    except Exception as e:
        _raise_internal_error("rss analysis failed", e)


@app.get("/api/rss/sentiment_stats")
async def get_rss_sentiment_stats():
    """获取情感分析统计"""
    try:
        from src.ai_engine.sentiment import get_sentiment_stats
        return await run_in_threadpool(get_sentiment_stats, _repo)
    except Exception as e:
        _raise_internal_error("rss sentiment stats failed", e)


# ============================================================
# 调度器 API
# ============================================================

@app.get("/api/scheduler/jobs")
async def get_scheduler_jobs(_: None = Depends(verify_api_key)):
    """获取所有调度任务状态"""
    try:
        jobs = scheduler_manager.get_jobs()
        return {
            "running": scheduler_manager._running,
            "jobs": [
                {
                    "id": j.task_id,
                    "name": j.name,
                    "description": j.description,
                    "enabled": j.enabled,
                    "next_run": j.next_run.isoformat() if j.next_run else None,
                    "last_run": j.last_run.isoformat() if j.last_run else None,
                    "last_result": j.last_result,
                    "run_count": j.run_count
                }
                for j in jobs
            ]
        }
    except Exception as e:
        _raise_internal_error("scheduler jobs failed", e)


@app.post("/api/scheduler/trigger/{job_id}")
async def trigger_scheduler_job(job_id: str, _: None = Depends(verify_api_key)):
    """手动触发任务"""
    try:
        result = await scheduler_manager.trigger_job(job_id)
        return {
            "success": result.success,
            "message": result.message,
            "duration": (result.end_time - result.start_time).total_seconds()
        }
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        _raise_internal_error("scheduler trigger failed", e)


@app.post("/api/scheduler/pause/{job_id}")
async def pause_scheduler_job(job_id: str, _: None = Depends(verify_api_key)):
    """暂停任务"""
    success = scheduler_manager.pause_job(job_id)
    if success:
        return {"message": f"任务 {job_id} 已暂停"}
    raise HTTPException(status_code=404, detail=f"任务 {job_id} 不存在")


@app.post("/api/scheduler/resume/{job_id}")
async def resume_scheduler_job(job_id: str, _: None = Depends(verify_api_key)):
    """恢复任务"""
    success = scheduler_manager.resume_job(job_id)
    if success:
        return {"message": f"任务 {job_id} 已恢复"}
    raise HTTPException(status_code=404, detail=f"任务 {job_id} 不存在")


@app.get("/api/scheduler/history/{job_id}")
async def get_scheduler_history(
    job_id: str,
    limit: int = 10,
    _: None = Depends(verify_api_key),
):
    """获取任务执行历史"""
    history = scheduler_manager.get_task_history(job_id, limit)
    return {"job_id": job_id, "history": history}


# ============================================================
# 定时任务 API（避免 SQLite 多进程锁）
# ============================================================

class RunTaskRequest(BaseModel):
    skip_rss: bool = False
    skip_trendradar: bool = False


@app.post("/api/run_task")
async def run_scheduled_task(
    request: RunTaskRequest = RunTaskRequest(),
    _: None = Depends(verify_api_key)
):
    """
    在 Web 进程内执行定时任务，避免 SQLite 锁冲突
    
    流程：RSS 抓取 → 数据加载 → AI 分析 → 存储
    """
    from datetime import datetime

    # 非阻塞获取锁：locked() 检查与 acquire() 之间无 await，
    # 在 asyncio 单线程模型中是原子的（无 yield point）。
    # 若已被占用则立即拒绝，不排队等待。
    if _task_lock.locked():
        raise HTTPException(status_code=409, detail="任务正在执行中，请稍后重试")
    async with _task_lock:
        result = {
            "start_time": datetime.now().isoformat(),
            "steps": []
        }

        # Step 1: 抓取 RSS
        if not request.skip_rss:
            try:
                from rss_fetcher import run_rss_fetch
                items = await run_rss_fetch(save=True)
                result["steps"].append({"step": "rss_fetch", "status": "ok", "count": len(items)})
            except Exception as e:
                result["steps"].append({"step": "rss_fetch", "status": "error", "error": str(e)})

        # Step 2: 加载数据（优先 RSS，然后 news 表）
        items = []
        data_source = None

        try:
            from rss_fetcher import get_recent_rss
            rss_items = get_recent_rss(limit=20)
            if rss_items:
                items = [{"id": r["id"], "title": r["title"], "content": r.get("summary", "")} for r in rss_items]
                data_source = "rss"
        except Exception as e:
            logger.warning("RSS 加载失败: %s", e)

        if not items:
            try:
                news_rows = _repo.get_recent_news_for_task(limit=20)
                if news_rows:
                    items = news_rows
                    data_source = "news"
            except Exception as e:
                logger.warning("News 加载失败: %s", e)

        if not items:
            raise HTTPException(status_code=404, detail="没有可用数据，请先抓取 RSS 或导入新闻")

        result["steps"].append({"step": "load_data", "status": "ok", "source": data_source, "count": len(items)})

        # Step 3: AI 分析
        analyzer = create_analyzer_from_env()
        if not analyzer:
            raise HTTPException(status_code=503, detail="AI 分析器未配置，请设置 AI_ANALYSIS_ENABLED=true")

        try:
            analysis = await analyzer.analyze_opportunities(items)
            if "error" in analysis:
                result["steps"].append({"step": "ai_analyze", "status": "error", "error": analysis["error"]})
                return result
            result["steps"].append({"step": "ai_analyze", "status": "ok"})
        except Exception as e:
            result["steps"].append({"step": "ai_analyze", "status": "error", "error": str(e)})
            return result

        # Step 4: 保存到数据库
        try:
            date = datetime.now().strftime("%Y-%m-%d")
            analysis_id = _repo.insert_analysis(
                date=date,
                input_count=len(items),
                analysis_summary=analysis.get("analysis_summary", ""),
                opportunities=analysis.get("opportunities", []),
            )
            result["steps"].append({"step": "save_db", "status": "ok", "analysis_id": analysis_id})
        except Exception as e:
            result["steps"].append({"step": "save_db", "status": "error", "error": str(e)})

        # 汇总
        result["end_time"] = datetime.now().isoformat()
        result["analysis_summary"] = analysis.get("analysis_summary", "")
        result["opportunities_count"] = len(analysis.get("opportunities", []))

        return result


# ============================================================
# 研报 API
# ============================================================

@app.get("/api/research/reports")
async def get_research_reports(
    stock_code: Optional[str] = Query(None, pattern=r'^\d{6}$'),
    limit: int = Query(20, ge=1, le=500),
):
    """获取研报列表"""
    try:
        from fetchers.research_report import get_latest_reports, get_stock_reports
        
        if stock_code:
            reports = await run_in_threadpool(get_stock_reports, stock_code, limit)
        else:
            reports = await run_in_threadpool(get_latest_reports, limit)
        
        return {"total": len(reports), "data": reports}
    except Exception as e:
        _raise_internal_error("research reports failed", e)


@app.post("/api/research/fetch")
async def fetch_research_reports(
    stock_code: Optional[str] = Query(None, pattern=r'^\d{6}$'),
    limit: int = Query(30, ge=1, le=500),
    _: None = Depends(verify_api_key),
):
    """抓取研报数据"""
    try:
        from fetchers.research_report import fetch_stock_reports, save_reports, fetch_hot_stock_reports
        
        if stock_code:
            reports = await run_in_threadpool(fetch_stock_reports, stock_code)
            saved = await run_in_threadpool(save_reports, reports)
            return {"stock_code": stock_code, "fetched": len(reports), "saved": saved}
        else:
            total = await run_in_threadpool(fetch_hot_stock_reports, limit)
            return {"fetched": total}
    except Exception as e:
        _raise_internal_error("research fetch failed", e)


@app.get("/api/research/stats")
async def get_research_stats():
    """获取研报统计"""
    try:
        from fetchers.research_report import get_rating_stats
        return await run_in_threadpool(get_rating_stats)
    except Exception as e:
        _raise_internal_error("research stats failed", e)


# ============================================================
# 异常检测 API
# ============================================================

@app.get("/api/anomalies")
async def get_anomalies(
    stock_code: Optional[str] = Query(None, pattern=r'^\d{6}$'),
    days: int = Query(7, ge=1, le=365),
    limit: int = Query(50, ge=1, le=500),
):
    """获取技术面异常信号"""
    try:
        from src.analysis.anomaly import get_recent_anomalies, get_stock_anomalies
        
        if stock_code:
            anomalies = await run_in_threadpool(get_stock_anomalies, stock_code, days)
        else:
            anomalies = await run_in_threadpool(get_recent_anomalies, days, limit)
        
        return {"total": len(anomalies), "data": anomalies}
    except Exception as e:
        _raise_internal_error("anomalies query failed", e)


@app.post("/api/anomalies/detect")
async def detect_anomalies(
    stock_code: Optional[str] = Query(None, pattern=r'^\d{6}$'),
    limit: int = Query(50, ge=1, le=500),
    _: None = Depends(verify_api_key),
):
    """运行异常检测"""
    try:
        from src.analysis.anomaly import (
            detect_all_hot_stocks,
            detect_anomalies_for_stock,
            init_anomaly_table,
        )
        
        await run_in_threadpool(init_anomaly_table)
        
        if stock_code:
            result = await run_in_threadpool(detect_anomalies_for_stock, stock_code)
            return {"stock_code": stock_code, "result": result}
        else:
            result = await run_in_threadpool(detect_all_hot_stocks, limit)
            return {"result": result}
    except Exception as e:
        _raise_internal_error("anomalies detect failed", e)


@app.get("/api/anomalies/stats")
async def get_anomaly_stats():
    """获取异常统计"""
    try:
        from src.analysis.anomaly import get_anomaly_stats
        return await run_in_threadpool(get_anomaly_stats)
    except Exception as e:
        _raise_internal_error("anomalies stats failed", e)


# ============================================================
# 数据完整性 API
# ============================================================

@app.get("/api/integrity/check")
async def check_data_integrity():
    """检查数据完整性"""
    try:
        from fetchers.integrity_checker import generate_integrity_report
        return await run_in_threadpool(generate_integrity_report)
    except Exception as e:
        _raise_internal_error("integrity check failed", e)


@app.get("/api/integrity/freshness")
async def check_data_freshness():
    """检查数据新鲜度"""
    try:
        from fetchers.integrity_checker import check_table_freshness
        tables = await run_in_threadpool(check_table_freshness)
        return {"tables": tables}
    except Exception as e:
        _raise_internal_error("freshness check failed", e)


# ============================================================
# 交易日历 API
# ============================================================

@app.get("/api/calendar/is_trading_day")
async def is_trading_day(date: Optional[str] = Query(None, pattern=r'^\d{4}-\d{2}-\d{2}$')):
    """判断是否为交易日"""
    try:
        from fetchers.trading_calendar import (
            get_latest_trading_day,
            is_trading_day as check_trading_day,
        )

        if date is None:
            date = datetime.now().strftime("%Y-%m-%d")

        return {
            "date": date,
            "is_trading_day": check_trading_day(date),
            "latest_trading_day": get_latest_trading_day()
        }
    except Exception as e:
        _raise_internal_error("trading day check failed", e)


# ============================================================
# 筛选器快照 API
# ============================================================


@app.get("/api/screens/rps", response_model=ScreenRpsResponse)
async def get_screen_rps(
    date: Optional[str] = Query(None, pattern=r'^\d{4}-\d{2}-\d{2}$'),
    limit: int = Query(50, ge=1, le=500),
):
    """获取 RPS 强度排名快照"""
    from src.strategies.snapshot_service import ensure_snapshot_tables
    ensure_snapshot_tables()

    from src.database.connection import get_connection
    conn = get_connection()
    try:
        if date:
            row = conn.execute(
                "SELECT snapshot_date, source_trade_date, generated_at FROM screen_rps_snapshot WHERE snapshot_date = ? LIMIT 1",
                (date,)
            ).fetchone()
        else:
            row = conn.execute(
                "SELECT snapshot_date, source_trade_date, generated_at FROM screen_rps_snapshot ORDER BY snapshot_date DESC LIMIT 1"
            ).fetchone()

        if not row:
            return {"snapshot_date": "", "source_trade_date": "", "generated_at": "", "total": 0, "items": []}

        snap_date = row["snapshot_date"] if isinstance(row, dict) else row[0]
        source_date = row["source_trade_date"] if isinstance(row, dict) else row[1]
        gen_at = row["generated_at"] if isinstance(row, dict) else row[2]

        items = conn.execute(
            "SELECT ts_code, stock_name, rps_10, rps_20, rps_50, rps_120, rank FROM screen_rps_snapshot WHERE snapshot_date = ? ORDER BY rank ASC LIMIT ?",
            (snap_date, limit)
        ).fetchall()

        return {
            "snapshot_date": str(snap_date),
            "source_trade_date": str(source_date),
            "generated_at": str(gen_at),
            "total": len(items),
            "items": [dict(r) if isinstance(r, dict) else {
                "ts_code": r[0], "stock_name": r[1],
                "rps_10": r[2], "rps_20": r[3], "rps_50": r[4], "rps_120": r[5],
                "rank": r[6]
            } for r in items]
        }
    finally:
        conn.close()


@app.get("/api/screens/potential", response_model=ScreenPotentialResponse)
async def get_screen_potential(
    date: Optional[str] = Query(None, pattern=r'^\d{4}-\d{2}-\d{2}$'),
    limit: int = Query(20, ge=1, le=200),
):
    """获取多因子潜力股筛选快照"""
    from src.strategies.snapshot_service import ensure_snapshot_tables
    ensure_snapshot_tables()

    from src.database.connection import get_connection
    conn = get_connection()
    try:
        if date:
            row = conn.execute(
                "SELECT snapshot_date, source_trade_date, generated_at FROM screen_potential_snapshot WHERE snapshot_date = ? LIMIT 1",
                (date,)
            ).fetchone()
        else:
            row = conn.execute(
                "SELECT snapshot_date, source_trade_date, generated_at FROM screen_potential_snapshot ORDER BY snapshot_date DESC LIMIT 1"
            ).fetchone()

        if not row:
            return {"snapshot_date": "", "source_trade_date": "", "generated_at": "", "total": 0, "items": []}

        snap_date = row["snapshot_date"] if isinstance(row, dict) else row[0]
        source_date = row["source_trade_date"] if isinstance(row, dict) else row[1]
        gen_at = row["generated_at"] if isinstance(row, dict) else row[2]

        items = conn.execute(
            "SELECT ts_code, stock_name, total_score, capital_score, trading_score, fundamental_score, technical_score, signals, rank FROM screen_potential_snapshot WHERE snapshot_date = ? ORDER BY rank ASC LIMIT ?",
            (snap_date, limit)
        ).fetchall()

        return {
            "snapshot_date": str(snap_date),
            "source_trade_date": str(source_date),
            "generated_at": str(gen_at),
            "total": len(items),
            "items": [dict(r) if isinstance(r, dict) else {
                "ts_code": r[0], "stock_name": r[1],
                "total_score": r[2], "capital_score": r[3],
                "trading_score": r[4], "fundamental_score": r[5],
                "technical_score": r[6], "signals": r[7], "rank": r[8]
            } for r in items]
        }
    finally:
        conn.close()


# ============================================================
# 筛选器 CSV 导出 API
# ============================================================


@app.get("/api/stocks/{ts_code}/daily/export")
async def export_stock_daily_csv(
    ts_code: str = FastPath(..., pattern=r'^\d{6}\.(SH|SZ|BJ)$'),
    start_date: Optional[str] = Query(None, pattern=r'^\d{4}-\d{2}-\d{2}$'),
    end_date: Optional[str] = Query(None, pattern=r'^\d{4}-\d{2}-\d{2}$'),
):
    """导出个股日线数据为 CSV"""
    from src.database.connection import get_connection
    conn = get_connection()
    try:
        sql = "SELECT trade_date, open, high, low, close, vol, amount, pct_chg FROM ts_daily WHERE ts_code = ?"
        params: list = [ts_code]
        if start_date:
            sql += " AND trade_date >= ?"
            params.append(start_date.replace("-", ""))
        if end_date:
            sql += " AND trade_date <= ?"
            params.append(end_date.replace("-", ""))
        sql += " ORDER BY trade_date ASC"
        rows = conn.execute(sql, params).fetchall()
    finally:
        conn.close()

    output = io.StringIO()
    output.write("\ufeff")  # UTF-8 BOM
    writer = csv.writer(output)
    writer.writerow(["trade_date", "open", "high", "low", "close", "vol", "amount", "pct_chg"])
    for r in rows:
        writer.writerow([r[0], r[1], r[2], r[3], r[4], r[5], r[6], r[7]])

    output.seek(0)
    filename = f"{ts_code}_daily.csv"
    return StreamingResponse(
        output,
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@app.get("/api/screens/rps/export")
async def export_screen_rps_csv():
    """导出 RPS 强度排名最新快照为 CSV"""
    from src.database.connection import get_connection
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT snapshot_date FROM screen_rps_snapshot ORDER BY snapshot_date DESC LIMIT 1"
        ).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="无 RPS 快照数据")
        snap_date = row[0]
        rows = conn.execute(
            "SELECT rank, ts_code, stock_name, rps_10, rps_20, rps_50, rps_120 FROM screen_rps_snapshot WHERE snapshot_date = ? ORDER BY rank ASC",
            (snap_date,)
        ).fetchall()
    finally:
        conn.close()

    output = io.StringIO()
    output.write("\ufeff")  # UTF-8 BOM
    writer = csv.writer(output)
    writer.writerow(["rank", "ts_code", "stock_name", "rps_10", "rps_20", "rps_50", "rps_120"])
    for r in rows:
        writer.writerow([r[0], r[1], r[2], r[3], r[4], r[5], r[6]])

    output.seek(0)
    filename = f"rps_{snap_date}.csv"
    return StreamingResponse(
        output,
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@app.get("/api/screens/potential/export")
async def export_screen_potential_csv():
    """导出多因子潜力股最新快照为 CSV"""
    from src.database.connection import get_connection
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT snapshot_date FROM screen_potential_snapshot ORDER BY snapshot_date DESC LIMIT 1"
        ).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="无潜力股快照数据")
        snap_date = row[0]
        rows = conn.execute(
            "SELECT rank, ts_code, stock_name, total_score, capital_score, trading_score, fundamental_score, technical_score, signals FROM screen_potential_snapshot WHERE snapshot_date = ? ORDER BY rank ASC",
            (snap_date,)
        ).fetchall()
    finally:
        conn.close()

    output = io.StringIO()
    output.write("\ufeff")  # UTF-8 BOM
    writer = csv.writer(output)
    writer.writerow(["rank", "ts_code", "stock_name", "total_score", "capital_score", "trading_score", "fundamental_score", "technical_score", "signals"])
    for r in rows:
        writer.writerow([r[0], r[1], r[2], r[3], r[4], r[5], r[6], r[7], r[8]])

    output.seek(0)
    filename = f"potential_{snap_date}.csv"
    return StreamingResponse(
        output,
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@app.get("/api/analysis/full/{ts_code}")
async def get_full_analysis(ts_code: str = FastPath(..., pattern=r'^\d{6}(\.[A-Z]{2})?$')):
    """获取个股完整分析快照（缓存 + 懒生成）"""
    from src.utils.cache import cache
    from src.strategies.snapshot_service import get_analysis_snapshot, ensure_snapshot_tables
    ensure_snapshot_tables()

    cache_key = f"analysis_full:{ts_code}"
    cached = cache.get(cache_key)
    if cached:
        return cached

    result = get_analysis_snapshot(ts_code)
    if result is None:
        raise HTTPException(status_code=404, detail=f"无法生成 {ts_code} 的分析数据")

    cache.set(cache_key, result)
    return result


# ============================================================
# 统一搜索 API
# ============================================================


@app.get("/api/search")
async def unified_search(
    q: str = Query(..., min_length=1, max_length=50),
    type: str = Query("all", pattern=r'^(stocks|news|all)$'),
    limit: int = Query(20, ge=1, le=100),
):
    """统一搜索：股票代码/名称 + 新闻标题/摘要"""
    from src.utils.search import search
    return await run_in_threadpool(search, q, type, limit)


# ============================================================
# 盘中数据 API
# ============================================================


@app.get("/api/intraday/{ts_code}")
async def get_intraday(ts_code: str = FastPath(..., pattern=r'^\d{6}\.[A-Z]{2}$')):
    """获取个股最新盘中快照"""
    from src.database.connection import get_connection
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT ts_code, price, change_pct, volume, amount, update_time "
            "FROM intraday_snapshot WHERE ts_code = ? "
            "ORDER BY update_time DESC LIMIT 1",
            (ts_code,),
        ).fetchone()

        if not row:
            return {
                "ts_code": ts_code, "price": None, "change_pct": None,
                "volume": None, "amount": None, "update_time": None,
            }

        return {
            "ts_code": row[0], "price": row[1], "change_pct": row[2],
            "volume": row[3], "amount": row[4], "update_time": str(row[5]),
        }
    except Exception:
        # 表可能不存在（首次运行前）
        return {
            "ts_code": ts_code, "price": None, "change_pct": None,
            "volume": None, "amount": None, "update_time": None,
        }
    finally:
        conn.close()


# ============================================================
# 股票行情 API (stocks.db — 只读)
# ============================================================


@app.get("/api/stocks", response_model=StockListResponse)
async def get_stocks(
    search: Optional[str] = None,
    industry: Optional[str] = None,
    market: Optional[str] = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    sort_by: Optional[str] = Query(None),
    sort_order: str = Query("asc"),
):
    """股票列表（搜索/行业/市场/分页/排序）"""
    return await run_in_threadpool(
        _stock_repo.get_stock_list, search, industry, market, page, page_size,
        sort_by, sort_order,
    )


@app.get("/api/stocks/industries")
async def get_stock_industries():
    """行业列表（用于筛选下拉）"""
    industries = await run_in_threadpool(_stock_repo.get_industries)
    return {"data": industries}


@app.get("/api/stocks/{ts_code}/profile", response_model=StockProfileResponse)
async def get_stock_profile(ts_code: str = FastPath(..., pattern=r'^\d{6}\.(SH|SZ|BJ)$')):
    """个股档案 + 估值指标"""
    profile = await run_in_threadpool(_stock_repo.get_stock_profile, ts_code)
    if not profile:
        raise HTTPException(status_code=404, detail=f"Stock {ts_code} not found")
    return profile


@app.get("/api/stocks/{ts_code}/valuation-history")
async def get_valuation_history(
    ts_code: str = FastPath(..., pattern=r'^\d{6}\.(SH|SZ|BJ)$'),
    limit: int = Query(250, ge=1, le=1000),
):
    """个股估值历史"""
    data = await run_in_threadpool(
        _stock_repo.get_valuation_history, ts_code, limit
    )
    return {"data": data}


@app.get("/api/stocks/{ts_code}/daily", response_model=StockDailyResponse)
async def get_stock_daily(
    ts_code: str = FastPath(..., pattern=r'^\d{6}\.(SH|SZ|BJ)$'),
    start_date: Optional[str] = Query(None, pattern=r'^\d{4}-\d{2}-\d{2}$'),
    end_date: Optional[str] = Query(None, pattern=r'^\d{4}-\d{2}-\d{2}$'),
    limit: int = Query(250, ge=1, le=1000),
):
    """个股日线行情"""
    data = await run_in_threadpool(
        _stock_repo.get_stock_daily, ts_code, start_date, end_date, limit
    )
    return {"data": data}


@app.get("/api/market/overview", response_model=MarketOverviewResponse)
async def get_market_overview(trade_date: Optional[str] = Query(None, pattern=r'^\d{4}-\d{2}-\d{2}$')):
    """大盘指数概览"""
    data = await run_in_threadpool(_stock_repo.get_market_overview, trade_date)
    return {"data": data}


@app.get("/api/money-flow")
async def get_money_flow(
    trade_date: Optional[str] = Query(None, pattern=r'^\d{4}-\d{2}-\d{2}$'),
    flow_type: Optional[str] = None,
    ts_code: Optional[str] = Query(None, pattern=r'^\d{6}\.(SH|SZ|BJ)$'),
    limit: int = Query(50, ge=1, le=200),
):
    """资金流向"""
    data = await run_in_threadpool(
        _stock_repo.get_money_flow, trade_date, flow_type, ts_code, limit
    )
    return {"data": data}


@app.get("/api/dragon-tiger")
async def get_dragon_tiger(
    trade_date: Optional[str] = Query(None, pattern=r'^\d{4}-\d{2}-\d{2}$'),
    ts_code: Optional[str] = Query(None, pattern=r'^\d{6}\.(SH|SZ|BJ)$'),
    limit: int = Query(50, ge=1, le=200),
):
    """龙虎榜"""
    data = await run_in_threadpool(
        _stock_repo.get_dragon_tiger, trade_date, ts_code, limit
    )
    return {"data": data}


@app.get("/api/sectors")
async def get_sectors(
    block_type: Optional[str] = None,
    trade_date: Optional[str] = Query(None, pattern=r'^\d{4}-\d{2}-\d{2}$'),
    limit: int = Query(50, ge=1, le=200),
):
    """板块行情"""
    data = await run_in_threadpool(
        _stock_repo.get_sectors, block_type, trade_date, limit
    )
    return {"data": data}


# ============================================================
# Polymarket 预测市场 API
# ============================================================


@app.get("/api/polymarket/markets")
async def get_polymarket_markets(limit: int = Query(50, ge=1, le=200)):
    """获取活跃预测市场列表"""
    markets = await run_in_threadpool(_polymarket_repo.get_active_markets, limit)
    return {"total": len(markets), "data": markets}


@app.get("/api/polymarket/markets/{condition_id}")
async def get_polymarket_market_detail(condition_id: str):
    """获取单个预测市场详情"""
    detail = await run_in_threadpool(_polymarket_repo.get_market_detail, condition_id)
    if not detail:
        raise HTTPException(status_code=404, detail=f"Market {condition_id} not found")
    return detail


@app.get("/api/polymarket/markets/{condition_id}/history")
async def get_polymarket_history(
    condition_id: str,
    limit: int = Query(100, ge=1, le=500),
):
    """获取预测市场价格历史"""
    history = await run_in_threadpool(
        _polymarket_repo.get_price_history, condition_id, limit
    )
    return {"total": len(history), "data": history}


# ============================================================
# AI 用量统计 API
# ============================================================

@app.get("/api/ai/usage")
async def get_ai_usage(_: None = Depends(verify_api_key)):
    """获取 AI API 用量统计"""
    from src.ai_engine.gemini_client import get_usage_stats
    return get_usage_stats()


@app.post("/api/polymarket/translate")
async def trigger_polymarket_translation(
    limit: int = Query(200, ge=1, le=1000),
    _: None = Depends(verify_api_key),
):
    """手动触发预测市场问题翻译"""
    from src.data_ingestion.polymarket.translator import MarketTranslator
    translator = MarketTranslator()
    count = await run_in_threadpool(translator.translate_markets, _Session, limit)
    return {"translated": count}
