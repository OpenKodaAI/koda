"""Tests for MCP catalog, agent connections, and tool policy CRUD."""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

import koda.control_plane.manager as manager_mod

# ---------------------------------------------------------------------------
# Lightweight in-memory DB stub
# ---------------------------------------------------------------------------


class _MemDB:
    """Minimal row store that supports the fetch_one / fetch_all / execute API."""

    def __init__(self) -> None:
        self.tables: dict[str, list[dict[str, Any]]] = {
            "cp_mcp_server_catalog": [],
            "cp_mcp_agent_connections": [],
            "cp_mcp_discovered_tools": [],
            "cp_mcp_tool_policies": [],
            "cp_mcp_oauth_tokens": [],
            "cp_connection_discovery_runs": [],
            "cp_connection_discovery_run_tools": [],
            "cp_agent_definitions": [{"id": "agent-1"}],
        }

    def _match(self, table: str, **filters: Any) -> list[dict[str, Any]]:
        rows = self.tables.get(table, [])
        result = []
        for row in rows:
            if all(row.get(k) == v for k, v in filters.items()):
                result.append(row)
        return result

    def execute(self, query: str, params: tuple[Any, ...] = ()) -> int:
        q = query.strip().upper()
        if q.startswith("INSERT"):
            return self._handle_insert(query, params)
        if q.startswith("DELETE"):
            return self._handle_delete(query, params)
        if q.startswith("UPDATE"):
            return self._handle_update(query, params)
        return 0

    def fetch_one(self, query: str, params: tuple[Any, ...] = ()) -> Any | None:
        rows = self.fetch_all(query, params)
        return rows[0] if rows else None

    def fetch_all(self, query: str, params: tuple[Any, ...] = ()) -> list[Any]:
        table = self._extract_table(query)
        if table is None:
            return []
        rows = self.tables.get(table, [])
        where_cols = self._extract_where_columns(query)
        if where_cols:
            filtered = []
            for row in rows:
                match = True
                for i, col in enumerate(where_cols):
                    if i < len(params) and row.get(col) != params[i]:
                        match = False
                        break
                if match:
                    filtered.append(row)
            rows = filtered
        if "ORDER BY DISCOVERED_AT DESC" in query.upper():
            rows = sorted(rows, key=lambda row: str(row.get("discovered_at") or ""), reverse=True)
        elif "ORDER BY TOOL_NAME" in query.upper():
            rows = sorted(rows, key=lambda row: str(row.get("tool_name") or ""))
        return [_DictRow(r) for r in rows]

    def _handle_insert(self, query: str, params: tuple[Any, ...]) -> int:
        table = self._extract_table(query)
        if table is None:
            return 0
        columns = self._extract_insert_columns(query)
        row = dict(zip(columns, params, strict=False))
        # Determine PK columns
        pk_cols = self._pk_for(table)
        existing_idx = None
        if "ON CONFLICT" in query.upper():
            for i, existing in enumerate(self.tables.get(table, [])):
                if all(existing.get(c) == row.get(c) for c in pk_cols):
                    existing_idx = i
                    break
        if existing_idx is not None:
            # Update non-PK columns
            for col in columns:
                if col not in pk_cols:
                    self.tables[table][existing_idx][col] = row[col]
            return 1
        self.tables.setdefault(table, []).append(row)
        return 1

    def _handle_update(self, query: str, params: tuple[Any, ...]) -> int:
        import re

        table = self._extract_table(query)
        if table is None:
            return 0
        # Extract SET columns and WHERE columns separately
        set_match = re.search(r"SET\s+(.+?)\s+WHERE", query, re.I | re.S)
        if not set_match:
            return 0
        set_clause = set_match.group(1)
        set_cols = re.findall(r"(\w+)\s*=\s*\?", set_clause)

        where_part = query[set_match.end() :]
        where_cols = re.findall(r"(\w+)\s*=\s*\?", where_part)

        # Split params into set_values and where_values
        set_values = params[: len(set_cols)]
        where_values = params[len(set_cols) :]

        rows = self.tables.get(table, [])
        updated = 0
        for row in rows:
            match = True
            for j, col in enumerate(where_cols):
                if j < len(where_values) and row.get(col) != where_values[j]:
                    match = False
                    break
            if match:
                for j, col in enumerate(set_cols):
                    if j < len(set_values):
                        row[col] = set_values[j]
                updated += 1
        return updated

    def _handle_delete(self, query: str, params: tuple[Any, ...]) -> int:
        table = self._extract_table(query)
        if table is None:
            return 0
        where_cols = self._extract_where_columns(query)
        rows = self.tables.get(table, [])
        to_remove = []
        for i, row in enumerate(rows):
            match = True
            for j, col in enumerate(where_cols):
                if j < len(params) and row.get(col) != params[j]:
                    match = False
                    break
            if match:
                to_remove.append(i)
        for idx in reversed(to_remove):
            rows.pop(idx)
        return len(to_remove)

    def _pk_for(self, table: str) -> list[str]:
        pks: dict[str, list[str]] = {
            "cp_mcp_server_catalog": ["server_key"],
            "cp_mcp_agent_connections": ["agent_id", "server_key"],
            "cp_mcp_discovered_tools": ["agent_id", "server_key", "tool_name"],
            "cp_mcp_tool_policies": ["agent_id", "server_key", "tool_name"],
            "cp_mcp_oauth_tokens": ["agent_id", "server_key"],
            "cp_connection_discovery_runs": ["run_id"],
            "cp_connection_discovery_run_tools": ["run_id", "tool_name"],
        }
        return pks.get(table, ["id"])

    @staticmethod
    def _extract_table(query: str) -> str | None:
        import re

        m = re.search(r"(?:FROM|INTO|UPDATE|DELETE\s+FROM)\s+(\w+)", query, re.I)
        return m.group(1) if m else None

    @staticmethod
    def _extract_insert_columns(query: str) -> list[str]:
        import re

        m = re.search(r"\(([^)]+)\)\s*(?:VALUES|SELECT)", query, re.I)
        if not m:
            return []
        return [c.strip() for c in m.group(1).split(",")]

    @staticmethod
    def _extract_where_columns(query: str) -> list[str]:
        import re

        cols = re.findall(r"(\w+)\s*=\s*\?", query)
        return cols


class _DictRow(dict):
    def __getitem__(self, key: str) -> Any:
        return super().__getitem__(key)

    def keys(self):
        return super().keys()


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _run_coro_sync_stub(coro: Any) -> Any:
    """Synchronous stub that drives a coroutine to completion."""
    import asyncio

    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)
    # Fallback: create a new loop
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


@pytest.fixture()
def mcp_manager(monkeypatch: pytest.MonkeyPatch):
    db = _MemDB()
    monkeypatch.setattr(manager_mod, "fetch_one", db.fetch_one)
    monkeypatch.setattr(manager_mod, "fetch_all", db.fetch_all)
    monkeypatch.setattr(manager_mod, "execute", db.execute)
    monkeypatch.setattr(manager_mod, "encrypt_secret", lambda v: f"ENC:{v}")
    monkeypatch.setattr(manager_mod, "decrypt_secret", lambda v: v.removeprefix("ENC:"))
    monkeypatch.setattr(manager_mod, "mask_secret", lambda v: v[:2] + "***")
    monkeypatch.setattr(manager_mod, "run_coro_sync", _run_coro_sync_stub)

    mgr = object.__new__(manager_mod.ControlPlaneManager)
    return mgr, db


# ---------------------------------------------------------------------------
# MCP Catalog tests
# ---------------------------------------------------------------------------


class TestMCPCatalog:
    def test_list_catalog_empty(self, mcp_manager):
        mgr, _db = mcp_manager
        assert mgr.list_mcp_catalog() == []

    def test_upsert_rejects_reserved_native_server_keys(self, mcp_manager):
        mgr, _db = mcp_manager
        with pytest.raises(ValueError, match="reserved"):
            mgr.upsert_mcp_catalog_entry("github", {"display_name": "GitHub"})

    def test_upsert_and_get_catalog_entry(self, mcp_manager):
        mgr, _db = mcp_manager
        result = mgr.upsert_mcp_catalog_entry(
            "linear",
            {
                "display_name": "Linear",
                "description": "Linear MCP server",
                "transport_type": "stdio",
                "command": ["npx", "-y", "@modelcontextprotocol/server-linear"],
                "category": "developer",
            },
        )
        assert result["server_key"] == "linear"
        assert result["display_name"] == "Linear"
        assert result["transport_type"] == "stdio"
        assert result["command"] == ["npx", "-y", "@modelcontextprotocol/server-linear"]
        assert result["category"] == "developer"
        assert result["enabled"] is True

        fetched = mgr.get_mcp_catalog_entry("linear")
        assert fetched["server_key"] == "linear"

    def test_upsert_updates_existing(self, mcp_manager):
        mgr, _db = mcp_manager
        mgr.upsert_mcp_catalog_entry("linear", {"display_name": "Linear"})
        mgr.upsert_mcp_catalog_entry("linear", {"display_name": "Linear v2", "category": "vcs"})

        result = mgr.get_mcp_catalog_entry("linear")
        assert result["display_name"] == "Linear v2"
        assert result["category"] == "vcs"

    def test_list_catalog_returns_entries(self, mcp_manager):
        mgr, _db = mcp_manager
        mgr.upsert_mcp_catalog_entry("linear", {"display_name": "Linear"})
        mgr.upsert_mcp_catalog_entry("slack", {"display_name": "Slack"})
        entries = mgr.list_mcp_catalog()
        assert len(entries) == 2

    def test_delete_catalog_entry(self, mcp_manager):
        mgr, _db = mcp_manager
        mgr.upsert_mcp_catalog_entry("linear", {"display_name": "Linear"})
        result = mgr.delete_mcp_catalog_entry("linear")
        assert result["deleted"] is True
        assert mgr.list_mcp_catalog() == []

    def test_delete_nonexistent_returns_false(self, mcp_manager):
        mgr, _db = mcp_manager
        result = mgr.delete_mcp_catalog_entry("nonexistent")
        assert result["deleted"] is False

    def test_get_nonexistent_raises(self, mcp_manager):
        mgr, _db = mcp_manager
        with pytest.raises(KeyError):
            mgr.get_mcp_catalog_entry("missing")

    def test_catalog_entry_defaults(self, mcp_manager):
        mgr, _db = mcp_manager
        result = mgr.upsert_mcp_catalog_entry("minimal", {})
        assert result["display_name"] == "minimal"
        assert result["transport_type"] == "stdio"
        assert result["category"] == "general"
        assert result["enabled"] is True
        assert result["command"] == []
        assert result["url"] is None

    def test_delete_cascades_connections_and_policies(self, mcp_manager):
        mgr, db = mcp_manager
        mgr.upsert_mcp_catalog_entry("linear", {"display_name": "Linear"})
        mgr.upsert_mcp_agent_connection("agent-1", "linear", {"enabled": True})
        mgr.upsert_mcp_tool_policy("agent-1", "linear", "create_issue", "auto")
        assert len(db.tables["cp_mcp_agent_connections"]) == 1
        assert len(db.tables["cp_mcp_tool_policies"]) == 1

        mgr.delete_mcp_catalog_entry("linear")
        assert len(db.tables["cp_mcp_agent_connections"]) == 0
        assert len(db.tables["cp_mcp_tool_policies"]) == 0


# ---------------------------------------------------------------------------
# MCP Agent Connection tests
# ---------------------------------------------------------------------------


class TestMCPAgentConnections:
    def _seed_catalog(self, mgr):
        mgr.upsert_mcp_catalog_entry("linear", {"display_name": "Linear"})

    def test_list_connections_empty(self, mcp_manager):
        mgr, _db = mcp_manager
        assert mgr.list_mcp_agent_connections("agent-1") == []

    def test_upsert_and_get_connection(self, mcp_manager):
        mgr, _db = mcp_manager
        self._seed_catalog(mgr)
        result = mgr.upsert_mcp_agent_connection(
            "agent-1",
            "linear",
            {
                "enabled": True,
                "env_values": {"GITHUB_TOKEN": "ghp_abc123"},
            },
        )
        assert result["agent_id"] == "AGENT_1"
        assert result["server_key"] == "linear"
        assert result["enabled"] is True
        assert "***" in result["env_values"]["GITHUB_TOKEN"]

    def test_connection_requires_catalog_entry(self, mcp_manager):
        mgr, _db = mcp_manager
        with pytest.raises(KeyError, match="unknown MCP server"):
            mgr.upsert_mcp_agent_connection("agent-1", "nonexistent", {})

    def test_list_connections(self, mcp_manager):
        mgr, _db = mcp_manager
        self._seed_catalog(mgr)
        mgr.upsert_mcp_agent_connection("agent-1", "linear", {})
        connections = mgr.list_mcp_agent_connections("agent-1")
        assert len(connections) == 1

    def test_delete_connection(self, mcp_manager):
        mgr, _db = mcp_manager
        self._seed_catalog(mgr)
        mgr.upsert_mcp_agent_connection("agent-1", "linear", {})
        result = mgr.delete_mcp_agent_connection("agent-1", "linear")
        assert result["deleted"] is True
        assert mgr.list_mcp_agent_connections("agent-1") == []

    def test_delete_connection_cascades_policies(self, mcp_manager):
        mgr, db = mcp_manager
        self._seed_catalog(mgr)
        mgr.upsert_mcp_agent_connection("agent-1", "linear", {})
        mgr.upsert_mcp_tool_policy("agent-1", "linear", "create_issue", "auto")
        assert len(db.tables["cp_mcp_tool_policies"]) == 1

        mgr.delete_mcp_agent_connection("agent-1", "linear")
        assert len(db.tables["cp_mcp_tool_policies"]) == 0

    def test_get_nonexistent_connection_raises(self, mcp_manager):
        mgr, _db = mcp_manager
        with pytest.raises(KeyError):
            mgr.get_mcp_agent_connection("agent-1", "nonexistent")

    def test_env_values_encrypted(self, mcp_manager):
        mgr, db = mcp_manager
        self._seed_catalog(mgr)
        mgr.upsert_mcp_agent_connection(
            "agent-1",
            "linear",
            {
                "env_values": {"TOKEN": "secret123"},
            },
        )
        raw_row = db.tables["cp_mcp_agent_connections"][0]
        env_json = json.loads(raw_row["env_values_json"])
        assert env_json["TOKEN"] == "ENC:secret123"

    def test_upsert_updates_existing_connection(self, mcp_manager):
        mgr, _db = mcp_manager
        self._seed_catalog(mgr)
        mgr.upsert_mcp_agent_connection("agent-1", "linear", {"enabled": True})
        mgr.upsert_mcp_agent_connection("agent-1", "linear", {"enabled": False})
        conn = mgr.get_mcp_agent_connection("agent-1", "linear")
        assert conn["enabled"] is False
        assert conn["connection_key"] == "mcp:linear"


class TestCanonicalConnections:
    def test_list_connection_catalog_includes_core_and_mcp(self, mcp_manager):
        mgr, _db = mcp_manager
        mgr.upsert_mcp_catalog_entry(
            "linear",
            {
                "display_name": "Linear",
                "oauth_mode": "dcr",
                "auth_strategy": "oauth_dcr",
            },
        )

        payload = mgr.list_connection_catalog()

        assert any(item["connection_key"] == "core:gws" for item in payload["items"])
        assert any(item["connection_key"] == "mcp:linear" for item in payload["items"])

    def test_generic_mcp_connection_round_trip(self, mcp_manager):
        mgr, _db = mcp_manager
        mgr.upsert_mcp_catalog_entry("linear", {"display_name": "Linear"})
        mgr.put_agent_connection("agent-1", "mcp:linear", {"enabled": True})

        payload = mgr.get_agent_connection("agent-1", "mcp:linear")

        assert payload["kind"] == "mcp"
        assert payload["connection_key"] == "mcp:linear"

    def test_generic_core_connection_uses_canonical_key(self, mcp_manager):
        mgr, _db = mcp_manager
        mgr._merged_global_env = lambda: {}
        mgr.get_system_settings = lambda: {"integrations": {}}

        payload = mgr.get_agent_connection("agent-1", "core:browser")

        assert payload["kind"] == "core"
        assert payload["connection_key"] == "core:browser"


# ---------------------------------------------------------------------------
# MCP Tool Policy tests
# ---------------------------------------------------------------------------


class TestMCPToolPolicies:
    def _seed(self, mgr):
        mgr.upsert_mcp_catalog_entry("linear", {"display_name": "Linear"})
        mgr.upsert_mcp_agent_connection("agent-1", "linear", {})

    def test_list_policies_empty(self, mcp_manager):
        mgr, _db = mcp_manager
        assert mgr.list_mcp_tool_policies("agent-1", "linear") == []

    def test_upsert_and_list_policy(self, mcp_manager):
        mgr, _db = mcp_manager
        self._seed(mgr)
        result = mgr.upsert_mcp_tool_policy("agent-1", "linear", "create_issue", "always_allow")
        assert result["policy"] == "always_allow"
        assert result["tool_name"] == "create_issue"

        policies = mgr.list_mcp_tool_policies("agent-1", "linear")
        assert len(policies) == 1
        assert policies[0]["policy"] == "always_allow"

    def test_upsert_updates_existing_policy(self, mcp_manager):
        mgr, _db = mcp_manager
        self._seed(mgr)
        mgr.upsert_mcp_tool_policy("agent-1", "linear", "create_issue", "auto")
        mgr.upsert_mcp_tool_policy("agent-1", "linear", "create_issue", "blocked")

        policies = mgr.list_mcp_tool_policies("agent-1", "linear")
        assert len(policies) == 1
        assert policies[0]["policy"] == "blocked"

    def test_invalid_policy_raises(self, mcp_manager):
        mgr, _db = mcp_manager
        with pytest.raises(ValueError, match="invalid MCP tool policy"):
            mgr.upsert_mcp_tool_policy("agent-1", "linear", "create_issue", "yolo")

    def test_delete_policy(self, mcp_manager):
        mgr, _db = mcp_manager
        self._seed(mgr)
        mgr.upsert_mcp_tool_policy("agent-1", "linear", "create_issue", "auto")
        result = mgr.delete_mcp_tool_policy("agent-1", "linear", "create_issue")
        assert result["deleted"] is True
        assert mgr.list_mcp_tool_policies("agent-1", "linear") == []

    def test_delete_nonexistent_policy(self, mcp_manager):
        mgr, _db = mcp_manager
        result = mgr.delete_mcp_tool_policy("agent-1", "linear", "nonexistent")
        assert result["deleted"] is False

    def test_all_valid_policies(self, mcp_manager):
        mgr, _db = mcp_manager
        self._seed(mgr)
        for policy in ("auto", "always_allow", "always_ask", "blocked"):
            result = mgr.upsert_mcp_tool_policy("agent-1", "linear", f"tool_{policy}", policy)
            assert result["policy"] == policy


# ---------------------------------------------------------------------------
# test_mcp_connection / discover_mcp_tools tests
# ---------------------------------------------------------------------------


class TestMCPTestConnection:
    def _seed(self, mgr):
        mgr.upsert_mcp_catalog_entry(
            "linear",
            {
                "display_name": "Linear",
                "transport_type": "stdio",
                "command": ["npx", "server-linear"],
            },
        )
        mgr.upsert_mcp_agent_connection("agent-1", "linear", {"enabled": True})

    def test_test_connection_success(self, mcp_manager, monkeypatch):
        mgr, _db = mcp_manager
        self._seed(mgr)

        from koda.services.mcp_client import McpToolDefinition
        from koda.services.mcp_manager import McpServerInstance

        mock_instance = MagicMock(spec=McpServerInstance)
        mock_instance.cached_tools = [
            McpToolDefinition(name="create_issue"),
            McpToolDefinition(name="list_repos"),
        ]
        mock_instance.start = AsyncMock()
        mock_instance.stop = AsyncMock()
        mock_instance.health_check = AsyncMock(return_value=True)

        monkeypatch.setattr(
            "koda.services.mcp_manager.McpServerInstance",
            lambda **kw: mock_instance,
        )

        result = mgr.test_mcp_connection("agent-1", "linear")

        assert result["success"] is True
        assert result["healthy"] is True
        assert result["tool_count"] == 2
        assert result["server_key"] == "linear"

    def test_test_connection_failure(self, mcp_manager, monkeypatch):
        mgr, _db = mcp_manager
        self._seed(mgr)

        from koda.services.mcp_manager import McpServerInstance

        mock_instance = MagicMock(spec=McpServerInstance)
        mock_instance.start = AsyncMock(side_effect=ConnectionError("refused"))
        mock_instance.stop = AsyncMock()

        monkeypatch.setattr(
            "koda.services.mcp_manager.McpServerInstance",
            lambda **kw: mock_instance,
        )

        result = mgr.test_mcp_connection("agent-1", "linear")

        assert result["success"] is False
        assert result["healthy"] is False
        assert "refused" in result["error"]

    def test_test_connection_missing_catalog(self, mcp_manager):
        mgr, _db = mcp_manager
        with pytest.raises(KeyError):
            mgr.test_mcp_connection("agent-1", "nonexistent")


class TestMCPDiscoverTools:
    def _seed(self, mgr):
        mgr.upsert_mcp_catalog_entry(
            "linear",
            {
                "display_name": "Linear",
                "transport_type": "stdio",
                "command": ["npx", "server-linear"],
            },
        )
        mgr.upsert_mcp_agent_connection("agent-1", "linear", {"enabled": True})

    def test_discover_tools_success(self, mcp_manager, monkeypatch):
        mgr, db = mcp_manager
        self._seed(mgr)

        from koda.services.mcp_client import McpToolAnnotations, McpToolDefinition
        from koda.services.mcp_manager import McpServerInstance

        mock_instance = MagicMock(spec=McpServerInstance)
        mock_instance.cached_tools = [
            McpToolDefinition(
                name="create_issue",
                description="Create an issue",
                input_schema={"type": "object"},
                annotations=McpToolAnnotations(
                    title="Create Issue",
                    read_only_hint=False,
                    destructive_hint=True,
                    idempotent_hint=False,
                ),
            ),
        ]
        mock_instance.start = AsyncMock()
        mock_instance.stop = AsyncMock()

        monkeypatch.setattr(
            "koda.services.mcp_manager.McpServerInstance",
            lambda **kw: mock_instance,
        )

        result = mgr.discover_mcp_tools("agent-1", "linear")

        assert result["success"] is True
        assert result["tool_count"] == 1
        assert result["tools"][0]["name"] == "create_issue"
        assert result["tools"][0]["annotations"]["destructive_hint"] is True
        assert result["cached_at"] is not None

        # Verify cached_tools_json was persisted
        conn_row = db.tables["cp_mcp_agent_connections"][0]
        cached = json.loads(conn_row["cached_tools_json"])
        assert len(cached) == 1
        assert cached[0]["name"] == "create_issue"

    def test_discover_tools_failure(self, mcp_manager, monkeypatch):
        mgr, _db = mcp_manager
        self._seed(mgr)

        from koda.services.mcp_manager import McpServerInstance

        mock_instance = MagicMock(spec=McpServerInstance)
        mock_instance.start = AsyncMock(side_effect=RuntimeError("cannot connect"))
        mock_instance.stop = AsyncMock()

        monkeypatch.setattr(
            "koda.services.mcp_manager.McpServerInstance",
            lambda **kw: mock_instance,
        )

        result = mgr.discover_mcp_tools("agent-1", "linear")

        assert result["success"] is False
        assert "cannot connect" in result["error"]
        assert result["tool_count"] == 0

    def test_discover_tools_persists_diff_and_resets_changed_policy(self, mcp_manager, monkeypatch):
        mgr, db = mcp_manager
        self._seed(mgr)

        from koda.services.mcp_client import McpToolAnnotations, McpToolDefinition
        from koda.services.mcp_manager import McpServerInstance

        first_instance = MagicMock(spec=McpServerInstance)
        first_instance.cached_tools = [
            McpToolDefinition(
                name="create_issue",
                description="Create issue",
                input_schema={"type": "object", "properties": {"title": {"type": "string"}}},
                annotations=McpToolAnnotations(read_only_hint=False),
            ),
        ]
        first_instance.start = AsyncMock()
        first_instance.stop = AsyncMock()

        second_instance = MagicMock(spec=McpServerInstance)
        second_instance.cached_tools = [
            McpToolDefinition(
                name="create_issue",
                description="Create issue",
                input_schema={
                    "type": "object",
                    "properties": {
                        "title": {"type": "string"},
                        "priority": {"type": "string"},
                    },
                },
                annotations=McpToolAnnotations(read_only_hint=False),
            ),
            McpToolDefinition(
                name="list_issues",
                description="List issues",
                input_schema={"type": "object"},
                annotations=McpToolAnnotations(read_only_hint=True),
            ),
        ]
        second_instance.start = AsyncMock()
        second_instance.stop = AsyncMock()

        instances = [first_instance, second_instance]
        monkeypatch.setattr(
            "koda.services.mcp_manager.McpServerInstance",
            lambda **kw: instances.pop(0),
        )

        mgr.discover_mcp_tools("agent-1", "linear")
        mgr.upsert_mcp_tool_policy("agent-1", "linear", "create_issue", "always_allow")
        result = mgr.discover_mcp_tools("agent-1", "linear")

        assert result["success"] is True
        assert result["diff"] == {
            "added": ["list_issues"],
            "removed": [],
            "changed": ["create_issue"],
        }

        tool_payload = mgr.get_mcp_connection_tools("agent-1", "linear")
        assert tool_payload["summary"]["total"] == 2
        assert tool_payload["diff"]["changed"] == ["create_issue"]
        assert tool_payload["policies"]["create_issue"] == "always_ask"
        assert len(db.tables["cp_connection_discovery_runs"]) == 2
