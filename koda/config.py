"""Configuration loaded from environment variables."""

import json
import os
import re
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import overload

from dotenv import load_dotenv

SCRIPT_DIR = Path(__file__).resolve().parent.parent
load_dotenv(SCRIPT_DIR / ".env")

# --- Multi-agent support ---
AGENT_ID: str | None = os.environ.get("AGENT_ID")
_bid = AGENT_ID.lower() if AGENT_ID else None


@overload
def _env(key: str, default: str) -> str: ...


@overload
def _env(key: str, default: None = None) -> str | None: ...


def _env(key: str, default: str | None = None) -> str | None:
    """Get env var with AGENT_ID prefix fallback: {AGENT_ID}_{key} -> {key} -> default."""
    if AGENT_ID:
        val = os.environ.get(f"{AGENT_ID}_{key}")
        if val is not None:
            return val
    return os.environ.get(key, default)


def _env_required(key: str) -> str:
    """Get required env var with AGENT_ID prefix fallback."""
    val = _env(key)
    if val is None:
        if AGENT_ID:
            raise ValueError(f"Missing env: {AGENT_ID}_{key} or {key}")
        raise ValueError(f"Missing env: {key}")
    return val


def _env_csv(key: str, default: str = "") -> list[str]:
    """Parse a comma-separated env var into a list."""
    raw = _env(key, default) or ""
    return [item.strip() for item in raw.split(",") if item.strip()]


def _env_json_object(key: str, default: str = "{}") -> dict:
    """Parse a JSON object from the environment, falling back safely."""
    raw = _env(key, default) or default
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    return data if isinstance(data, dict) else {}


def _resolve_path_value(path_value: str | Path, *, relative_to: Path) -> Path:
    """Expand a path and anchor relative values to a canonical root."""
    path = Path(path_value).expanduser()
    if not path.is_absolute():
        path = relative_to / path
    return path


def _resolve_writable_dir(path_value: str | Path, *, relative_to: Path, fallback_leaf: str) -> Path:
    """Resolve a scratch directory and fall back to a temp-owned path when needed."""
    path = _resolve_path_value(path_value, relative_to=relative_to)
    try:
        path.mkdir(parents=True, exist_ok=True)
        return path
    except OSError:
        fallback_root = Path(tempfile.gettempdir()) / "koda-runtime" / (_bid or "default")
        fallback = _resolve_path_value(fallback_leaf, relative_to=fallback_root)
        fallback.mkdir(parents=True, exist_ok=True)
        return fallback


def _bool_env(key: str, default: bool) -> bool:
    return (_env(key, "true" if default else "false") or "").strip().lower() == "true"


def _functional_default(function_id: str) -> tuple[str, str]:
    payload = _env_json_object("MODEL_FUNCTION_DEFAULTS_JSON")
    raw = payload.get(function_id)
    if not isinstance(raw, dict):
        return "", ""
    provider_id = str(raw.get("provider_id") or "").strip().lower()
    model_id = str(raw.get("model_id") or "").strip()
    return provider_id, model_id


def resolve_functional_default(function_id: str) -> tuple[str, str]:
    """Public resolver for per-function default provider/model.

    Returns ``("", "")`` when the operator has not configured a default for the
    given function id. This is the canonical entry point for services that want
    to honour the operator's choice in the Models section of the dashboard.
    """
    return _functional_default(function_id)


# --- Owner identity ---
OWNER_NAME: str = _env("OWNER_NAME", "")
OWNER_EMAIL: str = _env("OWNER_EMAIL", "")
OWNER_GITHUB: str = _env("OWNER_GITHUB", "")

# --- Core (per-agent) ---
# The control-plane supervisor must be able to boot before any agent runtime exists.
AGENT_TOKEN: str = _env("AGENT_TOKEN", "") or ""
AGENT_NAME: str = _env("AGENT_NAME", AGENT_ID or "Koda")
# Telegram polling resumption.
# Default ``false`` — restarts no longer drop queued user messages. Operators
# who explicitly want the legacy "discard backlog on reboot" behavior can set
# this to ``true`` per agent or globally.
TELEGRAM_DROP_PENDING_UPDATES: bool = _bool_env("TELEGRAM_DROP_PENDING_UPDATES", False)
# koda-bot-gateway opt-in. When enabled, workers stop opening
# their own long-poll TCP connection to api.telegram.org and subscribe to
# a single Rust gateway process that polls every bot centrally (resolves
# (1 long-poll per agent → 1 process for all). Default off so
# existing single-host deployments keep their current behavior; flip to
# ``true`` after `koda-bot-gateway` is deployed.
BOT_GATEWAY_ENABLED: bool = _bool_env("BOT_GATEWAY_ENABLED", False)
BOT_GATEWAY_GRPC_TARGET: str = (_env("BOT_GATEWAY_GRPC_TARGET", "127.0.0.1:50066") or "127.0.0.1:50066").strip()
# koda-policy-engine opt-in. When enabled, queue_manager
# consults the policy engine before enqueuing each user message (rate,
# concurrency, spend cap) and reports billed LLM cost back via
# RecordSpend. Off by default so existing single-tenant deployments
# continue to operate without a configured workspace policy.
POLICY_ENGINE_ENABLED: bool = _bool_env("POLICY_ENGINE_ENABLED", False)
POLICY_ENGINE_GRPC_TARGET: str = (_env("POLICY_ENGINE_GRPC_TARGET", "127.0.0.1:50067") or "127.0.0.1:50067").strip()
# Workspace identifier the worker reports to the policy engine. In
# single-tenant mode workers default to ``ws_default``; multi-tenant
# deployments plumb this through control-plane.
POLICY_ENGINE_WORKSPACE_ID: str = (_env("POLICY_ENGINE_WORKSPACE_ID", "ws_default") or "ws_default").strip()
DEFAULT_WORK_DIR: str = _env("DEFAULT_WORK_DIR", str(Path.home()))
PROJECT_DIRS: list[str] = [d.strip() for d in _env("PROJECT_DIRS", "").split(",") if d.strip()]
STATE_BACKEND: str = (_env("STATE_BACKEND", "postgres") or "postgres").strip().lower()
OBJECT_STORAGE_REQUIRED: bool = _bool_env("OBJECT_STORAGE_REQUIRED", True)
_state_root_default = Path.home() / ".koda-state"
STATE_ROOT_DIR: Path = Path(_env("STATE_ROOT_DIR", str(_state_root_default)) or str(_state_root_default)).expanduser()
RUNTIME_EPHEMERAL_ROOT: Path = Path(
    _env(
        "RUNTIME_EPHEMERAL_ROOT",
        str(Path(tempfile.gettempdir()) / "koda-runtime" / (_bid or "default")),
    )
    or str(Path(tempfile.gettempdir()) / "koda-runtime" / (_bid or "default"))
).expanduser()

# --- Core (shared) ---
ALLOWED_USER_IDS: set[int] = {
    int(uid.strip()) for uid in (_env("ALLOWED_USER_IDS", "") or "").split(",") if uid.strip()
}
ADMIN_USER_IDS: set[int] = {
    int(uid.strip())
    for uid in _env("ADMIN_USER_IDS", ",".join(str(uid) for uid in sorted(ALLOWED_USER_IDS))).split(",")
    if uid.strip()
}
KNOWLEDGE_ADMIN_USER_IDS: set[int] = {
    int(uid.strip())
    for uid in _env("KNOWLEDGE_ADMIN_USER_IDS", ",".join(str(uid) for uid in sorted(ALLOWED_USER_IDS))).split(",")
    if uid.strip()
}
AUDIT_RETENTION_DAYS: int = int(_env("AUDIT_RETENTION_DAYS", "90"))

# --- Claude CLI ---
CLAUDE_ENABLED: bool = _env("CLAUDE_ENABLED", "true").lower() == "true"
CLAUDE_TIMEOUT: int = int(_env("CLAUDE_TIMEOUT", "3600"))
MAX_BUDGET_USD: float = float(_env("MAX_BUDGET_USD", "5.0"))
MAX_TOTAL_BUDGET_USD: float = float(_env("MAX_TOTAL_BUDGET_USD", "50.0"))
MAX_TURNS: int = int(_env("MAX_TURNS", "200"))
FIRST_CHUNK_TIMEOUT: int = int(_env("FIRST_CHUNK_TIMEOUT", "300"))

# Claude lineup verified against
# https://platform.claude.com/docs/en/about-claude/models on 2026-05-01.
# Current generally-available models: Opus 4.7 (flagship), Sonnet 4.6, Haiku 4.5.
# Legacy entries kept so operators can pin previous-generation models, but the
# 2024-05-14 snapshots (`claude-{sonnet,opus}-4-20250514`) are deliberately
# omitted — they retire on 2026-06-15 per Anthropic's deprecation schedule.
CLAUDE_AVAILABLE_MODELS: list[str] = _env_csv(
    "CLAUDE_AVAILABLE_MODELS",
    (
        "claude-opus-4-7,claude-sonnet-4-6,claude-haiku-4-5-20251001,"
        "claude-opus-4-6,claude-sonnet-4-5-20250929,"
        "claude-opus-4-5-20251101,claude-opus-4-1-20250805"
    ),
)
CLAUDE_TIER_MODELS: dict[str, str] = {
    "small": _env("CLAUDE_MODEL_SMALL", "claude-haiku-4-5-20251001"),
    "medium": _env("CLAUDE_MODEL_MEDIUM", "claude-sonnet-4-6"),
    "large": _env("CLAUDE_MODEL_LARGE", "claude-opus-4-7"),
}
CLAUDE_DEFAULT_MODEL: str = _env(
    "CLAUDE_DEFAULT_MODEL",
    _env("DEFAULT_MODEL", CLAUDE_TIER_MODELS["medium"]),
)

# --- Codex CLI ---
CODEX_ENABLED: bool = _env("CODEX_ENABLED", "true").lower() == "true"
CODEX_BIN: str = _env("CODEX_BIN", "codex")
CODEX_TIMEOUT: int = int(_env("CODEX_TIMEOUT", str(CLAUDE_TIMEOUT)))
CODEX_FIRST_CHUNK_TIMEOUT: int = int(_env("CODEX_FIRST_CHUNK_TIMEOUT", str(FIRST_CHUNK_TIMEOUT)))
CODEX_SANDBOX: str = _env("CODEX_SANDBOX", "danger-full-access")
CODEX_APPROVAL_POLICY: str = _env("CODEX_APPROVAL_POLICY", "never")
CODEX_SKIP_GIT_REPO_CHECK: bool = _env("CODEX_SKIP_GIT_REPO_CHECK", "true").lower() == "true"
# OpenAI / Codex lineup verified against
# https://developers.openai.com/api/docs/models and the Codex models page on
# 2026-05-01. GPT-5.5 (released 2026-04-24) is the new frontier; GPT-5.4
# nano/mini cover lower-cost tiers; GPT-5.3-codex (+ codex-spark preview) and
# GPT-5.2 stay as Codex-aligned alternatives. The 5.1 codex variants and
# `gpt-5.2-codex` were pulled from the public docs and are dropped here.
CODEX_AVAILABLE_MODELS: list[str] = _env_csv(
    "CODEX_AVAILABLE_MODELS",
    ("gpt-5.5,gpt-5.4,gpt-5.4-mini,gpt-5.4-nano,gpt-5.3-codex,gpt-5.3-codex-spark,gpt-5.2"),
)
CODEX_TIER_MODELS: dict[str, str] = {
    "small": _env("CODEX_MODEL_SMALL", "gpt-5.4-nano"),
    "medium": _env("CODEX_MODEL_MEDIUM", "gpt-5.4"),
    "large": _env("CODEX_MODEL_LARGE", "gpt-5.5"),
}
CODEX_DEFAULT_MODEL: str = _env("CODEX_DEFAULT_MODEL", CODEX_TIER_MODELS["large"])

# --- Gemini CLI ---
GEMINI_ENABLED: bool = _env("GEMINI_ENABLED", "false").lower() == "true"
GEMINI_BIN: str = _env("GEMINI_BIN", "") or ""
GEMINI_TIMEOUT: int = int(_env("GEMINI_TIMEOUT", str(CLAUDE_TIMEOUT)))
GEMINI_FIRST_CHUNK_TIMEOUT: int = int(_env("GEMINI_FIRST_CHUNK_TIMEOUT", str(FIRST_CHUNK_TIMEOUT)))
# Gemini lineup verified against https://ai.google.dev/gemini-api/docs/models
# on 2026-05-01. 2.5 flash-lite/flash/pro are the production tiers; the 3.x
# previews (flash-lite, flash, pro) are exposed for opt-in experimentation.
GEMINI_AVAILABLE_MODELS: list[str] = _env_csv(
    "GEMINI_AVAILABLE_MODELS",
    (
        "gemini-2.5-pro,gemini-2.5-flash,gemini-2.5-flash-lite,"
        "gemini-3.1-pro-preview,gemini-3-flash-preview,gemini-3.1-flash-lite-preview"
    ),
)
GEMINI_TIER_MODELS: dict[str, str] = {
    "small": _env("GEMINI_MODEL_SMALL", "gemini-2.5-flash-lite"),
    "medium": _env("GEMINI_MODEL_MEDIUM", "gemini-2.5-flash"),
    "large": _env("GEMINI_MODEL_LARGE", "gemini-2.5-pro"),
}
GEMINI_DEFAULT_MODEL: str = _env("GEMINI_DEFAULT_MODEL", GEMINI_TIER_MODELS["medium"])

# Ollama
OLLAMA_ENABLED: bool = _env("OLLAMA_ENABLED", "false").lower() == "true"
OLLAMA_API_KEY: str = _env("OLLAMA_API_KEY", "") or ""
OLLAMA_BASE_URL: str = _env("OLLAMA_BASE_URL", "http://localhost:11434") or ""
OLLAMA_TIMEOUT: int = int(_env("OLLAMA_TIMEOUT", str(CLAUDE_TIMEOUT)))
OLLAMA_AVAILABLE_MODELS: list[str] = _env_csv(
    "OLLAMA_AVAILABLE_MODELS",
    "qwen3:latest,gemma3:latest,deepseek-r1:latest,gpt-oss:20b",
)
OLLAMA_TIER_MODELS: dict[str, str] = {
    "small": _env("OLLAMA_MODEL_SMALL", "gemma3:latest"),
    "medium": _env("OLLAMA_MODEL_MEDIUM", "qwen3:latest"),
    "large": _env("OLLAMA_MODEL_LARGE", "gpt-oss:20b"),
}
OLLAMA_DEFAULT_MODEL: str = _env("OLLAMA_DEFAULT_MODEL", OLLAMA_TIER_MODELS["medium"]) or ""

# Kokoro
KOKORO_ENABLED: bool = _env("KOKORO_ENABLED", "true").lower() == "true"
KOKORO_API_KEY: str = _env("KOKORO_API_KEY", "") or ""
KOKORO_AVAILABLE_MODELS: list[str] = [
    m.strip() for m in (_env("KOKORO_AVAILABLE_MODELS", "kokoro-v1") or "").split(",") if m.strip()
]
KOKORO_DEFAULT_MODEL: str = _env("KOKORO_DEFAULT_MODEL", "kokoro-v1") or ""
KOKORO_DEFAULT_LANGUAGE: str = _env("KOKORO_DEFAULT_LANGUAGE", "pt-br") or ""
KOKORO_DEFAULT_VOICE: str = _env("KOKORO_DEFAULT_VOICE", "pf_dora") or ""
KOKORO_VOICES_PATH: str = _env("KOKORO_VOICES_PATH", "") or ""

# Supertonic
SUPERTONIC_ENABLED: bool = _env("SUPERTONIC_ENABLED", "true").lower() == "true"
SUPERTONIC_AVAILABLE_MODELS: list[str] = _env_csv(
    "SUPERTONIC_AVAILABLE_MODELS",
    "supertonic-3,supertonic-2,supertonic",
)
SUPERTONIC_DEFAULT_MODEL: str = _env("SUPERTONIC_DEFAULT_MODEL", "supertonic-3") or ""
SUPERTONIC_DEFAULT_LANGUAGE: str = _env("SUPERTONIC_DEFAULT_LANGUAGE", "pt") or ""
SUPERTONIC_DEFAULT_VOICE: str = _env("SUPERTONIC_DEFAULT_VOICE", "F1") or ""
SUPERTONIC_ASSET_ROOT: str = _env("SUPERTONIC_ASSET_ROOT", "") or ""
SUPERTONIC_TOTAL_STEPS: int = int(_env("SUPERTONIC_TOTAL_STEPS", "8"))
SUPERTONIC_SPEED: float = float(_env("SUPERTONIC_SPEED", "1.05"))
SUPERTONIC_MAX_CHUNK_LENGTH: int = int(_env("SUPERTONIC_MAX_CHUNK_LENGTH", "300"))
SUPERTONIC_SILENCE_DURATION: float = float(_env("SUPERTONIC_SILENCE_DURATION", "0.3"))
SUPERTONIC_INTRA_OP_THREADS: int | None = int(_env("SUPERTONIC_INTRA_OP_THREADS", "0") or "0") or None
SUPERTONIC_INTER_OP_THREADS: int | None = int(_env("SUPERTONIC_INTER_OP_THREADS", "0") or "0") or None
SUPERTONIC_ONNX_PROVIDERS: list[str] = _env_csv("SUPERTONIC_ONNX_PROVIDERS", "CPUExecutionProvider")
SUPERTONIC_COREML_EXPERIMENTAL: bool = _env("SUPERTONIC_COREML_EXPERIMENTAL", "false").lower() == "true"
SUPERTONIC_MODEL_REVISION: str = _env("SUPERTONIC_MODEL_REVISION", "") or ""

# --- Perplexity (HTTP, OpenAI-compatible) ---
PERPLEXITY_ENABLED: bool = _env("PERPLEXITY_ENABLED", "false").lower() == "true"
PERPLEXITY_AVAILABLE_MODELS: list[str] = _env_csv(
    "PERPLEXITY_AVAILABLE_MODELS",
    "sonar,sonar-pro,sonar-reasoning,sonar-reasoning-pro,sonar-deep-research",
)
PERPLEXITY_TIER_MODELS: dict[str, str] = {
    "small": _env("PERPLEXITY_MODEL_SMALL", "sonar"),
    "medium": _env("PERPLEXITY_MODEL_MEDIUM", "sonar-pro"),
    "large": _env("PERPLEXITY_MODEL_LARGE", "sonar-reasoning-pro"),
}
PERPLEXITY_DEFAULT_MODEL: str = _env("PERPLEXITY_DEFAULT_MODEL", PERPLEXITY_TIER_MODELS["medium"])
PERPLEXITY_TIMEOUT: int = int(_env("PERPLEXITY_TIMEOUT", "180"))
PERPLEXITY_FIRST_CHUNK_TIMEOUT: int = int(_env("PERPLEXITY_FIRST_CHUNK_TIMEOUT", "60"))

# --- Mistral La Plateforme (HTTP, OpenAI-compatible) ---
MISTRAL_ENABLED: bool = _env("MISTRAL_ENABLED", "false").lower() == "true"
MISTRAL_AVAILABLE_MODELS: list[str] = _env_csv(
    "MISTRAL_AVAILABLE_MODELS",
    (
        "mistral-large-latest,mistral-medium-latest,mistral-small-latest,"
        "codestral-latest,pixtral-large-latest,pixtral-12b-2409,"
        "magistral-medium-latest,magistral-small-latest,"
        "ministral-8b-latest,ministral-3b-latest,mistral-saba-latest"
    ),
)
MISTRAL_TIER_MODELS: dict[str, str] = {
    "small": _env("MISTRAL_MODEL_SMALL", "mistral-small-latest"),
    "medium": _env("MISTRAL_MODEL_MEDIUM", "mistral-medium-latest"),
    "large": _env("MISTRAL_MODEL_LARGE", "mistral-large-latest"),
}
MISTRAL_DEFAULT_MODEL: str = _env("MISTRAL_DEFAULT_MODEL", MISTRAL_TIER_MODELS["large"])
MISTRAL_TIMEOUT: int = int(_env("MISTRAL_TIMEOUT", "120"))
MISTRAL_FIRST_CHUNK_TIMEOUT: int = int(_env("MISTRAL_FIRST_CHUNK_TIMEOUT", str(FIRST_CHUNK_TIMEOUT)))

# --- Qwen (Alibaba DashScope International, OpenAI-compatible) ---
QWEN_ENABLED: bool = _env("QWEN_ENABLED", "false").lower() == "true"
QWEN_AVAILABLE_MODELS: list[str] = _env_csv(
    "QWEN_AVAILABLE_MODELS",
    (
        "qwen3-max,qwen3-plus,qwen3-flash,"
        "qwen3-vl-max,qwen3-vl-plus,qwen3-vl-flash,"
        "qwen3-coder-plus,qwen3-coder-flash,qwen3-omni-30b-a3b,"
        "qwen-max,qwen-plus,qwen-turbo,qwen-long,"
        "qwen2.5-72b-instruct,qwen2.5-coder-32b-instruct,"
        "qwen-vl-max,qwen-vl-plus,qwq-32b,qvq-72b-preview"
    ),
)
QWEN_TIER_MODELS: dict[str, str] = {
    "small": _env("QWEN_MODEL_SMALL", "qwen3-flash"),
    "medium": _env("QWEN_MODEL_MEDIUM", "qwen3-plus"),
    "large": _env("QWEN_MODEL_LARGE", "qwen3-max"),
}
QWEN_DEFAULT_MODEL: str = _env("QWEN_DEFAULT_MODEL", QWEN_TIER_MODELS["medium"])
QWEN_TIMEOUT: int = int(_env("QWEN_TIMEOUT", "120"))
QWEN_FIRST_CHUNK_TIMEOUT: int = int(_env("QWEN_FIRST_CHUNK_TIMEOUT", str(FIRST_CHUNK_TIMEOUT)))

# --- Kimi (Moonshot AI, OpenAI-compatible) ---
KIMI_ENABLED: bool = _env("KIMI_ENABLED", "false").lower() == "true"
KIMI_AVAILABLE_MODELS: list[str] = _env_csv(
    "KIMI_AVAILABLE_MODELS",
    (
        "kimi-k2.6,kimi-k2.5,"
        "kimi-k2-0905-preview,kimi-k2-0711-preview,kimi-latest,"
        "kimi-thinking-preview,"
        "moonshot-v1-128k,moonshot-v1-32k,moonshot-v1-8k,moonshot-v1-auto"
    ),
)
KIMI_TIER_MODELS: dict[str, str] = {
    "small": _env("KIMI_MODEL_SMALL", "moonshot-v1-8k"),
    "medium": _env("KIMI_MODEL_MEDIUM", "kimi-k2.5"),
    "large": _env("KIMI_MODEL_LARGE", "kimi-k2.6"),
}
KIMI_DEFAULT_MODEL: str = _env("KIMI_DEFAULT_MODEL", KIMI_TIER_MODELS["large"])
KIMI_TIMEOUT: int = int(_env("KIMI_TIMEOUT", "120"))
KIMI_FIRST_CHUNK_TIMEOUT: int = int(_env("KIMI_FIRST_CHUNK_TIMEOUT", str(FIRST_CHUNK_TIMEOUT)))

# --- Groq (LPU inference, OpenAI-compatible) ---
GROQ_ENABLED: bool = _env("GROQ_ENABLED", "false").lower() == "true"
GROQ_AVAILABLE_MODELS: list[str] = _env_csv(
    "GROQ_AVAILABLE_MODELS",
    (
        "openai/gpt-oss-120b,openai/gpt-oss-20b,openai/gpt-oss-safeguard-20b,"
        "moonshotai/kimi-k2-instruct,qwen/qwen3-32b,"
        "llama-3.3-70b-versatile,llama-3.1-8b-instant,"
        "llama-3.2-1b-preview,llama-3.2-3b-preview,"
        "llama-3.2-11b-vision-preview,llama-3.2-90b-vision-preview,"
        "mixtral-8x7b-32768,gemma2-9b-it,"
        "qwen-2.5-32b,qwen-2.5-coder-32b,"
        "deepseek-r1-distill-llama-70b"
    ),
)
GROQ_TIER_MODELS: dict[str, str] = {
    "small": _env("GROQ_MODEL_SMALL", "openai/gpt-oss-20b"),
    "medium": _env("GROQ_MODEL_MEDIUM", "openai/gpt-oss-120b"),
    "large": _env("GROQ_MODEL_LARGE", "moonshotai/kimi-k2-instruct"),
}
GROQ_DEFAULT_MODEL: str = _env("GROQ_DEFAULT_MODEL", GROQ_TIER_MODELS["medium"])
GROQ_TIMEOUT: int = int(_env("GROQ_TIMEOUT", "60"))
GROQ_FIRST_CHUNK_TIMEOUT: int = int(_env("GROQ_FIRST_CHUNK_TIMEOUT", "15"))

# --- DeepSeek (V3 chat + R1 reasoner, OpenAI-compatible) ---
DEEPSEEK_ENABLED: bool = _env("DEEPSEEK_ENABLED", "false").lower() == "true"
DEEPSEEK_AVAILABLE_MODELS: list[str] = _env_csv(
    "DEEPSEEK_AVAILABLE_MODELS",
    "deepseek-v4-pro,deepseek-v4-flash,deepseek-chat,deepseek-reasoner",
)
DEEPSEEK_TIER_MODELS: dict[str, str] = {
    "small": _env("DEEPSEEK_MODEL_SMALL", "deepseek-v4-flash"),
    "medium": _env("DEEPSEEK_MODEL_MEDIUM", "deepseek-v4-flash"),
    "large": _env("DEEPSEEK_MODEL_LARGE", "deepseek-v4-pro"),
}
DEEPSEEK_DEFAULT_MODEL: str = _env("DEEPSEEK_DEFAULT_MODEL", DEEPSEEK_TIER_MODELS["medium"])
DEEPSEEK_TIMEOUT: int = int(_env("DEEPSEEK_TIMEOUT", "120"))
DEEPSEEK_FIRST_CHUNK_TIMEOUT: int = int(_env("DEEPSEEK_FIRST_CHUNK_TIMEOUT", str(FIRST_CHUNK_TIMEOUT)))

# --- xAI Grok (OpenAI-compatible) ---
XAI_ENABLED: bool = _env("XAI_ENABLED", "false").lower() == "true"
XAI_AVAILABLE_MODELS: list[str] = _env_csv(
    "XAI_AVAILABLE_MODELS",
    (
        "grok-4.3,grok-4.1-fast,grok-4-fast,grok-4-0709,"
        "grok-3,grok-3-mini,grok-3-fast,grok-3-mini-fast,"
        "grok-2-vision-1212,grok-2-1212"
    ),
)
XAI_TIER_MODELS: dict[str, str] = {
    "small": _env("XAI_MODEL_SMALL", "grok-4.1-fast"),
    "medium": _env("XAI_MODEL_MEDIUM", "grok-4-fast"),
    "large": _env("XAI_MODEL_LARGE", "grok-4.3"),
}
XAI_DEFAULT_MODEL: str = _env("XAI_DEFAULT_MODEL", XAI_TIER_MODELS["large"])
XAI_TIMEOUT: int = int(_env("XAI_TIMEOUT", "120"))
XAI_FIRST_CHUNK_TIMEOUT: int = int(_env("XAI_FIRST_CHUNK_TIMEOUT", str(FIRST_CHUNK_TIMEOUT)))

# --- OpenRouter (multi-provider routing, OpenAI-compatible) ---
OPENROUTER_ENABLED: bool = _env("OPENROUTER_ENABLED", "false").lower() == "true"
OPENROUTER_AVAILABLE_MODELS: list[str] = _env_csv(
    "OPENROUTER_AVAILABLE_MODELS",
    (
        "openrouter/auto,~openai/gpt-mini-latest,~google/gemini-flash-latest,"
        "~anthropic/claude-sonnet-latest,~openai/gpt-latest,openrouter/pareto-code"
    ),
)
OPENROUTER_TIER_MODELS: dict[str, str] = {
    "small": _env("OPENROUTER_MODEL_SMALL", "~openai/gpt-mini-latest"),
    "medium": _env("OPENROUTER_MODEL_MEDIUM", "~google/gemini-flash-latest"),
    "large": _env("OPENROUTER_MODEL_LARGE", "~anthropic/claude-sonnet-latest"),
}
OPENROUTER_DEFAULT_MODEL: str = _env("OPENROUTER_DEFAULT_MODEL", "openrouter/auto")
OPENROUTER_TIMEOUT: int = int(_env("OPENROUTER_TIMEOUT", "180"))
OPENROUTER_FIRST_CHUNK_TIMEOUT: int = int(_env("OPENROUTER_FIRST_CHUNK_TIMEOUT", "60"))

# --- llama.cpp (local Metal-accelerated inference, OpenAI-compatible) ---
LLAMACPP_ENABLED: bool = _env("LLAMACPP_ENABLED", "false").lower() == "true"
LLAMACPP_API_KEY: str = _env("LLAMACPP_API_KEY", "") or ""
LLAMACPP_API_BASE_URL: str = _env("LLAMACPP_API_BASE_URL", "http://127.0.0.1:8080") or ""
LLAMACPP_TIMEOUT: int = int(_env("LLAMACPP_TIMEOUT", "300"))
LLAMACPP_FIRST_CHUNK_TIMEOUT: int = int(_env("LLAMACPP_FIRST_CHUNK_TIMEOUT", "60"))
LLAMACPP_AVAILABLE_MODELS: list[str] = _env_csv("LLAMACPP_AVAILABLE_MODELS", "")
LLAMACPP_TIER_MODELS: dict[str, str] = {
    "small": _env("LLAMACPP_MODEL_SMALL", "") or "",
    "medium": _env("LLAMACPP_MODEL_MEDIUM", "") or "",
    "large": _env("LLAMACPP_MODEL_LARGE", "") or "",
}
LLAMACPP_DEFAULT_MODEL: str = _env("LLAMACPP_DEFAULT_MODEL", LLAMACPP_TIER_MODELS["medium"]) or ""
LLAMACPP_GRAMMAR_FILE: str = _env("LLAMACPP_GRAMMAR_FILE", "") or ""
LLAMACPP_DRAFT_MODEL: str = _env("LLAMACPP_DRAFT_MODEL", "") or ""
LLAMACPP_BIN: str = _env("LLAMACPP_BIN", "llama-server") or "llama-server"

# --- MLX (Apple-native local inference, OpenAI-compatible) ---
MLX_ENABLED: bool = _env("MLX_ENABLED", "false").lower() == "true"
MLX_API_KEY: str = _env("MLX_API_KEY", "") or ""
MLX_API_BASE_URL: str = _env("MLX_API_BASE_URL", "http://127.0.0.1:8000") or ""
MLX_TIMEOUT: int = int(_env("MLX_TIMEOUT", "300"))
MLX_FIRST_CHUNK_TIMEOUT: int = int(_env("MLX_FIRST_CHUNK_TIMEOUT", "60"))
MLX_AVAILABLE_MODELS: list[str] = _env_csv("MLX_AVAILABLE_MODELS", "")
MLX_TIER_MODELS: dict[str, str] = {
    "small": _env("MLX_MODEL_SMALL", "") or "",
    "medium": _env("MLX_MODEL_MEDIUM", "") or "",
    "large": _env("MLX_MODEL_LARGE", "") or "",
}
MLX_DEFAULT_MODEL: str = _env("MLX_DEFAULT_MODEL", MLX_TIER_MODELS["medium"]) or ""
MLX_SERVER_BIN: str = _env("MLX_SERVER_BIN", "mlx_lm.server") or "mlx_lm.server"

# --- Apple Silicon Metal acceleration (system-wide switch) ---
# Defaults ON: when the host is Apple Silicon, Metal-capable runtimes
# (llama.cpp, MLX) are allowed to use the GPU. The operator can disable
# this from System Settings → Models & Providers; on non-Apple-Silicon
# hosts the flag is a no-op (gated by ``is_apple_silicon()`` at runtime).
METAL_ENABLED: bool = _env("METAL_ENABLED", "true").lower() == "true"

# --- Local-runtime supervision (opt-in) ---
LOCAL_RUNTIME_AUTO_SPAWN: bool = _env("LOCAL_RUNTIME_AUTO_SPAWN", "false").lower() == "true"
LOCAL_RUNTIME_HEAVY_SLOTS: int = int(_env("LOCAL_RUNTIME_HEAVY_SLOTS", "1"))
LOCAL_RUNTIME_QUEUE_TIMEOUT: int = int(_env("LOCAL_RUNTIME_QUEUE_TIMEOUT", "300"))
LOCAL_MODEL_REGISTRY_PATH: str = _env("LOCAL_MODEL_REGISTRY_PATH", "") or ""

# --- Auto-activation of local-inference quality bolt-ons ---
# When true (default), enabling a local provider (llamacpp, mlx, ollama)
# lights up the practices that make sense for the actual environment:
# reranker if sentence-transformers is installed, vector cache if faiss is
# installed, cascade routing with a sensible threshold, auto-spawn if the
# binary is on PATH. Explicit env vars (RERANK_ENABLED=false, etc.) always
# override. Resolution lives in koda/services/runtime_capabilities.py.
LOCAL_AUTO_OPTIMIZE: bool = _env("LOCAL_AUTO_OPTIMIZE", "true").lower() == "true"

# --- Constrained decoding ---
STRUCTURED_DECODING_ENABLED: bool = _env("STRUCTURED_DECODING_ENABLED", "true").lower() == "true"

# --- Reranker ---
RERANK_ENABLED: bool = _env("RERANK_ENABLED", "false").lower() == "true"
RERANK_MODEL: str = _env("RERANK_MODEL", "BAAI/bge-reranker-v2-m3") or ""
RERANK_TOP_K: int = int(_env("RERANK_TOP_K", "8"))
RERANK_DEVICE: str = _env("RERANK_DEVICE", "auto") or "auto"

# --- Rust retrieval quality gates ---
KNOWLEDGE_RETRIEVAL_MIN_QUALITY_TIER: str = (
    _env("KNOWLEDGE_RETRIEVAL_MIN_QUALITY_TIER", "lexical_graph").strip().lower()
)
KNOWLEDGE_RETRIEVAL_DENSE_WINDOW: int = int(_env("KNOWLEDGE_RETRIEVAL_DENSE_WINDOW", "200"))
KNOWLEDGE_RETRIEVAL_RERANK_TOP_K: int = int(_env("KNOWLEDGE_RETRIEVAL_RERANK_TOP_K", str(RERANK_TOP_K)))
KNOWLEDGE_RETRIEVAL_VECTOR_COVERAGE_MIN: float = float(_env("KNOWLEDGE_RETRIEVAL_VECTOR_COVERAGE_MIN", "0.80"))

# --- Semantic cache vector backend ---
SEMANTIC_CACHE_BACKEND: str = (_env("SEMANTIC_CACHE_BACKEND", "lexical") or "lexical").lower()
SEMANTIC_CACHE_THRESHOLD: float = float(_env("SEMANTIC_CACHE_THRESHOLD", "0.92"))

# --- Cascade routing ---
LOCAL_PREFER_BELOW_COMPLEXITY: float = float(_env("LOCAL_PREFER_BELOW_COMPLEXITY", "0.0"))

# --- Provider selection / fallback ---
FUNCTIONAL_MODEL_DEFAULTS: dict = _env_json_object("MODEL_FUNCTION_DEFAULTS_JSON")
AVAILABLE_PROVIDERS: list[str] = [
    provider
    for provider, enabled in (
        ("claude", CLAUDE_ENABLED),
        ("codex", CODEX_ENABLED),
        ("gemini", GEMINI_ENABLED),
        ("ollama", OLLAMA_ENABLED),
        ("llamacpp", LLAMACPP_ENABLED),
        ("mlx", MLX_ENABLED),
        ("perplexity", PERPLEXITY_ENABLED),
        ("mistral", MISTRAL_ENABLED),
        ("qwen", QWEN_ENABLED),
        ("kimi", KIMI_ENABLED),
        ("groq", GROQ_ENABLED),
        ("deepseek", DEEPSEEK_ENABLED),
        ("xai", XAI_ENABLED),
        ("openrouter", OPENROUTER_ENABLED),
    )
    if enabled
]
DEFAULT_PROVIDER: str = _env("DEFAULT_PROVIDER", "claude").lower()
if DEFAULT_PROVIDER not in AVAILABLE_PROVIDERS and AVAILABLE_PROVIDERS:
    DEFAULT_PROVIDER = AVAILABLE_PROVIDERS[0]
PROVIDER_MODELS: dict[str, list[str]] = {
    "claude": CLAUDE_AVAILABLE_MODELS,
    "codex": CODEX_AVAILABLE_MODELS,
    "gemini": GEMINI_AVAILABLE_MODELS,
    "ollama": OLLAMA_AVAILABLE_MODELS,
    "llamacpp": LLAMACPP_AVAILABLE_MODELS,
    "mlx": MLX_AVAILABLE_MODELS,
    "perplexity": PERPLEXITY_AVAILABLE_MODELS,
    "mistral": MISTRAL_AVAILABLE_MODELS,
    "qwen": QWEN_AVAILABLE_MODELS,
    "kimi": KIMI_AVAILABLE_MODELS,
    "groq": GROQ_AVAILABLE_MODELS,
    "deepseek": DEEPSEEK_AVAILABLE_MODELS,
    "xai": XAI_AVAILABLE_MODELS,
    "openrouter": OPENROUTER_AVAILABLE_MODELS,
}
PROVIDER_DEFAULT_MODELS: dict[str, str] = {
    "claude": CLAUDE_DEFAULT_MODEL,
    "codex": CODEX_DEFAULT_MODEL,
    "gemini": GEMINI_DEFAULT_MODEL,
    "ollama": OLLAMA_DEFAULT_MODEL,
    "llamacpp": LLAMACPP_DEFAULT_MODEL,
    "mlx": MLX_DEFAULT_MODEL,
    "perplexity": PERPLEXITY_DEFAULT_MODEL,
    "mistral": MISTRAL_DEFAULT_MODEL,
    "qwen": QWEN_DEFAULT_MODEL,
    "kimi": KIMI_DEFAULT_MODEL,
    "groq": GROQ_DEFAULT_MODEL,
    "deepseek": DEEPSEEK_DEFAULT_MODEL,
    "xai": XAI_DEFAULT_MODEL,
    "openrouter": OPENROUTER_DEFAULT_MODEL,
}
PROVIDER_TIER_MODELS: dict[str, dict[str, str]] = {
    "claude": CLAUDE_TIER_MODELS,
    "codex": CODEX_TIER_MODELS,
    "gemini": GEMINI_TIER_MODELS,
    "ollama": OLLAMA_TIER_MODELS,
    "llamacpp": LLAMACPP_TIER_MODELS,
    "mlx": MLX_TIER_MODELS,
    "perplexity": PERPLEXITY_TIER_MODELS,
    "mistral": MISTRAL_TIER_MODELS,
    "qwen": QWEN_TIER_MODELS,
    "kimi": KIMI_TIER_MODELS,
    "groq": GROQ_TIER_MODELS,
    "deepseek": DEEPSEEK_TIER_MODELS,
    "xai": XAI_TIER_MODELS,
    "openrouter": OPENROUTER_TIER_MODELS,
}
DEFAULT_MODEL: str = PROVIDER_DEFAULT_MODELS.get(DEFAULT_PROVIDER, CLAUDE_DEFAULT_MODEL)
AVAILABLE_MODELS: list[str] = [model for models in PROVIDER_MODELS.values() for model in models]
PROVIDER_FALLBACK_ORDER: list[str] = [
    provider for provider in _env_csv("PROVIDER_FALLBACK_ORDER", "") if provider in AVAILABLE_PROVIDERS
]
TRANSCRIPT_REPLAY_LIMIT: int = int(_env("TRANSCRIPT_REPLAY_LIMIT", "10"))
MODEL_PRICING_USD: dict = _env_json_object("MODEL_PRICING_USD")

# --- Agent mode ---
DEFAULT_AGENT_MODE: str = _env("DEFAULT_AGENT_MODE", "autonomous")
AVAILABLE_AGENT_MODES: list[str] = ["autonomous", "supervised"]

# --- Shell ---
SHELL_TIMEOUT: int = int(_env("SHELL_TIMEOUT", "30"))
SHELL_ENABLED: bool = _env("SHELL_ENABLED", "true").lower() == "true"
SHELL_BG_MAX_PROCESSES: int = int(_env("SHELL_BG_MAX_PROCESSES", "5"))
SHELL_BG_OUTPUT_MAX: int = int(_env("SHELL_BG_OUTPUT_MAX", "8000"))

# --- File Operations ---
FILEOPS_ENABLED: bool = _env("FILEOPS_ENABLED", "true").lower() == "true"
FILEOPS_MAX_READ_SIZE: int = int(_env("FILEOPS_MAX_READ_SIZE", "1048576"))  # 1MB
FILEOPS_BLOCKED_EXTENSIONS: frozenset[str] = frozenset(
    {".env", ".key", ".pem", ".p12", ".pfx", ".jks", ".keystore", ".secret", ".credentials"}
)
BLOCKED_SHELL_PATTERN: re.Pattern = re.compile(
    # Destructive filesystem operations
    r"rm\s+-rf|mkfs|dd\s+if=|shutdown|reboot|chmod\s+777\s+/"
    # Pipe-to-shell patterns (download & execute)
    r"|curl.*\|.*(?:ba)?sh|wget.*\|.*(?:ba)?sh|>\s*/dev/sd"
    # Two-step download-then-execute bypasses
    r"|curl\s+.*(?:-o|>)\s*/tmp/.*&&.*(?:ba)?sh\s"
    r"|wget\s+.*-O\s*/tmp/.*&&.*(?:ba)?sh\s"
    # Shell wrappers around download commands
    r"|(?:ba)?sh\s+-c\s+.*(?:curl|wget)\b"
    # Python one-liner escapes
    r"|python[23]?\s+-c\s+.*(?:urllib|requests|subprocess|os\.system)"
    # Environment variable exfiltration
    r"|(?:^|\s)env(?:\s|$)|(?:^|\s)printenv(?:\s|$)|(?:^|\s)set(?:\s|$)"
    r"|/proc/self/environ|/proc/\d+/environ"
    r"|(?:^|\s)export\s+-p"
    r"|(?:^|\s)compgen\s+-e|(?:^|\s)declare\s+-[xp]"
    # Privilege escalation
    r"|(?:^|\s|;|&&|\|\|)sudo\b"
    # Dangerous system commands
    r"|(?:^|\s|;|&&|\|\|)(?:iptables|ip6tables)\b"
    r"|(?:^|\s|;|&&|\|\|)(?:mount|umount)\b"
    r"|(?:^|\s|;|&&|\|\|)fdisk\b"
    r"|(?:^|\s|;|&&|\|\|)(?:systemctl|service)\s"
    # Shared memory and device access
    r"|/dev/shm"
    # Reverse shell patterns
    r"|(?:^|\s|;|&&|\|\|)(?:nc|ncat|netcat)\s.*-[elp]"
    r"|/dev/tcp/"
    r"|(?:^|\s)socat\s",
    re.I,
)

# Token-level blocked commands (checked after regex, defense-in-depth)
BLOCKED_COMMAND_TOKENS: frozenset[str] = frozenset(
    {
        "sudo",
        "su",
        "iptables",
        "ip6tables",
        "mount",
        "umount",
        "fdisk",
        "mkfs",
        "shutdown",
        "reboot",
        "systemctl",
        "service",
        "nc",
        "ncat",
        "netcat",
        "socat",
        "chroot",
        "nsenter",
        "unshare",
        "crontab",
    }
)
ALLOWED_GIT_CMDS: set[str] = {
    "status",
    "log",
    "diff",
    "branch",
    "show",
    "stash",
    "pull",
    "push",
    "commit",
    "add",
    "checkout",
    "merge",
    "rebase",
    "fetch",
    "tag",
    "remote",
    "reset",
    "cherry-pick",
}
GIT_META_CHARS: re.Pattern = re.compile(r"[;|&`$(){}<>#!~\n\r\\]")
SENSITIVE_DIRS: frozenset[str] = frozenset(
    {
        "/etc",
        "/root",
        "/proc",
        "/sys",
        "/dev",
        "/boot",
        "/var/run",
        "/var/lib",
        # macOS resolves /var -> /private/var, /etc -> /private/etc
        "/private/etc",
        "/private/var/run",
        "/private/var/lib",
    }
)

# --- Git ---
GIT_ENABLED: bool = _env("GIT_ENABLED", "true").lower() == "true"

# --- Local runtime CLI ---
DOCKER_ENABLED: bool = _env("DOCKER_ENABLED", "false").lower() == "true"

BLOCKED_DOCKER_PATTERN: re.Pattern | None = re.compile(
    _env("BLOCKED_DOCKER_PATTERN", r"--privileged|--net=host|--pid=host|-v\s+/:/"),
    re.I,
)
ALLOWED_DOCKER_CMDS: set[str] = {
    "ps",
    "images",
    "logs",
    "inspect",
    "stats",
    "top",
    "pull",
    "build",
    "run",
    "exec",
    "stop",
    "start",
    "restart",
    "rm",
    "compose",
    "volume",
    "network",
}

# --- Package managers ---
PIP_ENABLED: bool = _env("PIP_ENABLED", "true").lower() == "true"
NPM_ENABLED: bool = _env("NPM_ENABLED", "true").lower() == "true"
_blocked_pip = _env("BLOCKED_PIP_PATTERN")
BLOCKED_PIP_PATTERN: re.Pattern | None = re.compile(_blocked_pip, re.I) if _blocked_pip else None
_blocked_npm = _env("BLOCKED_NPM_PATTERN")
BLOCKED_NPM_PATTERN: re.Pattern | None = re.compile(_blocked_npm, re.I) if _blocked_npm else None

# --- Inter-agent communication ---
INTER_AGENT_ENABLED: bool = _env("INTER_AGENT_ENABLED", "false").lower() == "true"
SQUADS_ENABLED: bool = _env("SQUADS_ENABLED", "false").lower() == "true"
INTER_AGENT_MAX_DELEGATION_DEPTH: int = int(_env("INTER_AGENT_MAX_DELEGATION_DEPTH", "3"))
INTER_AGENT_MESSAGE_TIMEOUT: int = int(_env("INTER_AGENT_MESSAGE_TIMEOUT", "60"))
# "memory" keeps the legacy in-process bus; "postgres" persists + delivers cross-process via LISTEN/NOTIFY.
INTER_AGENT_BUS_BACKEND: str = (_env("INTER_AGENT_BUS_BACKEND", "memory") or "memory").strip().lower()
SQUAD_MESSAGE_TIMEOUT_S: int = int(_env("SQUAD_MESSAGE_TIMEOUT_S", "300"))
SQUAD_INBOX_MAX_DEPTH: int = int(_env("SQUAD_INBOX_MAX_DEPTH", "200"))
SQUAD_INBOX_MAX_DELIVERY_ATTEMPTS: int = int(_env("SQUAD_INBOX_MAX_DELIVERY_ATTEMPTS", "5"))
SQUAD_BUS_LISTEN_ENABLED: bool = _env("SQUAD_BUS_LISTEN_ENABLED", "true").lower() == "true"
SQUAD_POLL_INTERVAL_S: float = float(_env("SQUAD_POLL_INTERVAL_S", "2"))
SQUAD_DEBOUNCE_MS: int = int(_env("SQUAD_DEBOUNCE_MS", "800"))
SQUAD_FANOUT_MAX_PER_TURN: int = int(_env("SQUAD_FANOUT_MAX_PER_TURN", "5"))
SQUAD_CLAIM_TTL_S: int = int(_env("SQUAD_CLAIM_TTL_S", "900"))
SQUAD_ROUTER_SWEEP_INTERVAL_S: float = float(_env("SQUAD_ROUTER_SWEEP_INTERVAL_S", "15"))
SQUAD_COORDINATOR_MODE: str = _env("SQUAD_COORDINATOR_MODE", "supervisor").strip().lower()
SQUAD_COORDINATOR_PLANNER: str = _env("SQUAD_COORDINATOR_PLANNER", "semantic_llm").strip().lower()
SQUAD_SEMANTIC_ROUTING_ENABLED: bool = _env("SQUAD_SEMANTIC_ROUTING_ENABLED", "true").lower() == "true"
SQUAD_SEMANTIC_TOP_K: int = int(_env("SQUAD_SEMANTIC_TOP_K", "5"))
SQUAD_SEMANTIC_MIN_SCORE: float = float(_env("SQUAD_SEMANTIC_MIN_SCORE", "0.28"))
SQUAD_SEMANTIC_NEGATIVE_PENALTY: float = float(_env("SQUAD_SEMANTIC_NEGATIVE_PENALTY", "0.35"))
SQUAD_COORDINATOR_LLM_TIMEOUT_S: float = float(_env("SQUAD_COORDINATOR_LLM_TIMEOUT_S", "20"))
SQUAD_OPERATOR_BREAK_GLASS_ENABLED: bool = _env("SQUAD_OPERATOR_BREAK_GLASS_ENABLED", "false").lower() == "true"
SQUAD_TELEGRAM_STRICT_ADMIN_CHECK: bool = _env("SQUAD_TELEGRAM_STRICT_ADMIN_CHECK", "true").lower() == "true"

# --- MCP Bridge ---
MCP_ENABLED: bool = _env("MCP_ENABLED", "false").lower() in ("1", "true", "yes")
MCP_OAUTH_ENABLED: bool = _env("MCP_OAUTH_ENABLED", "true").lower() in ("1", "true", "yes")
MCP_OAUTH_CALLBACK_BASE_URL: str = _env("MCP_OAUTH_CALLBACK_BASE_URL", "")

# --- PostgreSQL ---
POSTGRES_ENABLED: bool = STATE_BACKEND == "postgres" or _env("POSTGRES_ENABLED", "false").lower() == "true"
POSTGRES_URL: str = _env("POSTGRES_URL", "") or _env("KNOWLEDGE_V2_POSTGRES_DSN", "")
POSTGRES_QUERY_TIMEOUT: int = int(_env("POSTGRES_QUERY_TIMEOUT", "30"))
POSTGRES_MAX_ROWS: int = int(_env("POSTGRES_MAX_ROWS", "100"))
DB_POOL_MAX_SIZE: int = int(_env("DB_POOL_MAX_SIZE", "5"))

# --- PostgreSQL Write ---
POSTGRES_WRITE_ENABLED: bool = _env("POSTGRES_WRITE_ENABLED", "false").lower() == "true"
POSTGRES_WRITE_ENVS: list[str] = [e.strip().lower() for e in _env("POSTGRES_WRITE_ENVS", "dev").split(",") if e.strip()]
POSTGRES_WRITE_MAX_AFFECTED_ROWS: int = int(_env("POSTGRES_WRITE_MAX_AFFECTED_ROWS", "100"))
POSTGRES_WRITE_REQUIRE_WHERE: bool = _env("POSTGRES_WRITE_REQUIRE_WHERE", "true").lower() == "true"

# --- PostgreSQL SSL ---
POSTGRES_SSL_MODE: str = _env("POSTGRES_SSL_MODE", "disable")
POSTGRES_SSL_CA_CERT: str = _env("POSTGRES_SSL_CA_CERT", "")
POSTGRES_SSL_CLIENT_CERT: str = _env("POSTGRES_SSL_CLIENT_CERT", "")
POSTGRES_SSL_CLIENT_KEY: str = _env("POSTGRES_SSL_CLIENT_KEY", "")

# --- PostgreSQL SSH Tunnel ---
POSTGRES_SSH_ENABLED: bool = _env("POSTGRES_SSH_ENABLED", "false").lower() == "true"
POSTGRES_SSH_HOST: str = _env("POSTGRES_SSH_HOST", "")
POSTGRES_SSH_PORT: int = int(_env("POSTGRES_SSH_PORT", "22"))
POSTGRES_SSH_USER: str = _env("POSTGRES_SSH_USER", "")
POSTGRES_SSH_KEY_FILE: str = _env("POSTGRES_SSH_KEY_FILE", "")
POSTGRES_SSH_PASSWORD: str = _env("POSTGRES_SSH_PASSWORD", "")


# --- PostgreSQL Per-Environment Config ---
@dataclass(frozen=True)
class PostgresEnvConfig:
    url: str
    ssl_mode: str
    ssl_ca_cert: str
    ssl_client_cert: str
    ssl_client_key: str
    ssh_enabled: bool
    ssh_host: str
    ssh_port: int
    ssh_user: str
    ssh_key_file: str
    ssh_password: str


def _pg_env_config(suffix: str) -> PostgresEnvConfig | None:
    url = _env(f"POSTGRES_URL_{suffix}", "")
    if not url:
        return None
    return PostgresEnvConfig(
        url=url,
        ssl_mode=_env(f"POSTGRES_SSL_MODE_{suffix}", "disable"),
        ssl_ca_cert=_env(f"POSTGRES_SSL_CA_CERT_{suffix}", ""),
        ssl_client_cert=_env(f"POSTGRES_SSL_CLIENT_CERT_{suffix}", ""),
        ssl_client_key=_env(f"POSTGRES_SSL_CLIENT_KEY_{suffix}", ""),
        ssh_enabled=_env(f"POSTGRES_SSH_ENABLED_{suffix}", "false").lower() == "true",
        ssh_host=_env(f"POSTGRES_SSH_HOST_{suffix}", ""),
        ssh_port=int(_env(f"POSTGRES_SSH_PORT_{suffix}", "22")),
        ssh_user=_env(f"POSTGRES_SSH_USER_{suffix}", ""),
        ssh_key_file=_env(f"POSTGRES_SSH_KEY_FILE_{suffix}", ""),
        ssh_password=_env(f"POSTGRES_SSH_PASSWORD_{suffix}", ""),
    )


POSTGRES_ENV_DEV: PostgresEnvConfig | None = _pg_env_config("DEV")
POSTGRES_ENV_PROD: PostgresEnvConfig | None = _pg_env_config("PROD")

POSTGRES_ENV_DEFAULT: PostgresEnvConfig | None = (
    (
        PostgresEnvConfig(
            url=POSTGRES_URL,
            ssl_mode=POSTGRES_SSL_MODE,
            ssl_ca_cert=POSTGRES_SSL_CA_CERT,
            ssl_client_cert=POSTGRES_SSL_CLIENT_CERT,
            ssl_client_key=POSTGRES_SSL_CLIENT_KEY,
            ssh_enabled=POSTGRES_SSH_ENABLED,
            ssh_host=POSTGRES_SSH_HOST,
            ssh_port=POSTGRES_SSH_PORT,
            ssh_user=POSTGRES_SSH_USER,
            ssh_key_file=POSTGRES_SSH_KEY_FILE,
            ssh_password=POSTGRES_SSH_PASSWORD,
        )
        if POSTGRES_URL
        else None
    )
    if not POSTGRES_ENV_DEV and not POSTGRES_ENV_PROD
    else None
)

POSTGRES_AVAILABLE_ENVS: list[str] = [k for k, v in [("dev", POSTGRES_ENV_DEV), ("prod", POSTGRES_ENV_PROD)] if v] or (
    ["default"] if POSTGRES_ENV_DEFAULT else []
)

POSTGRES_ENV_CONFIGS: dict[str, PostgresEnvConfig] = {}
if POSTGRES_ENV_DEV:
    POSTGRES_ENV_CONFIGS["dev"] = POSTGRES_ENV_DEV
if POSTGRES_ENV_PROD:
    POSTGRES_ENV_CONFIGS["prod"] = POSTGRES_ENV_PROD
if POSTGRES_ENV_DEFAULT:
    POSTGRES_ENV_CONFIGS["default"] = POSTGRES_ENV_DEFAULT

# --- Workflows ---
WORKFLOW_ENABLED: bool = _env("WORKFLOW_ENABLED", "false").lower() == "true"
WORKFLOW_MAX_STEPS: int = int(_env("WORKFLOW_MAX_STEPS", "50"))
WORKFLOW_MAX_PARALLEL: int = int(_env("WORKFLOW_MAX_PARALLEL", "5"))

# --- Webhooks ---
WEBHOOK_ENABLED: bool = _env("WEBHOOK_ENABLED", "false").lower() == "true"
WEBHOOK_MAX_REGISTRATIONS: int = int(_env("WEBHOOK_MAX_REGISTRATIONS", "10"))
WEBHOOK_TIMEOUT_MAX: int = int(_env("WEBHOOK_TIMEOUT_MAX", "300"))

# --- Channel integrations ---
CHANNEL_WEBHOOK_BASE_URL: str = _env("CHANNEL_WEBHOOK_BASE_URL", "")
CHANNEL_ADAPTERS_ENABLED: bool = _env("CHANNEL_ADAPTERS_ENABLED", "true").lower() == "true"
CHANNEL_POLLING_INTERVAL: int = int(_env("CHANNEL_POLLING_INTERVAL", "2"))

# --- Browser ---
BROWSER_ENABLED: bool = _env("BROWSER_ENABLED", "false").lower() == "true"
BROWSER_NETWORK_INTERCEPTION_ENABLED: bool = _env("BROWSER_NETWORK_INTERCEPTION_ENABLED", "false").lower() == "true"
BROWSER_NETWORK_CAPTURE_LIMIT: int = int(_env("BROWSER_NETWORK_CAPTURE_LIMIT", "500"))

# --- Link Analysis ---
LINK_ANALYSIS_ENABLED: bool = _env("LINK_ANALYSIS_ENABLED", "true").lower() == "true"

# --- Whisper (audio transcription) ---
WHISPER_ENABLED: bool = _env("WHISPER_ENABLED", "true").lower() == "true"
WHISPER_BIN: str = _env("WHISPER_BIN", "whisper-cli")
WHISPER_MODEL: str = _env(
    "WHISPER_MODEL",
    str(Path.home() / ".cache" / "whisper-cpp" / "models" / "ggml-large-v3-turbo-q5_0.bin"),
)
# Directory used by the in-app downloader to place GGML model files. Defaults
# to the parent of WHISPER_MODEL so the path resolves identically to the
# whisper-cli expectations once a download completes.
WHISPER_ASSET_ROOT: str = _env(
    "WHISPER_ASSET_ROOT",
    str(Path(WHISPER_MODEL).expanduser().parent),
)
WHISPER_LANGUAGE: str = _env("WHISPER_LANGUAGE", "pt")
WHISPER_TIMEOUT: int = int(_env("WHISPER_TIMEOUT", "120"))
AUDIO_PREPROCESS: bool = _env("AUDIO_PREPROCESS", "true").lower() == "true"
_transcription_default_provider, _transcription_default_model = _functional_default("transcription")
TRANSCRIPTION_PROVIDER: str = (_transcription_default_provider or "whispercpp").strip().lower()
TRANSCRIPTION_MODEL: str = (_transcription_default_model or "whisper-cpp-local").strip()

# --- TTS (ElevenLabs + local Kokoro/Supertonic fallback) ---
_audio_default_provider, _audio_default_model = _functional_default("audio")
TTS_ENABLED: bool = _env("TTS_ENABLED", "true").lower() == "true"
_tts_default_voice = SUPERTONIC_DEFAULT_VOICE if _audio_default_provider == "supertonic" else KOKORO_DEFAULT_VOICE
TTS_DEFAULT_VOICE: str = _env("TTS_DEFAULT_VOICE", _tts_default_voice or "pf_dora")
ELEVENLABS_DEFAULT_LANGUAGE: str = _env("ELEVENLABS_DEFAULT_LANGUAGE", "pt")
TTS_MAX_CHARS: int = int(_env("TTS_MAX_CHARS", "4000"))
TTS_SPEED: float = float(_env("TTS_SPEED", "1.0"))
VOICE_SPOKEN_MAX_CHARS: int = int(_env("VOICE_SPOKEN_MAX_CHARS", "900"))

# --- ElevenLabs TTS ---
ELEVENLABS_ENABLED: bool = _env("ELEVENLABS_ENABLED", "false").lower() == "true"
ELEVENLABS_API_KEY: str | None = _env("ELEVENLABS_API_KEY")
ELEVENLABS_MODEL: str = _env(
    "ELEVENLABS_MODEL",
    _audio_default_model if _audio_default_provider == "elevenlabs" and _audio_default_model else "eleven_flash_v2_5",
)
ELEVENLABS_TIMEOUT: int = int(_env("ELEVENLABS_TIMEOUT", "30"))

# --- Rate limiting ---
RATE_LIMIT_PER_MINUTE: int = int(_env("RATE_LIMIT_PER_MINUTE", "10"))

# --- Paths (scratch only; canonical state lives in Postgres/object storage) ---
IMAGE_TEMP_DIR: Path = _resolve_writable_dir(
    _env(
        "IMAGE_TEMP_DIR",
        str(RUNTIME_EPHEMERAL_ROOT / "image-scratch"),
    )
    or str(RUNTIME_EPHEMERAL_ROOT / "image-scratch"),
    relative_to=RUNTIME_EPHEMERAL_ROOT,
    fallback_leaf="image-scratch",
)
ARTIFACT_CACHE_DIR: Path = _resolve_writable_dir(
    _env(
        "ARTIFACT_CACHE_DIR",
        str(RUNTIME_EPHEMERAL_ROOT / "artifact-scratch"),
    )
    or str(RUNTIME_EPHEMERAL_ROOT / "artifact-scratch"),
    relative_to=RUNTIME_EPHEMERAL_ROOT,
    fallback_leaf="artifact-scratch",
)
RUNTIME_ROOT_DIR: Path = _resolve_writable_dir(
    _env(
        "RUNTIME_ROOT_DIR",
        str(RUNTIME_EPHEMERAL_ROOT),
    )
    or str(RUNTIME_EPHEMERAL_ROOT),
    relative_to=RUNTIME_EPHEMERAL_ROOT,
    fallback_leaf="runtime",
)
ARTIFACT_EXTRACTION_TIMEOUT: int = int(_env("ARTIFACT_EXTRACTION_TIMEOUT", "180"))
ARTIFACT_EXTRACTION_VERSION: str = _env("ARTIFACT_EXTRACTION_VERSION", "1")

# --- Defaults ---
DEFAULT_IMAGE_PROMPT_TEXT: str = (_env("DEFAULT_IMAGE_PROMPT_TEXT", "") or "").strip()
DEFAULT_IMAGE_PROMPT: str = DEFAULT_IMAGE_PROMPT_TEXT or "Describe and analyze this image in detail."

# --- Compiled per-agent prompt injected from control-plane/runtime snapshot ---
AGENT_COMPILED_PROMPT_TEXT: str = (_env("AGENT_COMPILED_PROMPT_TEXT", "") or "").strip()

_owner_identity_block = ""
if OWNER_NAME:
    _owner_lines = [
        "## Owner Identity",
        f"- You work for **{OWNER_NAME}**. All actions you take are on their behalf.",
        "- Use the following information for commits, PRs, e-mails, and any authored content:",
        f"  - Name: {OWNER_NAME}",
    ]
    if OWNER_EMAIL:
        _owner_lines.append(f"  - Email: {OWNER_EMAIL}")
    if OWNER_GITHUB:
        _owner_lines.append(f"  - GitHub: {OWNER_GITHUB}")
    _owner_lines.append("- Never sign as AI, agent, or assistant. You represent the owner.")
    _owner_identity_block = "\n".join(_owner_lines) + "\n\n"

DEFAULT_SYSTEM_PROMPT: str = f"""\
You are Koda, an AI engineering companion delivered through Telegram,
powered by a unified coding runtime that may use Claude Code CLI or Codex CLI.

<environment>
- Responses are delivered inside Telegram messages (~4090 char limit per message).
- The user interacts through a Telegram chat interface.
- You have full filesystem access within the current working directory.
- Messages render as HTML (auto-converted from your Markdown).
  Supported: bold, italic, strikethrough, code, pre, blockquote, links.
  LaTeX is not supported.
- Code blocks over 50 lines are automatically extracted and sent as file attachments.
- File limits: 10 MB for photos, 50 MB for documents/videos.
</environment>

{_owner_identity_block}<response_format>
- Be concise. Prefer bullet points and short paragraphs over walls of text.
- Use Markdown normally — it is converted to Telegram HTML automatically.
- For code: show only the relevant snippet inline.
  If the full file is needed, use the Write tool to save it
  (the agent sends created files automatically).
- Lead with the answer or action, then provide reasoning if needed.
- Match the user's language: if they write in Portuguese, respond in Portuguese.
  If in English, respond in English.
  Keep the response in a single language.
</response_format>

<artifact_creation>
When asked to create files, images, charts, or any artifact:
1. Use the Write tool to save it — the agent auto-detects and sends created files.
2. Use descriptive filenames with proper extensions (e.g., report.html, chart.png, data.csv).
3. For HTML content (infographics, reports, visualizations):
   write a single self-contained .html file with inline CSS/JS.
4. After writing a file, describe what you created briefly — do not paste the full content in your response.
5. For images: save as .png, .jpg, .svg, or .html.
</artifact_creation>

<voice_tts>
The agent can send responses as voice notes (audio) in Telegram.
- The user controls continuous voice mode via /voice command
  (toggle on/off, change voice, list voices).
- When voice mode is ACTIVE, an additional "VOICE MODE ATIVO" section appears
  in this prompt with specific speech formatting rules.
  Follow those rules strictly because the response will be read aloud by a TTS engine.
- If a voice-active section appears, voice delivery is active for the current response.
  Never claim that voice, audio, or TTS is disabled in that response, and do not ask
  the user to enable /voice for that same response.
- When voice mode is INACTIVE, format responses normally with Markdown.
- Available voices: alice (female), bill (male), brian (male),
  pf_dora (female, local), pm_alex (male, local), pm_santa (male, local).
- If no voice-active section appears and the user asks to configure ongoing voice mode,
  guide them to /voice.
</voice_tts>

<professional_authorship>
All output must read as if written by a skilled human professional — no trace of AI involvement.

Code:
- Do not add unnecessary comments, docstrings, or type annotations to code you didn't change.
- Only add comments where the logic is genuinely non-obvious. Never add explanatory comments to self-evident code.
- Do not add "# TODO", "# NOTE", "# HACK" or similar markers unless they are genuinely needed.
- Do not over-document. Avoid verbose inline explanations that a competent developer wouldn't write.
- Match the existing code style, comment density, and documentation patterns of the project.

Commits, PRs, and communications:
- Write commit messages, PR descriptions, and emails with natural, concise language.
- Do not include AI signatures, co-authored-by tags, "generated by AI" disclaimers, or any AI attribution.
- Do not use formulaic patterns
  (numbered lists of every file changed, excessive bullet points,
  corporate-sounding summaries).
- Keep PR descriptions short and natural — like a developer explaining their own work.

Represent the owner directly in all authored content.
</professional_authorship>

<software_engineering>
Code Principles:
- Clean Code: readable, self-explanatory, well-named
- SOLID: Single Responsibility, Open/Closed, Liskov Substitution, Interface Segregation, Dependency Inversion
- KISS: simple, direct solutions — avoid unnecessary complexity
- YAGNI: implement only what is requested — focus on the current requirement
- DRY: avoid duplication; extract only when real repetition exists

Quality and Testing:
- When the project has tests, run them before considering the task complete
- Write or update unit tests for new implementations
- Ensure E2E tests are not broken if the project has them
- Prioritize coverage on critical paths and edge cases

Performance:
- Consider algorithmic complexity (Big O)
- Avoid N+1 operations, unnecessary loops, and excessive allocations
- Prefer solutions that scale with real data volume

Git:
- Conventional Commits: feat:, fix:, docs:, refactor:, test:, ci:, chore:
- Atomic commits: one logical change per commit
- Clear, descriptive commit messages — explain the "why", not just the "what"
- Create a dedicated branch for each task with a semantic name
- Require explicit owner approval before committing, pushing, or merging to
  protected branches (main/master, develop/stage), deleting branches,
  or executing CI/CD pipelines
- On merge conflicts: notify the owner, present options, and let them decide before resolving
</software_engineering>

<code_validation>
The project enforces automated validations. All must pass before considering any task complete:

1. Lint: `ruff check .` — fix all errors.
   Do not suppress rules with `# noqa` unless there is a justified,
   documented reason.
2. Formatting: `ruff format .` — apply the project's formatting standard. Never commit unformatted code.
3. Type checking: `mypy koda/ --ignore-missing-imports` —
   all new and modified code must be fully typed and pass without errors.
4. Tests: `pytest --cov=koda --cov-report=term-missing` —
   all existing tests must pass. Write or update tests for new code.
5. Run these validations locally before every commit.
   If any validation fails, fix the issue before proceeding — do not defer it.
6. Never skip or bypass validation mechanisms:
   no `--no-verify`, no disabling git hooks,
   no `type: ignore` without explicit justification,
   no removing lint rules to make code pass.
7. If a pre-existing validation failure is found
   (not caused by your changes),
   report it to the user rather than silently ignoring it
   or working around it.
8. Respect all project-configured rules in pyproject.toml
   (ruff, mypy, pytest).
   Do not override, relax, or change tool configurations
   unless the user explicitly requests it.
</code_validation>

<autonomous_work>
When executing complex tasks requiring multiple steps:
1. Read and understand the relevant code before making changes.
2. Break the task into logical phases: analyze existing code, implement changes, run tests.
3. Make changes in dependency order — interfaces before implementations, shared code before consumers.
4. Run existing tests after each significant change to catch regressions early.
5. If you encounter an unexpected error, diagnose the root cause before retrying.
6. When complete, provide a concise summary of what was done, files changed, and tests run.
7. For very long tasks: prefer incremental working solutions over one large change at the end.
</autonomous_work>

<parallel_tasks>
When the user requests more than one task simultaneously:
1. Identify and list each distinct task before starting execution.
2. Assess the complexity and scope of each task — consider files touched,
   risk of conflicts, and interdependencies.
   For trivial tasks (single-file changes, quick fixes),
   sequential execution in the same branch is fine
   even if they are independent.
3. For independent, non-trivial tasks that touch different parts of the codebase:
   - When available, use git worktrees to isolate each task in its own branch,
     preventing merge conflicts and keeping work reviewable.
   - When possible, dispatch parallel agents (subagents / agent teams)
     so tasks execute concurrently rather than sequentially.
4. For tasks that share dependencies or modify the same files:
   - Execute them sequentially in dependency order to avoid conflicts.
   - Clearly communicate to the user why sequential execution was chosen.
5. If one task fails while others are in progress,
   continue with remaining tasks,
   then report the failure with diagnosis and options for the user.
6. After all parallel work completes, summarize the results of each task,
   branches created, and any follow-up needed (e.g., merging branches).
7. Prefer concurrent execution when tasks are independent. If you must serialize parallelizable tasks, explain why.
8. All approval requirements from <software_engineering> still apply —
   do not bypass approval workflows to speed up parallel execution.
</parallel_tasks>
"""

DEFAULT_SYSTEM_PROMPT += """

<grounded_execution>
For non-trivial work, follow this sequence: plan -> gather evidence -> act -> verify -> summarize.

When the system prompt includes sourced knowledge,
treat those entries as higher-trust references than stale conversational memory.
If you rely on them, cite the source label and updated date briefly in the final answer.

Before any write-capable agent tool call, emit a structured <action_plan> with:
- summary
- assumptions
- evidence
- sources
- risk
- verification
- rollback (when the task is deploy-like)
- probable_cause (when the task is bugfix-like)
- escalation (when the task is investigation-like)
- success

If you are missing evidence or sources, gather read-only evidence first instead of forcing the write.
</grounded_execution>
"""

_default_voice_active_prompt = """\
## 🎙️ VOICE MODE ACTIVE

Your response will be converted to audio by a TTS engine and sent as a voice note on Telegram. \
Write as if speaking aloud to a person.

<voice_rules>
Voice delivery is active for this response. Do not say that voice mode, audio, or TTS is disabled. \
Do not ask the user to enable /voice for this response.

Flowing, continuous prose with no formatting. The TTS engine does not interpret bullet points, \
headers, bold, italic, code blocks, tables, or lists — those elements create broken, confusing audio.

Write the way a person speaks. Use natural transitions like "so,", "alright,", "look,", \
"actually,", "thing is,". Use short pauses with commas and ellipses, and thinking markers \
like "here's the deal...".

Keep responses short enough for comfortable listening, ideally under 60 seconds of audio. \
If the topic is complex, give a summary and offer to go deeper.

Use the user's language and the agent's configured persona. Do not force English if the \
conversation or agent prompt is in another language. Keep the spoken part concise and clear.

For long, technical, or multi-part work, prioritize a brief spoken summary and keep detailed \
steps, tables, code, logs, citations, and exact file contents in the text response or attachments.

If you need separate wording for audio, include a short <spoken_response>...</spoken_response> \
block. Keep that block self-contained, natural, and short; the runtime will use it for TTS and \
remove the tag from the visible text.

Describe URLs and file paths verbally ("in the project repo", \
"in the React official docs"). The TTS cannot pronounce URLs.

If the response needs code, say so verbally ("this answer needs code, I'll send it as text") \
and write a normal formatted response instead of trying to read code aloud.

Spell out numbers and symbols. Say "greater than" instead of ">", "equals" instead of "=", \
"slash" instead of "/". The TTS mispronounces those characters.

Use punctuation to create natural rhythm. Commas for short pauses, periods for longer pauses, \
ellipses for hesitation. Break into short, clear sentences.
</voice_rules>

<voice_example>
So, about that performance question you asked... the main issue \
is in that search function, you know? It runs a query for every result, like a loop \
of lookups. The right move would be a single query that pulls everything at once. That should \
cut the response time a lot, especially with large datasets. If you want, \
I can make that change now and send the code formatted as text.
</voice_example>
"""
VOICE_ACTIVE_PROMPT_TEXT: str = (_env("VOICE_ACTIVE_PROMPT_TEXT", "") or "").strip()
VOICE_ACTIVE_PROMPT: str = VOICE_ACTIVE_PROMPT_TEXT or _default_voice_active_prompt

SHARED_PLATFORM_PROMPT = DEFAULT_SYSTEM_PROMPT

if AGENT_COMPILED_PROMPT_TEXT:
    DEFAULT_SYSTEM_PROMPT = AGENT_COMPILED_PROMPT_TEXT + "\n\n" + SHARED_PLATFORM_PROMPT

# --- Agent Tool Loop ---
MAX_AGENT_TOOL_ITERATIONS: int = int(_env("MAX_AGENT_TOOL_ITERATIONS", "8"))
TOOL_RATE_LIMIT_PER_MINUTE: int = int(_env("TOOL_RATE_LIMIT_PER_MINUTE", "30"))
AGENT_TOOL_TIMEOUT: int = int(_env("AGENT_TOOL_TIMEOUT", "60"))
BROWSER_TOOL_TIMEOUT: int = int(_env("BROWSER_TOOL_TIMEOUT", "90"))
BROWSER_MAX_TABS: int = int(_env("BROWSER_MAX_TABS", "5"))
AGENT_ALLOWED_TOOLS: set[str] = {item for item in _env_csv("AGENT_ALLOWED_TOOLS") if item}
AGENT_TOOL_POLICY: dict = _env_json_object("AGENT_TOOL_POLICY_JSON")
AGENT_MODEL_POLICY: dict = _env_json_object("AGENT_MODEL_POLICY_JSON")
AGENT_AUTONOMY_POLICY: dict = _env_json_object("AGENT_AUTONOMY_POLICY_JSON")
AGENT_EXECUTION_POLICY: dict = _env_json_object("AGENT_EXECUTION_POLICY_JSON")
AGENT_RESOURCE_ACCESS_POLICY: dict = _env_json_object("AGENT_RESOURCE_ACCESS_POLICY_JSON")

# --- Approval policies DSL ---
APPROVAL_POLICIES_ENABLED: bool = _env("APPROVAL_POLICIES_ENABLED", "false").lower() == "true"
APPROVAL_POLICIES_PATH: str = _env("APPROVAL_POLICIES_PATH", "") or ""
APPROVAL_POLICIES_HOT_RELOAD: bool = _env("APPROVAL_POLICIES_HOT_RELOAD", "true").lower() == "true"

# --- Structured data output ---
STRUCTURED_DATA_OUTPUT_ENABLED: bool = _env("STRUCTURED_DATA_OUTPUT_ENABLED", "false").lower() == "true"

# --- Unified scheduler ---
SCHEDULER_ENABLED: bool = _env("SCHEDULER_ENABLED", "true").lower() == "true"
SCHEDULER_POLL_INTERVAL_SECONDS: int = int(_env("SCHEDULER_POLL_INTERVAL_SECONDS", "15"))
SCHEDULER_LEASE_SECONDS: int = int(_env("SCHEDULER_LEASE_SECONDS", "300"))
SCHEDULER_MAX_CATCHUP_PER_CYCLE: int = int(_env("SCHEDULER_MAX_CATCHUP_PER_CYCLE", "10"))
SCHEDULER_MAX_DISPATCH_PER_CYCLE: int = int(_env("SCHEDULER_MAX_DISPATCH_PER_CYCLE", "20"))
SCHEDULER_CATCHUP_WINDOW_HOURS: int = int(_env("SCHEDULER_CATCHUP_WINDOW_HOURS", "24"))
SCHEDULER_RUN_MAX_ATTEMPTS: int = int(_env("SCHEDULER_RUN_MAX_ATTEMPTS", "3"))
SCHEDULER_RETRY_BASE_DELAY: int = int(_env("SCHEDULER_RETRY_BASE_DELAY", "60"))
SCHEDULER_RETRY_MAX_DELAY: int = int(_env("SCHEDULER_RETRY_MAX_DELAY", "3600"))
SCHEDULER_MIN_INTERVAL_SECONDS: int = int(_env("SCHEDULER_MIN_INTERVAL_SECONDS", "60"))
SCHEDULER_MAX_CONCURRENT_RUNS_PER_JOB: int = int(_env("SCHEDULER_MAX_CONCURRENT_RUNS_PER_JOB", "1"))
SCHEDULER_NOTIFICATION_MODE: str = _env("SCHEDULER_NOTIFICATION_MODE", "summary_complete")
SCHEDULER_DEFAULT_TIMEZONE: str = _env("SCHEDULER_DEFAULT_TIMEZONE", "America/Sao_Paulo")
RUNBOOK_GOVERNANCE_ENABLED: bool = _env("RUNBOOK_GOVERNANCE_ENABLED", "true").lower() == "true"
RUNBOOK_GOVERNANCE_HOUR: int = int(_env("RUNBOOK_GOVERNANCE_HOUR", "4"))
RUNBOOK_REVALIDATION_STALE_DAYS: int = int(_env("RUNBOOK_REVALIDATION_STALE_DAYS", "30"))
RUNBOOK_REVALIDATION_MIN_VERIFIED_RUNS: int = int(_env("RUNBOOK_REVALIDATION_MIN_VERIFIED_RUNS", "3"))
RUNBOOK_REVALIDATION_MIN_SUCCESS_RATE: float = float(_env("RUNBOOK_REVALIDATION_MIN_SUCCESS_RATE", "0.80"))
RUNBOOK_REVALIDATION_CORRECTION_THRESHOLD: int = int(_env("RUNBOOK_REVALIDATION_CORRECTION_THRESHOLD", "2"))
RUNBOOK_REVALIDATION_ROLLBACK_THRESHOLD: int = int(_env("RUNBOOK_REVALIDATION_ROLLBACK_THRESHOLD", "1"))

# --- Parallel tasks ---
MAX_CONCURRENT_TASKS_PER_USER: int = int(_env("MAX_CONCURRENT_TASKS_PER_USER", "3"))
TASK_MAX_RETRY_ATTEMPTS: int = int(_env("TASK_MAX_RETRY_ATTEMPTS", "3"))
TASK_RETRY_BASE_DELAY: float = float(_env("TASK_RETRY_BASE_DELAY", "2.0"))
TASK_RETRY_MAX_DELAY: float = float(_env("TASK_RETRY_MAX_DELAY", "30.0"))
MAX_QUEUED_TASKS_PER_USER: int = int(_env("MAX_QUEUED_TASKS_PER_USER", "25"))
QUEUE_MAX_RECOVERY_ATTEMPTS: int = int(_env("QUEUE_MAX_RECOVERY_ATTEMPTS", "3"))
MAX_STANDARD_TASKS_GLOBAL: int = int(_env("MAX_STANDARD_TASKS_GLOBAL", "3"))
MAX_HEAVY_TASKS_GLOBAL: int = int(_env("MAX_HEAVY_TASKS_GLOBAL", "1"))
MAX_BROWSER_TASKS_GLOBAL: int = int(_env("MAX_BROWSER_TASKS_GLOBAL", "1"))

# --- Health endpoint (per-agent) ---
HEALTH_PORT: int = int(_env("HEALTH_PORT", "8080"))

# --- Logging & observability ---
LOG_FORMAT: str = _env("LOG_FORMAT", "console")  # 'json' for K8s, 'console' for dev
POD_NAME: str = os.environ.get("POD_NAME", "local")
NODE_NAME: str = os.environ.get("NODE_NAME", "")
POD_NAMESPACE: str = os.environ.get("POD_NAMESPACE", "")

# --- Resilience ---
MAX_CONCURRENT_TASKS_GLOBAL: int = int(_env("MAX_CONCURRENT_TASKS_GLOBAL", "10"))

# --- Runtime environments / control plane ---
RUNTIME_ENVIRONMENTS_ENABLED: bool = _env("RUNTIME_ENVIRONMENTS_ENABLED", "false").lower() == "true"
RUNTIME_EVENT_STREAM_ENABLED: bool = _env("RUNTIME_EVENT_STREAM_ENABLED", "true").lower() == "true"
RUNTIME_PTY_ENABLED: bool = _env("RUNTIME_PTY_ENABLED", "true").lower() == "true"
RUNTIME_BROWSER_LIVE_ENABLED: bool = _env("RUNTIME_BROWSER_LIVE_ENABLED", "true").lower() == "true"
RUNTIME_RECOVERY_ENABLED: bool = _env("RUNTIME_RECOVERY_ENABLED", "true").lower() == "true"
RUNTIME_FRONTEND_API_ENABLED: bool = _env("RUNTIME_FRONTEND_API_ENABLED", "true").lower() == "true"
RUNTIME_RETENTION_SUCCESS_HOURS: int = int(_env("RUNTIME_RETENTION_SUCCESS_HOURS", "24"))
RUNTIME_RETENTION_FAILURE_HOURS: int = int(_env("RUNTIME_RETENTION_FAILURE_HOURS", "72"))
RUNTIME_BUNDLE_RETENTION_DAYS: int = int(_env("RUNTIME_BUNDLE_RETENTION_DAYS", "7"))
RUNTIME_HEARTBEAT_INTERVAL_SECONDS: int = int(_env("RUNTIME_HEARTBEAT_INTERVAL_SECONDS", "15"))

# Per-task lease (crash-safe orchestration). Workers acquire a lease when
# they pick up a task, renew it every ``HEARTBEAT_SECONDS``, and release it
# on terminal state. The janitor reaps tasks whose lease has expired
# (no renewal for ``DURATION_SECONDS``) — requeueing if attempts remain or
# moving to ``failed`` when exhausted. ``DURATION`` must be ≥ 3× ``HEARTBEAT``
# so a transient renewal hiccup does not trigger a false-positive reap.
TASK_LEASE_DURATION_SECONDS: int = int(_env("TASK_LEASE_DURATION_SECONDS", "60"))
TASK_LEASE_HEARTBEAT_SECONDS: int = int(_env("TASK_LEASE_HEARTBEAT_SECONDS", "15"))
TASK_LEASE_JANITOR_INTERVAL_SECONDS: int = int(_env("TASK_LEASE_JANITOR_INTERVAL_SECONDS", "30"))
RUNTIME_STALE_AFTER_SECONDS: int = int(_env("RUNTIME_STALE_AFTER_SECONDS", "60"))
RUNTIME_RESOURCE_SAMPLE_INTERVAL_SECONDS: int = int(_env("RUNTIME_RESOURCE_SAMPLE_INTERVAL_SECONDS", "10"))
RUNTIME_RECOVERY_SWEEP_INTERVAL_SECONDS: int = int(_env("RUNTIME_RECOVERY_SWEEP_INTERVAL_SECONDS", "120"))
RUNTIME_CLEANUP_SWEEP_INTERVAL_SECONDS: int = int(_env("RUNTIME_CLEANUP_SWEEP_INTERVAL_SECONDS", "300"))
RUNTIME_LOCAL_UI_BIND: str = _env("RUNTIME_LOCAL_UI_BIND", _env("HEALTH_BIND", "127.0.0.1"))
RUNTIME_LOCAL_UI_TOKEN: str = _env("RUNTIME_LOCAL_UI_TOKEN", "")
RUNTIME_SUPERVISED_ATTACH_ENABLED: bool = _env("RUNTIME_SUPERVISED_ATTACH_ENABLED", "true").lower() == "true"

RUNTIME_OPERATOR_SESSION_TTL_SECONDS: int = int(_env("RUNTIME_OPERATOR_SESSION_TTL_SECONDS", "1800"))
RUNTIME_ATTACH_IDLE_TIMEOUT_SECONDS: int = int(_env("RUNTIME_ATTACH_IDLE_TIMEOUT_SECONDS", "900"))
BROWSER_ALLOW_PRIVATE_NETWORK: bool = _bool_env("BROWSER_ALLOW_PRIVATE_NETWORK", False)
RUNTIME_BROWSER_TRANSPORT: str = _env("RUNTIME_BROWSER_TRANSPORT", "novnc")
RUNTIME_BROWSER_DISPLAY_BASE: int = int(_env("RUNTIME_BROWSER_DISPLAY_BASE", "90"))
RUNTIME_BROWSER_VNC_BASE_PORT: int = int(_env("RUNTIME_BROWSER_VNC_BASE_PORT", "5900"))
RUNTIME_BROWSER_NOVNC_BASE_PORT: int = int(_env("RUNTIME_BROWSER_NOVNC_BASE_PORT", "6900"))
RUNTIME_PTY_CHUNK_BYTES: int = int(_env("RUNTIME_PTY_CHUNK_BYTES", "8192"))
RUNTIME_PTY_BACKPRESSURE_KB: int = int(_env("RUNTIME_PTY_BACKPRESSURE_KB", "512"))
RUNTIME_LOOP_MAX_CYCLES: int = int(_env("RUNTIME_LOOP_MAX_CYCLES", "12"))
RUNTIME_LOOP_MAX_RETRIES_PER_PHASE: int = int(_env("RUNTIME_LOOP_MAX_RETRIES_PER_PHASE", "3"))
RUNTIME_LOOP_NO_CHANGE_LIMIT: int = int(_env("RUNTIME_LOOP_NO_CHANGE_LIMIT", "2"))
RUNTIME_SAVE_VERIFY_TIMEOUT_SECONDS: int = int(_env("RUNTIME_SAVE_VERIFY_TIMEOUT_SECONDS", "30"))
RUNTIME_CHECKPOINT_MAX_UNTRACKED_BYTES: int = int(
    _env("RUNTIME_CHECKPOINT_MAX_UNTRACKED_BYTES", str(500 * 1024 * 1024))
)
# Internal service kernels now run in Rust+gRPC only.
INTERNAL_RPC_MODE: str = "rust"
INTERNAL_RPC_DEADLINE_MS: int = int(_env("INTERNAL_RPC_DEADLINE_MS", "1500"))
# process-local circuit breaker for internal gRPC clients.
# Defaults: 5 failures within 30s open the breaker for 30s. After
# cool-down a single half-open probe is allowed; on success the
# breaker closes, on failure it re-opens. Tunable per deployment but
# the defaults match what we observed during the pause/activate
# cascading-deadlock incident.
INTERNAL_RPC_BREAKER_THRESHOLD: int = int(_env("INTERNAL_RPC_BREAKER_THRESHOLD", "5"))
INTERNAL_RPC_BREAKER_WINDOW_SECONDS: float = float(_env("INTERNAL_RPC_BREAKER_WINDOW_SECONDS", "30"))
INTERNAL_RPC_BREAKER_OPEN_SECONDS: float = float(_env("INTERNAL_RPC_BREAKER_OPEN_SECONDS", "30"))
_RUNTIME_KERNEL_DEFAULT_TARGET: str = (
    _env("RUNTIME_KERNEL_GRPC_TARGET", str(RUNTIME_EPHEMERAL_ROOT / "rpc" / "runtime-kernel.sock"))
    or str(RUNTIME_EPHEMERAL_ROOT / "rpc" / "runtime-kernel.sock")
).strip()
RUNTIME_KERNEL_SOCKET: str = (
    _env("RUNTIME_KERNEL_SOCKET", _RUNTIME_KERNEL_DEFAULT_TARGET) or _RUNTIME_KERNEL_DEFAULT_TARGET
).strip()
RETRIEVAL_GRPC_TARGET: str = (_env("RETRIEVAL_GRPC_TARGET", "127.0.0.1:50062") or "127.0.0.1:50062").strip()
MEMORY_GRPC_TARGET: str = (_env("MEMORY_GRPC_TARGET", "127.0.0.1:50063") or "127.0.0.1:50063").strip()
ARTIFACT_GRPC_TARGET: str = (_env("ARTIFACT_GRPC_TARGET", "127.0.0.1:50064") or "127.0.0.1:50064").strip()
SECURITY_GRPC_TARGET: str = (_env("SECURITY_GRPC_TARGET", "127.0.0.1:50065") or "127.0.0.1:50065").strip()

# Browser features are required both for explicit browser commands and for runtime
# live-preview flows exposed through the control plane.
BROWSER_FEATURES_ENABLED: bool = BROWSER_ENABLED or RUNTIME_BROWSER_LIVE_ENABLED

# Browser session persistence — save/restore cookies and localStorage across sessions.
BROWSER_SESSION_PERSISTENCE_ENABLED: bool = _env("BROWSER_SESSION_PERSISTENCE_ENABLED", "false").lower() == "true"
BROWSER_SESSION_DIR: str = _env("BROWSER_SESSION_DIR", "")
BROWSER_SESSION_MAX_AGE: int = int(_env("BROWSER_SESSION_MAX_AGE", "86400"))

# --- Observability dashboard ---
DASHBOARD_ENABLED: bool = _env("DASHBOARD_ENABLED", "false").lower() == "true"

# --- Snapshots ---
SNAPSHOT_ENABLED: bool = _env("SNAPSHOT_ENABLED", "false").lower() == "true"
SNAPSHOT_MAX_SIZE_MB: int = int(_env("SNAPSHOT_MAX_SIZE_MB", "100"))
SNAPSHOT_RETENTION_HOURS: int = int(_env("SNAPSHOT_RETENTION_HOURS", "168"))

# --- Plugin system ---
PLUGIN_SYSTEM_ENABLED: bool = _env("PLUGIN_SYSTEM_ENABLED", "false").lower() == "true"
PLUGIN_DIRS: list[str] = [p.strip() for p in _env("PLUGIN_DIRS", "").split(",") if p.strip()]
PLUGIN_SANDBOX_ENABLED: bool = _env("PLUGIN_SANDBOX_ENABLED", "true").lower() == "true"
PLUGIN_MAX_EXECUTION_TIMEOUT: int = int(_env("PLUGIN_MAX_EXECUTION_TIMEOUT", "30"))

# --- gRPC TLS ---
GRPC_TLS_ENABLED: bool = _env("GRPC_TLS_ENABLED", "false").lower() == "true"
GRPC_TLS_CA_CERT: str = (_env("GRPC_TLS_CA_CERT") or "").strip()
GRPC_TLS_CLIENT_CERT: str = (_env("GRPC_TLS_CLIENT_CERT") or "").strip()
GRPC_TLS_CLIENT_KEY: str = (_env("GRPC_TLS_CLIENT_KEY") or "").strip()
