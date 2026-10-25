# Spano Python SDK

Spano is a lightweight Python SDK for recording AI-agent traces and exporting spans to an HTTP ingestion endpoint. This early release provides manual tracing; automatic LangChain/LangGraph instrumentation is not included yet.

## Install for local development

```bash
uv sync
uv run pytest
```

## Quick start

```python
from spano import Spano, SpanKind

client = Spano(
    api_key="your-api-key",
    endpoint="http://localhost:8000",
    # The server must implement POST /api/v1/traces.
)

try:
    with client.start_trace("research-agent", attributes={"environment": "dev"}) as trace:
        with trace.start_span("search-web", kind=SpanKind.TOOL, attributes={"tool": "web-search"}):
            # Run your tool here.
            pass
finally:
    client.close()
```

## Ingestion contract

Spano sends `POST {endpoint}/api/v1/traces` with `Authorization: Bearer <api-key>` and a JSON body shaped like:

```json
{"spans": [{"trace_id": "...", "span_id": "...", "parent_span_id": null, "name": "research-agent", "kind": "agent", "start_time": "...", "end_time": "...", "duration_ms": 1.2, "status": "ok", "attributes": {}, "error": null}]}
```

The endpoint should return a 2xx response. If the response body is non-empty, it must be a JSON object; an optional integer `accepted` field should equal the number of spans in the request. This SDK does not include the backend or persist traces itself.

## Buffering and failures

- `flush()` exports buffered spans and returns `True` on success, `False` when best-effort delivery fails.
- `close()` attempts to flush and is safe to call more than once.
- Buffer capacity is bounded. If it fills, the oldest span is dropped and `client.dropped_spans` increments.
- Transport errors are logged and passed to `on_error` if supplied. Set `strict_transport=True` to raise transport errors from `flush()`/`close()`.
- Application exceptions are recorded in spans and re-raised; Spano does not swallow them.
- Input/output prompts and responses are not captured automatically. Only metadata explicitly provided by the developer is recorded. Do not add credentials or sensitive values to attributes.

## Configuration

`Spano(api_key, endpoint="http://localhost:8000", timeout=5.0, ingestion_path="/api/v1/traces", max_buffer_size=1000, batch_size=100, strict_transport=False, logger=None, on_error=None)`

This package is an early alpha. Review behavior and endpoint compatibility before production use.
