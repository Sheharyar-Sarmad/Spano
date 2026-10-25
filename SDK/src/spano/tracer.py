"""Trace and span context managers."""

from __future__ import annotations

from contextvars import ContextVar, Token
from typing import Any, TYPE_CHECKING

from .events import Span, SpanKind, SpanStatus

if TYPE_CHECKING:
    from .client import Spano

_active_trace: ContextVar[Trace | None] = ContextVar("spano_active_trace", default=None)
_active_span: ContextVar[Span | None] = ContextVar("spano_active_span", default=None)


class SpanScope:
    """Context manager that automatically finishes a span and captures exceptions."""

    def __init__(self, trace: "Trace", span: Span) -> None:
        self.trace = trace
        self.span = span
        self._token: Token[Span | None] | None = None

    def __enter__(self) -> Span:
        if self.trace.finished:
            raise RuntimeError("Cannot create a span in a finished trace")
        self._token = _active_span.set(self.span)
        return self.span

    def __exit__(self, exc_type: Any, exc: BaseException | None, tb: Any) -> bool:
        try:
            if self.span.end_time is None:
                if exc is not None:
                    self.span.finish(
                        status=SpanStatus.ERROR,
                        error={"type": exc_type.__name__ if exc_type else type(exc).__name__, "message": str(exc)[:1000]},
                    )
                else:
                    self.span.finish()
        finally:
            if self._token is not None:
                _active_span.reset(self._token)
        return False


class Trace:
    """A trace owns a root span and all child spans created inside it."""

    def __init__(self, client: "Spano", name: str, attributes: dict[str, Any] | None = None) -> None:
        self.client = client
        self.root_span = Span(name=name, kind=SpanKind.AGENT, attributes=dict(attributes or {}))
        self.spans: list[Span] = [self.root_span]
        self.finished = False
        self._trace_token: Token[Trace | None] | None = None
        self._span_token: Token[Span | None] | None = None

    @property
    def trace_id(self) -> str:
        return self.root_span.trace_id

    def __enter__(self) -> "Trace":
        if self.finished:
            raise RuntimeError("Trace has already finished")
        self._trace_token = _active_trace.set(self)
        self._span_token = _active_span.set(self.root_span)
        return self

    def start_span(
        self,
        name: str,
        *,
        kind: SpanKind = SpanKind.INTERNAL,
        attributes: dict[str, Any] | None = None,
    ) -> SpanScope:
        if self.finished:
            raise RuntimeError("Cannot create a span in a finished trace")
        active_trace = _active_trace.get()
        active_span = _active_span.get()
        parent = active_span if active_trace is self and active_span is not None else self.root_span
        span = Span(
            name=name,
            kind=kind,
            trace_id=self.trace_id,
            parent_span_id=parent.span_id,
            attributes=dict(attributes or {}),
        )
        self.spans.append(span)
        return SpanScope(self, span)

    def set_attributes(self, attributes: dict[str, Any] | None = None, **kwargs: Any) -> None:
        self.root_span.set_attributes(attributes, **kwargs)

    def __exit__(self, exc_type: Any, exc: BaseException | None, tb: Any) -> bool:
        try:
            if not self.finished:
                if exc is not None:
                    self.root_span.finish(
                        status=SpanStatus.ERROR,
                        error={"type": exc_type.__name__ if exc_type else type(exc).__name__, "message": str(exc)[:1000]},
                    )
                else:
                    self.root_span.finish()
                self.finished = True
                self.client._enqueue(self.spans)
        finally:
            if self._span_token is not None:
                _active_span.reset(self._span_token)
            if self._trace_token is not None:
                _active_trace.reset(self._trace_token)
        return False
