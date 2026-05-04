"""Contract tests for the canonical MCP catalog.

These guarantees used to live in TS (mcp-catalog-data.test.ts) when the
frontend duplicated the catalog as a literal. The TS literal was removed in
favor of the API; the corresponding shape invariants now belong in Python so
the SSoT itself is verified.
"""

from __future__ import annotations

from koda.control_plane.mcp_catalog import authoritative_mcp_catalog_entries
from koda.integrations.mcp_catalog import MCP_CATALOG, MCP_CATALOG_BY_KEY


def test_runtime_and_authoritative_catalogs_have_matching_keys() -> None:
    runtime_keys = {spec.server_key for spec in MCP_CATALOG}
    authoritative_keys = {entry["server_key"] for entry in authoritative_mcp_catalog_entries()}
    assert runtime_keys == authoritative_keys, (
        f"runtime-only={sorted(runtime_keys - authoritative_keys)} "
        f"authoritative-only={sorted(authoritative_keys - runtime_keys)}"
    )


def test_no_duplicate_server_keys() -> None:
    runtime_keys = [spec.server_key for spec in MCP_CATALOG]
    assert len(runtime_keys) == len(set(runtime_keys)), "duplicate server_key in runtime catalog"

    authoritative_keys = [entry["server_key"] for entry in authoritative_mcp_catalog_entries()]
    assert len(authoritative_keys) == len(set(authoritative_keys)), "duplicate server_key in authoritative catalog"


def test_command_templates_are_pinned() -> None:
    """Floating @latest deps would invalidate every cached connection; pin
    each MCP bootstrap dependency explicitly so behavior is reproducible."""
    for spec in MCP_CATALOG:
        joined = " ".join(spec.command_template)
        assert "@latest" not in joined, f"{spec.server_key} command_template uses floating @latest: {joined}"


def test_npx_commands_use_dash_y_flag() -> None:
    """Catalog entries that bootstrap via npx must pass `-y` so the runtime
    never blocks waiting for an interactive prompt."""
    for spec in MCP_CATALOG:
        if not spec.command_template:
            continue
        if spec.command_template[0] == "npx":
            assert spec.command_template[1] == "-y", (
                f"{spec.server_key} npx command must include -y, got {spec.command_template}"
            )
            assert len(spec.command_template) >= 3, (
                f"{spec.server_key} npx command missing package name: {spec.command_template}"
            )


def test_categories_match_known_set() -> None:
    valid = {"general", "development", "productivity", "data", "cloud"}
    for spec in MCP_CATALOG:
        assert spec.category in valid, f"{spec.server_key} has invalid category: {spec.category}"


def test_every_spec_has_non_empty_metadata() -> None:
    for spec in MCP_CATALOG:
        assert spec.display_name.strip(), f"{spec.server_key} has empty display_name"
        assert spec.tagline.strip(), f"{spec.server_key} has empty tagline"
        assert spec.description.strip(), f"{spec.server_key} has empty description"
        assert spec.documentation_url.startswith("http"), f"{spec.server_key} documentation_url must be a URL"


def test_every_tool_has_a_classification() -> None:
    valid = {"read", "write", "destructive"}
    for spec in MCP_CATALOG:
        for tool in spec.tools:
            assert tool.classification in valid, (
                f"{spec.server_key}.{tool.name} has invalid classification: {tool.classification}"
            )


def test_no_duplicate_tool_names_per_server() -> None:
    for spec in MCP_CATALOG:
        names = [tool.name for tool in spec.tools]
        assert len(names) == len(set(names)), f"{spec.server_key} declares duplicate tool names: {names}"


def test_lookup_index_covers_all_specs() -> None:
    for spec in MCP_CATALOG:
        assert MCP_CATALOG_BY_KEY.get(spec.server_key) is spec, f"{spec.server_key} missing from MCP_CATALOG_BY_KEY"


def test_remote_servers_declare_remote_url() -> None:
    for spec in MCP_CATALOG:
        if spec.transport_type == "http_sse":
            assert spec.remote_url, f"{spec.server_key} http_sse spec missing remote_url"


def test_runtime_and_authoritative_transport_match() -> None:
    authoritative_by_key = {entry["server_key"]: entry for entry in authoritative_mcp_catalog_entries()}
    for spec in MCP_CATALOG:
        entry = authoritative_by_key[spec.server_key]
        assert entry["transport_type"] == spec.transport_type, (
            f"{spec.server_key} transport mismatch: runtime={spec.transport_type} "
            f"authoritative={entry['transport_type']}"
        )
        expected_remote_url = spec.remote_url or None
        actual_remote_url = entry.get("remote_url") or entry.get("url") or None
        assert actual_remote_url == expected_remote_url, (
            f"{spec.server_key} remote_url mismatch: runtime={expected_remote_url} authoritative={actual_remote_url}"
        )


def test_auth_capabilities_declare_flow_kind() -> None:
    valid_flow_kinds = {
        "api_key",
        "local_session",
        "manual_header",
        "mcp_remote_oauth_confidential",
        "mcp_remote_oauth_dcr",
        "none",
        "provider_native_oauth",
    }
    for entry in authoritative_mcp_catalog_entries():
        capabilities = entry.get("metadata", {}).get("auth_capabilities", {})
        flow_kind = capabilities.get("auth_flow_kind")
        assert flow_kind in valid_flow_kinds, f"{entry['server_key']} has invalid auth_flow_kind={flow_kind!r}"
        if entry.get("oauth_enabled"):
            assert flow_kind, f"{entry['server_key']} oauth_enabled without auth_flow_kind"


def test_executable_oauth_is_remote_and_has_url() -> None:
    for entry in authoritative_mcp_catalog_entries():
        capabilities = entry.get("metadata", {}).get("auth_capabilities", {})
        flow_kind = str(capabilities.get("auth_flow_kind") or "")
        if flow_kind in {"mcp_remote_oauth_dcr", "mcp_remote_oauth_confidential"}:
            assert entry["transport_kind"] == "remote", f"{entry['server_key']} executable OAuth must be remote"
            assert entry.get("remote_url") or entry.get("url"), f"{entry['server_key']} OAuth remote missing URL"
            assert entry.get("oauth_enabled") is True, f"{entry['server_key']} executable OAuth not enabled"


def test_stdio_entries_do_not_use_generic_oauth_dcr() -> None:
    for entry in authoritative_mcp_catalog_entries():
        if entry["transport_kind"] == "local":
            assert entry.get("oauth_mode") != "dcr", (
                f"{entry['server_key']} is stdio/local and must not use generic MCP OAuth DCR"
            )
