"""
Unified exception hierarchy for AI_news.

AppError
├── DataFetchError   — data ingestion failures
├── AnalysisError    — analysis module failures
├── DatabaseError    — database operation failures
└── ConfigError      — configuration/env errors
"""


class AppError(Exception):
    """Base exception for all AI_news errors."""
    pass


class DataFetchError(AppError):
    """Raised when data fetching fails (Tushare, AkShare, RSS, etc.)."""

    def __init__(self, message: str, *, source: str = "", code: str = ""):
        super().__init__(message)
        self.source = source
        self.code = code


class AnalysisError(AppError):
    """Raised when an analysis module fails."""

    def __init__(self, message: str, *, module: str = ""):
        super().__init__(message)
        self.module = module


class DatabaseError(AppError):
    """Raised when a database operation fails."""

    def __init__(self, message: str, *, table: str = ""):
        super().__init__(message)
        self.table = table


class ConfigError(AppError):
    """Raised when required configuration is missing or invalid."""
    pass
