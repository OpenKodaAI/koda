"""Dynamic system prompt generation for agent tools available to the runtime."""

from koda.agent_contract import normalize_string_list, resolve_allowed_tool_ids
from koda.config import (
    AGENT_ALLOWED_TOOLS,
    AGENT_TOOL_POLICY,
    BROWSER_FEATURES_ENABLED,
    CONFLUENCE_ENABLED,
    GWS_ENABLED,
    JIRA_ENABLED,
    POSTGRES_AVAILABLE_ENVS,
    POSTGRES_ENABLED,
    POSTGRES_MAX_ROWS_CAP,
)
from koda.services.cache_config import CACHE_ENABLED, SCRIPT_LIBRARY_ENABLED


def build_agent_tools_prompt(postgres_env: str | None = None) -> str:
    """Generate the <agent_tools> section of the system prompt based on feature flags."""
    sections: list[str] = []
    feature_flags = {
        "browser": BROWSER_FEATURES_ENABLED,
        "postgres": POSTGRES_ENABLED,
        "jira": JIRA_ENABLED,
        "confluence": CONFLUENCE_ENABLED,
        "gws": GWS_ENABLED,
    }
    if AGENT_TOOL_POLICY:
        tool_policy = AGENT_TOOL_POLICY
    elif AGENT_ALLOWED_TOOLS:
        tool_policy = {"allowed_tool_ids": sorted(AGENT_ALLOWED_TOOLS)}
    else:
        tool_policy = {}
    has_explicit_tool_subset = bool(normalize_string_list(tool_policy.get("allowed_tool_ids")))
    allowed_tool_ids = resolve_allowed_tool_ids(tool_policy, feature_flags=feature_flags)
    if has_explicit_tool_subset and allowed_tool_ids:
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

    if has_explicit_tool_subset and allowed_tool_ids:
        sections.append(
            "\n".join(
                [
                    "",
                    "## Enabled Tool Subset",
                    "Only the following core tools are enabled for this agent.",
                    "Do not emit any other <agent_cmd> tool ids because the runtime will reject them.",
                    ", ".join(f"`{tool_id}`" for tool_id in allowed_tool_ids),
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
  `{"job_type": "reminder", "schedule_expr": "2026-03-17T15:00:00+00:00", "text": "..."}`
  Shell command params:
  `{"job_type": "shell_command", "trigger_type": "cron", "schedule_expr": "...", "command": "git status"}`
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
- `agent_get_status` — Get agent status (work_dir, model, session, mode, cost). Params: `{}`""")

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

    if POSTGRES_ENABLED:
        multi_env = len(POSTGRES_AVAILABLE_ENVS) > 1
        active_env = postgres_env or (
            "prod"
            if "prod" in POSTGRES_AVAILABLE_ENVS
            else POSTGRES_AVAILABLE_ENVS[0]
            if POSTGRES_AVAILABLE_ENVS
            else "default"
        )

        if multi_env:
            env_list = ", ".join(POSTGRES_AVAILABLE_ENVS)
            sections.append(f"""
### Database (PostgreSQL)
Read-only access to PostgreSQL databases.

**Environments:** {env_list}
**Active:** {active_env}

- `db_query` — Run a read-only SQL query.
  Params: `{{"sql": "SELECT * FROM users LIMIT 10"}}`
  Optional: `{{"sql": "...", "max_rows": 500}}`
- `db_schema` — List tables or inspect table columns. Params: `{{}}` or `{{"table": "users"}}`
- `db_explain` — Show query execution plan. Params: `{{"sql": "SELECT ...", "analyze": true}}`
- `db_switch_env` — Switch database environment. Params: `{{"env": "dev"}}`

#### Environment Guidelines
- Default is **prod**. Always state which environment you're querying.
- When the user mentions "staging", "test", "dev", or "development" — switch to **dev** first.
- When the user mentions "production", "prod", or "live" — switch to **prod** first.
- Confirm the switch before running queries on a different environment.

#### Database Best Practices
1. Default limit is 100 rows. Use SQL `LIMIT` or the `max_rows` parameter to control result size.
2. Use `db_schema` first to discover table names and column types before querying.
3. Use `db_explain` to check query performance before running expensive queries.
4. Only SELECT queries are allowed — no INSERT, UPDATE, DELETE, or DDL.

#### Row Limit Override (`max_rows`)
- **Reports and data exports**: when the user explicitly asks for a report,
  data export, full listing, or any task that naturally requires many rows,
  use `max_rows` freely to return the needed data. No confirmation needed.
- **Debug and investigation**: when YOU judge that fetching more than 100 rows
  is needed to investigate a problem or debug an issue, but the user did not
  explicitly ask for many rows, first explain why you need more data and ask
  for confirmation before running the query with elevated `max_rows`.
- When not specified, the default 100-row limit applies.
  Maximum allowed is {POSTGRES_MAX_ROWS_CAP}.
  Always use the smallest `max_rows` that serves the purpose.""")
        else:
            sections.append(f"""
### Database (PostgreSQL)
Read-only access to the PostgreSQL database for debugging, investigation, and data analysis.

- `db_query` — Run a read-only SQL query.
  Params: `{{"sql": "SELECT * FROM users LIMIT 10"}}`
  Optional: `{{"sql": "...", "max_rows": 500}}`
- `db_schema` — List tables or inspect table columns. Params: `{{}}` or `{{"table": "users"}}`
- `db_explain` — Show query execution plan. Params: `{{"sql": "SELECT ...", "analyze": true}}`

#### Database Best Practices
1. Default limit is 100 rows. Use SQL `LIMIT` or the `max_rows` parameter to control result size.
2. Use `db_schema` first to discover table names and column types before querying.
3. Use `db_explain` to check query performance before running expensive queries.
4. Only SELECT queries are allowed — no INSERT, UPDATE, DELETE, or DDL.

#### Row Limit Override (`max_rows`)
- **Reports and data exports**: when the user explicitly asks for a report,
  data export, full listing, or any task that naturally requires many rows,
  use `max_rows` freely to return the needed data. No confirmation needed.
- **Debug and investigation**: when YOU judge that fetching more than 100 rows
  is needed to investigate a problem or debug an issue, but the user did not
  explicitly ask for many rows, first explain why you need more data and ask
  for confirmation before running the query with elevated `max_rows`.
- When not specified, the default 100-row limit applies.
  Maximum allowed is {POSTGRES_MAX_ROWS_CAP}.
  Always use the smallest `max_rows` that serves the purpose.""")

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

    sections.append("""
## Important Rules
1. Use these tools to execute actions directly.
   Do NOT instruct the user to type /cron, /search, /fetch, or any other agent command.
2. For cron commands: validate that the cron expression makes sense for what the user asked.
   Example: "every day at 3am" = "0 3 * * *".
3. Shell commands, git, GitHub CLI, Docker, pip, and npm are already available
   through your native Bash/CLI tools. Do NOT use agent tools for those.
4. Wait for <tool_result> before composing your final response to the user.
</agent_tools>""")

    return "\n".join(sections)
