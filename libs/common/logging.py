"""Structured logging with correlation IDs.

Uses structlog with JSON output in production and colored console in dev.
Every log line carries a correlation_id for request tracing across services.
"""

from __future__ import annotations

import uuid
from contextvars import ContextVar

import structlog
from dpdp_core.pii.log_redactor import pii_redaction_processor

correlation_id_var: ContextVar[str] = ContextVar("correlation_id", default="")


def get_correlation_id() -> str:
    cid = correlation_id_var.get()
    if not cid:
        cid = str(uuid.uuid4())
        correlation_id_var.set(cid)
    return cid


def new_correlation_id() -> str:
    cid = str(uuid.uuid4())
    correlation_id_var.set(cid)
    return cid


def add_correlation_id(
    logger: structlog.types.WrappedLogger,
    method_name: str,
    event_dict: structlog.types.EventDict,
) -> structlog.types.EventDict:
    event_dict["correlation_id"] = get_correlation_id()
    return event_dict


def configure_logging(*, json_output: bool = True, log_level: str = "INFO") -> None:
    """Configure structlog for the application.

    Args:
        json_output: True for JSON lines (prod), False for colored console (dev).
        log_level: Standard log level string.
    """
    import logging

    shared_processors: list[structlog.types.Processor] = [
        structlog.contextvars.merge_contextvars,
        add_correlation_id,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.stdlib.add_logger_name,
    ]

    if json_output:
        renderer: structlog.types.Processor = structlog.processors.JSONRenderer()
    else:
        renderer = structlog.dev.ConsoleRenderer()

    structlog.configure(
        processors=[
            *shared_processors,
            pii_redaction_processor,
            structlog.processors.EventRenamer("msg"),
            renderer,
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )

    logging.basicConfig(format="%(message)s", level=getattr(logging, log_level.upper()))
