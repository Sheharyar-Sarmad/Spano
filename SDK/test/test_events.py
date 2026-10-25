import pytest

from spano import Span, SpanKind, SpanStatus


def test_span_generates_valid_ids() -> None:
    span = Span(name="agent.run")
    assert len(span.trace_id) == 32
    assert len(span.span_id) == 16
    assert span.trace_id != "0" * 32
    assert span.span_id != "0" * 16


def test_span_starts_unfinished() -> None:
    span = Span(name="llm.call", kind=SpanKind.LLM)
    assert span.end_time is None
    assert span.duration_ms is None
    assert span.status == SpanStatus.UNSET


def test_span_finishes_successfully() -> None:
    span = Span(name="tool.search")
    span.finish()
    assert span.end_time is not None
    assert span.duration_ms is not None
    assert span.duration_ms >= 0
    assert span.status == SpanStatus.OK


def test_error_span_requires_details() -> None:
    span = Span(name="llm.call")
    with pytest.raises(ValueError, match="error details"):
        span.finish(status=SpanStatus.ERROR)


def test_span_serializes_to_dict() -> None:
    span = Span(name="agent.run", kind=SpanKind.AGENT)
    data = span.to_dict()
    assert data["name"] == "agent.run"
    assert data["kind"] == "agent"
    assert data["trace_id"] == span.trace_id
    assert data["duration_ms"] is None


def test_attributes_must_be_json_serializable() -> None:
    with pytest.raises(ValueError, match="JSON-serializable"):
        Span(name="bad", attributes={"object": object()})


def test_set_attributes() -> None:
    span = Span(name="agent")
    span.set_attributes(model="gpt-test", token_count=12)
    assert span.attributes == {"model": "gpt-test", "token_count": 12}
