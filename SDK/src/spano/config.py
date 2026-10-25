"""Configuration for the Spano SDK."""

from dataclasses import dataclass
import math
from urllib.parse import urlsplit


@dataclass(frozen=True, slots=True)
class SpanoConfig:
    api_key: str
    endpoint: str = "http://localhost:8000"
    timeout: float = 5.0
    ingestion_path: str = "/api/v1/traces"
    max_buffer_size: int = 1000
    batch_size: int = 100
    strict_transport: bool = False

    def __post_init__(self) -> None:
        if not isinstance(self.api_key, str) or not self.api_key.strip():
            raise ValueError("api_key cannot be empty")
        if not isinstance(self.endpoint, str):
            raise ValueError("endpoint must be a string")
        parsed = urlsplit(self.endpoint)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError("endpoint must be an absolute HTTP or HTTPS URL")
        if parsed.username or parsed.password:
            raise ValueError("endpoint must not contain embedded credentials")
        if parsed.query or parsed.fragment:
            raise ValueError("endpoint must not contain a query or fragment")
        if not math.isfinite(self.timeout) or self.timeout <= 0:
            raise ValueError("timeout must be a finite number greater than zero")
        if not isinstance(self.ingestion_path, str) or not self.ingestion_path.startswith("/"):
            raise ValueError("ingestion_path must start with '/'")
        if self.max_buffer_size < 1:
            raise ValueError("max_buffer_size must be at least 1")
        if self.batch_size < 1:
            raise ValueError("batch_size must be at least 1")
        object.__setattr__(self, "endpoint", self.endpoint.rstrip("/"))
        object.__setattr__(self, "ingestion_path", "/" + self.ingestion_path.strip("/"))
