"""Declarative profile shared by HTTP-based provider runners and credential verifiers."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Literal

CapabilityProbe = Literal["models_endpoint", "health_only", "static"]
AuthMode = Literal["api_key", "local"]


@dataclass(frozen=True, slots=True)
class ProviderHttpProfile:
    """Declarative description of an OpenAI-compatible HTTP LLM provider.

    Both the runtime adapter (``openai_compatible_runner``) and the credential
    verifier (``provider_auth._verify_openai_compatible_api_key``) consume the
    same profile so URLs, headers and quirks cannot drift between paths.

    ``auth_mode="local"`` skips the API-key requirement so local runtimes
    (llama.cpp's ``llama-server``, ``mlx-openai-server``) can plug into the
    same adapter without forcing operators to invent fake keys.
    """

    provider_id: str
    base_url: str
    chat_path: str = "/v1/chat/completions"
    models_path: str | None = "/v1/models"
    auth_header_name: str = "Authorization"
    auth_header_format: str = "Bearer {api_key}"
    extra_headers: tuple[tuple[str, str], ...] = ()
    capability_probe: CapabilityProbe = "models_endpoint"
    health_path: str = "/"
    first_chunk_timeout_seconds: float = 30.0
    request_timeout_seconds: float = 120.0
    vision_models: frozenset[str] = field(default_factory=frozenset)
    supports_response_format: bool = True
    extra_payload: tuple[tuple[str, object], ...] = ()
    allow_private_base_url: bool = False
    citations_extractor: Callable[[dict], list[str]] | None = None
    auth_mode: AuthMode = "api_key"

    def chat_url(self) -> str:
        return _join(self.base_url, self.chat_path)

    def models_url(self) -> str | None:
        if not self.models_path:
            return None
        return _join(self.base_url, self.models_path)

    def health_url(self) -> str:
        return _join(self.base_url, self.health_path)

    def headers(self, api_key: str) -> dict[str, str]:
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        if self.auth_mode == "api_key":
            headers[self.auth_header_name] = self.auth_header_format.format(api_key=api_key)
        elif api_key:
            # Local mode with an optional bearer (some operators front llama-server with a proxy)
            headers[self.auth_header_name] = self.auth_header_format.format(api_key=api_key)
        for key, value in self.extra_headers:
            headers[key] = value
        return headers


def _join(base: str, path: str) -> str:
    base = base.rstrip("/")
    if not path:
        return base
    if not path.startswith("/"):
        path = "/" + path
    return base + path
