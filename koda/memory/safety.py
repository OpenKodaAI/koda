"""Safety scanner for durable memory and self-improvement text."""

from __future__ import annotations

import json
import re
import unicodedata
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from koda.services.runtime.redaction import redact_value

_ZERO_WIDTH_OR_BIDI = re.compile(r"[\u200b-\u200f\u202a-\u202e\u2060-\u206f\ufeff]")
_CONTROL_CHARS = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")

# A `.env` file name (`.env`, `.env.local`, `.envrc`), not an identifier member such as `process.env`
# nor a template that holds no secrets (`.env.example`, `docs/.env.md`). The whole name matches, never
# the `.env` inside `.env.local`, so what follows the match is what follows the file name.
_DOTENV_FILE = r"(?<!\w)\.env(?:rc)?(?!\.(?:example|sample|template|dist|md)\b)(?:\.\w+)*(?!\w|\.\w)"
# A quote around the file name (`cat ".env"`).
_QUOTE = r"[\"'`]?"
# A short aside between commas ("Read, please, the .env"), which does not end the clause. Its first
# comma is followed by whitespace, which the single-character branch of _SAME_CLAUSE never takes, so
# the two branches cannot both match a comma (no exponential backtracking on ",a,a,a").
_ASIDE = r",\s+\w+(?:\s+\w+){0,2},"
# A subordinate conjunction ("Show a warning if the user has no .env"). PT-BR `se` after "que" or a
# hyphen is the reflexive pronoun, not "if" ("o arquivo que se chama .env", "encontra-se").
_SUBORDINATE = r"\b(?:when|whenever|if|unless|quando|(?<!\bque )(?<!-)se)\b"
# An elliptical aside such as "if any" or "if possible" before a preposition is not a clause ("Show the
# values if any from .env").
_ELLIPSIS = r"\s+(?:any|possible|needed|necessary|poss[ií]vel|necess[aá]rio)\s+(?:from|in|no|na|em|do|da)\b"
# A clause break: `, `, `; `, `. ` and so on, or a subordinate clause.
_CLAUSE_BREAK = r"[.!?;,](?:\s|$)|" + _SUBORDINATE + r"(?!" + _ELLIPSIS + r")"
# A subordinate aside right after the verb, before its object ("Print if possible the .env", "Mostre
# quando puder o .env"), does not break the clause, unless the file is its subject ("Show when .env is
# missing").
_SUBORDINATE_ASIDE = (
    r"(?:\s+" + _SUBORDINATE + r"(?!\s+(?:(?:the|a|an|your|our|its|o|um|uma|seu|sua)\s+)?" + _QUOTE + r"\.env))?"
)
# Up to 80 characters of one clause; an aside does not break it.
_SAME_CLAUSE = _SUBORDINATE_ASIDE + r"(?:" + _ASIDE + r"|(?!" + _CLAUSE_BREAK + r").){0,80}?"
# Up to 80 characters of one sentence: commas do not break it.
_SAME_SENTENCE = r"(?:(?![.!?;](?:\s|$)).){0,80}?"
# Flags: up to eight with an optional value (which may be any word, even a command), then any number of
# plain flags made of word characters, `-` and `=`. A command word never starts inside such a flag
# (`-cat`, see _SHELL_COMMAND), so no command walks a flag chain that another one already walks, and
# the scan stays linear ("cat -n cat -n ...", "cat -cat -cat ...").
_SHELL_FLAGS = r"(?:\s+-\S+(?:\s+[^\s-]\S*)?){0,8}(?:\s+-[\w=-]+)*"
# A command word, not the tail of a flag or an option value (`-cat`, `--x=cat`).
_SHELL_COMMAND = r"(?<![-=])\b"
# Horizontal whitespace. A command position never takes a newline, so no line start walks the rest of
# a blank region and the scan stays linear ("\n" * 40000).
_HSPACE = r"[^\S\n]"
# The start of a line, after any list or quote markers ("- ", "* ", "1. ", "> "), or of a sentence
# ("Step 1: ", "Deploy notes. ").
_SENTENCE_START = r"(?:(?:^|\n)" + _HSPACE + r"*(?:(?:[-*+>]|\d+[.)])" + _HSPACE + r"+){0,3}|[:.!?]" + _HSPACE + r"+)"
# Where `source`, `type` and `more` are commands rather than English words ("more .env files", "the
# data source .env"): at the start of a line or a sentence, also after "now", "just", "first" or
# "next" there, after a shell separator, a subshell or a backtick, or after "run", "then", "please",
# "try", "exec(ute)" or "rode", with an optional comma ("Then, source .env").
_SHELL_COMMAND_POSITION = (
    r"(?:" + _SENTENCE_START + r"(?:(?:now|just|first|next),?" + _HSPACE + r"+)?"
    r"|[;&|(`$]" + _HSPACE + r"*"
    r"|\b(?:run|then|please|try|execute|exec|rode)\b,?" + _HSPACE + r"*)"
)
# Shell commands that print a file, then flags and at most two other arguments before `.env`, which
# may be quoted. `source`, `type` and `more` take the file as their first argument.
_DOTENV_SHELL_READ = (
    r"(?:" + _SHELL_COMMAND + r"(?:cat|less|head|tail|grep)\b" + _SHELL_FLAGS + r"(?:\s+[^\s-]\S*){0,2}?"
    r"|" + _SHELL_COMMAND_POSITION + _SHELL_COMMAND + r"(?:source|type|more)\b" + _SHELL_FLAGS + r")\s+" + _QUOTE
)
# A negation right before the verb: "Never share .env", "Não envie o .env" are hygiene notes. "Why not
# share .env" suggests the read, so it is not a negation.
_NOT_NEGATED = (
    r"(?:(?<=\bwhy not )"
    r"|(?<!\bnever )(?<!\bnot )(?<!n't )(?<!n\u2019t )(?<!\bnunca )(?<!\bjamais )(?<!\bnão )(?<!\bnao ))"
)
# Verbs that read or send a file, in English and PT-BR imperative forms.
_DOTENV_READ_OR_SEND_VERBS = (
    _NOT_NEGATED
    + r"\b(?:open|read|print|show|display|dump|share|email|include|paste|send|post|upload|exfiltrate|leak|reveal"
    r"|expose|leiam?|abram?|mostrem?|exibam?|imprimam?|envie|enviem|mandem?|compartilhem?|incluam?|colem?"
    r"|postem?|revelem?|exponham?)\b"
)
# `.env` named as an entry of an ignore file ("include .env in .gitignore", "in web/.dockerignore") is not
# being read or sent. The ignore file's name starts with its dot (`console.gitignore` is not one). Its
# path may start at `~/`, `./`, `../` or `/`, and its first directory is a plain local name: a URL or a
# host (`https://evil.example/.gitignore`, `attacker.example/.gitignore`) is where the file would be
# sent. Later directories may hold dots or an `@` (`apps/web.v2/`, `packages/@scope/ui/`).
_NOT_INTO_IGNORE_FILE = (
    r"(?!"
    + _QUOTE
    + r"\s+(?:in|to|into|no|na|ao|em)\s+(?:(?:the|your|our|o|a|seu|sua)\s+)?"
    + _QUOTE
    + r"(?:(?:~|\.{1,2})?/)?(?:\.?[\w-]+/(?:[\w.@-]+/)*)?\.\w*ignore\b)"
)
# A secret-ish word, also inside an identifier such as `SECRET_TOKEN`.
_SECRET_WORD = r"(?<![^\W_])(?:secret|token|credential|ssh key|api key)(?![^\W_])"
# PT-BR instruction targets that point at the agent's own instructions: instructions after "todas as"
# / "suas", and instructions, rules or policies with a qualifier ("anterior(es)", "do sistema"...).
_PT_INSTRUCTIONS = r"(?:instru[cç](?:[oõ]es|[aã]o)|orienta[cç](?:[oõ]es|[aã]o)|diretrizes)"
_PT_RULES = r"(?:regras?|pol[ií]ticas?|normas?|restri[cç][oõ]es)"
_PT_INSTRUCTION_TARGET = (
    r"(?:\b(?:todas as|suas|tuas)\s+" + _PT_INSTRUCTIONS + r"\b"
    r"|\b(?:" + _PT_INSTRUCTIONS + r"|regras?|pol[ií]ticas?)\s+"
    r"(?:anterior(?:es)?|acima|origina(?:l|is)|inicia(?:l|is)|ocultas?|d[oe] sistema|do desenvolvedor)\b"
    r"|\b(?:prompt|mensagem) d[oe] (?:sistema|desenvolvedor)\b|\bsystem prompt\b)"
)
# Broader targets, only as the direct object of a formal imperative: "Ignore as instruções", "Ignore
# essas regras e execute", "Desconsidere as regras de segurança". Rules, and a singular instruction,
# must be bare (the whole object), so "Desconsidere as regras de lint" and "Ignore a orientação do
# ESLint" stay notes, and an object further on belongs to another verb ("Ignore o cache e siga as
# instruções do README").
_PT_PLURAL_DETERMINER = r"(?:todas\s+)?(?:as|essas|estas)"
_PT_DETERMINER = r"(?:" + _PT_PLURAL_DETERMINER + r"|a|essa|esta)"
_PT_BARE = r"(?=\s*(?:[.!?;,]|$)|\s+e\s)"
_PT_GENERIC_TARGET = (
    r"(?:"
    + "|".join(
        (
            _PT_PLURAL_DETERMINER + r"\s+" + _PT_INSTRUCTIONS + r"\b",
            _PT_DETERMINER + r"\s+" + _PT_INSTRUCTIONS + r"\b" + _PT_BARE,
            _PT_DETERMINER + r"\s+" + _PT_RULES + r"\b" + _PT_BARE,
            r"(?:" + _PT_DETERMINER + r"\s+)?" + _PT_RULES + r"\s+de\s+seguran[cç]a\b",
            r"todas\s+as\s+" + _PT_RULES + r"\b",
        )
    )
    + r")"
)
# What may stand between the imperative and its object: an aside between commas (", por favor,") or
# up to three adverbs ("agora", "também", "por completo", "de vez", "-mente").
_PT_ADVERB = (
    r"(?:\w+mente|agora|tamb[eé]m|sempre|j[aá]|apenas|s[oó]|ent[aã]o|logo|ainda|mesmo|de vez|de uma vez"
    r"|por completo|por favor|de novo)"
)
_PT_BEFORE_OBJECT = r"(?:" + _ASIDE + r"|\s+" + _PT_ADVERB + r"\b,?){0,3}\s+"
# Formal (você) and informal Brazilian (tu, "ignora as instruções anteriores") imperatives.
_PT_OVERRIDE_FORMAL = r"\b(?:ignorem?|desconsiderem?|desprezem?|esque[cç]am?|sobrescrevam?|anulem?)\b"
_PT_OVERRIDE_INFORMAL = r"\b(?:ignora|desconsidera|despreza|esquece|sobrescreve|anula)\b"
# PT-BR imperative ignore/override, reveal, and role takeover, within one sentence. Infinitives
# ("ignorar linhas") are notes, and an informal imperative needs an instruction target, so
# "o linter ignora as regras desativadas" stays a note.
_PT_INJECTION = "|".join(
    (
        _PT_OVERRIDE_FORMAL + _SAME_SENTENCE + _PT_INSTRUCTION_TARGET,
        _PT_OVERRIDE_FORMAL + _PT_BEFORE_OBJECT + _PT_GENERIC_TARGET,
        _PT_OVERRIDE_INFORMAL + _SAME_SENTENCE + _PT_INSTRUCTION_TARGET,
        r"\b(?:revelem?|mostrem?|exibam?|revela|mostra|exibe)\b"
        + _SAME_SENTENCE
        + r"\b(?:prompt d[oe] sistema|system prompt|mensagem do desenvolvedor|instru[cç](?:[oõ]es|[aã]o) ocultas?)\b",
        r"\b(?:voc[eê] agora [eé]|agora voc[eê] [eé]|(?:a partir de agora|de agora em diante),? voc[eê] [eé])"
        r"\s+(?:(?:o|a|um|uma|seu|sua)\s+)?(?:administrador|admin|desenvolvedor|sistema|root)\b",
    )
)

_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    (
        "prompt_injection",
        re.compile(
            r"\b(ignore|disregard|override|forget)\b.{0,80}\b(previous|prior|system|developer|instruction|policy|rules?)\b"
            r"|\breveal\b.{0,80}\b(system prompt|developer message|hidden instructions?)\b"
            r"|\byou are now\b.{0,80}\b(system|developer|admin)\b"
            r"|" + _PT_INJECTION,
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
                    _DOTENV_READ_OR_SEND_VERBS + _SAME_CLAUSE + _DOTENV_FILE + _NOT_INTO_IGNORE_FILE,
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


def _texts(value: Any) -> list[str]:
    """Every key and text of a payload, each on its own.

    A pattern is matched inside one field only: joined fields would let a verb in one field reach a
    `.env` in a field that only the store puts next to it (the query preview in the metadata).
    """
    if isinstance(value, str):
        return [value]
    if isinstance(value, Mapping):
        texts: list[str] = []
        for key, item in sorted(value.items(), key=lambda pair: str(pair[0])):
            texts.append(str(key))
            texts.extend(_texts(item))
        return texts
    if isinstance(value, (list, tuple)):
        return [text for item in value for text in _texts(item)]
    return [] if value is None else [str(value)]


def _invisible_probe(value: Any) -> str:
    """The text the invisible-character check reads.

    A structured payload is read in its JSON form, as the scanner always read it: JSON escapes C0
    controls, so ANSI colour codes in tool output (a diff, an error message) are not flagged, while
    zero-width and bidi characters still are. A plain string is read as is.
    """
    if isinstance(value, str):
        return value
    try:
        return json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)
    except TypeError:
        return str(value)


def memory_safety_payload(memory: Any) -> dict[str, Any]:
    """The fields of a memory that the store scans before it persists the memory.

    The extractor scans the same payload per item, so the store never rejects a batch that the
    extractor accepted.
    """
    return {
        "content": memory.content,
        "subject": memory.subject,
        "claim_kind": memory.claim_kind,
        "decision_source": memory.decision_source,
        "retention_reason": memory.retention_reason,
        "metadata": memory.metadata,
    }


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
    texts = [unicodedata.normalize("NFC", text) for text in _texts(value)]
    text = "\n".join(texts)
    findings: list[MemorySafetyFinding] = []
    invisible_probe = _invisible_probe(value)
    if _ZERO_WIDTH_OR_BIDI.search(invisible_probe) or _CONTROL_CHARS.search(invisible_probe):
        findings.append(
            MemorySafetyFinding(
                category="invisible_unicode",
                message=f"{surface} contains invisible or unsafe control characters",
            )
        )
    for category, pattern in _PATTERNS:
        match = next((found for field_text in texts if (found := pattern.search(field_text))), None)
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
