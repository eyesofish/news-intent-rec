from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from typing import Any, ClassVar

from prometheus_client import (
    CONTENT_TYPE_LATEST,
    Counter,
    Gauge,
    Histogram,
    generate_latest,
    start_http_server,
)

HTTP_REQUESTS = Counter(
    "newsrec_http_requests_total",
    "HTTP requests handled by the API.",
    ("method", "path", "status"),
)
HTTP_REQUEST_DURATION = Histogram(
    "newsrec_http_request_duration_seconds",
    "HTTP request duration.",
    ("method", "path"),
)
CONSUMER_EVENTS = Counter(
    "newsrec_consumer_events_total",
    "Kafka profile-consumer outcomes.",
    ("outcome", "event_type"),
)
CONSUMER_RETRIES = Counter(
    "newsrec_consumer_retries_total",
    "Kafka profile-consumer transient retries.",
)
CONSUMER_LAG = Gauge(
    "newsrec_consumer_lag_messages",
    "Approximate Kafka consumer lag by partition.",
    ("topic", "partition"),
)
OUTBOX_PUBLISHED = Counter(
    "newsrec_outbox_published_total",
    "Outbox messages delivered to Kafka.",
)
OUTBOX_FAILURES = Counter(
    "newsrec_outbox_failures_total",
    "Outbox publish batch failures.",
)
OUTBOX_ROWS = Gauge(
    "newsrec_outbox_rows",
    "Current outbox rows by status.",
    ("status",),
)
SEARCH_RESOLUTIONS = Counter(
    "newsrec_search_resolutions_total",
    "Search query resolution outcomes.",
    ("mode", "source", "outcome"),
)
SEARCH_RETRIEVAL_DURATION = Histogram(
    "newsrec_search_retrieval_duration_seconds",
    "Search query resolution and retrieval duration.",
    ("mode",),
)


class JsonLogFormatter(logging.Formatter):
    _standard_fields: ClassVar[set[str]] = {
        "args",
        "asctime",
        "created",
        "exc_info",
        "exc_text",
        "filename",
        "funcName",
        "levelname",
        "levelno",
        "lineno",
        "message",
        "module",
        "msecs",
        "msg",
        "name",
        "pathname",
        "process",
        "processName",
        "relativeCreated",
        "stack_info",
        "thread",
        "threadName",
    }

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": datetime.now(UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        for key, value in record.__dict__.items():
            if key not in self._standard_fields and not key.startswith("_"):
                payload[key] = value
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=True, default=str)


def configure_logging(level: int = logging.INFO) -> None:
    root = logging.getLogger()
    if any(getattr(handler, "_newsrec_json", False) for handler in root.handlers):
        return
    handler = logging.StreamHandler()
    handler.setFormatter(JsonLogFormatter())
    handler._newsrec_json = True  # type: ignore[attr-defined]
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(level)


def metrics_payload() -> tuple[bytes, str]:
    return generate_latest(), CONTENT_TYPE_LATEST


def start_worker_metrics_server(port: int) -> None:
    start_http_server(port)


def set_outbox_status_counts(counts: dict[str, int]) -> None:
    for status in ("pending", "publishing", "published", "dead"):
        OUTBOX_ROWS.labels(status=status).set(counts.get(status, 0))
