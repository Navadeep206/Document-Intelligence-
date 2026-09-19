"""Structured logging configuration and request tracing middleware."""

import json
import logging
import sys
import time
from typing import Any, Callable

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from app.core.config import get_settings

SENSITIVE_KEYS = {
    "password",
    "token",
    "access_token",
    "refresh_token",
    "secret",
    "authorization",
    "cookie",
    "api_key",
    "apikey",
    "file",
    "content",
}


class SensitiveDataFilter(logging.Filter):
    """Filter to prevent accidental logging of sensitive credentials and content."""

    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.msg, dict):
            record.msg = self._sanitize_dict(record.msg)
        elif isinstance(record.msg, str):
            for key in SENSITIVE_KEYS:
                if f"{key}=" in record.msg.lower() or f'"{key}":' in record.msg.lower():
                    record.msg = "[SANITIZED_MESSAGE_CONTAINING_SENSITIVE_KEYS]"
                    break
        return True

    def _sanitize_dict(self, data: dict[str, Any]) -> dict[str, Any]:
        sanitized = {}
        for k, v in data.items():
            if any(sens in k.lower() for sens in SENSITIVE_KEYS):
                sanitized[k] = "[REDACTED]"
            elif isinstance(v, dict):
                sanitized[k] = self._sanitize_dict(v)
            else:
                sanitized[k] = v
        return sanitized


class StructuredLogFormatter(logging.Formatter):
    """Format logs as structured JSON records for production observability."""

    def format(self, record: logging.LogRecord) -> str:
        log_obj: dict[str, Any] = {
            "timestamp": self.formatTime(record, self.datefmt),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }

        if hasattr(record, "request_id"):
            log_obj["request_id"] = record.request_id
        if hasattr(record, "method"):
            log_obj["method"] = record.method
        if hasattr(record, "path"):
            log_obj["path"] = record.path
        if hasattr(record, "status_code"):
            log_obj["status_code"] = record.status_code
        if hasattr(record, "duration_ms"):
            log_obj["duration_ms"] = record.duration_ms

        if record.exc_info and not record.exc_text:
            record.exc_text = self.formatException(record.exc_info)
        if record.exc_text:
            log_obj["exception"] = record.exc_text

        return json.dumps(log_obj)


def setup_logging() -> logging.Logger:
    """Initialize structured application logging based on configuration."""
    settings = get_settings()
    log_level = getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO)

    root_logger = logging.getLogger()
    root_logger.setLevel(log_level)

    # Remove default handlers to avoid duplication
    for handler in list(root_logger.handlers):
        root_logger.removeHandler(handler)

    handler = logging.StreamHandler(sys.stdout)
    handler.setLevel(log_level)
    handler.addFilter(SensitiveDataFilter())

    if settings.APP_ENV.lower() == "production":
        formatter = StructuredLogFormatter(datefmt="%Y-%m-%dT%H:%M:%S%z")
    else:
        formatter = logging.Formatter(
            fmt="%(asctime)s [%(levelname)s] [%(name)s] %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )

    handler.setFormatter(formatter)
    root_logger.addHandler(handler)

    # Silence overly verbose external loggers
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)

    logger = logging.getLogger(settings.APP_NAME)
    logger.info("Structured logging initialized at level %s", settings.LOG_LEVEL)
    return logger


logger = logging.getLogger("document-intelligence-service")


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """Middleware to log every HTTP request method, path, response status, and duration."""

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        start_time = time.perf_counter()
        method = request.method
        path = request.url.path

        try:
            response = await call_next(request)
            duration_ms = round((time.perf_counter() - start_time) * 1000, 2)

            logger.info(
                "%s %s -> %s (%sms)",
                method,
                path,
                response.status_code,
                duration_ms,
                extra={
                    "method": method,
                    "path": path,
                    "status_code": response.status_code,
                    "duration_ms": duration_ms,
                },
            )
            return response
        except Exception as exc:
            duration_ms = round((time.perf_counter() - start_time) * 1000, 2)
            logger.exception(
                "Unhandled error processing %s %s after %sms: %s",
                method,
                path,
                duration_ms,
                str(exc),
                extra={
                    "method": method,
                    "path": path,
                    "duration_ms": duration_ms,
                },
            )
            raise
