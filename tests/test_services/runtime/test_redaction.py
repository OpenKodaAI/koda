from __future__ import annotations

import json

from koda.services.runtime.redaction import redact_json_dumps, redact_value


def test_redact_value_masks_nested_secret_keys_and_runtime_tokens():
    payload = {
        "authorization": "Bearer abcdefghijklmnopqrstuvwxyz123456",
        "cookie": "session=supersecretcookie",
        "nested": {
            "api_key": "abcdefghijklmnopqrstuvwxyz123456",
            "url": "https://user:pass@example.com/path",
        },
        "message": "token abcdefghijklmnopqrstuvwxyz123456",
    }

    redacted = redact_value(payload)

    assert redacted["authorization"] == "[REDACTED]"
    assert redacted["cookie"] == "[REDACTED]"
    assert redacted["nested"]["api_key"] == "[REDACTED]"
    assert redacted["nested"]["url"] == "https://[REDACTED]:[REDACTED]@example.com/path"
    assert redacted["message"] == "token [REDACTED]"


def test_redact_json_dumps_serializes_redacted_payload():
    payload = {"Authorization": "Bearer abcdefghijklmnopqrstuvwxyz123456", "status": "ok"}

    encoded = redact_json_dumps(payload)
    decoded = json.loads(encoded)

    assert decoded == {"Authorization": "[REDACTED]", "status": "ok"}
