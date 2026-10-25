import json
from unittest.mock import patch

import pytest

from spano import Spano, SpanoConfig, SpanKind, SpanStatus, SpanoTransportError


class FakeResponse:
    status = 200

    def __init__(self, body: bytes = b'{"accepted": 2}') -> None:
        self.body = body

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self) -> bytes:
        return self.body


def test_client_initializes() -> None:
    client = Spano(api_key="test-key", endpoint="http://localhost:8000/")
    assert client.config.endpoint == "http://localhost:8000"
    assert not client.closed


def test_empty_api_key_is_rejected() -> None:
    with pytest.raises(ValueError, match="api_key"):
        Spano(api_key="  ")


def test_invalid_endpoint_is_rejected() -> None:
    with pytest.raises(ValueError, match="endpoint"):
        Spano(api_key="test-key", endpoint="localhost:8000")


def test_config_is_immutable() -> None:
    config = SpanoConfig(api_key="test-key")
    with pytest.raises(AttributeError):
        config.timeout = 10.0  # type: ignore[misc]


def test_nested_spans_share_trace_and_parent_ids() -> None:
    client = Spano(api_key="test-key")
    with patch.object(client._exporter, "export") as export:
        with client.start_trace("agent.run") as trace:
            with trace.start_span("tool.search", kind=SpanKind.TOOL):
                with trace.start_span("http.request") as child:
                    child.set_attributes(status_code=200)
        assert client.flush() is True
        assert export.call_count == 1
        spans = export.call_args.args[0]
        assert len(spans) == 3
        assert len({span["trace_id"] for span in spans}) == 1
        assert spans[1]["parent_span_id"] == spans[0]["span_id"]
        assert spans[2]["parent_span_id"] == spans[1]["span_id"]
        assert spans[0]["status"] == "ok"
        assert spans[2]["attributes"]["status_code"] == 200


def test_exceptions_are_recorded_and_propagated() -> None:
    client = Spano(api_key="test-key")
    with patch.object(client._exporter, "export") as export:
        with pytest.raises(ValueError, match="application failure"):
            with client.start_trace("agent.run") as trace:
                with trace.start_span("tool.fail"):
                    raise ValueError("application failure")
        assert client.flush() is True
        spans = export.call_args.args[0]
        assert spans[1]["status"] == "error"
        assert spans[1]["error"]["type"] == "ValueError"
        assert spans[0]["status"] == "error"


def test_flush_sends_bearer_token_and_json_payload() -> None:
    client = Spano(api_key="secret", batch_size=1)
    with patch("spano.transport.urlopen", return_value=FakeResponse(b'{"accepted": 2}')) as mocked:
        with client.start_trace("agent"):
            pass
        request = mocked.call_args.args[0]
        assert request.get_header("Authorization") == "Bearer secret"
        payload = json.loads(request.data.decode())
        assert len(payload["spans"]) == 1


def test_transport_failure_is_nonfatal_by_default_and_reported() -> None:
    errors: list[Exception] = []
    client = Spano(api_key="test-key", on_error=errors.append)
    with patch.object(client._exporter, "export", side_effect=SpanoTransportError("offline")):
        with client.start_trace("agent"):
            pass
        assert client.flush() is False
        assert len(errors) == 1
        assert client._buffer


def test_strict_transport_raises() -> None:
    client = Spano(api_key="test-key", strict_transport=True)
    with patch.object(client._exporter, "export", side_effect=SpanoTransportError("offline")):
        with client.start_trace("agent"):
            pass
        with pytest.raises(SpanoTransportError):
            client.flush()


def test_close_flushes_and_is_idempotent() -> None:
    client = Spano(api_key="test-key")
    with patch.object(client._exporter, "export") as export:
        with client.start_trace("agent"):
            pass
        client.close()
        client.close()
        assert client.closed
        assert export.call_count == 1
    with pytest.raises(RuntimeError, match="closed"):
        client.start_trace("too-late")


def test_buffer_is_bounded() -> None:
    client = Spano(api_key="test-key", max_buffer_size=1, batch_size=100)
    with patch.object(client._exporter, "export"):
        with client.start_trace("first"):
            pass
        with client.start_trace("second"):
            pass
        assert len(client._buffer) == 1
        assert client.dropped_spans == 1
