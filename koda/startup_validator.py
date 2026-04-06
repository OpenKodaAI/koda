"""Startup configuration validator. Fails loud on misconfiguration."""

from __future__ import annotations

import os

from koda.logging_config import get_logger

log = get_logger(__name__)


class StartupValidationError(Exception):
    """Raised when startup configuration is invalid."""


def validate_startup_config() -> list[str]:
    """Validate configuration at startup. Returns list of warnings (empty = all good).

    Raises StartupValidationError for critical misconfigurations.
    """
    warnings: list[str] = []

    from koda.config import (
        ALLOWED_USER_IDS,
        AVAILABLE_PROVIDERS,
        CODEX_APPROVAL_POLICY,
        DEFAULT_PROVIDER,
        ELEVENLABS_API_KEY,
        ELEVENLABS_ENABLED,
        GWS_CREDENTIALS_FILE,
        GWS_ENABLED,
        JIRA_API_TOKEN,
        JIRA_ENABLED,
        JIRA_URL,
        KOKORO_ENABLED,
        KOKORO_VOICES_PATH,
        OLLAMA_BASE_URL,
        OLLAMA_ENABLED,
        POSTGRES_AVAILABLE_ENVS,
        POSTGRES_ENABLED,
        POSTGRES_SSH_ENABLED,
        POSTGRES_SSH_HOST,
        POSTGRES_SSH_KEY_FILE,
        POSTGRES_URL,
        SCHEDULER_ENABLED,
    )

    # --- Critical: no authentication configured ---
    if not ALLOWED_USER_IDS:
        raise StartupValidationError(
            "ALLOWED_USER_IDS is empty. The bot would reject all messages. Set at least one Telegram user ID."
        )

    # --- Critical: no providers available ---
    if not AVAILABLE_PROVIDERS:
        raise StartupValidationError(
            "No LLM providers are enabled. Enable at least one of: "
            "CLAUDE_ENABLED, CODEX_ENABLED, GEMINI_ENABLED, OLLAMA_ENABLED."
        )

    # --- Provider-specific checks ---
    if DEFAULT_PROVIDER not in AVAILABLE_PROVIDERS:
        warnings.append(
            f"DEFAULT_PROVIDER='{DEFAULT_PROVIDER}' is not in AVAILABLE_PROVIDERS "
            f"({', '.join(AVAILABLE_PROVIDERS)}). The first available provider will be used."
        )

    if OLLAMA_ENABLED and not OLLAMA_BASE_URL:
        warnings.append("OLLAMA_ENABLED=true but OLLAMA_BASE_URL is empty. Ollama calls will fail.")

    # --- Codex approval policy ---
    valid_policies = {"never", "auto-edit", "full-auto", "suggest"}
    if CODEX_APPROVAL_POLICY and CODEX_APPROVAL_POLICY not in valid_policies:
        warnings.append(
            f"CODEX_APPROVAL_POLICY='{CODEX_APPROVAL_POLICY}' is not a recognized value "
            f"({', '.join(sorted(valid_policies))}). Codex may reject or misinterpret it."
        )

    # --- Integration credential checks ---
    if GWS_ENABLED and not GWS_CREDENTIALS_FILE:
        warnings.append("GWS_ENABLED=true but GWS_CREDENTIALS_FILE is not set. Google Workspace commands will fail.")

    if GWS_ENABLED and GWS_CREDENTIALS_FILE and not os.path.isfile(GWS_CREDENTIALS_FILE):
        warnings.append(
            f"GWS_CREDENTIALS_FILE='{GWS_CREDENTIALS_FILE}' does not exist. Google Workspace commands will fail."
        )

    if JIRA_ENABLED and (not JIRA_URL or not JIRA_API_TOKEN):
        warnings.append("JIRA_ENABLED=true but JIRA_URL or JIRA_API_TOKEN is empty. Jira commands will fail.")

    if ELEVENLABS_ENABLED and not ELEVENLABS_API_KEY:
        warnings.append("ELEVENLABS_ENABLED=true but ELEVENLABS_API_KEY is not set. ElevenLabs TTS will not work.")

    # --- Database checks ---
    if POSTGRES_ENABLED and not POSTGRES_URL and not POSTGRES_AVAILABLE_ENVS:
        warnings.append(
            "POSTGRES_ENABLED=true but no POSTGRES_URL or per-environment URLs are configured. "
            "Database queries will fail."
        )

    if POSTGRES_SSH_ENABLED and not POSTGRES_SSH_HOST:
        warnings.append("POSTGRES_SSH_ENABLED=true but POSTGRES_SSH_HOST is empty. SSH tunnel connection will fail.")

    if POSTGRES_SSH_ENABLED and POSTGRES_SSH_KEY_FILE and not os.path.isfile(POSTGRES_SSH_KEY_FILE):
        warnings.append(
            f"POSTGRES_SSH_KEY_FILE='{POSTGRES_SSH_KEY_FILE}' does not exist. SSH tunnel connection will fail."
        )

    # --- Kokoro voices path ---
    if KOKORO_ENABLED and KOKORO_VOICES_PATH and not os.path.isdir(KOKORO_VOICES_PATH):
        warnings.append(
            f"KOKORO_VOICES_PATH='{KOKORO_VOICES_PATH}' does not exist. Custom Kokoro voices will not be loaded."
        )

    # --- Log feature flags status ---
    enabled_features: list[str] = []
    if POSTGRES_ENABLED:
        enabled_features.append("postgres")
    if GWS_ENABLED:
        enabled_features.append("gws")
    if JIRA_ENABLED:
        enabled_features.append("jira")
    if ELEVENLABS_ENABLED:
        enabled_features.append("elevenlabs")
    if KOKORO_ENABLED:
        enabled_features.append("kokoro")
    if SCHEDULER_ENABLED:
        enabled_features.append("scheduler")
    if OLLAMA_ENABLED:
        enabled_features.append("ollama")

    if enabled_features:
        log.info("startup_features_enabled", features=", ".join(enabled_features))

    if warnings:
        for w in warnings:
            log.warning("startup_config_warning", message=w)

    return warnings
