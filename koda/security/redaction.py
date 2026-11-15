"""The one secret redactor (TD-056).

Audit details, runtime streams and store rows, run graphs, eval exports, memory previews
and structured logs all redact through this module. Its patterns are the union of the
lists those paths used to keep apart: the audit regexes, the Rust security core's runtime
redaction, the eval and run-graph sidecar fallbacks and the control-plane logging keys.
"""

from __future__ import annotations

import json
import re
from typing import Any

REDACTED = "[REDACTED]"

# A key matches when it contains one of these words, in any case.
_SENSITIVE_KEY_RE = re.compile(
    r"auth|token|secret|password|passwd|cookie|session|credential"
    r"|api[_-]?key|access[_-]?key|private[_-]?key|recovery[_-]?code|bootstrap[_-]?code",
    re.IGNORECASE,
)
# Keys that are only sensitive as a whole word (a one-time or OAuth code, not exit_code).
_SENSITIVE_EXACT_KEYS = frozenset({"code"})

# Applied in order; each keeps its first group and masks the rest of the match. The bearer
# rule also covers the audit trail's old `Authorization: Bearer` rule.
_TEXT_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"(?i)(bearer\s+)([a-z0-9._\-]+)"), rf"\1{REDACTED}"),
    (
        re.compile(
            r"(?i)\b((?:api[_-]?key|access[_-]?token|refresh[_-]?token|secret|password|passwd|cookie)\s*[=:]\s*)"
            r"([^,\s]+)"
        ),
        rf"\1{REDACTED}",
    ),
    (re.compile(r"(?i)([?&](?:api[_-]?key|access[_-]?token|token|secret|password)=)([^&\s]+)"), rf"\1{REDACTED}"),
    (re.compile(r"(?i)(token=)([^&,\s]+)"), rf"\1{REDACTED}"),
    (re.compile(r"(?i)(cookie\s*[:=]\s*)([^;\n]+)"), rf"\1{REDACTED}"),
    (re.compile(r"(https?://)([^/\s:@]+):([^/\s@]+)@"), rf"\1{REDACTED}:{REDACTED}@"),
    (re.compile(r"(?i)\b[a-z0-9_\-]{24,}\b"), REDACTED),
)


def is_sensitive_key(key: str) -> bool:
    """Whether the value stored under ``key`` is a secret as a whole."""
    return bool(_SENSITIVE_KEY_RE.search(key)) or key.lower() in _SENSITIVE_EXACT_KEYS


def redact_text(text: str) -> str:
    """Mask the inline secrets (bearer tokens, key=value secrets, URL credentials, long tokens)."""
    for pattern, replacement in _TEXT_PATTERNS:
        text = pattern.sub(replacement, text)
    return text


def _redact(value: Any, key_hint: str | None, path: str, paths: list[str] | None) -> Any:
    if key_hint is not None and is_sensitive_key(key_hint):
        if paths is not None and path:
            paths.append(path)
        return REDACTED
    if isinstance(value, dict):
        return {key: _redact(item, key, f"{path}.{key}" if path else key, paths) for key, item in value.items()}
    if isinstance(value, list):
        return [_redact(item, None, f"{path}[{index}]", paths) for index, item in enumerate(value)]
    if isinstance(value, str):
        redacted = redact_text(value)
        if paths is not None and path and redacted != value:
            paths.append(path)
        return redacted
    return value


def _json_value(value: Any) -> Any:
    # Every path sees the JSON form, so tuples, sets and datetimes are scanned as text too.
    return json.loads(json.dumps(value, ensure_ascii=False, default=str))


def redact_value(value: Any, *, key_hint: str | None = None) -> Any:
    """Return the JSON form of ``value`` with every secret masked."""
    return _redact(_json_value(value), key_hint, "", None)


def redact_value_with_paths(value: Any) -> tuple[Any, list[str]]:
    """Like ``redact_value``, also returning the dotted paths whose values were masked."""
    paths: list[str] = []
    return _redact(_json_value(value), None, "", paths), paths


def redact_json_dumps(value: Any) -> str:
    """Serialize a value after redaction."""
    return json.dumps(redact_value(value), ensure_ascii=False, default=str)
