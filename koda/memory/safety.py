"""Safety scanner for durable memory and self-improvement text."""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from koda.services.runtime.redaction import redact_value

_ZERO_WIDTH_OR_BIDI = re.compile(r"[\u200b-\u200f\u202a-\u202e\u2060-\u206f\ufeff]")
_CONTROL_CHARS = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")

# A `.env` file name (`.env`, `.env.local`, `.envrc`), not an identifier member such as `process.env`
# nor a template that holds no secrets (`.env.example`, `docs/.env.md`).
_DOTENV_FILE = r"(?<!\w)\.env(?:rc)?(?!\.(?:example|sample|template|dist|md)\b)(?:\.\w+)?(?!\w)"
# Up to 80 characters that do not cross a clause break (`, `, `; `, `. ` and so on).
_SAME_CLAUSE = r"(?:(?![.!?;,](?:\s|$)).){0,80}?"
# Shell commands that print a file: only their own arguments (at most two) may sit before `.env`.
_DOTENV_SHELL_READ = r"\b(?:cat|less|more|head|tail|grep|source|type)\b(?:\s+\S+){0,2}?\s+"
# Verbs that read or send a file, in English and PT-BR imperative forms.
_DOTENV_READ_OR_SEND_VERBS = (
    r"\b(?:open|read|print|show|display|dump|share|email|include|paste|send|post|upload|exfiltrate|leak|reveal"
    r"|expose|leiam?|abram?|mostrem?|exibam?|imprimam?|envie|enviem|mandem?|compartilhem?|incluam?|colem?"
    r"|postem?|revelem?|exponham?)\b"
)
# A secret-ish word, also inside an identifier such as `SECRET_TOKEN`.
_SECRET_WORD = r"(?<![^\W_])(?:secret|token|credential|ssh key|api key)(?![^\W_])"
# PT-BR instruction targets: instructions on their own only after "todas as" / "suas", and rules or
# policies only with a qualifier that points at the agent's own instructions.
_PT_INSTRUCTIONS = r"(?:instru[cç](?:[oõ]es|[aã]o)|orienta[cç][oõ]es|diretrizes)"
_PT_INSTRUCTION_TARGET = (
    r"(?:\b(?:todas as|suas|tuas)\s+" + _PT_INSTRUCTIONS + r"\b"
    r"|\b(?:" + _PT_INSTRUCTIONS + r"|regras?|pol[ií]ticas?)\s+"
    r"(?:anteriores|acima|originais|iniciais|ocultas|d[oe] sistema|do desenvolvedor)\b"
    r"|\b(?:prompt|mensagem) d[oe] (?:sistema|desenvolvedor)\b|\bsystem prompt\b)"
)

_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    (
        "prompt_injection",
        re.compile(
            r"\b(ignore|disregard|override|forget)\b.{0,80}\b(previous|prior|system|developer|instruction|policy|rules?)\b"
            r"|\breveal\b.{0,80}\b(system prompt|developer message|hidden instructions?)\b"
            r"|\byou are now\b.{0,80}\b(system|developer|admin)\b"
            # PT-BR: imperative ignore/override, reveal, and role takeover. Descriptive or infinitive
            # forms ("o linter ignora", "ignorar linhas") are ordinary notes, not instructions.
            r"|\b(?:ignorem?|desconsiderem?|desprezem?|esque[cç]am?|sobrescrevam?|anulem?)\b.{0,80}?"
            + _PT_INSTRUCTION_TARGET
            + r"|\b(?:revelem?|mostrem?|exibam?)\b.{0,80}?"
            r"\b(?:prompt d[oe] sistema|system prompt|mensagem do desenvolvedor|instru[cç](?:[oõ]es|[aã]o) ocultas?)\b"
            r"|\b(?:voc[eê] agora [eé]|agora voc[eê] [eé]|(?:a partir de agora|de agora em diante),? voc[eê] [eé])"
            r"\s+(?:(?:o|a|um|uma|seu|sua)\s+)?(?:administrador|admin|desenvolvedor|sistema|root)\b",
            re.IGNORECASE | re.DOTALL,
        ),
    ),
    (
        "exfiltration",
        re.compile(
            r"\b(curl|wget|nc|netcat|scp|rsync)\b.{0,120}\b(http|https|ftp|ssh)://"
            r"|\b(post|upload|exfiltrate|send)\b.{0,120}(" + _SECRET_WORD + "|" + _DOTENV_FILE + ")",
            re.IGNORECASE | re.DOTALL,
        ),
    ),
    (
        "secret_path",
        re.compile(
            "|".join(
                (
                    r"/etc/passwd|/etc/shadow|~/.ssh/|\.ssh/id_(rsa|ed25519)|\.aws/credentials|\.kube/config",
                    # `.env` only behind a path separator, a shell read, a read or send verb in the same
                    # clause, or before "paste" ("copie o .env e cole aqui"), so `process.env.X` stays allowed.
                    r"[/\\]" + _DOTENV_FILE,
                    _DOTENV_SHELL_READ + _DOTENV_FILE,
                    _DOTENV_READ_OR_SEND_VERBS + _SAME_CLAUSE + _DOTENV_FILE,
                    _DOTENV_FILE + _SAME_CLAUSE + r"\b(?:paste|colem?)\b",
                )
            ),
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
    """Join a payload's keys and text with real newlines.

    JSON would turn a newline into the two characters backslash-n, so the word before a line-initial
    `.env` or verb would end in `n` and every word-boundary anchor would miss it.
    """
    if isinstance(value, str):
        return value
    if isinstance(value, Mapping):
        items = sorted(value.items(), key=lambda pair: str(pair[0]))
        return "\n".join(f"{key}\n{_stringify(item)}" for key, item in items)
    if isinstance(value, (list, tuple)):
        return "\n".join(_stringify(item) for item in value)
    return "" if value is None else str(value)


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

    # NFC, so a decomposed accent (`e` + U+0301) matches the precomposed letters in the patterns.
    text = unicodedata.normalize("NFC", _stringify(value))
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
