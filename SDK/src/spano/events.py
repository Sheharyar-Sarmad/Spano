"""Core tracing events and span models for the Spano SDK."""

from __future__ import annotations

import json
import math
import secrets
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import StrEnum
from typing import Any


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def new_trace_id() -> str:
    """Generate a 32-character hexadecimal trace ID."""
    return secrets.token_hex(16)


def new_span_id() -> str:
    """Generate a 16-character hexadecimal span ID."""
    return secrets.token_hex(8)


class SpanKind(StrEnum):
    AGENT = "agent"
    LLM = "llm"
    TOOL = "tool"
    CHAIN = "chain"
    INTERNAL = "internal"


class SpanStatus(StrEnum):
    UNSET = "unset"
    OK = "ok"
    ERROR = "error"


def validate_attributes(attributes: dict[str, Any]) -> None:
    if not isinstance(attributes, dict):
        raise ValueError("attributes must be a dictionary")
    if any(not isinstance(key, str) for key in attributes):
        raise ValueError("attribute keys must be strings")
    try:
        json.dumps(attributes, allow_nan=False)
    except (TypeError, ValueError) as exc:
        raise ValueError("attributes must contain JSON-serializable values") from exc


@dataclass(slots=True)
class Span:
    """Represents one unit of work within an execution trace."""

    name: str
    kind: SpanKind = SpanKind.INTERNAL
    trace_id: str = field(default_factory=new_trace_id)
    span_id: str = field(default_factory=new_span_id)
    parent_span_id: str | None = None
    start_time: datetime = field(default_factory=utc_now)
    end_time: datetime | None = None
    status: SpanStatus = SpanStatus.UNSET
    attributes: dict[str, Any] = field(default_factory=dict)
    error: dict[str, str] | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.name, str) or not self.name.strip():
            raise ValueError("Span name cannot be empty")
        if not isinstance(self.kind, SpanKind):
            raise ValueError("kind must be a SpanKind")
        self._validate_id(self.trace_id, 32, "trace_id")
        self._validate_id(self.span_id, 16, "span_id")
        if self.parent_span_id is not None:
            self._validate_id(self.parent_span_id, 16, "parent_span_id")
            if self.parent_span_id == self.span_id:
                raise ValueError("A span cannot be its own parent")
        self._validate_timestamp(self.start_time, "start_time")
        if self.end_time is not None:
            self._validate_timestamp(self.end_time, "end_time")
            if self.end_time < self.start_time:
                raise ValueError("end_time cannot precede start_time")
        validate_attributes(self.attributes)

    @staticmethod
    def _validate_id(value: str, length: int, name: str) -> None:
        if (
            not isinstance(value, str)
            or len(value) != length
            or any(char not in "0123456789abcdef" for char in value)
            or set(value) == {"0"}
        ):
            raise ValueError(f"{name} must be {length} non-zero hexadecimal characters")

    @staticmethod
    def _validate_timestamp(value: datetime, name: str) -> None:
        if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
            raise ValueError(f"{name} must be timezone-aware")

    @property
    def duration_ms(self) -> float | None:
        if self.end_time is None:
            return None
        return (self.end_time - self.start_time).total_seconds() * 1000

    def set_attributes(self, attributes: dict[str, Any] | None = None, **kwargs: Any) -> None:
        """Add JSON-serializable metadata to this span."""
        updates = dict(attributes or {})
        updates.update(kwargs)
        validate_attributes(updates)
        self.attributes.update(updates)
        validate_attributes(self.attributes)

    def finish(
        self,
        status: SpanStatus = SpanStatus.OK,
        error: dict[str, str] | None = None,
    ) -> None:
        if self.end_time is not None:
            raise RuntimeError("Span has already finished")
        if not isinstance(status, SpanStatus):
            raise ValueError("status must be a SpanStatus")
        if status == SpanStatus.ERROR and error is None:
            raise ValueError("An error span must include error details")
        if status != SpanStatus.ERROR and error is not None:
            raise ValueError("Error details require ERROR status")
        self.end_time = utc_now()
        self.status = status
        self.error = error

    def to_dict(self) -> dict[str, Any]:
        return {
            "trace_id": self.trace_id,
            "span_id": self.span_id,
            "parent_span_id": self.parent_span_id,
            "name": self.name,
            "kind": self.kind.value,
            "start_time": self.start_time.isoformat(),
            "end_time": self.end_time.isoformat() if self.end_time is not None else None,
            "duration_ms": self.duration_ms,
            "status": self.status.value,
            "attributes": self.attributes,
            "error": self.error,
        }
