"""Unified exception handling middleware for FastAPI."""
import json

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from src.exceptions import AppError, DataFetchError, AnalysisError, DatabaseError
from src.logging import get_logger

logger = get_logger("api.middleware")


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
            logger.error("unexpected_error", error=str(exc), type=type(exc).__name__)
            response = JSONResponse(
                status_code=500,
                content={"error": "Internal server error", "type": type(exc).__name__},
            )
            await response(scope, receive, send)


def register_exception_handlers(app: FastAPI) -> None:
    """Register exception handlers on the FastAPI app."""

    # Catch-all middleware for unhandled exceptions.
    app.add_middleware(CatchAllMiddleware)

    @app.exception_handler(DataFetchError)
    async def data_fetch_handler(request: Request, exc: DataFetchError):
        logger.error("data_fetch_error", error=str(exc), source=exc.source, code=exc.code)
        return JSONResponse(
            status_code=502,
            content={"error": str(exc), "type": "DataFetchError", "source": exc.source, "code": exc.code},
        )

    @app.exception_handler(DatabaseError)
    async def database_handler(request: Request, exc: DatabaseError):
        logger.error("database_error", error=str(exc), table=exc.table)
        return JSONResponse(
            status_code=503,
            content={"error": str(exc), "type": "DatabaseError", "table": exc.table},
        )

    @app.exception_handler(AnalysisError)
    async def analysis_handler(request: Request, exc: AnalysisError):
        logger.error("analysis_error", error=str(exc), module=exc.module)
        return JSONResponse(
            status_code=500,
            content={"error": str(exc), "type": "AnalysisError", "module": exc.module},
        )

    @app.exception_handler(AppError)
    async def app_error_handler(request: Request, exc: AppError):
        logger.error("app_error", error=str(exc))
        return JSONResponse(
            status_code=400,
            content={"error": str(exc), "type": "AppError"},
        )
