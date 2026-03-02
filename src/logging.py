"""
Structured logging for AI_news.

Usage:
    from src.logging import get_logger
    logger = get_logger(__name__)
    logger.info("fetching data", stock="000001.SZ")
"""

import structlog


def setup_logging(json_output: bool = True) -> None:
    """Configure structlog processors."""
    processors = [
        structlog.stdlib.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
    ]
    if json_output:
        processors.append(structlog.processors.JSONRenderer())
    else:
        processors.append(structlog.dev.ConsoleRenderer())

    structlog.configure(
        processors=processors,
        wrapper_class=structlog.make_filtering_bound_logger(0),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=False,
    )


def get_logger(module: str) -> structlog.BoundLogger:
    """Get a logger bound with module name."""
    return structlog.get_logger(module=module)


# Default setup (JSON in production, console in dev)
setup_logging(json_output=True)
