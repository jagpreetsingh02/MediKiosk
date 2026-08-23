"""Structured logging. One configuration call, used by the app and by the eval runner."""
from __future__ import annotations

import logging
import sys

import structlog

from app.core.config import settings

_configured = False


def configure_logging(level: str | None = None) -> None:
    global _configured
    if _configured:
        return
    logging.basicConfig(
        format="%(message)s", stream=sys.stdout, level=getattr(logging, (level or settings.log_level).upper(), logging.INFO)
    )
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            structlog.dev.ConsoleRenderer(colors=sys.stdout.isatty()),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(
            getattr(logging, (level or settings.log_level).upper(), logging.INFO)
        ),
        cache_logger_on_first_use=True,
    )
    _configured = True


def get_logger(name: str) -> structlog.stdlib.BoundLogger:
    configure_logging()
    return structlog.get_logger(name)  # type: ignore[no-any-return]
