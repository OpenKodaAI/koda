"""Dynamic system prompt generation for agent tools available to the runtime."""

from __future__ import annotations

from typing import Any

from koda.agent_contract import resolve_feature_filtered_tools, summarize_integration_grants
from koda.config import (
    AGENT_ALLOWED_TOOLS,
    AGENT_EXECUTION_POLICY,
    AGENT_RESOURCE_ACCESS_POLICY,
    AGENT_TOOL_POLICY,
    BROWSER_FEATURES_ENABLED,
    BROWSER_NETWORK_INTERCEPTION_ENABLED,
    BROWSER_SESSION_PERSISTENCE_ENABLED,
    CONFLUENCE_ENABLED,
    FILEOPS_ENABLED,
    GIT_ENABLED,
    GWS_ENABLED,
    INTER_AGENT_ENABLED,
    JIRA_ENABLED,
    MCP_ENABLED,
    PLUGIN_SYSTEM_ENABLED,
    SHELL_ENABLED,
    SNAPSHOT_ENABLED,
    WEBHOOK_ENABLED,
    WORKFLOW_ENABLED,
)
from koda.config import (
    POSTGRES_ENABLED as _POSTGRES_ENABLED,
)
from koda.services.cache_config import CACHE_ENABLED, SCRIPT_LIBRARY_ENABLED
from koda.services.execution_policy import resolve_execution_policy_allowed_tool_ids

# Compatibility export kept for older tests and monkeypatch-based callers.
POSTGRES_ENABLED = _POSTGRES_ENABLED


def _tool_id_from_bullet_line(line: str) -> str | None:
    stripped = line.lstrip()
    if not stripped.startswith("- `"):
        return None
    end = stripped.find("`", 3)
    if end == -1:
        return None
    if "—" not in stripped[end + 1 :]:
        return None
    return stripped[3:end].strip() or None


def _filter_prompt_to_allowed_tools(prompt: str, allowed_tool_ids: set[str]) -> str:
    if not prompt.strip():
        return prompt

    blocked_tool_ids = {
        tool_id
        for tool_id in {
            "job_list",
            "job_get",
            "job_create",
            "job_update",
            "job_validate",
            "job_activate",
            "job_pause",
            "job_resume",
            "job_delete",
            "job_run_now",
            "job_runs",
            "cron_list",
            "cron_add",
            "cron_delete",
            "cron_toggle",
            "web_search",
            "fetch_url",
            "http_request",
            "agent_set_workdir",
            "agent_get_status",
            "browser_navigate",
            "browser_click",
            "browser_type",
            "browser_submit",
            "browser_screenshot",
            "browser_get_text",
            "browser_get_elements",
            "browser_select",
            "browser_scroll",
            "browser_wait",
            "browser_back",
            "browser_forward",
            "browser_hover",
            "browser_press_key",
            "browser_cookies",
            "sqlite_query",
            "sqlite_schema",
            "mongo_query",
            "browser_tab_open",
            "browser_tab_close",
            "browser_tab_switch",
            "browser_tab_list",
            "browser_tab_compare",
            "browser_execute_js",
            "browser_download",
            "browser_upload",
            "browser_set_viewport",
            "browser_pdf",
            "db_query",
            "db_schema",
            "db_explain",
            "db_switch_env",
            "mysql_query",
            "mysql_schema",
            "script_search",
            "script_list",
            "script_save",
            "script_delete",
            "cache_clear",
            "cache_stats",
            "snapshot_save",
            "snapshot_restore",
            "snapshot_list",
            "snapshot_diff",
            "snapshot_delete",
            "redis_query",
            "file_read",
            "file_write",
            "file_edit",
            "file_list",
            "file_search",
            "file_grep",
            "file_delete",
            "file_move",
            "file_info",
            "shell_execute",
            "shell_bg",
            "shell_status",
            "shell_kill",
            "shell_output",
            "git_status",
            "git_diff",
            "git_log",
            "git_commit",
            "git_branch",
            "git_checkout",
            "git_push",
            "git_pull",
            "plugin_list",
            "plugin_info",
            "plugin_install",
            "plugin_uninstall",
            "plugin_reload",
            "workflow_create",
            "workflow_run",
            "workflow_list",
            "workflow_get",
            "workflow_delete",
            "agent_send",
            "agent_receive",
            "agent_delegate",
            "agent_list_agents",
            "agent_broadcast",
        }
        if tool_id not in allowed_tool_ids
    }

    lines = prompt.splitlines()
    filtered: list[str] = []
    skip_tool_block = False
    index = 0

    while index < len(lines):
        line = lines[index]

        if skip_tool_block:
            if line.startswith("#") or line.startswith("- `"):
                skip_tool_block = False
            else:
                index += 1
                continue

        tool_id = _tool_id_from_bullet_line(line)
        if tool_id and tool_id not in allowed_tool_ids:
            skip_tool_block = True
            index += 1
            continue

        if any(blocked_tool_id in line for blocked_tool_id in blocked_tool_ids):
            index += 1
            continue

        filtered.append(line)
        index += 1

    return "\n".join(filtered).strip()


def _configured_tool_policy(tool_policy: dict[str, Any] | None = None) -> dict[str, Any]:
    if tool_policy is not None:
        return dict(tool_policy)
    if AGENT_TOOL_POLICY:
        return dict(AGENT_TOOL_POLICY)
    if AGENT_ALLOWED_TOOLS:
        return {"allowed_tool_ids": sorted(AGENT_ALLOWED_TOOLS)}
    return {}


def _configured_execution_policy(execution_policy: dict[str, Any] | None = None) -> dict[str, Any]:
    if execution_policy is not None:
        return dict(execution_policy)
    if AGENT_EXECUTION_POLICY:
        return dict(AGENT_EXECUTION_POLICY)
    return {}


def _configured_resource_access_policy(resource_access_policy: dict[str, Any] | None = None) -> dict[str, Any]:
    if resource_access_policy is not None:
        return dict(resource_access_policy)
    if AGENT_RESOURCE_ACCESS_POLICY:
        return dict(AGENT_RESOURCE_ACCESS_POLICY)
    return {}


def _blocked_mcp_tool_names(agent_id: str, server_key: str) -> set[str]:
    try:
        from koda.control_plane.manager import get_control_plane_manager

        return {
            str(item.get("tool_name") or "")
            for item in get_control_plane_manager().list_mcp_tool_policies(agent_id, server_key)
            if str(item.get("policy") or "") == "blocked"
        }
    except Exception:
        return set()


def _build_mcp_tools_prompt(agent_id: str) -> str:
    """Generate system prompt section documenting available MCP tools for an agent."""
    from koda.services.mcp_manager import mcp_server_manager

    sections: list[str] = []

    # Collect all running MCP instances for this agent
    for key, instance in mcp_server_manager.active_instances.items():
        if not key.startswith(f"{agent_id}:"):
            continue
        if not instance.started or not instance.cached_tools:
            continue
        blocked_tool_names = _blocked_mcp_tool_names(agent_id, instance.server_key)

        server_section_lines: list[str] = []
        server_section_lines.append(f"### MCP Server: {instance.server_key}")
        server_section_lines.append("")

        for tool in instance.cached_tools:
            if tool.name in blocked_tool_names:
                continue
            from koda.services.mcp_bridge import mcp_tool_id

            tid = mcp_tool_id(instance.server_key, tool.name)
            desc = tool.description or "No description available."
            server_section_lines.append(f"**`{tid}`** — {desc}")

            # Add parameter schema if available
            if tool.input_schema and tool.input_schema.get("properties"):
                props = tool.input_schema["properties"]
                required = set(tool.input_schema.get("required", []))
                param_lines: list[str] = []
                for param_name, param_info in props.items():
                    param_type = param_info.get("type", "any")
                    param_desc = param_info.get("description", "")
                    req_marker = " (required)" if param_name in required else ""
                    param_lines.append(f"  - `{param_name}` ({param_type}{req_marker}): {param_desc}")
                if param_lines:
                    server_section_lines.append("  Parameters:")
                    server_section_lines.extend(param_lines)

            server_section_lines.append("")

        if server_section_lines:
            sections.append("\n".join(server_section_lines))

    if not sections:
        return ""

    header = (
        "## MCP Server Tools\n\n"
        "The following tools are available from connected MCP servers. "
        'Use them with `<agent_cmd tool="TOOL_ID">{"param": "value"}</agent_cmd>`.\n\n'
    )
    return header + "\n".join(sections)


def build_agent_tools_prompt(
    *,
    agent_id: str | None = None,
    tool_policy: dict[str, Any] | None = None,
    execution_policy: dict[str, Any] | None = None,
    resource_access_policy: dict[str, Any] | None = None,
    feature_flags: dict[str, bool] | None = None,
) -> str:
    """Generate the <agent_tools> section of the system prompt based on feature flags."""
    sections: list[str] = []
    resolved_feature_flags = {
        "browser": BROWSER_FEATURES_ENABLED,
        "jira": JIRA_ENABLED,
        "confluence": CONFLUENCE_ENABLED,
        "gws": GWS_ENABLED,
        "fileops": FILEOPS_ENABLED,
        "shell": SHELL_ENABLED,
        "git": GIT_ENABLED,
        "plugins": PLUGIN_SYSTEM_ENABLED,
        "workflows": WORKFLOW_ENABLED,
        "inter_agent": INTER_AGENT_ENABLED,
        "snapshots": SNAPSHOT_ENABLED,
        **dict(feature_flags or {}),
    }
    tool_policy = _configured_tool_policy(tool_policy)
    execution_policy = _configured_execution_policy(execution_policy)
    resource_access_policy = _configured_resource_access_policy(resource_access_policy)
    allowed_tool_ids = resolve_execution_policy_allowed_tool_ids(
        tool_policy=tool_policy,
        execution_policy=execution_policy,
        feature_flags=resolved_feature_flags,
    )
    available_tool_ids = [
        str(item["id"]) for item in resolve_feature_filtered_tools(resolved_feature_flags) if bool(item["available"])
    ]
    has_tool_subset = set(allowed_tool_ids) != set(available_tool_ids)
    integration_grant_summaries = summarize_integration_grants(resource_access_policy)
    if has_tool_subset and allowed_tool_ids:
        allowed_tool_ids = sorted(allowed_tool_ids)

    sections.append("""\
<agent_tools>
You have access to agent-specific tools that you can invoke using <agent_cmd> XML tags.
These tools let you execute actions directly — do NOT tell the user to type /commands manually.

## Protocol
- Emit one or more <agent_cmd> tags in your response. The agent will execute them and return results.
- Each tag must have a tool attribute and a JSON body with the parameters.
- You may emit multiple <agent_cmd> tags in a single response.
- After emitting <agent_cmd> tags, STOP and wait for the results.
  Do not continue with a final answer until you receive <tool_result> tags.
- JSON must be valid. Invalid JSON will be silently skipped.
- Before any write-capable <agent_cmd>, emit exactly one <action_plan> block in the same response.
- If you do not yet have enough evidence or sources, do not emit the write tool yet. Gather read-only evidence first.

## Format
```
<agent_cmd tool="tool_name">{"param": "value"}</agent_cmd>
```

## Required <action_plan> For Writes
Use this exact structure before any write operation:
```
<action_plan>
<summary>What you are about to do</summary>
<assumptions>Important assumptions and unknowns</assumptions>
<evidence>What evidence you already gathered</evidence>
<sources>Which source labels, files, or docs justify this action</sources>
<risk>Main risk if the action is wrong</risk>
<verification>How you will verify the resulting state after the write</verification>
<rollback>Rollback note when the task kind is deploy-like</rollback>
<probable_cause>Probable cause when the task kind is bugfix-like</probable_cause>
<escalation>Why this write is justified when the task kind is investigation-like</escalation>
<success>How you will verify success after the write</success>
</action_plan>
```

The runtime can block low-confidence writes if the plan or sources are missing.
""")

    if has_tool_subset:
        tool_ids_line = (
            ", ".join(f"`{tool_id}`" for tool_id in allowed_tool_ids)
            if allowed_tool_ids
            else "No core tools are enabled for this agent."
        )
        sections.append(
            "\n".join(
                [
                    "",
                    "## Enabled Tool Subset",
                    "Only the following core tools are enabled for this agent.",
                    "Do not emit any other <agent_cmd> tool ids because the runtime will reject them.",
                    tool_ids_line,
                    "",
                ]
            )
        )

    if integration_grant_summaries:
        sections.append(
            "\n".join(
                [
                    "",
                    "## Integration Grants",
                    "Respect the active integration grants before emitting any tool call.",
                    (
                        "If a target integration/action is not granted, "
                        "gather read-only evidence and ask for scope changes "
                        "instead of forcing the call."
                    ),
                    *[f"- {line}" for line in integration_grant_summaries],
                    "",
                ]
            )
        )

    sections.append("""\

## Available Tools

### Scheduled Jobs
Prefer these tools for all new automations.
New jobs must be created with evidence and validated safely before activation.
Initial validation auto-activates the job by default when it passes safely.

- `job_list` — List scheduled jobs. Params: `{}`
- `job_get` — Inspect one scheduled job. Params: `{"job_id": 123}`
- `job_create` — Create a new scheduled job.
  Agent query params:
  `{"job_type": "agent_query", ...}`
  Required keys: `trigger_type`, `schedule_expr`, `query`.
  Optional keys: `timezone`, `provider`, `model`, `work_dir`, `session_id`, `auto_activate_after_validation`.
  Reminder params:
  `{"job_type": "reminder", "trigger_type": "one_shot|interval|cron",`
  `"schedule_expr": "2026-03-17T15:00:00+00:00", "text": "..."}`
  Shell command params:
  `{"job_type": "shell_command", "trigger_type": "cron", "schedule_expr": "...", "command": "git status"}`
- `job_update` — Edit an existing scheduled job without losing audit history.
  Params:
  `{"job_id": 123, "patch": {"schedule_expr": "7200", "trigger_type": "interval",`
  `"timezone": "America/Sao_Paulo"}, "reason": "cadence update",`
  `"expected_config_version": 3, "evidence": {"requested_by": "user"}}`
- `job_validate` — Queue a safe dry-run validation without changing activation state. Params: `{"job_id": 123}`
- `job_activate` — Activate a validated job. Params: `{"job_id": 123}`
- `job_pause` — Pause a job. Params: `{"job_id": 123}`
- `job_resume` — Resume a paused or failed-open job. Params: `{"job_id": 123}`
- `job_delete` — Archive a job. Params: `{"job_id": 123}`
- `job_run_now` — Queue an immediate manual run. Params: `{"job_id": 123}`
- `job_runs` — Show recent runs. Params: `{"job_id": 123, "limit": 10}`

### Legacy Cron Jobs
Use these only when the user explicitly asks for cron compatibility or for a simple read-only shell command.
- `cron_list` — List legacy cron jobs for the user. Params: `{}`
- `cron_add` — Create a legacy read-only cron job.
  Params: `{"expression": "cron_expr", "command": "shell_cmd", "description": "optional desc"}`
- `cron_delete` — Delete a legacy cron job. Params: `{"job_id": 123}`
- `cron_toggle` — Enable or disable a legacy cron job. Params: `{"job_id": 123, "enabled": true/false}`

### Web & HTTP
- `web_search` — Search the web. Params: `{"query": "search terms"}`
- `fetch_url` — Fetch the content of a URL. Params: `{"url": "https://..."}`
- `http_request` — Make an HTTP request.
  Params: `{"method": "GET/POST/...", "url": "https://...", "body": "optional", "headers": {"key": "val"}}`

### Agent Management
- `agent_set_workdir` — Change the agent's working directory. Params: `{"path": "/absolute/path"}`
- `agent_get_status` — Get agent status (work_dir, model, session, mode, cost). Params: `{}`
- `request_skill` — Request an expert skill by name, alias, or description.
  Returns the full skill methodology with instructions.
  Params: `{"query": "tdd"}` or `{"query": "security analysis"}` or `{"query": "code-review"}`""")

    if BROWSER_FEATURES_ENABLED:
        sections.append("""
### Browser Automation
Use these tools for web browsing, form filling, scraping, and interactive web tasks.

- `browser_navigate` — Navigate to a URL. Params: `{"url": "https://..."}`
- `browser_click` — Click an element (CSS, button text, link text, aria-label). Params: `{"selector": "Submit"}`
- `browser_type` — Type into a field. Params: `{"selector": "input[name=email]", "text": "user@example.com"}`
- `browser_submit` — Submit a form. Params: `{}` or `{"selector": "form#login"}`
- `browser_screenshot` — Take a screenshot (returns image path). Params: `{}`
- `browser_get_text` — Get page text content. Params: `{}` or `{"selector": "#content"}`
- `browser_get_elements` — List interactive elements. Params: `{}` or `{"element_type": "buttons"}`
- `browser_select` — Select dropdown option. Params: `{"selector": "select#country", "label": "Brazil"}`
- `browser_scroll` — Scroll page. Params: `{"direction": "down", "amount": 500}`
- `browser_wait` — Wait for element. Params: `{"selector": "#results", "state": "visible"}`
- `browser_back` — Go back. Params: `{}`
- `browser_forward` — Go forward. Params: `{}`
- `browser_hover` — Hover over an element (for menus, tooltips). Params: `{"selector": "Menu"}`
- `browser_press_key` — Press a keyboard key.
  Supported keys include Enter, Escape, Tab, Backspace, Delete, ArrowUp,
  ArrowDown, ArrowLeft, ArrowRight, or combos like Control+A.
  Params: `{"key": "Enter"}` or `{"key": "Escape", "selector": "input#search"}`
- `browser_cookies` — Get/set cookies. Params: `{"action": "get"}` or `{"action": "set", "name": "k", "value": "v"}`
- `browser_execute_js` — Execute JavaScript in page context. Params: `{"script": "document.title"}`
- `browser_download` — Download a file. Params: `{"url": "https://example.com/file.pdf"}`
  Optional: `{"url": "...", "filename": "report.pdf"}`
- `browser_upload` — Upload file to input. Params: `{"file_path": "/path/to/file.pdf"}`
  Optional: `{"file_path": "...", "selector": "input#upload"}`
- `browser_set_viewport` — Change viewport size. Params: `{"width": 1920, "height": 1080}`
- `browser_pdf` — Generate PDF of current page. Params: `{}`

#### Tab Management
- `browser_tab_open` — Open a new tab. Params: `{}` or `{"url": "https://..."}`
- `browser_tab_close` — Close a tab. Params: `{"tab_id": 1}` or `{}` (closes active)
- `browser_tab_switch` — Switch active tab. Params: `{"tab_id": 1}`
- `browser_tab_list` — List all open tabs. Params: `{}`
- `browser_tab_compare` — Compare content of tabs.
  Params: `{"tab_ids": [0, 1]}` Optional: `{"tab_ids": [0, 1], "selector": "#main"}`

#### Browser Workflow Best Practices
1. After `browser_navigate`, ALWAYS use `browser_screenshot` to see the page state.
2. Before clicking or typing, use `browser_get_elements` to identify correct selectors.
3. Prefer text selectors ("Sign In") over CSS selectors ("#btn-submit") when possible.
4. After form submission or click, take a screenshot to verify the result.
5. If a click/type fails, retry with alternative selectors (text, aria-label, placeholder).
6. For multi-step workflows, provide progress updates to the user between steps.
7. Use `browser_scroll` to reach elements below the fold before interacting.
8. Batch related operations: emit `browser_navigate` + `browser_screenshot` in the same response.
9. Use `browser_hover` to open dropdown menus before clicking their items.
10. Use `browser_press_key` with "Enter" to submit search fields that lack a submit button.""")

    if BROWSER_FEATURES_ENABLED and BROWSER_NETWORK_INTERCEPTION_ENABLED:
        sections.append("""
#### Network Interception
Capture, inspect, and mock network requests made by the browser.

- `browser_network_capture_start` — Start capturing network requests.
  Params: `{}` Optional: `{"url_pattern": "**/api/*"}`
- `browser_network_capture_stop` — Stop capturing and return summary.
  Params: `{}`
- `browser_network_requests` — Get captured network requests.
  Params: `{}` Optional: `{"limit": 50, "filter": "api"}`
- `browser_network_mock` — Mock a network route with a custom response.
  Params: `{"url_pattern": "**/api/*",`
  `"response": {"status": 200, "body": "{}", "headers": {"Content-Type": "application/json"}}}`""")

    if BROWSER_FEATURES_ENABLED and BROWSER_SESSION_PERSISTENCE_ENABLED:
        sections.append("""
#### Session Persistence
Save and restore browser sessions (cookies, local storage, session storage).

- `browser_session_save` — Save the current browser session. Params: `{"name": "logged-in"}`
- `browser_session_restore` — Restore a saved session. Params: `{"name": "logged-in"}`
- `browser_session_list` — List saved sessions. Params: `{}`""")

    if GWS_ENABLED:
        sections.append("""
### Google Workspace
- `gws` — Execute a Google Workspace CLI command.
  Params: `{"args": "gmail users.messages.list --params '{\"userId\": \"me\"}'"}"`
  - Follow the same security tiers defined in the Google Workspace section of this prompt.
  - Tier 3 operations (send, delete, share): ask user confirmation BEFORE invoking.""")

    if JIRA_ENABLED:
        sections.append("""
### Jira
- `jira` — Execute a Jira command. Params: `{"args": "issues search --jql 'project = PROJ'"}`
  - `issues analyze --key PROJ-123` — Build the full issue dossier: metadata, description, comments, attachments,
    media refs, URLs, linked pages, and proactive artifact extraction for PDFs, DOCX, spreadsheets, text, images,
    audio, and videos, including public video URLs found inside the issue when they can be accessed safely
  - `issues transitions --key PROJ-123` — List available transitions for an issue
  - `issues comment_get --key PROJ-123 --comment-id 10000` — Read one specific comment
  - `issues comment_edit --key PROJ-123 --comment-id 10000 --body "..."` —
    Edit a comment authored by the service account
  - `issues comment_delete --key PROJ-123 --comment-id 10000` — Delete a comment authored by the service account
  - `issues comment_reply --key PROJ-123 --comment-id 10000 --body "..."` — Create a safe linked reply
    as a new top-level comment
  - `issues attachments --key PROJ-123` — List issue attachments
  - `issues links --key PROJ-123` — List issue links and remote links
  - `issues view_video --key PROJ-123 --attachment-id 12345`
    — Download video attachment, extract frames, and analyze visually
  - `issues view_image --key PROJ-123 --attachment-id 12345` — Download image attachment for visual analysis
  - `issues view_audio --key PROJ-123 --attachment-id 12345` — Download and transcribe audio attachment
  - Format: `<resource> <action> [--key value ...]`
  - Mention syntax in comments: `[~accountId:ACCOUNT_ID]` — use `users search --query "name"` to find account IDs
  - Replies are implemented as linked top-level comments for safety and documented API compatibility
  - When a task mentions a Jira issue key, build the full issue dossier first and use it as grounding context
  - If the dossier reports critical extraction gaps, keep the task read-only until the missing artifacts are resolved
  - Follow the same security tiers defined in the Atlassian section of this prompt.""")

    if CONFLUENCE_ENABLED:
        sections.append("""
### Confluence
- `confluence` — Execute a Confluence command. Params: `{"args": "pages search --cql 'space = DEV'"}`
  - Format: `<resource> <action> [--key value ...]`
  - Follow the same security tiers defined in the Atlassian section of this prompt.""")

    if SCRIPT_LIBRARY_ENABLED:
        sections.append("""
### Script Library
Reusable code snippets saved by the user. Before generating code from scratch, check if a relevant script exists.

- `script_save` — Save a reusable script.
  Params:
  `{"title": "name", "description": "what it does",`
  `"content": "code...", "language": "python",`
  `"tags": ["util", "api"]}`
- `script_search` — Search for relevant scripts.
  Params: `{"query": "search terms"}`
  Optional: `{"query": "...", "language": "python"}`
- `script_list` — List saved scripts. Params: `{}` Optional: `{"language": "python", "limit": 10}`
- `script_delete` — Remove a script. Params: `{"script_id": 123}`

#### Script Workflow
1. Before generating code from scratch, use `script_search` to check for existing relevant scripts.
2. After creating useful, reusable code, save it with `script_save` for future reference.
3. When adapting a saved script, acknowledge the source and explain the changes.""")

    if CACHE_ENABLED:
        sections.append("""
### Cache Management
- `cache_stats` — View cache statistics and estimated token savings. Params: `{}`
- `cache_clear` — Clear all cached responses for the user. Params: `{}`""")

    if SNAPSHOT_ENABLED:
        sections.append("""
### Environment Snapshots
Save and restore complete agent environment state for debugging and reproducibility.

- `snapshot_save` — Save a named snapshot. Params: `{"name": "before-deploy"}`
- `snapshot_restore` — Load a saved snapshot (inspection only). Params: `{"name": "before-deploy"}`
- `snapshot_list` — List saved snapshots. Params: `{}`
- `snapshot_diff` — Compare two snapshots. Params: `{"from": "before-deploy", "to": "after-deploy"}`
- `snapshot_delete` — Delete a snapshot. Params: `{"name": "old-snapshot"}`

#### Snapshot Best Practices
1. Save a snapshot before making significant environment changes.
2. Use `snapshot_diff` to understand what changed between two points in time.
3. Snapshot names must be alphanumeric with hyphens/underscores (1-64 chars).""")

    if WEBHOOK_ENABLED:
        sections.append("""
### Webhooks
Register webhook endpoints to receive external events and wait for incoming payloads.

- `webhook_register` — Register a webhook endpoint.
  Params: `{"name": "deploy-hook", "path": "/hooks/deploy"}`
  Optional: `{"name": "...", "path": "...", "secret": "s3cret"}`
- `webhook_unregister` — Remove a webhook. Params: `{"name": "deploy-hook"}`
- `webhook_list` — List registered webhooks. Params: `{}`
- `event_wait` — Wait for an incoming webhook event.
  Params: `{"event_type": "webhook.deploy-hook"}`
  Optional: `{"event_type": "...", "timeout": 60}` (max 300s)

#### Webhook Best Practices
1. Use `webhook_list` to check existing registrations before creating new ones.
2. Set a secret for production webhooks to verify signatures.
3. Use reasonable timeouts for `event_wait` to avoid blocking the agent.""")

    if PLUGIN_SYSTEM_ENABLED:
        sections.append("""
### Plugin Management
- `plugin_list` — List installed plugins. Params: `{}`
- `plugin_info` — Get plugin details. Params: `{"name": "my-plugin"}`
- `plugin_install` — Install a plugin from path. Params: `{"path": "/plugins/my-plugin"}`
- `plugin_uninstall` — Uninstall a plugin. Params: `{"name": "my-plugin"}`
- `plugin_reload` — Hot-reload a plugin. Params: `{"name": "my-plugin"}`""")
        # Add dynamic prompt sections from plugins
        from koda.plugins import get_registry

        for section in get_registry().get_prompt_sections():
            sections.append(section)

    if WORKFLOW_ENABLED:
        sections.append("""
### Workflows (Tool Composition)
- `workflow_create` — Create a workflow.
  Params: `{"name": "my-flow", "steps": [{"id": "s1", "tool": "web_search", "params": {"query": "..."}},`
  `{"id": "s2", "tool": "fetch_url", "params": {"url": "https://example.com"}}]}`
- `workflow_run` — Run a workflow. Params: `{"name": "my-flow"}`
- `workflow_list` — List workflows. Params: `{}`
- `workflow_get` — Get workflow details. Params: `{"name": "my-flow"}`
- `workflow_delete` — Delete a workflow. Params: `{"name": "my-flow"}`

Use `{{ steps.<step_id>.<field> }}` for variable binding between steps (output, success).
Steps execute sequentially. Use `"condition"` for conditional execution and `"on_failure": "continue|stop|skip"`.""")

    if INTER_AGENT_ENABLED:
        sections.append("""
### Inter-Agent Communication
Communicate with other agents, delegate tasks, and coordinate work.

- `agent_send` — Send a message to another agent. Params: `{"to": "agent-2", "message": "Hello"}`
- `agent_receive` — Receive the next message from inbox. Params: `{"timeout": 30}`
- `agent_delegate` — Delegate a task and wait for result.
  Params: `{"to": "agent-2", "task": "Analyze report", "timeout": 60}`
- `agent_list_agents` — List known agents and inbox status. Params: `{}`
- `agent_broadcast` — Send a message to all known agents. Params: `{"message": "Status update"}`""")

    if FILEOPS_ENABLED:
        sections.append("""
### File Operations
Read, write, search, and manage files within the agent's working directory.
All paths are sandboxed to the work directory. Sensitive files (.env, .key, etc.) are blocked.

- `file_read` — Read file contents. Params: `{"path": "src/main.py"}`
  Optional: `{"path": "...", "offset": 10, "limit": 50}`
- `file_write` — Create or overwrite a file.
  Params: `{"path": "output.txt", "content": "Hello world"}`
- `file_edit` — Replace text in a file.
  Params: `{"path": "src/main.py", "old_string": "foo", "new_string": "bar"}`
  Optional: `{"...", "replace_all": true}`
- `file_list` — List directory contents. Params: `{}` or `{"path": "src/"}`
- `file_search` — Search files by name pattern. Params: `{"pattern": "*.py"}`
  Optional: `{"pattern": "...", "path": "src/"}`
- `file_grep` — Search file contents by regex. Params: `{"pattern": "TODO"}`
  Optional: `{"pattern": "...", "path": "src/", "glob": "*.py"}`
- `file_delete` — Delete a file. Params: `{"path": "temp.txt"}`
- `file_move` — Move or rename. Params: `{"source": "old.txt", "destination": "new.txt"}`
- `file_info` — Get file metadata. Params: `{"path": "src/main.py"}`

#### File Operations Best Practices
1. Use `file_list` and `file_search` to explore before reading.
2. Use `file_read` with offset/limit for large files.
3. Prefer `file_edit` over `file_write` for modifying existing files.
4. Use `file_grep` to find code patterns before editing.
5. Paths are relative to the work directory unless absolute.""")

    if SHELL_ENABLED:
        sections.append("""
### Shell Execution
Execute shell commands within the agent's working directory.
Dangerous commands (rm -rf, mkfs, shutdown, etc.) are blocked. Commands run with the agent's environment.

- `shell_execute` — Run a command and get output.
  Params: `{"command": "ls -la"}` Optional: `{"command": "...", "timeout": 60}`
- `shell_bg` — Run a command in the background.
  Params: `{"command": "npm run build"}` Optional: `{"command": "...", "timeout": 300}`
- `shell_status` — Check background process status. Params: `{"handle_id": "bg-111-1"}`
- `shell_kill` — Kill a background process. Params: `{"handle_id": "bg-111-1"}`
- `shell_output` — Read output from a finished background process. Params: `{"handle_id": "bg-111-1"}`

#### Shell Best Practices
1. Prefer `shell_execute` for quick commands (< 30s).
2. Use `shell_bg` for long-running commands (builds, tests, servers).
3. Always check `shell_status` before reading `shell_output`.
4. Kill background processes when they're no longer needed.
5. Maximum timeout: 300s for execute, 600s for background.""")

    if GIT_ENABLED:
        sections.append("""
### Git Operations
Structured git commands for version control within the working directory.
All operations are validated against the allowed git commands list.

- `git_status` — Show working tree status. Params: `{}` Optional: `{"short": true}`
- `git_diff` — Show changes. Params: `{}` Optional: `{"staged": true, "ref": "HEAD~3", "path": "src/", "stat": true}`
- `git_log` — Show commit history. Params: `{}` Optional: `{"limit": 20, "all": true, "graph": true, "path": "src/"}`
- `git_commit` — Create a commit. Params: `{"message": "fix: resolve login bug"}`
  Optional: `{"message": "...", "all": true}`
- `git_branch` — List branches: `{}` or `{"all": true}`.
  Create: `{"name": "feature/x"}` Optional: `{"name": "...", "start_point": "main"}`
- `git_checkout` — Switch branch: `{"target": "main"}`. Create and switch: `{"target": "feature/x", "create": true}`
- `git_push` — Push to remote. Params: `{}` Optional: `{"remote": "origin", "branch": "main", "set_upstream": true}`
- `git_pull` — Pull from remote. Params: `{}` Optional: `{"remote": "origin", "branch": "main", "rebase": true}`

#### Git Best Practices
1. Always check `git_status` before committing.
2. Review changes with `git_diff` before committing.
3. Write descriptive commit messages following conventional commits.
4. Use `git_branch` to isolate work before making changes.
5. Pull before pushing to avoid conflicts.""")

    if MCP_ENABLED and agent_id:
        mcp_section = _build_mcp_tools_prompt(agent_id)
        if mcp_section:
            sections.append("\n" + mcp_section)

    sections.append("""
## Important Rules
1. Use these tools to execute actions directly.
   Do NOT instruct the user to type /cron, /search, /fetch, or any other agent command.
2. For cron commands: validate that the cron expression makes sense for what the user asked.
   Example: "every day at 3am" = "0 3 * * *".
3. Database access is MCP-only. Do NOT emit native database tool ids or request native DB access.
4. Shell commands, git, GitHub CLI, Docker, pip, and npm are already available
   through your native Bash/CLI tools. Do NOT use agent tools for those.
5. Wait for <tool_result> before composing your final response to the user.
</agent_tools>""")

    prompt = "\n".join(sections)
    if has_tool_subset:
        prompt = _filter_prompt_to_allowed_tools(prompt, set(allowed_tool_ids))
    return prompt
