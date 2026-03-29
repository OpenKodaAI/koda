"""Tests for scoped runtime access envelopes."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
from datetime import UTC, datetime, timedelta

from koda.services.runtime_access_service import RuntimeAccessService


def test_runtime_access_service_round_trip_and_sensitive_gate():
    service = RuntimeAccessService("secret")
    envelope, token = service.issue(
        agent_scope="AGENT_A",
        workspace_scope=("workspace-a",),
        source_scope=("policy:*",),
        sensitive_allowed=True,
    )

    authorized = service.authorize(token, agent_scope="AGENT_A", sensitive_required=True)

    assert authorized is not None
    assert authorized.agent_scope == "AGENT_A"
    assert authorized.workspace_scope == ("workspace-a",)
    assert envelope.sensitive_allowed is True


def test_runtime_access_service_rejects_expired_tokens():
    service = RuntimeAccessService("secret")
    envelope = {
        "agent_scope": "AGENT_A",
        "workspace_scope": [],
        "source_scope": [],
        "sensitive_allowed": True,
        "issued_at": datetime.now(tz=UTC).isoformat(),
        "expires_at": (datetime.now(tz=UTC) - timedelta(seconds=5)).isoformat(),
    }
    payload = json.dumps(envelope, ensure_ascii=True, separators=(",", ":")).encode("utf-8")
    signature = hmac.new(b"secret", payload, hashlib.sha256).digest()
    expired_payload = base64.urlsafe_b64encode(payload).decode("ascii").rstrip("=")
    encoded_signature = base64.urlsafe_b64encode(signature).decode("ascii").rstrip("=")
    token = f"{expired_payload}.{encoded_signature}"

    assert service.authorize(token, agent_scope="AGENT_A", sensitive_required=True) is None
