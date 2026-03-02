"""Database repositories — data-access layer for the news dashboard."""

from src.database.repositories.news import NewsRepository
from src.database.repositories.report import ReportRepository

__all__ = ["NewsRepository", "ReportRepository"]
