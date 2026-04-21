"""Provider-neutral agent contract helpers shared by runtime and control plane."""

from __future__ import annotations

import hashlib
import ipaddress
import json
import re
import shlex
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlparse


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
    connection_managed: bool = False
    show_in_settings: bool = True


RUNTIME_CONSTRAINT_KEYS: frozenset[str] = frozenset(
    {
        "allowed_domains",
        "allowed_paths",
        "allowed_db_envs",
        "allow_private_network",
        "read_only_mode",
    }
)

CONNECTION_STRATEGIES: frozenset[str] = frozenset(
    {
        "none",
        "api_key",
        "connection_string",
        "dual_token",
        "local_path",
        "local_app",
        "oauth_only",
        "oauth_preferred",
    }
)


@dataclass(frozen=True, slots=True)
class ConnectionField:
    """One credential/config field declared by a ConnectionProfile."""

    key: str
    label: str
    required: bool = True
    input_type: str = "password"
    help: str | None = None


@dataclass(frozen=True, slots=True)
class ConnectionProfile:
    """Declarative description of how an integration is connected.

    The frontend uses `strategy` to pick the matching sub-form; only the fields
    relevant to that strategy are rendered. Unused optional fields stay empty.
    """

    strategy: str
    oauth_provider: str | None = None
    oauth_scopes: tuple[str, ...] = ()
    fields: tuple[ConnectionField, ...] = ()
    scope_fields: tuple[ConnectionField, ...] = ()
    read_only_toggle: ConnectionField | None = None
    path_argument: ConnectionField | None = None
    local_app_name: str | None = None
    local_app_detection_hint: str | None = None

    def __post_init__(self) -> None:
        if self.strategy not in CONNECTION_STRATEGIES:
            raise ValueError(f"Unknown connection strategy: {self.strategy}")


@dataclass(frozen=True, slots=True)
class CoreIntegrationDefinition:
    """One integration surface exposed by the core runtime."""

    id: str
    title: str
    description: str
    transport: str
    auth_modes: tuple[str, ...] = ("none",)
    risk_class: str = "read"
    default_approval_mode: str = "guarded"
    required_secrets: tuple[str, ...] = ()
    required_env: tuple[str, ...] = ()
    timeout: int | None = None
    health_probe: str | None = None
    supports_persistence: bool = False
    connection_profile: ConnectionProfile | None = None
    runtime_constraints: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class IntegrationActionResolution:
    """Resolved integration/action envelope for one runtime tool call."""

    integration_id: str
    action_id: str
    access_level: str
    transport: str
    risk_class: str
    default_approval_mode: str
    tool_id: str
    auth_modes: tuple[str, ...] = ()
    domain: str | None = None
    db_env: str | None = None
    path: str | None = None
    private_network: bool = False
    resource_method: str | None = None


@dataclass(frozen=True, slots=True)
class GwsActionResolution:
    """Canonical Google Workspace action derived from CLI args."""

    service: str
    action_id: str
    resource_method: str
    access_level: str


@dataclass(frozen=True, slots=True)
class IntegrationGrantDecision:
    """Final allow/deny decision for one integration action."""

    allowed: bool
    integration_id: str
    action_id: str
    access_level: str
    transport: str
    risk_class: str
    default_approval_mode: str
    auth_mode: str
    reason: str | None = None
    grant: dict[str, Any] | None = None
    sensitive_access_used: bool = False


@dataclass(frozen=True, slots=True)
class ActionEnvelope:
    """Canonical execution envelope used by the central policy gate."""

    tool_id: str
    integration_id: str
    action_id: str
    transport: str
    access_level: str
    risk_class: str
    effect_tags: tuple[str, ...] = ()
    resource_method: str | None = None
    server_key: str | None = None
    domain: str | None = None
    path: str | None = None
    db_env: str | None = None
    private_network: bool = False
    uses_secrets: bool = False
    bulk_operation: bool = False
    external_side_effect: bool = False
    catalogued: bool = False
    resource_scope_fingerprint: str = ""
    params_fingerprint: str = ""


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
        "browser_network_capture_start",
        "Browser capture start",
        "browser",
        "Start network capture.",
        feature_flag="browser_network",
    ),
    CoreToolDefinition(
        "browser_network_capture_stop",
        "Browser capture stop",
        "browser",
        "Stop network capture.",
        feature_flag="browser_network",
    ),
    CoreToolDefinition(
        "browser_network_requests",
        "Browser captured requests",
        "browser",
        "Get captured requests.",
        read_only=True,
        feature_flag="browser_network",
    ),
    CoreToolDefinition(
        "browser_network_mock",
        "Browser mock route",
        "browser",
        "Mock a URL pattern.",
        feature_flag="browser_network",
    ),
    CoreToolDefinition(
        "browser_session_save",
        "Browser session save",
        "browser",
        "Save browser session.",
        feature_flag="browser_session",
    ),
    CoreToolDefinition(
        "browser_session_restore",
        "Browser session restore",
        "browser",
        "Restore browser session.",
        feature_flag="browser_session",
    ),
    CoreToolDefinition(
        "browser_session_list",
        "Browser session list",
        "browser",
        "List saved sessions.",
        read_only=True,
        feature_flag="browser_session",
    ),
    CoreToolDefinition("browser_tab_open", "Browser tab open", "browser", "Open new tab.", feature_flag="browser"),
    CoreToolDefinition("browser_tab_close", "Browser tab close", "browser", "Close a tab.", feature_flag="browser"),
    CoreToolDefinition(
        "browser_tab_switch", "Browser tab switch", "browser", "Switch active tab.", feature_flag="browser"
    ),
    CoreToolDefinition(
        "browser_tab_list", "Browser tab list", "browser", "List open tabs.", read_only=True, feature_flag="browser"
    ),
    CoreToolDefinition(
        "browser_tab_compare",
        "Browser tab compare",
        "browser",
        "Compare tab contents.",
        read_only=True,
        feature_flag="browser",
    ),
    CoreToolDefinition(
        "browser_execute_js", "Browser JS", "browser", "Execute JavaScript in page.", feature_flag="browser"
    ),
    CoreToolDefinition("browser_download", "Browser download", "browser", "Download a file.", feature_flag="browser"),
    CoreToolDefinition(
        "browser_upload", "Browser upload", "browser", "Upload a file to input.", feature_flag="browser"
    ),
    CoreToolDefinition(
        "browser_set_viewport", "Browser viewport", "browser", "Change viewport size.", feature_flag="browser"
    ),
    CoreToolDefinition(
        "browser_pdf", "Browser PDF", "browser", "Generate page PDF.", read_only=True, feature_flag="browser"
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
    CoreToolDefinition(
        "snapshot_save",
        "Snapshot save",
        "snapshots",
        "Save a named environment snapshot.",
        feature_flag="snapshots",
    ),
    CoreToolDefinition(
        "snapshot_restore",
        "Snapshot restore",
        "snapshots",
        "Load a saved environment snapshot.",
        read_only=True,
        feature_flag="snapshots",
    ),
    CoreToolDefinition(
        "snapshot_list",
        "Snapshot list",
        "snapshots",
        "List saved environment snapshots.",
        read_only=True,
        feature_flag="snapshots",
    ),
    CoreToolDefinition(
        "snapshot_diff",
        "Snapshot diff",
        "snapshots",
        "Compare two environment snapshots.",
        read_only=True,
        feature_flag="snapshots",
    ),
    CoreToolDefinition(
        "snapshot_delete",
        "Snapshot delete",
        "snapshots",
        "Delete a saved environment snapshot.",
        feature_flag="snapshots",
    ),
    CoreToolDefinition(
        "webhook_register",
        "Webhook register",
        "webhook",
        "Register a webhook endpoint.",
        feature_flag="webhooks",
    ),
    CoreToolDefinition(
        "webhook_unregister",
        "Webhook unregister",
        "webhook",
        "Remove a webhook.",
        feature_flag="webhooks",
    ),
    CoreToolDefinition(
        "webhook_list",
        "Webhook list",
        "webhook",
        "List registered webhooks.",
        read_only=True,
        feature_flag="webhooks",
    ),
    CoreToolDefinition(
        "event_wait",
        "Event wait",
        "webhook",
        "Wait for an event.",
        read_only=True,
        feature_flag="webhooks",
    ),
    CoreToolDefinition(
        "file_read", "File read", "fileops", "Read file contents.", read_only=True, feature_flag="fileops"
    ),
    CoreToolDefinition("file_write", "File write", "fileops", "Create or overwrite a file.", feature_flag="fileops"),
    CoreToolDefinition(
        "file_edit", "File edit", "fileops", "Edit a file by string replacement.", feature_flag="fileops"
    ),
    CoreToolDefinition(
        "file_list", "File list", "fileops", "List directory contents.", read_only=True, feature_flag="fileops"
    ),
    CoreToolDefinition(
        "file_search", "File search", "fileops", "Search files by glob pattern.", read_only=True, feature_flag="fileops"
    ),
    CoreToolDefinition(
        "file_grep", "File grep", "fileops", "Search file contents.", read_only=True, feature_flag="fileops"
    ),
    CoreToolDefinition("file_delete", "File delete", "fileops", "Delete a file.", feature_flag="fileops"),
    CoreToolDefinition("file_move", "File move", "fileops", "Move or rename a file.", feature_flag="fileops"),
    CoreToolDefinition(
        "file_info", "File info", "fileops", "Get file metadata.", read_only=True, feature_flag="fileops"
    ),
    CoreToolDefinition("shell_execute", "Shell execute", "shell", "Execute a shell command.", feature_flag="shell"),
    CoreToolDefinition("shell_bg", "Shell background", "shell", "Execute command in background.", feature_flag="shell"),
    CoreToolDefinition(
        "shell_status", "Shell status", "shell", "Check background process.", read_only=True, feature_flag="shell"
    ),
    CoreToolDefinition("shell_kill", "Shell kill", "shell", "Kill background process.", feature_flag="shell"),
    CoreToolDefinition(
        "shell_output", "Shell output", "shell", "Read background process output.", read_only=True, feature_flag="shell"
    ),
    CoreToolDefinition(
        "git_status", "Git status", "git", "Show working tree status.", read_only=True, feature_flag="git"
    ),
    CoreToolDefinition("git_diff", "Git diff", "git", "Show changes.", read_only=True, feature_flag="git"),
    CoreToolDefinition("git_log", "Git log", "git", "Show commit history.", read_only=True, feature_flag="git"),
    CoreToolDefinition("git_commit", "Git commit", "git", "Create a commit.", feature_flag="git"),
    CoreToolDefinition("git_branch", "Git branch", "git", "List or create branches.", feature_flag="git"),
    CoreToolDefinition("git_checkout", "Git checkout", "git", "Switch branch or restore files.", feature_flag="git"),
    CoreToolDefinition("git_push", "Git push", "git", "Push to remote.", feature_flag="git"),
    CoreToolDefinition("git_pull", "Git pull", "git", "Pull from remote.", feature_flag="git"),
    CoreToolDefinition(
        "plugin_list", "Plugin list", "plugin", "List installed plugins.", read_only=True, feature_flag="plugins"
    ),
    CoreToolDefinition(
        "plugin_info", "Plugin info", "plugin", "Plugin details.", read_only=True, feature_flag="plugins"
    ),
    CoreToolDefinition("plugin_install", "Plugin install", "plugin", "Install a plugin.", feature_flag="plugins"),
    CoreToolDefinition("plugin_uninstall", "Plugin uninstall", "plugin", "Uninstall a plugin.", feature_flag="plugins"),
    CoreToolDefinition("plugin_reload", "Plugin reload", "plugin", "Reload a plugin.", feature_flag="plugins"),
    CoreToolDefinition(
        "workflow_create",
        "Workflow create",
        "workflow",
        "Create a multi-step workflow.",
        feature_flag="workflows",
    ),
    CoreToolDefinition(
        "workflow_run",
        "Workflow run",
        "workflow",
        "Run a saved workflow.",
        feature_flag="workflows",
    ),
    CoreToolDefinition(
        "workflow_list",
        "Workflow list",
        "workflow",
        "List saved workflows.",
        read_only=True,
        feature_flag="workflows",
    ),
    CoreToolDefinition(
        "workflow_get",
        "Workflow get",
        "workflow",
        "Get workflow details.",
        read_only=True,
        feature_flag="workflows",
    ),
    CoreToolDefinition(
        "workflow_delete",
        "Workflow delete",
        "workflow",
        "Delete a saved workflow.",
        feature_flag="workflows",
    ),
    CoreToolDefinition(
        "agent_send",
        "Agent send",
        "agent_comm",
        "Send a message to another agent.",
        feature_flag="inter_agent",
    ),
    CoreToolDefinition(
        "agent_receive",
        "Agent receive",
        "agent_comm",
        "Receive the next message from inbox.",
        read_only=True,
        feature_flag="inter_agent",
    ),
    CoreToolDefinition(
        "agent_delegate",
        "Agent delegate",
        "agent_comm",
        "Delegate a task to another agent and wait for result.",
        feature_flag="inter_agent",
    ),
    CoreToolDefinition(
        "agent_list_agents",
        "Agent list",
        "agent_comm",
        "List known agents and inbox status.",
        read_only=True,
        feature_flag="inter_agent",
    ),
    CoreToolDefinition(
        "agent_broadcast",
        "Agent broadcast",
        "agent_comm",
        "Broadcast a message to all known agents.",
        feature_flag="inter_agent",
    ),
)

CORE_TOOL_CATALOG: dict[str, CoreToolDefinition] = {definition.id: definition for definition in _CORE_TOOL_DEFINITIONS}
CORE_TOOL_IDS: tuple[str, ...] = tuple(CORE_TOOL_CATALOG)

_CORE_PROVIDER_DEFINITIONS: tuple[CoreProviderDefinition, ...] = (
    CoreProviderDefinition(
        id="claude",
        title="Anthropic",
        vendor="Anthropic",
        runtime_adapter="claude_runner",
        description=(
            "Anthropic via API key, Claude subscription login (Koda spawns "
            "``claude setup-token`` in a PTY and forwards the operator's "
            "authorization code to the CLI's stdin), or local Claude Code CLI "
            "when the operator has already authenticated the binary on a "
            "mounted CLAUDE_CONFIG_DIR."
        ),
        binary="claude",
        supported_auth_modes=("api_key", "subscription_login", "local"),
        login_flow_kind="browser",
        connection_managed=True,
    ),
    CoreProviderDefinition(
        id="codex",
        title="OpenAI",
        vendor="OpenAI",
        runtime_adapter="codex_runner",
        description="Codex CLI/runtime integration used for provider-neutral fallback and execution.",
        binary="codex",
        login_flow_kind="device_auth",
        connection_managed=True,
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
        connection_managed=True,
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
        connection_managed=True,
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
        connection_managed=True,
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
        show_in_settings=False,
    ),
)

CORE_PROVIDER_CATALOG: dict[str, CoreProviderDefinition] = {
    definition.id: definition for definition in _CORE_PROVIDER_DEFINITIONS
}
CORE_PROVIDER_IDS: tuple[str, ...] = tuple(CORE_PROVIDER_CATALOG)

_CORE_INTEGRATION_DEFINITIONS: tuple[CoreIntegrationDefinition, ...] = (
    CoreIntegrationDefinition(
        id="scheduler",
        title="Scheduler",
        description="Scheduled jobs, cron compatibility, and validation runs.",
        transport="internal",
        risk_class="write",
        health_probe="scheduler_runtime",
        supports_persistence=True,
    ),
    CoreIntegrationDefinition(
        id="web",
        title="Web & HTTP",
        description="Web search, URL fetch, and governed HTTP requests.",
        transport="http",
        risk_class="write",
        health_probe="external_http",
        runtime_constraints=("allowed_domains", "allow_private_network"),
    ),
    CoreIntegrationDefinition(
        id="agent_runtime",
        title="Agent Runtime",
        description="Runtime-local state like workdir and execution status.",
        transport="runtime",
        risk_class="write",
        supports_persistence=True,
    ),
    CoreIntegrationDefinition(
        id="browser",
        title="Browser",
        description="Task-scoped browser automation.",
        transport="browser",
        risk_class="write",
        required_env=("BROWSER_ENABLED",),
        health_probe="browser_manager",
        supports_persistence=True,
        runtime_constraints=("allowed_domains", "allow_private_network"),
    ),
    CoreIntegrationDefinition(
        id="gws",
        title="Google Workspace",
        description="Governed Google Workspace CLI and service-account credentials.",
        transport="cli",
        auth_modes=("service_account", "service_account_key"),
        risk_class="write",
        required_env=(),
        health_probe="credentials_file",
        supports_persistence=True,
        connection_profile=ConnectionProfile(
            strategy="api_key",
            fields=(
                ConnectionField(
                    key="GOOGLE_APPLICATION_CREDENTIALS",
                    label="Service Account JSON (caminho ou conteúdo)",
                    required=True,
                    input_type="textarea",
                    help="Cole o JSON do service account ou o caminho absoluto do arquivo.",
                ),
            ),
        ),
        runtime_constraints=("allowed_domains", "allow_private_network"),
    ),
    CoreIntegrationDefinition(
        id="jira",
        title="Jira",
        description="Governed Jira operations and deep issue context.",
        transport="api",
        auth_modes=("api_token",),
        risk_class="write",
        required_secrets=("JIRA_API_TOKEN",),
        required_env=("JIRA_URL", "JIRA_USERNAME"),
        health_probe="credential_presence",
        supports_persistence=True,
        connection_profile=ConnectionProfile(
            strategy="api_key",
            fields=(
                ConnectionField(key="JIRA_URL", label="URL do site Jira", input_type="text"),
                ConnectionField(key="JIRA_USERNAME", label="Usuário (email)", input_type="text"),
                ConnectionField(key="JIRA_API_TOKEN", label="API Token", input_type="password"),
            ),
        ),
    ),
    CoreIntegrationDefinition(
        id="confluence",
        title="Confluence",
        description="Governed Confluence document access and mutations.",
        transport="api",
        auth_modes=("api_token",),
        risk_class="write",
        required_secrets=("CONFLUENCE_API_TOKEN",),
        required_env=("CONFLUENCE_URL", "CONFLUENCE_USERNAME"),
        health_probe="credential_presence",
        supports_persistence=True,
        connection_profile=ConnectionProfile(
            strategy="api_key",
            fields=(
                ConnectionField(key="CONFLUENCE_URL", label="URL do site Confluence", input_type="text"),
                ConnectionField(key="CONFLUENCE_USERNAME", label="Usuário (email)", input_type="text"),
                ConnectionField(key="CONFLUENCE_API_TOKEN", label="API Token", input_type="password"),
            ),
        ),
    ),
    CoreIntegrationDefinition(
        id="aws",
        title="AWS",
        description="Governed AWS profiles, regions, and CLI-backed runtime access.",
        transport="cli",
        auth_modes=("assume_role", "access_key", "local_session"),
        risk_class="write",
        required_env=("AWS_DEFAULT_REGION",),
        health_probe="sts_caller_identity",
        supports_persistence=True,
        connection_profile=ConnectionProfile(
            strategy="api_key",
            fields=(
                ConnectionField(key="AWS_ACCESS_KEY_ID", label="Access Key ID", input_type="password"),
                ConnectionField(key="AWS_SECRET_ACCESS_KEY", label="Secret Access Key", input_type="password"),
                ConnectionField(key="AWS_DEFAULT_REGION", label="Região padrão", input_type="text"),
            ),
            scope_fields=(
                ConnectionField(
                    key="AWS_SESSION_TOKEN",
                    label="Session Token (opcional)",
                    required=False,
                    input_type="password",
                ),
            ),
        ),
        runtime_constraints=("allowed_db_envs",),
    ),
    CoreIntegrationDefinition(
        id="script_library",
        title="Script Library",
        description="Saved script search and lifecycle operations.",
        transport="internal",
        risk_class="write",
        supports_persistence=True,
    ),
    CoreIntegrationDefinition(
        id="cache",
        title="Cache",
        description="Runtime cache inspection and invalidation.",
        transport="internal",
        risk_class="write",
        supports_persistence=True,
    ),
    CoreIntegrationDefinition(
        id="shell",
        title="Shell",
        description="Governed local shell execution.",
        transport="cli",
        risk_class="destructive",
        health_probe="binary_exec",
        runtime_constraints=("allowed_paths",),
    ),
    CoreIntegrationDefinition(
        id="git",
        title="Git",
        description="Governed git command execution.",
        transport="cli",
        risk_class="write",
        health_probe="binary_exec",
        runtime_constraints=("allowed_paths",),
    ),
    CoreIntegrationDefinition(
        id="gh",
        title="GitHub CLI",
        description="Governed GitHub CLI execution.",
        transport="cli",
        auth_modes=("local_session", "token"),
        risk_class="write",
        health_probe="gh_api_user",
        supports_persistence=True,
        connection_profile=ConnectionProfile(
            strategy="local_app",
            local_app_name="GitHub CLI (gh)",
            local_app_detection_hint="Execute `gh auth login` no terminal para autenticar.",
            fields=(
                ConnectionField(
                    key="GITHUB_PERSONAL_ACCESS_TOKEN",
                    label="Personal Access Token (fallback)",
                    required=False,
                    input_type="password",
                    help="Opcional: use apenas quando `gh auth login` não for viável.",
                ),
            ),
        ),
    ),
    CoreIntegrationDefinition(
        id="glab",
        title="GitLab CLI",
        description="Governed GitLab CLI execution.",
        transport="cli",
        auth_modes=("local_session", "token"),
        risk_class="write",
        health_probe="glab_api_user",
        supports_persistence=True,
        connection_profile=ConnectionProfile(
            strategy="local_app",
            local_app_name="GitLab CLI (glab)",
            local_app_detection_hint="Execute `glab auth login` no terminal para autenticar.",
            fields=(
                ConnectionField(
                    key="GITLAB_PERSONAL_ACCESS_TOKEN",
                    label="Personal Access Token (fallback)",
                    required=False,
                    input_type="password",
                ),
            ),
        ),
    ),
    CoreIntegrationDefinition(
        id="docker",
        title="Docker",
        description="Governed Docker CLI execution.",
        transport="cli",
        risk_class="destructive",
        health_probe="binary_exec",
        runtime_constraints=("allowed_paths",),
    ),
    CoreIntegrationDefinition(
        id="pip",
        title="pip",
        description="Governed Python package management commands.",
        transport="cli",
        risk_class="write",
        health_probe="binary_exec",
    ),
    CoreIntegrationDefinition(
        id="npm",
        title="npm",
        description="Governed Node package management commands.",
        transport="cli",
        risk_class="write",
        health_probe="binary_exec",
    ),
    CoreIntegrationDefinition(
        id="fileops",
        title="File Operations",
        description="Governed filesystem mutation commands.",
        transport="filesystem",
        risk_class="destructive",
        runtime_constraints=("allowed_paths",),
    ),
    CoreIntegrationDefinition(
        id="mcp",
        title="MCP Servers",
        description="Model Context Protocol server bridge for external tool integration.",
        transport="mcp",
        risk_class="write",
        default_approval_mode="guarded",
        supports_persistence=True,
    ),
)

CORE_INTEGRATION_CATALOG: dict[str, CoreIntegrationDefinition] = {
    definition.id: definition for definition in _CORE_INTEGRATION_DEFINITIONS
}
CORE_INTEGRATION_IDS: tuple[str, ...] = tuple(CORE_INTEGRATION_CATALOG)

APPROVAL_MODES: frozenset[str] = frozenset({"read_only", "supervised", "guarded", "escalation_required"})
AUTONOMY_TIERS: frozenset[str] = frozenset({"t0", "t1", "t2"})
PROMOTION_MODES: frozenset[str] = frozenset({"review_queue"})
ACCESS_LEVELS: frozenset[str] = frozenset({"read", "write", "admin", "destructive"})
_READ_HTTP_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})
_GWS_SERVICE_ALIASES = {
    "gmail": "gmail",
    "gcal": "calendar",
    "calendar": "calendar",
    "gdrive": "drive",
    "drive": "drive",
    "gsheets": "sheets",
    "sheets": "sheets",
    "chat": "chat",
    "admin": "admin",
}
_GWS_READ_ACTION_TOKENS = frozenset({"get", "list", "search", "schema", "read", "download", "export", "view"})
_GWS_WRITE_ACTION_TOKENS = frozenset(
    {"create", "update", "patch", "append", "send", "reply", "copy", "move", "import", "add"}
)
_GWS_ADMIN_ACTION_TOKENS = frozenset(
    {"insert", "makeadmin", "permissions", "delegates", "forwardingaddresses", "sendas", "emptytrash"}
)
_GWS_DESTRUCTIVE_ACTION_TOKENS = frozenset({"delete", "trash", "remove", "purge"})
_GWS_ADMIN_RESOURCE_HINTS = frozenset(
    {"admin", "forwardingaddresses", "sendas", "makeadmin", "permissions", "delegates", "emptytrash"}
)
_READ_ATLASSIAN_ACTIONS = frozenset(
    {
        "search",
        "get",
        "list",
        "comments",
        "comment_get",
        "view",
        "analyze",
        "attachments",
        "links",
        "issues",
        "children",
        "view_video",
        "view_image",
        "view_audio",
        "transitions",
    }
)
_DESTRUCTIVE_ACTION_TOKENS = frozenset({"delete", "clear", "purge", "remove", "disconnect"})
_ADMIN_ACTION_TOKENS = frozenset({"switch_env", "set", "configure"})
_SHELL_READ_ACTION_TOKENS = frozenset(
    {
        "ls",
        "cat",
        "head",
        "tail",
        "grep",
        "find",
        "wc",
        "file",
        "stat",
        "which",
        "whoami",
        "hostname",
        "uname",
        "date",
        "echo",
        "pwd",
        "df",
        "du",
        "free",
        "uptime",
        "id",
        "groups",
        "less",
        "more",
        "diff",
        "sort",
        "uniq",
        "tr",
        "cut",
        "test",
        "true",
        "false",
        "man",
        "help",
        "type",
        "readlink",
        "realpath",
        "basename",
        "dirname",
        "tree",
    }
)
_GIT_ACTION_LEVELS: dict[str, str] = {
    "status": "read",
    "log": "read",
    "diff": "read",
    "show": "read",
    "fetch": "read",
    "blame": "read",
    "shortlog": "read",
    "describe": "read",
    "rev-parse": "read",
    "ls-files": "read",
    "ls-tree": "read",
    "ls-remote": "read",
    "reflog": "read",
    "add": "write",
    "commit": "write",
    "checkout": "write",
    "switch": "write",
    "branch": "write",
    "merge": "write",
    "rebase": "write",
    "cherry-pick": "write",
    "stash": "write",
    "pull": "write",
    "push": "write",
    "tag": "write",
    "restore": "write",
    "reset": "destructive",
    "clean": "destructive",
}
_DOCKER_ACTION_LEVELS: dict[str, str] = {
    "ps": "read",
    "images": "read",
    "logs": "read",
    "inspect": "read",
    "stats": "read",
    "top": "read",
    "port": "read",
    "info": "read",
    "version": "read",
    "search": "read",
    "history": "read",
    "events": "read",
    "diff": "read",
    "run": "write",
    "exec": "write",
    "start": "write",
    "stop": "write",
    "restart": "write",
    "compose": "write",
    "build": "write",
    "pull": "write",
    "push": "write",
    "cp": "write",
    "create": "write",
    "network": "write",
    "volume": "write",
    "rm": "destructive",
    "rmi": "destructive",
    "kill": "destructive",
    "system": "destructive",
}
_DEFAULT_DENY_CORE_TOOL_PREFIXES: tuple[str, ...] = (
    "shell_",
    "file_",
    "git_",
    "plugin_",
    "workflow_",
    "webhook_",
    "mcp_",
)
_DEFAULT_DENY_CORE_TOOL_IDS: frozenset[str] = frozenset(
    {
        "agent_set_workdir",
        "agent_receive",
        "agent_list_agents",
        "agent_send",
        "agent_delegate",
        "agent_broadcast",
        "browser_cookies",
        "browser_network_capture_start",
        "browser_network_capture_stop",
        "browser_network_mock",
        "browser_session_save",
        "browser_session_restore",
    }
)
_PIP_ACTION_LEVELS: dict[str, str] = {
    "list": "read",
    "show": "read",
    "search": "read",
    "check": "read",
    "help": "read",
    "debug": "read",
    "inspect": "read",
    "freeze": "read",
    "cache": "read",
    "install": "write",
    "download": "write",
    "wheel": "write",
    "config": "write",
    "uninstall": "destructive",
}
_NPM_ACTION_LEVELS: dict[str, str] = {
    "list": "read",
    "ls": "read",
    "view": "read",
    "info": "read",
    "outdated": "read",
    "audit": "read",
    "explain": "read",
    "doctor": "read",
    "root": "read",
    "prefix": "read",
    "help": "read",
    "version": "read",
    "whoami": "read",
    "ping": "read",
    "install": "write",
    "update": "write",
    "dedupe": "write",
    "rebuild": "write",
    "ci": "write",
    "publish": "write",
    "cache": "write",
    "config": "write",
    "remove": "destructive",
    "rm": "destructive",
    "uninstall": "destructive",
    "unpublish": "destructive",
}
_GH_ACTION_LEVELS: dict[str, str] = {
    "auth.status": "read",
    "pr.list": "read",
    "pr.view": "read",
    "pr.diff": "read",
    "pr.checks": "read",
    "pr.status": "read",
    "pr.checkout": "write",
    "pr.comment": "write",
    "pr.create": "write",
    "pr.edit": "write",
    "pr.ready": "write",
    "pr.reopen": "write",
    "pr.update-branch": "write",
    "pr.close": "destructive",
    "pr.merge": "destructive",
    "issue.list": "read",
    "issue.view": "read",
    "issue.status": "read",
    "issue.comment": "write",
    "issue.create": "write",
    "issue.edit": "write",
    "issue.reopen": "write",
    "issue.close": "destructive",
    "issue.delete": "destructive",
    "repo.list": "read",
    "repo.view": "read",
    "repo.clone": "write",
    "repo.create": "write",
    "repo.fork": "write",
    "repo.delete": "destructive",
    "release.list": "read",
    "release.view": "read",
    "release.create": "write",
    "release.edit": "write",
    "release.upload": "write",
    "release.delete": "destructive",
    "run.list": "read",
    "run.view": "read",
    "run.download": "read",
    "run.watch": "read",
    "run.rerun": "write",
    "run.cancel": "destructive",
    "run.delete": "destructive",
    "workflow.list": "read",
    "workflow.view": "read",
    "workflow.run": "write",
    "workflow.enable": "write",
    "workflow.disable": "write",
}
_GLAB_ACTION_LEVELS: dict[str, str] = {
    "auth.status": "read",
    "mr.list": "read",
    "mr.view": "read",
    "mr.checkout": "write",
    "mr.create": "write",
    "mr.update": "write",
    "mr.rebase": "write",
    "mr.note": "write",
    "mr.approve": "write",
    "mr.revoke": "write",
    "mr.close": "destructive",
    "mr.merge": "destructive",
    "issue.list": "read",
    "issue.view": "read",
    "issue.note": "write",
    "issue.create": "write",
    "issue.update": "write",
    "issue.close": "destructive",
    "issue.delete": "destructive",
    "repo.view": "read",
    "repo.clone": "write",
    "repo.create": "write",
    "repo.delete": "destructive",
    "pipeline.list": "read",
    "pipeline.view": "read",
    "pipeline.run": "write",
    "pipeline.retry": "write",
    "pipeline.cancel": "destructive",
    "pipeline.delete": "destructive",
}
_SCHEDULER_ACTION_LEVELS: dict[str, str] = {
    "job_list": "read",
    "job_get": "read",
    "job_runs": "read",
    "job_create": "write",
    "job_validate": "write",
    "job_activate": "write",
    "job_pause": "write",
    "job_resume": "write",
    "job_run_now": "write",
    "job_delete": "destructive",
}
_SCRIPT_LIBRARY_ACTION_LEVELS: dict[str, str] = {
    "search": "read",
    "list": "read",
    "save": "write",
    "delete": "destructive",
    "auto_extract": "write",
}
_CACHE_ACTION_LEVELS: dict[str, str] = {
    "lookup": "read",
    "stats": "read",
    "store": "write",
    "clear": "destructive",
}
_BROWSER_ACTION_LEVELS: dict[str, str] = {
    "navigate": "read",
    "screenshot": "read",
    "get_text": "read",
    "get_elements": "read",
    "scroll": "read",
    "wait": "read",
    "back": "read",
    "forward": "read",
    "hover": "read",
    "cookies.get": "read",
    "click": "write",
    "type": "write",
    "select": "write",
    "submit": "write",
    "press_key": "write",
    "cookies.set": "admin",
}
_WEB_ACTION_LEVELS: dict[str, str] = {
    "search": "read",
    "fetch_url": "read",
    "http.get": "read",
    "http.head": "read",
    "http.options": "read",
    "http.post": "write",
    "http.put": "write",
    "http.patch": "write",
    "http.delete": "destructive",
}


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


def _integration_runtime_constraints(integration_id: str) -> frozenset[str]:
    """Return the set of runtime constraint keys applicable to an integration.

    Core integrations declare `runtime_constraints` directly on their
    `CoreIntegrationDefinition`. MCP integrations (prefixed `mcp:<server_key>`)
    are resolved through `koda.integrations.mcp_catalog` on demand, with a
    safe fallback of the empty set if the catalog entry is missing.
    """
    integration_id = integration_id.lower()
    definition = CORE_INTEGRATION_CATALOG.get(integration_id)
    if definition is not None:
        return frozenset(definition.runtime_constraints)
    if integration_id.startswith("mcp:"):
        try:
            from koda.integrations.mcp_catalog import MCP_CATALOG_BY_KEY
        except ImportError:
            return frozenset()
        server_key = integration_id.split(":", 1)[1]
        spec = MCP_CATALOG_BY_KEY.get(server_key)
        if spec is not None:
            return frozenset(spec.runtime_constraints)
    return frozenset()


def normalize_integration_grants(value: Any) -> dict[str, dict[str, Any]]:
    """Normalize resource_access_policy.integration_grants payloads.

    Runtime constraint keys (`allowed_domains`, `allowed_paths`,
    `allowed_db_envs`, `allow_private_network`, `read_only_mode`) are only
    persisted when the target integration declares them. Unsupported keys are
    silently dropped to keep stored grants in sync with the declarative
    catalog — preventing orphan fields surfaced by older UIs.
    """
    if not isinstance(value, dict):
        return {}

    normalized_grants: dict[str, dict[str, Any]] = {}
    for raw_integration_id, raw_payload in value.items():
        integration_id = str(raw_integration_id or "").strip().lower()
        if not integration_id or not isinstance(raw_payload, dict):
            continue
        applicable = _integration_runtime_constraints(integration_id)
        grant: dict[str, Any] = {}

        enabled = raw_payload.get("enabled")
        if isinstance(enabled, bool):
            grant["enabled"] = enabled

        allow_actions = [item.lower() for item in normalize_string_list(raw_payload.get("allow_actions"))]
        if allow_actions:
            grant["allow_actions"] = allow_actions

        deny_actions = [item.lower() for item in normalize_string_list(raw_payload.get("deny_actions"))]
        if deny_actions:
            grant["deny_actions"] = deny_actions

        approval_mode = str(raw_payload.get("approval_mode") or "").strip().lower()
        if approval_mode:
            grant["approval_mode"] = approval_mode

        secret_keys = [item.upper() for item in normalize_string_list(raw_payload.get("secret_keys"))]
        if secret_keys:
            grant["secret_keys"] = secret_keys

        shared_env_keys = [item.upper() for item in normalize_string_list(raw_payload.get("shared_env_keys"))]
        if shared_env_keys:
            grant["shared_env_keys"] = shared_env_keys

        if "allowed_domains" in applicable:
            allowed_domains = [item.lower() for item in normalize_string_list(raw_payload.get("allowed_domains"))]
            if allowed_domains:
                grant["allowed_domains"] = allowed_domains

        if "allowed_paths" in applicable:
            allowed_paths = normalize_string_list(raw_payload.get("allowed_paths"))
            if allowed_paths:
                grant["allowed_paths"] = allowed_paths

        if "allowed_db_envs" in applicable:
            allowed_db_envs = [item.lower() for item in normalize_string_list(raw_payload.get("allowed_db_envs"))]
            if allowed_db_envs:
                grant["allowed_db_envs"] = allowed_db_envs

        if "allow_private_network" in applicable:
            allow_private_network = raw_payload.get("allow_private_network")
            if isinstance(allow_private_network, bool):
                grant["allow_private_network"] = allow_private_network

        if "read_only_mode" in applicable:
            read_only_mode = raw_payload.get("read_only_mode")
            if isinstance(read_only_mode, bool):
                grant["read_only_mode"] = read_only_mode

        if grant:
            normalized_grants[integration_id] = grant

    return normalized_grants


def _command_tokens(args: str | None) -> list[str]:
    raw_args = str(args or "").strip()
    if not raw_args:
        return []
    try:
        return shlex.split(raw_args)
    except ValueError:
        return raw_args.split()


def _action_catalog(
    integration_id: str,
    action_levels: dict[str, str],
    *,
    auth_mode: str = "none",
) -> list[dict[str, Any]]:
    integration = _integration_defaults(integration_id)
    return [
        {
            "action_id": action_id,
            "access_level": access_level,
            "default_approval_mode": integration.default_approval_mode,
            "auth_mode": auth_mode,
        }
        for action_id, access_level in sorted(action_levels.items())
    ]


def _resolve_prefixed_subcommand_action(
    integration_id: str,
    args: str | None,
    registry: dict[str, str],
    *,
    default_access_level: str = "write",
) -> tuple[str, str]:
    tokens = _command_tokens(args)
    subcommand = str(tokens[0] if tokens else "unknown").strip().lower() or "unknown"
    access_level = registry.get(subcommand, default_access_level)
    return f"{integration_id}.{subcommand}", access_level


def _resolve_grouped_cli_action(
    integration_id: str,
    args: str | None,
    registry: dict[str, str],
    *,
    default_access_level: str = "write",
) -> tuple[str, str]:
    tokens = [token.strip().lower() for token in _command_tokens(args) if token.strip()]
    if not tokens:
        return f"{integration_id}.unknown", default_access_level
    if len(tokens) >= 2:
        candidate = f"{tokens[0]}.{tokens[1]}"
        if candidate in registry:
            return f"{integration_id}.{candidate}", registry[candidate]
    candidate = tokens[0]
    return f"{integration_id}.{candidate}", registry.get(candidate, default_access_level)


def canonicalize_gws_command_args(service: str, args: str | None = None) -> str:
    """Return canonical GWS CLI args in the form '<service> <resource.method> ...'."""
    normalized_service = _GWS_SERVICE_ALIASES.get(
        str(service or "").strip().lower(), str(service or "").strip().lower()
    )
    raw_args = str(args or "").strip()
    if not raw_args:
        return normalized_service
    tokens = shlex.split(raw_args)
    if tokens and _GWS_SERVICE_ALIASES.get(tokens[0].strip().lower(), tokens[0].strip().lower()) == normalized_service:
        return raw_args
    return f"{normalized_service} {raw_args}"


def _gws_is_admin_method(service: str, resource_method: str) -> bool:
    normalized_service = str(service or "").strip().lower()
    normalized_resource = str(resource_method or "").strip().lower()
    if not normalized_resource:
        return normalized_service == "admin"
    if normalized_service == "admin":
        return True
    if any(hint in normalized_resource for hint in _GWS_ADMIN_RESOURCE_HINTS):
        return True
    tokens = [token for token in normalized_resource.split(".") if token]
    return any(token in _GWS_ADMIN_ACTION_TOKENS for token in tokens)


def resolve_gws_action(args: str | None) -> GwsActionResolution:
    """Resolve one GWS command string to a canonical service.action envelope."""
    tokens = shlex.split(str(args or ""))
    service_token = str(tokens[0] if tokens else "generic").strip().lower()
    service = _GWS_SERVICE_ALIASES.get(service_token, service_token or "generic")
    resource_method = ""
    for token in tokens[1:]:
        if "." in token:
            resource_method = token.strip()
            break
    if not resource_method and len(tokens) > 1:
        resource_method = str(tokens[1]).strip()
    if not resource_method and tokens and "." in tokens[0]:
        resource_method = str(tokens[0]).strip()
        service = _GWS_SERVICE_ALIASES.get(resource_method.split(".", 1)[0].strip().lower(), service)
    if not resource_method:
        resource_method = "unknown"
    normalized_resource = resource_method.lower()
    action_token = normalized_resource.rsplit(".", 1)[-1] if normalized_resource else "unknown"
    if _gws_is_admin_method(service, normalized_resource):
        service = "admin"
        access_level = "admin"
    elif action_token in _GWS_DESTRUCTIVE_ACTION_TOKENS:
        access_level = "destructive"
    elif action_token in _GWS_READ_ACTION_TOKENS:
        access_level = "read"
    elif action_token in _GWS_ADMIN_ACTION_TOKENS:
        service = "admin"
        access_level = "admin"
    else:
        access_level = "write"
    return GwsActionResolution(
        service=service,
        action_id=f"{service}.{action_token}",
        resource_method=resource_method,
        access_level=access_level,
    )


def resolve_core_integration_catalog() -> list[dict[str, Any]]:
    """Return the integration catalog in a UI/API-friendly format."""
    return [
        {
            "id": definition.id,
            "title": definition.title,
            "description": definition.description,
            "transport": definition.transport,
            "auth_modes": list(definition.auth_modes),
            "risk_class": definition.risk_class,
            "default_approval_mode": definition.default_approval_mode,
            "required_secrets": list(definition.required_secrets),
            "required_env": list(definition.required_env),
            "timeout": definition.timeout,
            "health_probe": definition.health_probe,
            "supports_persistence": definition.supports_persistence,
        }
        for definition in _CORE_INTEGRATION_DEFINITIONS
    ]


def resolve_core_integration_action_catalog() -> dict[str, list[dict[str, Any]]]:
    """Return canonical action catalogs for integrations with explicit action surfaces."""
    return {
        "web": _action_catalog("web", _WEB_ACTION_LEVELS),
        "browser": _action_catalog("browser", _BROWSER_ACTION_LEVELS),
        "scheduler": _action_catalog("scheduler", _SCHEDULER_ACTION_LEVELS),
        "script_library": _action_catalog("script_library", _SCRIPT_LIBRARY_ACTION_LEVELS),
        "cache": _action_catalog("cache", _CACHE_ACTION_LEVELS),
        "shell": _action_catalog(
            "shell",
            {f"shell.{action}": "read" for action in sorted(_SHELL_READ_ACTION_TOKENS)},
        ),
        "git": _action_catalog("git", {f"git.{action}": level for action, level in _GIT_ACTION_LEVELS.items()}),
        "gh": _action_catalog("gh", {f"gh.{action}": level for action, level in _GH_ACTION_LEVELS.items()}),
        "glab": _action_catalog(
            "glab",
            {f"glab.{action}": level for action, level in _GLAB_ACTION_LEVELS.items()},
        ),
        "docker": _action_catalog(
            "docker",
            {f"docker.{action}": level for action, level in _DOCKER_ACTION_LEVELS.items()},
        ),
        "pip": _action_catalog("pip", {f"pip.{action}": level for action, level in _PIP_ACTION_LEVELS.items()}),
        "npm": _action_catalog("npm", {f"npm.{action}": level for action, level in _NPM_ACTION_LEVELS.items()}),
        "fileops": _action_catalog(
            "fileops",
            {
                "fileops.cat": "read",
                "fileops.read": "read",
                "fileops.list": "read",
                "fileops.search": "read",
                "fileops.grep": "read",
                "fileops.info": "read",
                "fileops.write": "write",
                "fileops.edit": "write",
                "fileops.move": "write",
                "fileops.mkdir": "write",
                "fileops.rm": "destructive",
                "fileops.delete": "destructive",
            },
        ),
        "gws": [
            {
                "action_id": f"{service}.{verb}",
                "access_level": level,
                "default_approval_mode": "guarded",
                "auth_mode": "service_account",
            }
            for service in ("gmail", "calendar", "drive", "sheets", "chat")
            for verb, level in (
                ("list", "read"),
                ("get", "read"),
                ("search", "read"),
                ("read", "read"),
                ("download", "read"),
                ("export", "read"),
                ("view", "read"),
                ("create", "write"),
                ("update", "write"),
                ("patch", "write"),
                ("append", "write"),
                ("send", "write"),
                ("reply", "write"),
                ("copy", "write"),
                ("move", "write"),
                ("import", "write"),
                ("add", "write"),
                ("delete", "destructive"),
                ("trash", "destructive"),
                ("remove", "destructive"),
                ("purge", "destructive"),
            )
        ]
        + [
            {
                "action_id": f"admin.{verb}",
                "access_level": "admin",
                "default_approval_mode": "guarded",
                "auth_mode": "service_account",
            }
            for verb in sorted(_GWS_ADMIN_ACTION_TOKENS)
        ],
        "jira": [
            {
                "action_id": "issues.search",
                "access_level": "read",
                "default_approval_mode": "guarded",
                "auth_mode": "api_token",
            },
            {
                "action_id": "issues.get",
                "access_level": "read",
                "default_approval_mode": "guarded",
                "auth_mode": "api_token",
            },
            {
                "action_id": "issues.create",
                "access_level": "write",
                "default_approval_mode": "guarded",
                "auth_mode": "api_token",
            },
            {
                "action_id": "issues.update",
                "access_level": "write",
                "default_approval_mode": "guarded",
                "auth_mode": "api_token",
            },
            {
                "action_id": "issues.delete",
                "access_level": "destructive",
                "default_approval_mode": "guarded",
                "auth_mode": "api_token",
            },
            {
                "action_id": "issues.transition",
                "access_level": "write",
                "default_approval_mode": "guarded",
                "auth_mode": "api_token",
            },
            {
                "action_id": "issues.transitions",
                "access_level": "read",
                "default_approval_mode": "guarded",
                "auth_mode": "api_token",
            },
            {
                "action_id": "issues.comment",
                "access_level": "write",
                "default_approval_mode": "guarded",
                "auth_mode": "api_token",
            },
            {
                "action_id": "issues.comment_get",
                "access_level": "read",
                "default_approval_mode": "guarded",
                "auth_mode": "api_token",
            },
            {
                "action_id": "issues.comment_edit",
                "access_level": "write",
                "default_approval_mode": "guarded",
                "auth_mode": "api_token",
            },
            {
                "action_id": "issues.comment_delete",
                "access_level": "destructive",
                "default_approval_mode": "guarded",
                "auth_mode": "api_token",
            },
            {
                "action_id": "issues.comment_reply",
                "access_level": "write",
                "default_approval_mode": "guarded",
                "auth_mode": "api_token",
            },
            {
                "action_id": "issues.assign",
                "access_level": "write",
                "default_approval_mode": "guarded",
                "auth_mode": "api_token",
            },
            {
                "action_id": "issues.comments",
                "access_level": "read",
                "default_approval_mode": "guarded",
                "auth_mode": "api_token",
            },
            {
                "action_id": "issues.link",
                "access_level": "write",
                "default_approval_mode": "guarded",
                "auth_mode": "api_token",
            },
            {
                "action_id": "issues.analyze",
                "access_level": "read",
                "default_approval_mode": "guarded",
                "auth_mode": "api_token",
            },
            {
                "action_id": "issues.attachments",
                "access_level": "read",
                "default_approval_mode": "guarded",
                "auth_mode": "api_token",
            },
            {
                "action_id": "issues.links",
                "access_level": "read",
                "default_approval_mode": "guarded",
                "auth_mode": "api_token",
            },
            {
                "action_id": "issues.view_video",
                "access_level": "read",
                "default_approval_mode": "guarded",
                "auth_mode": "api_token",
            },
            {
                "action_id": "issues.view_image",
                "access_level": "read",
                "default_approval_mode": "guarded",
                "auth_mode": "api_token",
            },
            {
                "action_id": "issues.view_audio",
                "access_level": "read",
                "default_approval_mode": "guarded",
                "auth_mode": "api_token",
            },
            {
                "action_id": "projects.list",
                "access_level": "read",
                "default_approval_mode": "guarded",
                "auth_mode": "api_token",
            },
            {
                "action_id": "projects.get",
                "access_level": "read",
                "default_approval_mode": "guarded",
                "auth_mode": "api_token",
            },
            {
                "action_id": "boards.list",
                "access_level": "read",
                "default_approval_mode": "guarded",
                "auth_mode": "api_token",
            },
            {
                "action_id": "boards.get",
                "access_level": "read",
                "default_approval_mode": "guarded",
                "auth_mode": "api_token",
            },
            {
                "action_id": "sprints.list",
                "access_level": "read",
                "default_approval_mode": "guarded",
                "auth_mode": "api_token",
            },
            {
                "action_id": "sprints.get",
                "access_level": "read",
                "default_approval_mode": "guarded",
                "auth_mode": "api_token",
            },
            {
                "action_id": "sprints.issues",
                "access_level": "read",
                "default_approval_mode": "guarded",
                "auth_mode": "api_token",
            },
            {
                "action_id": "users.search",
                "access_level": "read",
                "default_approval_mode": "guarded",
                "auth_mode": "api_token",
            },
            {
                "action_id": "components.list",
                "access_level": "read",
                "default_approval_mode": "guarded",
                "auth_mode": "api_token",
            },
            {
                "action_id": "versions.list",
                "access_level": "read",
                "default_approval_mode": "guarded",
                "auth_mode": "api_token",
            },
            {
                "action_id": "statuses.list",
                "access_level": "read",
                "default_approval_mode": "guarded",
                "auth_mode": "api_token",
            },
            {
                "action_id": "priorities.list",
                "access_level": "read",
                "default_approval_mode": "guarded",
                "auth_mode": "api_token",
            },
            {
                "action_id": "fields.list",
                "access_level": "read",
                "default_approval_mode": "guarded",
                "auth_mode": "api_token",
            },
        ],
        "confluence": [
            {
                "action_id": "pages.get",
                "access_level": "read",
                "default_approval_mode": "guarded",
                "auth_mode": "api_token",
            },
            {
                "action_id": "pages.search",
                "access_level": "read",
                "default_approval_mode": "guarded",
                "auth_mode": "api_token",
            },
            {
                "action_id": "pages.children",
                "access_level": "read",
                "default_approval_mode": "guarded",
                "auth_mode": "api_token",
            },
            {
                "action_id": "pages.create",
                "access_level": "write",
                "default_approval_mode": "guarded",
                "auth_mode": "api_token",
            },
            {
                "action_id": "pages.update",
                "access_level": "write",
                "default_approval_mode": "guarded",
                "auth_mode": "api_token",
            },
            {
                "action_id": "pages.delete",
                "access_level": "destructive",
                "default_approval_mode": "guarded",
                "auth_mode": "api_token",
            },
            {
                "action_id": "spaces.list",
                "access_level": "read",
                "default_approval_mode": "guarded",
                "auth_mode": "api_token",
            },
            {
                "action_id": "spaces.get",
                "access_level": "read",
                "default_approval_mode": "guarded",
                "auth_mode": "api_token",
            },
        ],
    }


def _host_from_url(value: str | None) -> str | None:
    if not value:
        return None
    try:
        host = urlparse(str(value).strip()).hostname
    except Exception:
        return None
    return str(host or "").strip().lower() or None


def _host_from_value(value: str | None) -> str | None:
    if not value:
        return None
    return _host_from_url(value) or str(value).strip().lower() or None


def _is_private_host(host: str | None) -> bool:
    if not host:
        return False
    if host in {"localhost", "localhost.localdomain"} or host.endswith(".local") or host.endswith(".internal"):
        return True
    try:
        ip_value = ipaddress.ip_address(host)
    except ValueError:
        return False
    return any(
        (
            ip_value.is_private,
            ip_value.is_loopback,
            ip_value.is_link_local,
            ip_value.is_reserved,
            ip_value.is_multicast,
        )
    )


def _matches_action_pattern(pattern: str, action_id: str) -> bool:
    normalized_pattern = str(pattern or "").strip().lower()
    normalized_action = str(action_id or "").strip().lower()
    if not normalized_pattern or not normalized_action:
        return False
    if normalized_pattern == "*":
        return True
    if normalized_pattern.endswith(".*"):
        prefix = normalized_pattern[:-2]
        return normalized_action == prefix or normalized_action.startswith(prefix + ".")
    if normalized_pattern.endswith("*"):
        return normalized_action.startswith(normalized_pattern[:-1])
    if "." not in normalized_pattern:
        return normalized_action == normalized_pattern or normalized_action.endswith("." + normalized_pattern)
    return normalized_action == normalized_pattern


def _domain_allowed(host: str | None, allowed_domains: list[str]) -> bool:
    if not host:
        return False
    normalized_host = host.lower()
    for pattern in allowed_domains:
        candidate = str(pattern or "").strip().lower()
        if not candidate:
            continue
        if candidate == "*":
            return True
        if candidate.startswith("*."):
            suffix = candidate[2:]
            if normalized_host.endswith("." + suffix):
                return True
            continue
        if normalized_host == candidate or normalized_host.endswith("." + candidate):
            return True
    return False


def _path_allowed(path: str | None, allowed_paths: list[str]) -> bool:
    normalized_path = str(path or "").strip()
    if not normalized_path:
        return False
    for allowed in allowed_paths:
        candidate = str(allowed or "").strip()
        if not candidate:
            continue
        if normalized_path == candidate or normalized_path.startswith(candidate.rstrip("/") + "/"):
            return True
    return False


def _action_level_from_tokens(action_token: str, *, read_actions: frozenset[str]) -> str:
    normalized_action = str(action_token or "").strip().lower()
    if normalized_action in read_actions:
        return "read"
    if normalized_action in _DESTRUCTIVE_ACTION_TOKENS:
        return "destructive"
    if normalized_action in _ADMIN_ACTION_TOKENS:
        return "admin"
    return "write"


def _integration_defaults(integration_id: str) -> CoreIntegrationDefinition:
    return CORE_INTEGRATION_CATALOG.get(
        integration_id,
        CoreIntegrationDefinition(
            id=integration_id,
            title=integration_id.replace("_", " ").title(),
            description="Dynamic integration surface.",
            transport="internal",
        ),
    )


def _tool_allowed_by_secure_default(definition: CoreToolDefinition | None) -> bool:
    if definition is None:
        return False
    if definition.id == "agent_get_status":
        return True
    if definition.id in _DEFAULT_DENY_CORE_TOOL_IDS:
        return False
    if any(definition.id.startswith(prefix) for prefix in _DEFAULT_DENY_CORE_TOOL_PREFIXES):
        return False
    return definition.read_only is True


def is_tool_allowed_by_secure_default(tool_id: str) -> bool:
    """Return whether a tool is part of the secure-by-default baseline."""
    return _tool_allowed_by_secure_default(CORE_TOOL_CATALOG.get(str(tool_id or "").strip()))


def _stable_json(value: Any) -> str:
    try:
        return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)
    except (TypeError, ValueError):
        return json.dumps(str(value), ensure_ascii=False)


def _fingerprint_payload(value: Any) -> str:
    return hashlib.sha256(_stable_json(value).encode("utf-8")).hexdigest()


def _normalize_effect_tags(
    *,
    tool_id: str,
    resolution: IntegrationActionResolution,
    params: dict[str, Any],
    grant_decision: IntegrationGrantDecision | None,
    server_key: str | None,
) -> tuple[str, ...]:
    tags: set[str] = set()
    normalized_action = resolution.action_id.lower()
    normalized_tool = tool_id.lower()

    if resolution.access_level == "destructive":
        tags.add("destructive_change")
    if resolution.private_network:
        tags.add("private_network")
    if resolution.access_level == "admin":
        tags.add("identity_admin")

    if resolution.integration_id == "browser" and resolution.access_level != "read":
        tags.add("browser_state_mutation")
    if normalized_action == "cookies.set":
        tags.update({"browser_state_mutation", "identity_admin"})

    if any(token in normalized_action for token in ("permission", "permissions", "acl", "share", "sharing")):
        tags.add("sharing_or_permissions")
    if normalized_action in {
        "gmail.users.messages.send",
        "chat.spaces.messages.create",
        "send",
        "broadcast",
    } or normalized_action.endswith(".send"):
        tags.add("external_communication")
    if normalized_tool in {"agent_send", "agent_delegate", "agent_broadcast"}:
        tags.add("external_communication")
    if normalized_tool == "agent_delegate":
        tags.add("delegation")

    if normalized_tool in {"plugin_install", "plugin_uninstall", "plugin_reload"} or normalized_action in {
        "install",
        "pip.install",
        "npm.install",
    }:
        tags.add("package_or_plugin_install")

    bulk_keys = ("items", "operations", "entries", "updates", "rows", "values", "ids", "paths", "files")
    if any(isinstance(params.get(key), list) and len(params.get(key) or []) > 1 for key in bulk_keys):
        tags.add("bulk_write")
    if any(token in normalized_action for token in ("batchupdate", "bulk", "clear")):
        tags.add("bulk_write")

    if resolution.integration_id.startswith("mcp:"):
        if resolution.access_level != "read":
            tags.add("mcp_write")
        if server_key:
            tags.add("mcp_tool")

    if (grant_decision and grant_decision.sensitive_access_used) or resolution.integration_id in {
        "gws",
        "jira",
        "confluence",
    }:
        tags.add("credential_access")

    return tuple(sorted(tags))


def _resolve_resource_scope(
    resolution: IntegrationActionResolution,
    params: dict[str, Any],
    *,
    server_key: str | None,
) -> dict[str, Any]:
    scope: dict[str, Any] = {
        "integration_id": resolution.integration_id,
        "action_id": resolution.action_id,
        "resource_method": resolution.resource_method,
        "domain": resolution.domain,
        "path": resolution.path,
        "db_env": resolution.db_env,
        "server_key": server_key,
    }
    resource_keys = (
        "url",
        "path",
        "id",
        "key",
        "fileId",
        "documentId",
        "spreadsheetId",
        "calendarId",
        "eventId",
        "messageId",
        "space",
        "spaceId",
        "to",
        "recipient",
        "recipients",
        "email",
        "emails",
        "name",
        "target",
        "branch",
        "remote",
        "command",
    )
    for key in resource_keys:
        value = params.get(key)
        if value not in (None, "", [], {}):
            scope[key] = value
    return scope


def build_action_envelope(
    tool_id: str,
    params: dict[str, Any] | None = None,
    *,
    grant_decision: IntegrationGrantDecision | None = None,
) -> ActionEnvelope:
    """Resolve the canonical action envelope for one tool invocation."""
    payload = params or {}
    resolution = resolve_integration_action(tool_id, payload)
    parsed_mcp_tool = _parse_mcp_tool_id(tool_id)
    server_key = parsed_mcp_tool[0] if parsed_mcp_tool is not None else None
    effect_tags = _normalize_effect_tags(
        tool_id=tool_id,
        resolution=resolution,
        params=payload,
        grant_decision=grant_decision,
        server_key=server_key,
    )
    resource_scope = _resolve_resource_scope(resolution, payload, server_key=server_key)
    external_side_effect = bool(
        resolution.integration_id.startswith("mcp:")
        or resolution.integration_id in {"web", "gws", "jira", "confluence"}
        or resolution.integration_id == "browser"
        or resolution.action_id in {"push", "agent_send", "agent_delegate", "agent_broadcast"}
        or "external_communication" in effect_tags
        or "sharing_or_permissions" in effect_tags
        or "package_or_plugin_install" in effect_tags
    )
    catalogued = bool(
        tool_id in CORE_TOOL_CATALOG
        or parsed_mcp_tool is not None
        or tool_id in {"gws", "jira", "confluence", "shell", "git", "docker", "pip", "npm", "gh", "glab"}
        or tool_id in {"write", "edit", "rm", "mkdir", "cat"}
    )
    return ActionEnvelope(
        tool_id=tool_id,
        integration_id=resolution.integration_id,
        action_id=resolution.action_id,
        transport=resolution.transport,
        access_level=resolution.access_level,
        risk_class=resolution.risk_class,
        effect_tags=effect_tags,
        resource_method=resolution.resource_method,
        server_key=server_key,
        domain=resolution.domain,
        path=resolution.path,
        db_env=resolution.db_env,
        private_network=resolution.private_network,
        uses_secrets=bool(grant_decision and grant_decision.sensitive_access_used),
        bulk_operation="bulk_write" in effect_tags,
        external_side_effect=external_side_effect,
        catalogued=catalogued,
        resource_scope_fingerprint=_fingerprint_payload(resource_scope),
        params_fingerprint=_fingerprint_payload(payload),
    )


def resolve_action_envelope(
    tool_id: str,
    params: dict[str, Any] | None,
    resource_access_policy: dict[str, Any] | None,
) -> tuple[ActionEnvelope, IntegrationGrantDecision]:
    """Resolve the canonical action envelope plus integration-grant decision."""
    payload = params or {}
    grant_decision = evaluate_integration_grant(tool_id, payload, resource_access_policy)
    return build_action_envelope(tool_id, payload, grant_decision=grant_decision), grant_decision


def _allow_implicit_integration_grant(resolution: IntegrationActionResolution) -> bool:
    if resolution.transport == "mcp":
        # MCP servers are governed primarily by per-tool policies seeded as
        # always_ask, so the absence of an integration_grant should not hard-block
        # the connection.
        return True
    if resolution.access_level != "read" or resolution.private_network:
        return False
    return _tool_allowed_by_secure_default(CORE_TOOL_CATALOG.get(resolution.tool_id))


def _parse_mcp_tool_id(tool_id: str) -> tuple[str, str] | None:
    if not tool_id.startswith("mcp_"):
        return None
    remainder = tool_id.removeprefix("mcp_")
    if "__" not in remainder:
        return None
    server_key, tool_name = remainder.split("__", 1)
    if not server_key or not tool_name:
        return None
    return server_key, tool_name


def _infer_mcp_access_level(tool_name: str) -> str:
    action_token = re.split(r"[_.-]", str(tool_name or "").strip().lower(), maxsplit=1)[0]
    if not action_token:
        return "write"
    return _action_level_from_tokens(action_token, read_actions=_GWS_READ_ACTION_TOKENS)


def resolve_integration_action(tool_id: str, params: dict[str, Any] | None = None) -> IntegrationActionResolution:
    """Resolve one tool invocation to a typed integration/action envelope."""
    tool = str(tool_id or "").strip()
    payload = params or {}

    parsed_mcp_tool = _parse_mcp_tool_id(tool)
    if parsed_mcp_tool is not None:
        server_key, tool_name = parsed_mcp_tool
        integration = _integration_defaults("mcp")
        access_level = _infer_mcp_access_level(tool_name)
        return IntegrationActionResolution(
            integration_id=f"mcp:{server_key}",
            action_id=tool_name,
            access_level=access_level,
            transport=integration.transport,
            risk_class=access_level,
            default_approval_mode=integration.default_approval_mode,
            tool_id=tool,
            auth_modes=integration.auth_modes,
            resource_method=tool_name,
        )

    if tool.startswith("job_") or tool.startswith("cron_"):
        integration = _integration_defaults("scheduler")
        access_level = _SCHEDULER_ACTION_LEVELS.get(tool, "write")
        return IntegrationActionResolution(
            integration_id=integration.id,
            action_id=tool,
            access_level=access_level,
            transport=integration.transport,
            risk_class=access_level,
            default_approval_mode=integration.default_approval_mode,
            tool_id=tool,
            auth_modes=integration.auth_modes,
        )

    if tool in {"web_search", "fetch_url", "http_request"}:
        integration = _integration_defaults("web")
        if tool == "http_request":
            method = str(payload.get("method") or "GET").strip().upper() or "GET"
            access_level = _WEB_ACTION_LEVELS.get(f"http.{method.lower()}", "write")
            action_id = f"http.{method.lower()}"
            host = _host_from_value(payload.get("url"))
        elif tool == "fetch_url":
            access_level = "read"
            action_id = "fetch_url"
            host = _host_from_value(payload.get("url"))
        else:
            access_level = "read"
            action_id = "search"
            host = None
        return IntegrationActionResolution(
            integration_id=integration.id,
            action_id=action_id,
            access_level=access_level,
            transport=integration.transport,
            risk_class=access_level,
            default_approval_mode=integration.default_approval_mode,
            tool_id=tool,
            auth_modes=integration.auth_modes,
            domain=host,
            private_network=_is_private_host(host),
            resource_method=action_id,
        )

    if tool.startswith("browser_"):
        integration = _integration_defaults("browser")
        action_id = tool.removeprefix("browser_")
        host = _host_from_value(payload.get("url")) or _host_from_value(payload.get("current_url"))
        if not host:
            host = _host_from_value(payload.get("current_domain") or payload.get("domain"))
        if action_id == "cookies" and str(payload.get("action") or "get").strip().lower() == "set":
            action_id = "cookies.set"
            access_level = "admin"
            host = (
                _host_from_value(payload.get("url"))
                or _host_from_value(payload.get("domain"))
                or _host_from_value(payload.get("current_url"))
                or _host_from_value(payload.get("current_domain"))
            )
        elif action_id == "cookies":
            action_id = "cookies.get"
            access_level = _BROWSER_ACTION_LEVELS[action_id]
        else:
            access_level = _BROWSER_ACTION_LEVELS.get(action_id, "write")
        return IntegrationActionResolution(
            integration_id=integration.id,
            action_id=action_id,
            access_level=access_level,
            transport=integration.transport,
            risk_class=access_level,
            default_approval_mode=integration.default_approval_mode,
            tool_id=tool,
            auth_modes=integration.auth_modes,
            domain=host,
            private_network=_is_private_host(host),
            resource_method=action_id,
        )

    if tool == "gws":
        integration = _integration_defaults("gws")
        gws_action = resolve_gws_action(str(payload.get("args") or ""))
        return IntegrationActionResolution(
            integration_id=integration.id,
            action_id=gws_action.action_id,
            resource_method=gws_action.resource_method,
            access_level=gws_action.access_level,
            transport=integration.transport,
            risk_class=gws_action.access_level,
            default_approval_mode=integration.default_approval_mode,
            tool_id=tool,
            auth_modes=integration.auth_modes,
        )

    if tool in {"jira", "confluence"}:
        integration = _integration_defaults(tool)
        tokens = shlex.split(str(payload.get("args") or ""))
        resource = str(tokens[0] if tokens else "generic").strip().lower()
        action_token = str(tokens[1] if len(tokens) > 1 else "unknown").strip().lower()
        access_level = _action_level_from_tokens(action_token, read_actions=_READ_ATLASSIAN_ACTIONS)
        return IntegrationActionResolution(
            integration_id=integration.id,
            action_id=f"{resource}.{action_token}",
            access_level=access_level,
            transport=integration.transport,
            risk_class=access_level,
            default_approval_mode=integration.default_approval_mode,
            tool_id=tool,
            auth_modes=integration.auth_modes,
            resource_method=f"{resource}.{action_token}",
        )

    if tool.startswith("script_"):
        integration = _integration_defaults("script_library")
        action_id = tool.removeprefix("script_")
        access_level = _SCRIPT_LIBRARY_ACTION_LEVELS.get(action_id, "write")
        return IntegrationActionResolution(
            integration_id=integration.id,
            action_id=action_id,
            access_level=access_level,
            transport=integration.transport,
            risk_class=access_level,
            default_approval_mode=integration.default_approval_mode,
            tool_id=tool,
            auth_modes=integration.auth_modes,
        )

    if tool.startswith("cache_"):
        integration = _integration_defaults("cache")
        action_id = tool.removeprefix("cache_")
        access_level = _CACHE_ACTION_LEVELS.get(action_id, "write")
        return IntegrationActionResolution(
            integration_id=integration.id,
            action_id=action_id,
            access_level=access_level,
            transport=integration.transport,
            risk_class=access_level,
            default_approval_mode=integration.default_approval_mode,
            tool_id=tool,
            auth_modes=integration.auth_modes,
        )

    if tool == "shell":
        integration = _integration_defaults("shell")
        action_id, access_level = _resolve_prefixed_subcommand_action(
            "shell",
            str(payload.get("args") or ""),
            {action: "read" for action in _SHELL_READ_ACTION_TOKENS},
            default_access_level="destructive",
        )
        return IntegrationActionResolution(
            integration_id=integration.id,
            action_id=action_id,
            access_level=access_level,
            transport=integration.transport,
            risk_class=access_level,
            default_approval_mode=integration.default_approval_mode,
            tool_id=tool,
            auth_modes=integration.auth_modes,
            resource_method=action_id,
        )

    if tool == "git":
        integration = _integration_defaults("git")
        action_id, access_level = _resolve_prefixed_subcommand_action(
            "git",
            str(payload.get("args") or ""),
            _GIT_ACTION_LEVELS,
        )
        return IntegrationActionResolution(
            integration_id=integration.id,
            action_id=action_id,
            access_level=access_level,
            transport=integration.transport,
            risk_class=access_level,
            default_approval_mode=integration.default_approval_mode,
            tool_id=tool,
            auth_modes=integration.auth_modes,
            resource_method=action_id,
        )

    if tool == "docker":
        integration = _integration_defaults("docker")
        action_id, access_level = _resolve_prefixed_subcommand_action(
            "docker",
            str(payload.get("args") or ""),
            _DOCKER_ACTION_LEVELS,
            default_access_level="destructive",
        )
        return IntegrationActionResolution(
            integration_id=integration.id,
            action_id=action_id,
            access_level=access_level,
            transport=integration.transport,
            risk_class=access_level,
            default_approval_mode=integration.default_approval_mode,
            tool_id=tool,
            auth_modes=integration.auth_modes,
            resource_method=action_id,
        )

    if tool == "pip":
        integration = _integration_defaults("pip")
        action_id, access_level = _resolve_prefixed_subcommand_action(
            "pip",
            str(payload.get("args") or ""),
            _PIP_ACTION_LEVELS,
        )
        return IntegrationActionResolution(
            integration_id=integration.id,
            action_id=action_id,
            access_level=access_level,
            transport=integration.transport,
            risk_class=access_level,
            default_approval_mode=integration.default_approval_mode,
            tool_id=tool,
            auth_modes=integration.auth_modes,
            resource_method=action_id,
        )

    if tool == "npm":
        integration = _integration_defaults("npm")
        action_id, access_level = _resolve_prefixed_subcommand_action(
            "npm",
            str(payload.get("args") or ""),
            _NPM_ACTION_LEVELS,
        )
        return IntegrationActionResolution(
            integration_id=integration.id,
            action_id=action_id,
            access_level=access_level,
            transport=integration.transport,
            risk_class=access_level,
            default_approval_mode=integration.default_approval_mode,
            tool_id=tool,
            auth_modes=integration.auth_modes,
            resource_method=action_id,
        )

    if tool == "gh":
        integration = _integration_defaults("gh")
        action_id, access_level = _resolve_grouped_cli_action("gh", str(payload.get("args") or ""), _GH_ACTION_LEVELS)
        return IntegrationActionResolution(
            integration_id=integration.id,
            action_id=action_id,
            access_level=access_level,
            transport=integration.transport,
            risk_class=access_level,
            default_approval_mode=integration.default_approval_mode,
            tool_id=tool,
            auth_modes=integration.auth_modes,
            resource_method=action_id,
        )

    if tool == "glab":
        integration = _integration_defaults("glab")
        action_id, access_level = _resolve_grouped_cli_action(
            "glab",
            str(payload.get("args") or ""),
            _GLAB_ACTION_LEVELS,
        )
        return IntegrationActionResolution(
            integration_id=integration.id,
            action_id=action_id,
            access_level=access_level,
            transport=integration.transport,
            risk_class=access_level,
            default_approval_mode=integration.default_approval_mode,
            tool_id=tool,
            auth_modes=integration.auth_modes,
            resource_method=action_id,
        )

    if tool in {"write", "edit", "rm", "mkdir", "cat"}:
        integration = _integration_defaults("fileops")
        action_id = f"fileops.{tool}"
        access_level = {
            "cat": "read",
            "write": "write",
            "edit": "write",
            "mkdir": "write",
            "rm": "destructive",
        }.get(tool, "write")
        return IntegrationActionResolution(
            integration_id=integration.id,
            action_id=action_id,
            access_level=access_level,
            transport=integration.transport,
            risk_class=access_level,
            default_approval_mode=integration.default_approval_mode,
            tool_id=tool,
            auth_modes=integration.auth_modes,
            path=str(payload.get("path") or "").strip() or None,
            resource_method=action_id,
        )

    if tool.startswith("file_"):
        integration = _integration_defaults("fileops")
        action_suffix = tool.removeprefix("file_")
        action_id = f"fileops.{action_suffix}"
        access_level = {
            "read": "read",
            "list": "read",
            "search": "read",
            "grep": "read",
            "info": "read",
            "write": "write",
            "edit": "write",
            "move": "write",
            "delete": "destructive",
        }.get(action_suffix, "write")
        path = str(payload.get("path") or payload.get("source") or payload.get("destination") or "").strip() or None
        return IntegrationActionResolution(
            integration_id=integration.id,
            action_id=action_id,
            access_level=access_level,
            transport=integration.transport,
            risk_class=access_level,
            default_approval_mode=integration.default_approval_mode,
            tool_id=tool,
            auth_modes=integration.auth_modes,
            path=path,
            resource_method=action_id,
        )

    if tool.startswith("agent_"):
        integration = _integration_defaults("agent_runtime")
        action_id = tool.removeprefix("agent_")
        access_level = "read" if action_id == "get_status" else "write"
        return IntegrationActionResolution(
            integration_id=integration.id,
            action_id=action_id,
            access_level=access_level,
            transport=integration.transport,
            risk_class=access_level,
            default_approval_mode=integration.default_approval_mode,
            tool_id=tool,
            auth_modes=integration.auth_modes,
            path=str(payload.get("path") or "").strip() or None,
            resource_method=action_id,
        )

    integration = _integration_defaults(tool)
    return IntegrationActionResolution(
        integration_id=integration.id,
        action_id=tool,
        access_level="write",
        transport=integration.transport,
        risk_class=integration.risk_class,
        default_approval_mode=integration.default_approval_mode,
        tool_id=tool,
        auth_modes=integration.auth_modes,
        resource_method=tool,
    )


def evaluate_integration_grant(
    tool_id: str,
    params: dict[str, Any] | None,
    resource_access_policy: dict[str, Any] | None,
) -> IntegrationGrantDecision:
    """Evaluate resource_access_policy.integration_grants for one tool call."""
    resolution = resolve_integration_action(tool_id, params)
    access_policy = resource_access_policy if isinstance(resource_access_policy, dict) else {}
    grants = normalize_integration_grants(access_policy.get("integration_grants"))
    integration = _integration_defaults(resolution.integration_id)
    auth_mode = integration.auth_modes[0] if integration.auth_modes else "none"
    grant = grants.get(resolution.integration_id)
    if grant is None and resolution.transport == "mcp" and resolution.integration_id.startswith("mcp:"):
        grant = grants.get(resolution.integration_id.removeprefix("mcp:"))

    if not grants or grant is None:
        allowed = _allow_implicit_integration_grant(resolution)
        return IntegrationGrantDecision(
            allowed=allowed,
            integration_id=resolution.integration_id,
            action_id=resolution.action_id,
            access_level=resolution.access_level,
            transport=resolution.transport,
            risk_class=resolution.risk_class,
            default_approval_mode=resolution.default_approval_mode,
            auth_mode=auth_mode,
            reason="implicit_read_only_baseline" if allowed else "explicit_integration_grant_required",
        )

    if grant.get("enabled") is False:
        return IntegrationGrantDecision(
            allowed=False,
            integration_id=resolution.integration_id,
            action_id=resolution.action_id,
            access_level=resolution.access_level,
            transport=resolution.transport,
            risk_class=resolution.risk_class,
            default_approval_mode=str(grant.get("approval_mode") or resolution.default_approval_mode),
            auth_mode=auth_mode,
            reason="integration_disabled",
            grant=grant,
        )

    for pattern in grant.get("deny_actions") or []:
        if _matches_action_pattern(str(pattern), resolution.action_id):
            return IntegrationGrantDecision(
                allowed=False,
                integration_id=resolution.integration_id,
                action_id=resolution.action_id,
                access_level=resolution.access_level,
                transport=resolution.transport,
                risk_class=resolution.risk_class,
                default_approval_mode=str(grant.get("approval_mode") or resolution.default_approval_mode),
                auth_mode=auth_mode,
                reason="action_denied",
                grant=grant,
            )

    allow_actions = [str(item) for item in grant.get("allow_actions") or []]
    if allow_actions and not any(_matches_action_pattern(pattern, resolution.action_id) for pattern in allow_actions):
        return IntegrationGrantDecision(
            allowed=False,
            integration_id=resolution.integration_id,
            action_id=resolution.action_id,
            access_level=resolution.access_level,
            transport=resolution.transport,
            risk_class=resolution.risk_class,
            default_approval_mode=str(grant.get("approval_mode") or resolution.default_approval_mode),
            auth_mode=auth_mode,
            reason="action_not_granted",
            grant=grant,
        )

    approval_mode = str(grant.get("approval_mode") or resolution.default_approval_mode).strip().lower()
    if approval_mode == "read_only" and resolution.access_level != "read":
        return IntegrationGrantDecision(
            allowed=False,
            integration_id=resolution.integration_id,
            action_id=resolution.action_id,
            access_level=resolution.access_level,
            transport=resolution.transport,
            risk_class=resolution.risk_class,
            default_approval_mode=approval_mode,
            auth_mode=auth_mode,
            reason="read_only_policy",
            grant=grant,
        )

    allowed_domains = [str(item) for item in grant.get("allowed_domains") or []]
    if (
        allowed_domains
        and resolution.integration_id == "browser"
        and resolution.action_id != "navigate"
        and not resolution.domain
    ):
        return IntegrationGrantDecision(
            allowed=False,
            integration_id=resolution.integration_id,
            action_id=resolution.action_id,
            access_level=resolution.access_level,
            transport=resolution.transport,
            risk_class=resolution.risk_class,
            default_approval_mode=approval_mode or resolution.default_approval_mode,
            auth_mode=auth_mode,
            reason="domain_unknown",
            grant=grant,
        )

    if allowed_domains and resolution.domain and not _domain_allowed(resolution.domain, allowed_domains):
        return IntegrationGrantDecision(
            allowed=False,
            integration_id=resolution.integration_id,
            action_id=resolution.action_id,
            access_level=resolution.access_level,
            transport=resolution.transport,
            risk_class=resolution.risk_class,
            default_approval_mode=approval_mode or resolution.default_approval_mode,
            auth_mode=auth_mode,
            reason="domain_not_granted",
            grant=grant,
        )

    if resolution.private_network and not bool(grant.get("allow_private_network")):
        return IntegrationGrantDecision(
            allowed=False,
            integration_id=resolution.integration_id,
            action_id=resolution.action_id,
            access_level=resolution.access_level,
            transport=resolution.transport,
            risk_class=resolution.risk_class,
            default_approval_mode=approval_mode or resolution.default_approval_mode,
            auth_mode=auth_mode,
            reason="private_network_not_granted",
            grant=grant,
        )

    allowed_db_envs = [str(item).lower() for item in grant.get("allowed_db_envs") or []]
    if allowed_db_envs and resolution.db_env and resolution.db_env not in allowed_db_envs:
        return IntegrationGrantDecision(
            allowed=False,
            integration_id=resolution.integration_id,
            action_id=resolution.action_id,
            access_level=resolution.access_level,
            transport=resolution.transport,
            risk_class=resolution.risk_class,
            default_approval_mode=approval_mode or resolution.default_approval_mode,
            auth_mode=auth_mode,
            reason="db_env_not_granted",
            grant=grant,
        )

    allowed_paths = [str(item) for item in grant.get("allowed_paths") or []]
    if allowed_paths and resolution.path and not _path_allowed(resolution.path, allowed_paths):
        return IntegrationGrantDecision(
            allowed=False,
            integration_id=resolution.integration_id,
            action_id=resolution.action_id,
            access_level=resolution.access_level,
            transport=resolution.transport,
            risk_class=resolution.risk_class,
            default_approval_mode=approval_mode or resolution.default_approval_mode,
            auth_mode=auth_mode,
            reason="path_not_granted",
            grant=grant,
        )

    sensitive_access_used = bool((grant.get("secret_keys") or []) or (grant.get("shared_env_keys") or []))
    return IntegrationGrantDecision(
        allowed=True,
        integration_id=resolution.integration_id,
        action_id=resolution.action_id,
        access_level=resolution.access_level,
        transport=resolution.transport,
        risk_class=resolution.risk_class,
        default_approval_mode=approval_mode or resolution.default_approval_mode,
        auth_mode=auth_mode,
        reason="granted",
        grant=grant,
        sensitive_access_used=sensitive_access_used,
    )


def summarize_integration_grants(resource_access_policy: dict[str, Any] | None) -> list[str]:
    """Return compact human-readable grant summaries for prompt rendering."""
    access_policy = resource_access_policy if isinstance(resource_access_policy, dict) else {}
    grants = normalize_integration_grants(access_policy.get("integration_grants"))
    summaries: list[str] = []
    for integration_id, grant in sorted(grants.items()):
        parts = [f"`{integration_id}`"]
        if grant.get("enabled") is False:
            parts.append("disabled")
        elif grant.get("allow_actions"):
            parts.append("allow=" + ", ".join(f"`{item}`" for item in grant["allow_actions"]))
        else:
            parts.append("all actions")
        if grant.get("deny_actions"):
            parts.append("deny=" + ", ".join(f"`{item}`" for item in grant["deny_actions"]))
        if grant.get("allowed_domains"):
            parts.append("domains=" + ", ".join(f"`{item}`" for item in grant["allowed_domains"]))
        if grant.get("allowed_paths"):
            parts.append("paths=" + ", ".join(f"`{item}`" for item in grant["allowed_paths"]))
        if grant.get("allow_private_network"):
            parts.append("private_network=allowed")
        summaries.append(" | ".join(parts))
    return summaries


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
        return [tool_id for tool_id in available_ids if _tool_allowed_by_secure_default(CORE_TOOL_CATALOG.get(tool_id))]

    raw_allowed = normalize_string_list(policy.get("allowed_tool_ids"))
    if not raw_allowed:
        return [tool_id for tool_id in available_ids if _tool_allowed_by_secure_default(CORE_TOOL_CATALOG.get(tool_id))]
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
            "supports_local_connection": "local" in definition.supported_auth_modes,
            "login_flow_kind": definition.login_flow_kind,
            "requires_project_id": definition.requires_project_id,
            "connection_managed": definition.connection_managed,
            "show_in_settings": definition.show_in_settings,
        }
        for definition in _CORE_PROVIDER_DEFINITIONS
    ]
