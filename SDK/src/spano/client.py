"""Public Spano client."""

from __future__ import annotations

import logging
from threading import RLock
from typing import Any, Callable

from .config import SpanoConfig
from .events import Span
from .exceptions import SpanoTransportError
from .tracer import Trace
from .transport import HTTPExporter

TelemetryErrorCallback = Callable[[Exception], None]


class Spano:
    """Client entry point for Spano tracing and telemetry export.

    Telemetry delivery is best-effort by default. Set ``strict_transport=True``
    to re-raise transport errors from ``flush()`` and ``close()``.
    """

    def __init__(
        self,
        api_key: str,
        endpoint: str = "http://localhost:8000",
        timeout: float = 5.0,
        *,
        ingestion_path: str = "/api/v1/traces",
        max_buffer_size: int = 1000,
        batch_size: int = 100,
        strict_transport: bool = False,
        logger: logging.Logger | None = None,
        on_error: TelemetryErrorCallback | None = None,
    ) -> None:
        self.config = SpanoConfig(
            api_key=api_key,
            endpoint=endpoint,
            timeout=timeout,
            ingestion_path=ingestion_path,
            max_buffer_size=max_buffer_size,
            batch_size=batch_size,
            strict_transport=strict_transport,
        )
        self._exporter = HTTPExporter(
            endpoint=self.config.endpoint,
            api_key=self.config.api_key,
            timeout=self.config.timeout,
            ingestion_path=self.config.ingestion_path,
        )
        self._logger = logger or logging.getLogger("spano")
        self._on_error = on_error
        self._buffer: list[dict[str, Any]] = []
        self._lock = RLock()
        self._closed = False
        self.dropped_spans = 0

    @property
    def closed(self) -> bool:
        return self._closed

    def start_trace(self, name: str, *, attributes: dict[str, Any] | None = None) -> Trace:
        if self._closed:
            raise RuntimeError("Spano client is closed")
        return Trace(self, name, attributes)

    def _enqueue(self, spans: list[Span]) -> None:
        with self._lock:
            if self._closed:
                self._report_error(RuntimeError("Cannot enqueue telemetry after client is closed"))
                return
            for span in spans:
                if len(self._buffer) >= self.config.max_buffer_size:
                    self._buffer.pop(0)
                    self.dropped_spans += 1
                self._buffer.append(span.to_dict())
            should_flush = len(self._buffer) >= self.config.batch_size
        if should_flush:
            self.flush()

    def flush(self) -> bool:
        """Send buffered spans. Returns True when the buffer is empty after success."""
        if self._closed and not self._buffer:
            return True
        while True:
            with self._lock:
                if not self._buffer:
                    return True
                batch = self._buffer[: self.config.batch_size]
            try:
                self._exporter.export(batch)
            except Exception as exc:
                self._report_error(exc)
                if self.config.strict_transport:
                    if isinstance(exc, SpanoTransportError):
                        raise
                    raise SpanoTransportError(str(exc)) from exc
                return False
            with self._lock:
                del self._buffer[: len(batch)]

    def close(self) -> None:
        """Flush buffered telemetry and close the client; safe to call repeatedly."""
        if self._closed:
            return
        try:
            self.flush()
        finally:
            self._closed = True

    def _report_error(self, error: Exception) -> None:
        self._logger.warning("Spano telemetry error: %s", error)
        if self._on_error is not None:
            try:
                self._on_error(error)
            except Exception:
                self._logger.exception("Spano error callback failed")

    def __enter__(self) -> "Spano":
        if self._closed:
            raise RuntimeError("Spano client is already closed")
        return self

    def __exit__(self, exc_type: Any, exc: BaseException | None, tb: Any) -> None:
        self.close()
