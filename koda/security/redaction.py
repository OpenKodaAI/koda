"""The one secret redactor (TD-056).

Audit details, runtime streams, store rows and API previews, run graphs, eval exports,
memory previews, workspace-import excerpts and structured logs all redact through this
module. It applies three rules, in this order:

1. Key rule: a value under a sensitive key is masked whole. Keys are split into words
   (camelCase, snake_case, kebab-case), so ``basicAuth`` and ``auth_key`` are sensitive
   and ``author``, ``auth_mode`` and ``authority`` are not. PT-BR names count too.
2. Known secret formats in free text, each anchored on a non-identifier left boundary:
   bearer and basic credentials, key=value and env-style lines under a sensitive key,
   URL credentials, query-string secrets, cookie headers and provider key prefixes.
3. Generic long tokens: a run of 24 or more token characters that mixes letters and
   digits is masked, except Koda's own identifier shapes (``_IDENTIFIER_SHAPES``), so
   session ids, tool names, file names and UUID paths stay readable.
"""

from __future__ import annotations

import json
import re
from typing import Any

REDACTED = "[REDACTED]"

# Matched against the key split into lowercase words joined by "_" (see _key_words).
# token, secret, password, cookie and credential match anywhere in the key, as before.
_SENSITIVE_KEY_RE = re.compile(
    r"authorization|token|secret|password|passwd|cookie|credential"
    r"|api_?key|access_?key|private_?key|recovery_?code|bootstrap_?code"
    # auth as the credential itself: the last word, or before key/header/pass/token.
    r"|(?:^|_)auth(?:_(?:key|header|pass|passwd|password|token|secret|value|string))?$"
    # PT-BR: senha, segredo and chave as words (not desenho, palavra_chave, chave_primaria).
    r"|(?:^|_)senhas?(?:_|$)|(?:^|_)segredos?(?:_|$)|credencia(?:l|is)"
    r"|^chaves?$|(?:^|_)chave_(?:de_|da_)?(?:api|acesso|secreta|privada)(?:_|$)"
)
# Keys that are only sensitive as the whole key (a one-time or OAuth code, not exit_code;
# a session cookie, not session_id). Free text does not use them ("exit code: 1").
_SENSITIVE_EXACT_KEYS = frozenset({"code", "session"})

_CAMEL_RE = re.compile(r"(?<=[a-z0-9])(?=[A-Z])|(?<=[A-Z])(?=[A-Z][a-z])")
_KEY_SEPARATOR_RE = re.compile(r"[\s.\-]+")


def _key_words(key: str) -> str:
    return _KEY_SEPARATOR_RE.sub("_", _CAMEL_RE.sub("_", key.strip())).lower()


def _key_is_sensitive(key: str, *, exact: bool) -> bool:
    words = _key_words(key)
    return bool(_SENSITIVE_KEY_RE.search(words)) or (exact and words in _SENSITIVE_EXACT_KEYS)


def is_sensitive_key(key: str) -> bool:
    """Whether the value stored under ``key`` is a secret as a whole."""
    return _key_is_sensitive(key, exact=True)


# A value after "key:" or "key=": quoted, or up to the next separator. A value that opens
# a structure ({ or [) is left alone, so a masked [REDACTED] is not masked twice.
_VALUE = r"(?:\"(?P<dq>[^\"\n]*)\"|'(?P<sq>[^'\n]*)'|(?P<bare>(?![\[{])[^\s,;&\"'}\])]+))"
# An auth scheme kept in front of the masked value (Authorization: Bearer [REDACTED]). The
# group is atomic: after a scheme, only the token may be masked, never the scheme word.
_SCHEME = r"(?>(?P<scheme>(?i:bearer|basic|digest|token)\s+)?)"
_SEP = r"(?P<sep>\s*[:=]\s*)"
_KEY_VALUE_RE = re.compile(
    r"(?<![A-Za-z0-9_.\-])(?P<q>[\"']?)(?P<key>[A-Za-z_][A-Za-z0-9_.\-]*)(?P=q)" + _SEP + _SCHEME + _VALUE
)
# Sensitive names written as several words.
_PHRASE_VALUE_RE = re.compile(
    r"(?<![A-Za-z0-9_\-])(?P<key>(?i:(?:api|access|secret|private)\s+key|token\s+de\s+acesso"
    r"|chave\s+(?:de\s+|da\s+)?(?:api|acesso)))" + _SEP + _SCHEME + _VALUE
)
_QUERY_RE = re.compile(r"(?P<lead>[?&])(?P<key>[A-Za-z0-9_.\-]+)=(?P<value>[^&\s#\"']+)")


def _mask_value(match: re.Match[str]) -> str:
    quote = '"' if match.group("dq") is not None else "'" if match.group("sq") is not None else ""
    return f"{match.string[match.start() : match.end('sep')]}{match.group('scheme') or ''}{quote}{REDACTED}{quote}"


def _mask_key_value(match: re.Match[str]) -> str:
    if not _key_is_sensitive(match.group("key"), exact=False):
        return match.group(0)
    return _mask_value(match)


def _mask_query(match: re.Match[str]) -> str:
    if not is_sensitive_key(match.group("key")):
        return match.group(0)
    return f"{match.group('lead')}{match.group('key')}={REDACTED}"


_ID = r"(?<![A-Za-z0-9_\-])"
_END = r"(?![A-Za-z0-9_\-])"
_SUBSTITUTIONS: tuple[tuple[re.Pattern[str], Any], ...] = (
    # URL credentials, any scheme (https://u:p@, postgresql://u:p@, redis://:p@).
    (
        re.compile(r"(?i)(?<![A-Za-z0-9+.\-])([a-z][a-z0-9+.\-]*://)[^/\s:@]*:[^/\s@]+@"),
        rf"\1{REDACTED}:{REDACTED}@",
    ),
    # Cookie headers carry every cookie up to the end of the line.
    (re.compile(r"(?i)" + _ID + r"((?:set-)?cookie\s*:\s*)[^\r\n\"]+"), rf"\1{REDACTED}"),
    # Bearer and basic credentials, the whole token with + / and = padding. A free-text
    # "basic" only counts before a base64 value (a digit, + or /, or a lower-upper pair).
    (re.compile(r"(?i)" + _ID + r"(bearer\s+)[A-Za-z0-9._~+/\-]+=*"), rf"\1{REDACTED}"),
    (
        re.compile(
            r"(?i)" + _ID + r"(basic\s+)(?-i:(?=[A-Za-z0-9+/]*(?:[0-9+/]|[a-z][A-Z])))"
            r"[A-Za-z0-9+/]{8,}={0,2}(?![A-Za-z0-9+/=])"
        ),
        rf"\1{REDACTED}",
    ),
    (_QUERY_RE, _mask_query),
    (_PHRASE_VALUE_RE, _mask_value),
    (_KEY_VALUE_RE, _mask_key_value),
    # Provider key prefixes: OpenAI and Anthropic, AWS, GitHub, Slack, Google.
    (re.compile(_ID + r"sk-[A-Za-z0-9_\-]{20,}"), REDACTED),
    (re.compile(r"(?<![A-Za-z0-9])(?:AKIA|ASIA)[A-Z0-9]{16}(?![A-Za-z0-9])"), REDACTED),
    (re.compile(_ID + r"(?:gh[pousr]_[A-Za-z0-9_]{30,}|github_pat_[A-Za-z0-9_]{22,})"), REDACTED),
    (re.compile(_ID + r"xox[abpr]-[A-Za-z0-9\-]{10,}"), REDACTED),
    (re.compile(_ID + r"AIza[A-Za-z0-9_\-]{35}" + _END), REDACTED),
)

# Koda's own identifier shapes, kept by the generic long-token rule. Where each is made:
_UUID_HEX = r"[0-9a-f]{12}[1-8][0-9a-f]{3}[89ab][0-9a-f]{15}"
_WORD = r"(?:(?:[a-z]+|[A-Z]+)[0-9]*|[0-9]+(?:[a-z]+|[A-Z]+)?)"
_IDENTIFIER_SHAPES = re.compile(
    "|".join(
        (
            # str(uuid4()): task, artifact, session and request ids across Koda.
            r"[0-9A-Fa-f]{8}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{12}",
            # uuid4().hex, bare or after a word prefix: session-<hex> (runtime/api.py),
            # req-<hex> (agents/postgres_message_bus.py), boot_/rec_/sess_/usr_/tok_<hex>
            # (control_plane/operator_auth.py), imp_/ipe_<hex> (improvement_proposals.py),
            # <prefix>_<hex> (scheduled_jobs.py), provider_auth.py session ids.
            r"(?:[a-z]+[_\-])*" + _UUID_HEX,
            # <prefix>-<sha256[:24]>: squad-<hex> (runtime/api.py, control_plane/manager.py),
            # <prefix>_<hex> (channels/gateway.py).
            r"(?:[a-z]+[_\-])+[0-9a-f]{24}",
            # task-<id>-operator-shell-<token_hex(6)> (runtime/controller.py).
            r"task-[0-9]+-operator-shell-[0-9a-f]{12}",
            # worker_<pid>_<hex12> (services/queue_manager.py).
            r"worker_[0-9]+_[0-9a-f]{12}",
            # Word-segment names (tool names, snake/kebab file and directory names, model
            # names): two or more single-case words, each optionally followed by digits.
            _WORD + r"(?:[_\-]+" + _WORD + r")+",
        )
    )
)
_LONG_TOKEN_RE = re.compile(_ID + r"[A-Za-z0-9_\-]{24,}" + _END)
_HAS_LETTER = re.compile(r"[A-Za-z]")
_HAS_DIGIT = re.compile(r"[0-9]")


def _mask_long_token(match: re.Match[str]) -> str:
    token = match.group(0)
    if not (_HAS_LETTER.search(token) and _HAS_DIGIT.search(token)) or _IDENTIFIER_SHAPES.fullmatch(token):
        return token
    return REDACTED


def redact_text(text: str) -> str:
    """Mask the secrets inside a string (known formats first, then long random tokens)."""
    for pattern, replacement in _SUBSTITUTIONS:
        text = pattern.sub(replacement, text)
    return _LONG_TOKEN_RE.sub(_mask_long_token, text)


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
