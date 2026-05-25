"""Safety scanner for durable memory and self-improvement text."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any

from koda.services.runtime.redaction import redact_value

_ZERO_WIDTH_OR_BIDI = re.compile(r"[\u200b-\u200f\u202a-\u202e\u2060-\u206f\ufeff]")
_CONTROL_CHARS = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")

_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    (
        "prompt_injection",
        re.compile(
            r"\b(ignore|disregard|override|forget)\b.{0,80}\b(previous|prior|system|developer|instruction|policy|rules?)\b"
            r"|\breveal\b.{0,80}\b(system prompt|developer message|hidden instructions?)\b"
            r"|\byou are now\b.{0,80}\b(system|developer|admin)\b",
            re.IGNORECASE | re.DOTALL,
        ),
    ),
    (
        "exfiltration",
        re.compile(
            r"\b(curl|wget|nc|netcat|scp|rsync)\b.{0,120}\b(http|https|ftp|ssh)://"
            r"|\b(post|upload|exfiltrate|send)\b.{0,120}\b(secret|token|credential|\.env|ssh key|api key)\b",
            re.IGNORECASE | re.DOTALL,
        ),
    ),
    (
        "secret_path",
        re.compile(
            r"(\b(cat|less|more|open|read|print|tail|head)\b.{0,80})?"
            r"(/etc/passwd|/etc/shadow|~/.ssh/|\.ssh/id_(rsa|ed25519)|\.env(\.\w+)?|\.aws/credentials|\.kube/config)",
            re.IGNORECASE | re.DOTALL,
        ),
    ),
    (
        "credential_leakage",
        re.compile(
            r"\b(AKIA|ASIA)[A-Z0-9]{16}\b"
            r"|sk-[A-Za-z0-9_-]{20,}"
            r"|xox[baprs]-[A-Za-z0-9-]{20,}"
            r"|gh[pousr]_[A-Za-z0-9_]{30,}"
            r"|\b(password|api[_ -]?key|access[_ -]?token|secret)\b\s*[:=]\s*['\"]?[A-Za-z0-9_./+=-]{16,}",
            re.IGNORECASE | re.DOTALL,
        ),
    ),
)


@dataclass(frozen=True, slots=True)
class MemorySafetyFinding:
    category: str
    message: str
    match_preview: str = ""

    def to_dict(self) -> dict[str, str]:
        return {
            "category": self.category,
            "message": self.message,
            "match_preview": self.match_preview,
        }


@dataclass(frozen=True, slots=True)
class MemorySafetyResult:
    allowed: bool
    findings: list[MemorySafetyFinding] = field(default_factory=list)
    redacted_preview: str = ""

    @property
    def blocked_categories(self) -> list[str]:
        categories: list[str] = []
        for finding in self.findings:
            if finding.category not in categories:
                categories.append(finding.category)
        return categories

    def to_dict(self) -> dict[str, Any]:
        return {
            "allowed": self.allowed,
            "findings": [finding.to_dict() for finding in self.findings],
            "blocked_categories": self.blocked_categories,
            "redacted_preview": self.redacted_preview,
            "error_envelope": self.error_envelope() if not self.allowed else None,
        }

    def error_envelope(self) -> dict[str, Any]:
        categories = ", ".join(self.blocked_categories) or "unknown"
        return {
            "code": "memory_safety.policy_denied",
            "category": "policy_denied",
            "message": f"Memory safety scanner blocked unsafe text: {categories}.",
            "retryable": False,
            "user_action": (
                "Remove prompt-injection, exfiltration, secret-path, invisible-character, "
                "or credential material before retrying."
            ),
        }


class MemorySafetyError(ValueError):
    """Raised when durable memory/proposal text fails the scanner."""

    def __init__(self, result: MemorySafetyResult) -> None:
        self.result = result
        super().__init__(result.error_envelope()["message"])

    def error_envelope(self) -> dict[str, Any]:
        return self.result.error_envelope()


def _stringify(value: Any) -> str:
    if isinstance(value, str):
        return value
    try:
        return json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)
    except TypeError:
        return str(value)


def _redacted_preview(text: str, *, limit: int = 240) -> str:
    sample = text[: max(limit * 2, limit)]
    try:
        redacted = str(redact_value(sample, key_hint="memory_safety"))
    except Exception:
        redacted = re.sub(
            r"(?i)(password|api[_ -]?key|access[_ -]?token|secret)\s*[:=]\s*['\"]?[^\\s'\"]+",
            r"\1=[REDACTED]",
            sample,
        )
        redacted = re.sub(r"(AKIA|ASIA)[A-Z0-9]{16}", "[REDACTED]", redacted)
        redacted = re.sub(r"sk-[A-Za-z0-9_-]{20,}", "[REDACTED]", redacted)
        redacted = re.sub(r"gh[pousr]_[A-Za-z0-9_]{30,}", "[REDACTED]", redacted)
    redacted = _ZERO_WIDTH_OR_BIDI.sub("", redacted)
    redacted = _CONTROL_CHARS.sub("", redacted)
    return redacted[:limit]


def scan_memory_text(value: Any, *, surface: str = "memory") -> MemorySafetyResult:
    """Scan user/model-authored durable text before persistence."""

    text = _stringify(value)
    findings: list[MemorySafetyFinding] = []
    if _ZERO_WIDTH_OR_BIDI.search(text) or _CONTROL_CHARS.search(text):
        findings.append(
            MemorySafetyFinding(
                category="invisible_unicode",
                message=f"{surface} contains invisible or unsafe control characters",
            )
        )
    for category, pattern in _PATTERNS:
        match = pattern.search(text)
        if match:
            findings.append(
                MemorySafetyFinding(
                    category=category,
                    message=f"{surface} contains {category.replace('_', ' ')} pattern",
                    match_preview=_redacted_preview(match.group(0), limit=120),
                )
            )
    return MemorySafetyResult(
        allowed=not findings,
        findings=findings,
        redacted_preview=_redacted_preview(text),
    )


def assert_memory_text_safe(value: Any, *, surface: str = "memory") -> MemorySafetyResult:
    result = scan_memory_text(value, surface=surface)
    if not result.allowed:
        raise MemorySafetyError(result)
    return result
