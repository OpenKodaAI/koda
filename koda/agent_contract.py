"""Provider-neutral agent contract helpers shared by runtime and control plane."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class CoreToolDefinition:
    """One tool exposed by the system core and selectively enabled per agent."""

    id: str
    title: str
    category: str
    description: str
    read_only: bool | None = None
    feature_flag: str | None = None


@dataclass(frozen=True, slots=True)
class CoreProviderDefinition:
    """One LLM/runtime provider exposed by the system core."""

    id: str
    title: str
    vendor: str
    runtime_adapter: str
    description: str
    category: str = "general"
    supports_streaming: bool = True
    supports_native_resume: bool = True
    supports_tool_loop: bool = True
    supports_long_context: bool = True
    supports_images: bool = True
    supports_structured_output: bool = True
    supports_fallback_bootstrap: bool = True
    binary: str | None = None
    supported_auth_modes: tuple[str, ...] = ("api_key", "subscription_login")
    login_flow_kind: str | None = None
    requires_project_id: bool = False


_CORE_TOOL_DEFINITIONS: tuple[CoreToolDefinition, ...] = (
    CoreToolDefinition("job_list", "Scheduled jobs list", "scheduler", "List scheduled jobs.", read_only=True),
    CoreToolDefinition("job_get", "Scheduled job detail", "scheduler", "Inspect one scheduled job.", read_only=True),
    CoreToolDefinition("job_create", "Scheduled job create", "scheduler", "Create a scheduled job."),
    CoreToolDefinition("job_validate", "Scheduled job validate", "scheduler", "Queue a safe validation run."),
    CoreToolDefinition("job_activate", "Scheduled job activate", "scheduler", "Activate a validated job."),
    CoreToolDefinition("job_pause", "Scheduled job pause", "scheduler", "Pause one scheduled job."),
    CoreToolDefinition("job_resume", "Scheduled job resume", "scheduler", "Resume a paused scheduled job."),
    CoreToolDefinition("job_delete", "Scheduled job delete", "scheduler", "Archive a scheduled job."),
    CoreToolDefinition("job_run_now", "Scheduled job run now", "scheduler", "Queue an immediate manual run."),
    CoreToolDefinition("job_runs", "Scheduled job runs", "scheduler", "List recent scheduled runs.", read_only=True),
    CoreToolDefinition("cron_list", "Legacy cron list", "scheduler", "List legacy cron jobs.", read_only=True),
    CoreToolDefinition("cron_add", "Legacy cron add", "scheduler", "Create a legacy cron job."),
    CoreToolDefinition("cron_delete", "Legacy cron delete", "scheduler", "Delete a legacy cron job."),
    CoreToolDefinition("cron_toggle", "Legacy cron toggle", "scheduler", "Enable or disable a legacy cron job."),
    CoreToolDefinition("web_search", "Web search", "research", "Search the web.", read_only=True),
    CoreToolDefinition("fetch_url", "Fetch URL", "research", "Fetch one URL.", read_only=True),
    CoreToolDefinition("http_request", "HTTP request", "research", "Make an HTTP request."),
    CoreToolDefinition("agent_set_workdir", "Set workdir", "agent", "Change the agent working directory."),
    CoreToolDefinition("agent_get_status", "Agent status", "agent", "Inspect runtime status.", read_only=True),
    CoreToolDefinition(
        "browser_navigate",
        "Browser navigate",
        "browser",
        "Navigate the browser to a URL.",
        read_only=True,
        feature_flag="browser",
    ),
    CoreToolDefinition("browser_click", "Browser click", "browser", "Click one element.", feature_flag="browser"),
    CoreToolDefinition("browser_type", "Browser type", "browser", "Type into one element.", feature_flag="browser"),
    CoreToolDefinition(
        "browser_submit",
        "Browser submit",
        "browser",
        "Submit the active or selected form.",
        feature_flag="browser",
    ),
    CoreToolDefinition(
        "browser_screenshot",
        "Browser screenshot",
        "browser",
        "Capture a screenshot.",
        read_only=True,
        feature_flag="browser",
    ),
    CoreToolDefinition(
        "browser_get_text",
        "Browser get text",
        "browser",
        "Read page text content.",
        read_only=True,
        feature_flag="browser",
    ),
    CoreToolDefinition(
        "browser_get_elements",
        "Browser get elements",
        "browser",
        "List interactive elements.",
        read_only=True,
        feature_flag="browser",
    ),
    CoreToolDefinition(
        "browser_select",
        "Browser select",
        "browser",
        "Select a dropdown option.",
        feature_flag="browser",
    ),
    CoreToolDefinition(
        "browser_scroll",
        "Browser scroll",
        "browser",
        "Scroll the page.",
        read_only=True,
        feature_flag="browser",
    ),
    CoreToolDefinition(
        "browser_wait",
        "Browser wait",
        "browser",
        "Wait for page state.",
        read_only=True,
        feature_flag="browser",
    ),
    CoreToolDefinition(
        "browser_back",
        "Browser back",
        "browser",
        "Go back in history.",
        read_only=True,
        feature_flag="browser",
    ),
    CoreToolDefinition(
        "browser_forward",
        "Browser forward",
        "browser",
        "Go forward in history.",
        read_only=True,
        feature_flag="browser",
    ),
    CoreToolDefinition("browser_hover", "Browser hover", "browser", "Hover one element.", feature_flag="browser"),
    CoreToolDefinition(
        "browser_press_key",
        "Browser press key",
        "browser",
        "Press one key.",
        feature_flag="browser",
    ),
    CoreToolDefinition(
        "browser_cookies",
        "Browser cookies",
        "browser",
        "Read or set cookies.",
        feature_flag="browser",
    ),
    CoreToolDefinition(
        "db_query",
        "Database query",
        "database",
        "Run a read-only SQL query.",
        read_only=True,
        feature_flag="postgres",
    ),
    CoreToolDefinition(
        "db_schema",
        "Database schema",
        "database",
        "Inspect database schema.",
        read_only=True,
        feature_flag="postgres",
    ),
    CoreToolDefinition(
        "db_explain",
        "Database explain",
        "database",
        "Explain one query.",
        read_only=True,
        feature_flag="postgres",
    ),
    CoreToolDefinition(
        "db_switch_env",
        "Database switch env",
        "database",
        "Switch the active database environment.",
        feature_flag="postgres",
    ),
    CoreToolDefinition(
        "gws",
        "Google Workspace",
        "integration",
        "Execute Google Workspace commands.",
        feature_flag="gws",
    ),
    CoreToolDefinition("jira", "Jira", "integration", "Execute Jira commands.", feature_flag="jira"),
    CoreToolDefinition(
        "confluence",
        "Confluence",
        "integration",
        "Execute Confluence commands.",
        feature_flag="confluence",
    ),
    CoreToolDefinition("script_search", "Script search", "library", "Search saved scripts.", read_only=True),
    CoreToolDefinition("script_list", "Script list", "library", "List saved scripts.", read_only=True),
    CoreToolDefinition("script_save", "Script save", "library", "Save or update one script."),
    CoreToolDefinition("script_delete", "Script delete", "library", "Delete one saved script."),
    CoreToolDefinition("cache_stats", "Cache stats", "runtime", "Read cache statistics.", read_only=True),
    CoreToolDefinition("cache_clear", "Cache clear", "runtime", "Clear runtime caches."),
)

CORE_TOOL_CATALOG: dict[str, CoreToolDefinition] = {definition.id: definition for definition in _CORE_TOOL_DEFINITIONS}
CORE_TOOL_IDS: tuple[str, ...] = tuple(CORE_TOOL_CATALOG)

_CORE_PROVIDER_DEFINITIONS: tuple[CoreProviderDefinition, ...] = (
    CoreProviderDefinition(
        id="claude",
        title="Anthropic",
        vendor="Anthropic",
        runtime_adapter="claude_runner",
        description="Primary Anthropic runtime integration for agent execution.",
        binary="claude",
        login_flow_kind="browser",
    ),
    CoreProviderDefinition(
        id="codex",
        title="OpenAI",
        vendor="OpenAI",
        runtime_adapter="codex_runner",
        description="Codex CLI/runtime integration used for provider-neutral fallback and execution.",
        binary="codex",
        login_flow_kind="device_auth",
    ),
    CoreProviderDefinition(
        id="gemini",
        title="Google",
        vendor="Google",
        runtime_adapter="gemini_runner",
        description="Gemini CLI/runtime integration used for Google AI Studio and Sign in with Google flows.",
        binary="gemini",
        supports_native_resume=False,
        supports_images=True,
        login_flow_kind="browser",
        requires_project_id=False,
    ),
    CoreProviderDefinition(
        id="ollama",
        title="Ollama",
        vendor="Ollama",
        runtime_adapter="ollama_runner",
        description="Modelos locais ou cloud via Ollama.",
        category="general",
        supports_native_resume=False,
        supports_fallback_bootstrap=False,
        binary="ollama",
        supported_auth_modes=("local", "api_key"),
        login_flow_kind=None,
    ),
    CoreProviderDefinition(
        id="elevenlabs",
        title="ElevenLabs",
        vendor="ElevenLabs",
        runtime_adapter="elevenlabs_runner",
        description="Síntese de voz e música com qualidade premium.",
        category="voice",
        supports_streaming=True,
        supports_native_resume=False,
        supports_tool_loop=False,
        supports_long_context=False,
        supports_images=False,
        supports_structured_output=False,
        supports_fallback_bootstrap=False,
        binary=None,
        supported_auth_modes=("api_key",),
        login_flow_kind=None,
    ),
    CoreProviderDefinition(
        id="kokoro",
        title="Kokoro",
        vendor="Kokoro",
        runtime_adapter="kokoro_runner",
        description="Vozes leves e rápidas para TTS.",
        category="voice",
        supports_streaming=True,
        supports_native_resume=False,
        supports_tool_loop=False,
        supports_long_context=False,
        supports_images=False,
        supports_structured_output=False,
        supports_fallback_bootstrap=False,
        binary=None,
        supported_auth_modes=("none",),
        login_flow_kind=None,
    ),
    CoreProviderDefinition(
        id="whispercpp",
        title="Whisper CPP",
        vendor="Open Source",
        runtime_adapter="whispercpp_runner",
        description="Transcricao local gratuita com whisper.cpp executada na API do agent.",
        category="infra",
        supports_streaming=False,
        supports_native_resume=False,
        supports_tool_loop=False,
        supports_long_context=False,
        supports_images=False,
        supports_structured_output=False,
        supports_fallback_bootstrap=False,
        binary="whisper-cli",
        supported_auth_modes=("none",),
        login_flow_kind=None,
    ),
    CoreProviderDefinition(
        id="sora",
        title="Sora",
        vendor="OpenAI",
        runtime_adapter="sora_runner",
        description="Geração de imagens e vídeos via OpenAI.",
        category="media",
        supports_streaming=False,
        supports_native_resume=False,
        supports_tool_loop=False,
        supports_long_context=False,
        supports_images=True,
        supports_structured_output=False,
        supports_fallback_bootstrap=False,
        binary=None,
        supported_auth_modes=("api_key",),
        login_flow_kind=None,
    ),
)

CORE_PROVIDER_CATALOG: dict[str, CoreProviderDefinition] = {
    definition.id: definition for definition in _CORE_PROVIDER_DEFINITIONS
}
CORE_PROVIDER_IDS: tuple[str, ...] = tuple(CORE_PROVIDER_CATALOG)

APPROVAL_MODES: frozenset[str] = frozenset({"read_only", "supervised", "guarded", "escalation_required"})
AUTONOMY_TIERS: frozenset[str] = frozenset({"t0", "t1", "t2"})
PROMOTION_MODES: frozenset[str] = frozenset({"review_queue"})


def normalize_string_list(value: Any) -> list[str]:
    """Return a trimmed string list from a heterogeneous payload."""
    if value is None:
        return []
    if isinstance(value, str):
        raw_items = value.split(",")
    elif isinstance(value, (list, tuple, set, frozenset)):
        raw_items = [str(item) for item in value]
    else:
        return []
    result: list[str] = []
    for item in raw_items:
        normalized = str(item).strip()
        if normalized and normalized not in result:
            result.append(normalized)
    return result


def resolve_feature_filtered_tools(feature_flags: dict[str, bool] | None = None) -> list[dict[str, Any]]:
    """Return the core tool catalog annotated with feature availability."""
    flags = feature_flags or {}
    items: list[dict[str, Any]] = []
    for definition in _CORE_TOOL_DEFINITIONS:
        available = True
        if definition.feature_flag:
            available = bool(flags.get(definition.feature_flag, False))
        items.append(
            {
                "id": definition.id,
                "title": definition.title,
                "category": definition.category,
                "description": definition.description,
                "read_only": definition.read_only,
                "feature_flag": definition.feature_flag,
                "available": available,
            }
        )
    return items


def resolve_allowed_tool_ids(
    policy: dict[str, Any] | None,
    *,
    feature_flags: dict[str, bool] | None = None,
) -> list[str]:
    """Resolve the effective allowed core tool ids for one agent."""
    available_catalog = resolve_feature_filtered_tools(feature_flags)
    available_ids = [str(item["id"]) for item in available_catalog if bool(item["available"])]
    if not policy:
        return available_ids

    raw_allowed = normalize_string_list(policy.get("allowed_tool_ids"))
    if not raw_allowed:
        return available_ids
    return [tool_id for tool_id in raw_allowed if tool_id in available_ids]


def tool_subset_summary(tool_ids: list[str]) -> dict[str, Any]:
    """Summarize a tool subset for diagnostics and UI display."""
    categories: dict[str, int] = {}
    for tool_id in tool_ids:
        definition = CORE_TOOL_CATALOG.get(tool_id)
        category = definition.category if definition else "unknown"
        categories[category] = categories.get(category, 0) + 1
    return {"count": len(tool_ids), "categories": categories}


def resolve_core_provider_catalog() -> list[dict[str, Any]]:
    """Return the provider catalog in a UI/API-friendly format."""
    return [
        {
            "id": definition.id,
            "provider": definition.id,
            "title": definition.title,
            "vendor": definition.vendor,
            "runtime_adapter": definition.runtime_adapter,
            "description": definition.description,
            "supports_streaming": definition.supports_streaming,
            "supports_native_resume": definition.supports_native_resume,
            "supports_tool_loop": definition.supports_tool_loop,
            "supports_long_context": definition.supports_long_context,
            "supports_images": definition.supports_images,
            "supports_structured_output": definition.supports_structured_output,
            "supports_fallback_bootstrap": definition.supports_fallback_bootstrap,
            "category": definition.category,
            "binary": definition.binary,
            "supported_auth_modes": list(definition.supported_auth_modes),
            "supports_api_key": "api_key" in definition.supported_auth_modes,
            "supports_subscription_login": "subscription_login" in definition.supported_auth_modes,
            "login_flow_kind": definition.login_flow_kind,
            "requires_project_id": definition.requires_project_id,
        }
        for definition in _CORE_PROVIDER_DEFINITIONS
    ]
