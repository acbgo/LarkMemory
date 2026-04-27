from __future__ import annotations

import logging
import sys
import time
import uuid
from collections.abc import Callable, Mapping
from pathlib import Path

from starlette.datastructures import Headers
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response


def setup_logging(
    level: str = "INFO",
    log_dir: str | Path = "logs",
    log_file: str = "larkmemory.log",
) -> None:
    resolved_level = getattr(logging, level.upper(), logging.INFO)
    if not isinstance(resolved_level, int):
        resolved_level = logging.INFO

    root_logger = logging.getLogger()
    root_logger.setLevel(resolved_level)

    formatter = logging.Formatter(
        "%(asctime)s %(levelname)s %(name)s %(message)s"
    )
    stream_handler = next(
        (
            handler
            for handler in root_logger.handlers
            if getattr(handler, "_larkmemory_handler", False)
        ),
        None,
    )
    if stream_handler is None:
        stream_handler = logging.StreamHandler(sys.stdout)
        setattr(stream_handler, "_larkmemory_handler", True)
        root_logger.addHandler(stream_handler)
    stream_handler.setLevel(resolved_level)
    stream_handler.setFormatter(formatter)

    log_path = Path(log_dir) / log_file
    log_path.parent.mkdir(parents=True, exist_ok=True)
    file_handler = next(
        (
            handler
            for handler in root_logger.handlers
            if getattr(handler, "_larkmemory_file_handler", False)
        ),
        None,
    )
    if (
        file_handler is not None
        and getattr(file_handler, "baseFilename", None) != str(log_path.resolve())
    ):
        root_logger.removeHandler(file_handler)
        file_handler.close()
        file_handler = None

    if file_handler is None:
        file_handler = logging.FileHandler(log_path, encoding="utf-8")
        setattr(file_handler, "_larkmemory_file_handler", True)
        root_logger.addHandler(file_handler)
    file_handler.setLevel(resolved_level)
    file_handler.setFormatter(formatter)


def get_request_id(headers: Mapping[str, str] | Headers) -> str:
    for name in ("x-request-id", "x-larkmemory-request-id"):
        value = headers.get(name)
        if value is not None and value.strip():
            return value.strip()
    return f"req-{uuid.uuid4().hex[:12]}"


class RequestLogMiddleware(BaseHTTPMiddleware):
    def __init__(self, app: Callable, logger_name: str = "larkmemory.request") -> None:
        super().__init__(app)
        self.logger = logging.getLogger(logger_name)

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        request_id = get_request_id(request.headers)
        started_at = time.perf_counter()
        try:
            response = await call_next(request)
        except Exception:
            duration_ms = (time.perf_counter() - started_at) * 1000
            self.logger.exception(
                "request failed method=%s path=%s duration_ms=%.2f client=%s request_id=%s",
                request.method,
                request.url.path,
                duration_ms,
                request.client.host if request.client else None,
                request_id,
            )
            raise

        duration_ms = (time.perf_counter() - started_at) * 1000
        response.headers["x-request-id"] = request_id
        self.logger.info(
            "request method=%s path=%s status_code=%s duration_ms=%.2f client=%s request_id=%s",
            request.method,
            request.url.path,
            response.status_code,
            duration_ms,
            request.client.host if request.client else None,
            request_id,
        )
        return response
