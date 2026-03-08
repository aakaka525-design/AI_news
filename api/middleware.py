"""Unified exception handling middleware for FastAPI."""

import re
import time

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from src.exceptions import AnalysisError, AppError, DatabaseError, DataFetchError
from src.logging import get_logger

logger = get_logger("api.middleware")

# 敏感关键词正则（用于日志脱敏）
_SENSITIVE_PATTERN = re.compile(
    r"(password|passwd|token|secret|api_key|apikey|authorization|credential)"
    r"\s*[:=]\s*\S+",
    re.IGNORECASE,
)


def _sanitize_error(msg: str) -> str:
    """过滤异常消息中的敏感信息"""
    return _SENSITIVE_PATTERN.sub(r"\1=***", msg)


class PerfMiddleware(BaseHTTPMiddleware):
    """Log request duration and add X-Response-Time header."""

    SLOW_THRESHOLD = 0.5  # seconds

    async def dispatch(self, request: Request, call_next):
        start = time.perf_counter()
        response = await call_next(request)
        elapsed = time.perf_counter() - start

        response.headers["X-Response-Time"] = f"{elapsed:.3f}s"

        log_kw = dict(method=request.method, path=request.url.path, elapsed=f"{elapsed:.3f}s")
        if elapsed > self.SLOW_THRESHOLD:
            logger.warning("slow_request", **log_kw)
        else:
            logger.info("request", **log_kw)

        return response


class CatchAllMiddleware:
    """Raw ASGI middleware that catches any unhandled exception and returns a 500 JSON response."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        try:
            await self.app(scope, receive, send)
        except Exception as exc:
            sanitized = _sanitize_error(str(exc))
            logger.error("unexpected_error", error=sanitized, type=type(exc).__name__)
            response = JSONResponse(
                status_code=500,
                content={"error": "Internal server error", "type": type(exc).__name__},
            )
            await response(scope, receive, send)


def register_exception_handlers(app: FastAPI) -> None:
    """Register exception handlers on the FastAPI app."""

    # Performance logging (innermost = runs first).
    app.add_middleware(PerfMiddleware)

    # Catch-all middleware for unhandled exceptions.
    app.add_middleware(CatchAllMiddleware)

    @app.exception_handler(DataFetchError)
    async def data_fetch_handler(request: Request, exc: DataFetchError):
        logger.error("data_fetch_error", error=_sanitize_error(str(exc)), source=exc.source, code=exc.code)
        return JSONResponse(
            status_code=502,
            content={
                "error": str(exc),
                "type": "DataFetchError",
                "source": exc.source,
                "code": exc.code,
            },
        )

    @app.exception_handler(DatabaseError)
    async def database_handler(request: Request, exc: DatabaseError):
        logger.error("database_error", error=_sanitize_error(str(exc)), table=exc.table)
        return JSONResponse(
            status_code=503,
            content={"error": str(exc), "type": "DatabaseError", "table": exc.table},
        )

    @app.exception_handler(AnalysisError)
    async def analysis_handler(request: Request, exc: AnalysisError):
        logger.error("analysis_error", error=_sanitize_error(str(exc)), module=exc.module)
        return JSONResponse(
            status_code=500,
            content={"error": str(exc), "type": "AnalysisError", "module": exc.module},
        )

    @app.exception_handler(AppError)
    async def app_error_handler(request: Request, exc: AppError):
        logger.error("app_error", error=_sanitize_error(str(exc)))
        return JSONResponse(
            status_code=400,
            content={"error": str(exc), "type": "AppError"},
        )
