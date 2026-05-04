# Koda Guardrail Test Matrix

This matrix maps the security boundaries agents rely on to adversarial tests.
Every test in `tests/security/` should prove the expected decision, the
presence or absence of execution, canary integrity, and secret redaction when
the scenario involves credentials or process output.

| Surface | Guardrail | Evidence Target |
| --- | --- | --- |
| Shell | Destructive commands, env exfiltration, reverse shells, and forbidden tokens are blocked before execution. | `tests/security/test_guardrail_adversarial_suite.py::test_shell_destructive_commands_do_not_touch_canary` |
| Background shell | Process handles are scoped to the owning user. | `tests/security/test_guardrail_adversarial_suite.py::test_background_shell_handle_is_user_scoped` |
| File operations | Paths must remain inside the workdir and sensitive extensions stay blocked. | `tests/security/test_guardrail_adversarial_suite.py::test_fileops_rejects_symlink_escape_and_sensitive_extensions` |
| Browser | Private-network downloads honor the global kill switch, redirects are blocked before the browser follows them, and uploads cannot read files outside the workdir. | `tests/security/test_guardrail_adversarial_suite.py::test_browser_private_download_respects_global_kill_switch`, `tests/security/test_guardrail_adversarial_suite.py::test_browser_download_blocks_private_redirect_before_network`, `tests/security/test_guardrail_adversarial_suite.py::test_browser_upload_rejects_path_outside_workdir` |
| HTTP/SSRF | Fetch/inspect/download re-check every redirect before following it. | Existing `tests/test_services/test_http_client.py` coverage plus MCP HTTP redirect tests below. |
| MCP HTTP | Remote MCP transports reject private/internal hosts during construction and on redirects. | `tests/security/test_guardrail_adversarial_suite.py::test_mcp_http_redirect_to_private_destination_is_blocked` |
| MCP stdio/custom | Custom command/env registration rejects obvious host-code-execution escapes and malformed argv values. | `tests/test_services/test_custom_mcp_registry.py` |
| MCP control plane | Agent connection overrides cannot smuggle unsafe commands, malformed argv, unsafe URLs, forbidden env names, non-string env values, or null-as-secret values into runtime config. | `tests/security/test_guardrail_adversarial_suite.py::test_mcp_agent_connection_rejects_unsafe_overrides`, `tests/test_control_plane_mcp.py::TestMCPAgentConnections::test_null_env_values_are_ignored_not_stored_as_literal_secret`, `tests/test_control_plane_mcp.py::TestMCPAgentConnections::test_env_values_reject_non_string_values` |
| MCP capabilities | Blocked resources are hidden whether policy stores the URI or the canonical URI hash. | `tests/security/test_guardrail_adversarial_suite.py::test_mcp_resource_blocking_accepts_uri_or_hash_policy_names` |
| Execution policy | Unknown tools fail closed, read-only tasks deny writes, approval grants replay only the authorized action. | `tests/security/test_guardrail_adversarial_suite.py::test_execution_policy_unknown_tool_fails_closed_with_evidence`, existing `tests/test_services/test_execution_policy.py` |
| Provider/runtime env | Tool subprocess env is allowlisted and fails safe if the security RPC is unavailable. | `tests/security/test_guardrail_adversarial_suite.py::test_tool_subprocess_env_drops_secret_canary` |
| Policy engine | Ingest/spend wrappers have explicit tests for deny, hard stop, and the configured outage fallback behavior. | Existing `tests/test_policy_engine_client.py` |

When a new agent-facing tool or MCP capability is added, update this document
in the same change as the policy/test coverage.
