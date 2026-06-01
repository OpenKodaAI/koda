"""Scoped runtime access envelopes for sensitive inspection routes."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any


def _b64url_encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")


def _b64url_decode(value: str) -> bytes:
    padding = "=" * ((4 - len(value) % 4) % 4)
    return base64.urlsafe_b64decode(value + padding)


@dataclass(slots=True)
class RuntimeAccessEnvelope:
    """Signed access scope for sensitive runtime reads."""

    agent_scope: str
    capabilities: tuple[str, ...] = ("read",)
    workspace_scope: tuple[str, ...] = ()
    source_scope: tuple[str, ...] = ()
    sensitive_allowed: bool = False
    issued_at: str = ""
    expires_at: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "agent_scope": self.agent_scope,
            "capabilities": list(self.capabilities),
            "workspace_scope": list(self.workspace_scope),
            "source_scope": list(self.source_scope),
            "sensitive_allowed": self.sensitive_allowed,
            "issued_at": self.issued_at,
            "expires_at": self.expires_at,
        }


class RuntimeAccessService:
    """Issue and validate short-lived runtime access scopes."""

    def __init__(self, secret: str) -> None:
        self._secret = secret.encode("utf-8")

    def issue(
        self,
        *,
        agent_scope: str,
        capabilities: tuple[str, ...] = ("read",),
        workspace_scope: tuple[str, ...] = (),
        source_scope: tuple[str, ...] = (),
        sensitive_allowed: bool = False,
        ttl_seconds: int = 900,
    ) -> tuple[RuntimeAccessEnvelope, str]:
        now = datetime.now(tz=UTC)
        normalized_capabilities = tuple(
            sorted({str(item).strip().lower() for item in capabilities if str(item).strip()})
        ) or ("read",)
        envelope = RuntimeAccessEnvelope(
            agent_scope=str(agent_scope or "").strip().upper(),
            capabilities=normalized_capabilities,
            workspace_scope=tuple(str(item).strip() for item in workspace_scope if str(item).strip()),
            source_scope=tuple(str(item).strip() for item in source_scope if str(item).strip()),
            sensitive_allowed=bool(sensitive_allowed),
            issued_at=now.isoformat(),
            expires_at=(now + timedelta(seconds=max(60, ttl_seconds))).isoformat(),
        )
        payload = json.dumps(envelope.to_dict(), ensure_ascii=True, separators=(",", ":")).encode("utf-8")
        signature = hmac.new(self._secret, payload, hashlib.sha256).digest()
        token = f"{_b64url_encode(payload)}.{_b64url_encode(signature)}"
        return envelope, token

    def authorize(
        self,
        token: str,
        *,
        agent_scope: str,
        sensitive_required: bool = False,
        capability: str | None = None,
    ) -> RuntimeAccessEnvelope | None:
        if not token:
            return None
        try:
            encoded_payload, encoded_signature = token.split(".", 1)
            payload = _b64url_decode(encoded_payload)
            signature = _b64url_decode(encoded_signature)
        except Exception:
            return None
        expected = hmac.new(self._secret, payload, hashlib.sha256).digest()
        if not hmac.compare_digest(signature, expected):
            return None
        try:
            raw = json.loads(payload.decode("utf-8"))
        except Exception:
            return None
        if not isinstance(raw, dict):
            return None
        envelope = RuntimeAccessEnvelope(
            agent_scope=str(raw.get("agent_scope") or "").strip().upper(),
            capabilities=tuple(
                str(item).strip().lower()
                for item in (raw.get("capabilities") or ["read"])
                if str(item).strip()
            )
            or ("read",),
            workspace_scope=tuple(str(item).strip() for item in raw.get("workspace_scope") or [] if str(item).strip()),
            source_scope=tuple(str(item).strip() for item in raw.get("source_scope") or [] if str(item).strip()),
            sensitive_allowed=bool(raw.get("sensitive_allowed") or False),
            issued_at=str(raw.get("issued_at") or ""),
            expires_at=str(raw.get("expires_at") or ""),
        )
        if envelope.agent_scope and str(agent_scope or "").strip().upper() not in {"", envelope.agent_scope}:
            return None
        normalized_capability = str(capability or "").strip().lower()
        if normalized_capability and normalized_capability not in envelope.capabilities:
            return None
        if sensitive_required and not envelope.sensitive_allowed:
            return None
        try:
            expires_at = datetime.fromisoformat(envelope.expires_at)
        except ValueError:
            return None
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=UTC)
        if expires_at <= datetime.now(tz=UTC):
            return None
        return envelope
