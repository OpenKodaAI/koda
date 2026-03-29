"""Redaction helpers for runtime streams."""

from __future__ import annotations

import json
from typing import Any

from koda.services.provider_env import redact_runtime_value


def redact_value(value: Any, *, key_hint: str | None = None) -> Any:
    """Recursively redact sensitive runtime values via the Rust security core."""
    return redact_runtime_value(value, key_hint=key_hint)


def redact_json_dumps(value: Any) -> str:
    """Serialize a value after redaction."""
    return json.dumps(redact_value(value), ensure_ascii=False, default=str)
