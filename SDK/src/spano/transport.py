"""HTTP transport for Spano telemetry, implemented with the standard library."""

from __future__ import annotations

import json
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from typing import Any

from .exceptions import SpanoTransportError


class HTTPExporter:
    def __init__(self, endpoint: str, api_key: str, timeout: float, ingestion_path: str) -> None:
        self.url = endpoint + ingestion_path
        self.api_key = api_key
        self.timeout = timeout

    def export(self, spans: list[dict[str, Any]]) -> None:
        if not spans:
            return
        body = json.dumps({"spans": spans}, allow_nan=False).encode("utf-8")
        request = Request(
            self.url,
            data=body,
            method="POST",
            headers={
                "Content-Type": "application/json",
                "Accept": "application/json",
                "Authorization": f"Bearer {self.api_key}",
                "User-Agent": "spano-python-sdk/0.1.0",
            },
        )
        try:
            with urlopen(request, timeout=self.timeout) as response:
                status = response.status
                response_body = response.read()
        except HTTPError as exc:
            raise SpanoTransportError(f"Telemetry endpoint returned HTTP {exc.code}") from exc
        except (URLError, TimeoutError, OSError) as exc:
            raise SpanoTransportError(f"Unable to send telemetry: {exc}") from exc

        if not 200 <= status < 300:
            raise SpanoTransportError(f"Telemetry endpoint returned HTTP {status}")
        if response_body:
            try:
                decoded = json.loads(response_body.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                raise SpanoTransportError("Telemetry endpoint returned invalid JSON") from exc
            if not isinstance(decoded, dict):
                raise SpanoTransportError("Telemetry endpoint response must be a JSON object")
            accepted = decoded.get("accepted")
            if accepted is not None and (not isinstance(accepted, int) or accepted != len(spans)):
                raise SpanoTransportError("Telemetry endpoint accepted count did not match batch size")
