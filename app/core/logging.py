"""Structured logging. One configuration call, used by the app and by the eval runner."""

from __future__ import annotations

import logging
import sys

import structlog

from app.core.config import settings

_configured = False

#: Libraries that log every HTTP request at INFO. `basicConfig` sets the ROOT level, so
#: setting LOG_LEVEL=INFO — the default — turned them all on. With the handwriting model
#: installed, one `make eval` run printed several hundred lines of Hugging Face CDN redirects
#: interleaved with the benchmark table, and the table became unreadable. These are wire-level
#: details of somebody else's client, not events in this system; they belong at DEBUG, and
#: setting LOG_LEVEL=DEBUG still brings them back.
_CHATTY = ("httpx", "httpcore", "urllib3", "huggingface_hub", "transformers", "filelock")


def configure_logging(level: str | None = None) -> None:
    global _configured
    if _configured:
        return
    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=getattr(logging, (level or settings.log_level).upper(), logging.INFO),
    )
    for name in _CHATTY:
        logging.getLogger(name).setLevel(
            logging.DEBUG if (level or settings.log_level).upper() == "DEBUG" else logging.WARNING
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
