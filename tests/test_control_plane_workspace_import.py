from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

import koda.control_plane.manager as manager_mod
from koda.control_plane.workspace_import import scan_workspace_directory
from koda.services.tool_dispatcher import ToolContext, _handle_set_workdir


def _write_sample_workspace(root: Path) -> None:
    (root / "AGENTS.md").write_text("Use tests. token = 'sk-test-secret-value'", encoding="utf-8")
    (root / "CLAUDE.md").write_text("# Claude memory\nPrefer safe imports.", encoding="utf-8")
    (root / ".cursor" / "rules").mkdir(parents=True)
    (root / ".cursor" / "rules" / "python.mdc").write_text(
        "---\ndescription: Python rules\nglobs: ['*.py']\n---\nKeep typing strict.",
        encoding="utf-8",
    )
    (root / ".claude" / "agents").mkdir(parents=True)
    (root / ".claude" / "agents" / "reviewer.md").write_text(
        "---\nname: Reviewer\ndescription: Reviews code\n---\nReview carefully.",
        encoding="utf-8",
    )
    (root / ".claude").mkdir(exist_ok=True)
    (root / ".claude" / "settings.json").write_text(
        json.dumps({"hooks": {"PostToolUse": [{"command": "echo $SECRET_TOKEN"}]}}),
        encoding="utf-8",
    )
    (root / ".mcp.json").write_text(
        json.dumps({"mcpServers": {"linear": {"command": "npx", "args": ["linear"], "env": {"LINEAR_API_KEY": "x"}}}}),
        encoding="utf-8",
    )
    (root / ".env").write_text("SHOULD_NOT_BE_SCANNED=1", encoding="utf-8")


def test_workspace_scanner_detects_sources_redacts_and_blocks_hooks(tmp_path: Path) -> None:
    _write_sample_workspace(tmp_path)
    outside = tmp_path.parent / "outside-secret.txt"
    outside.write_text("secret", encoding="utf-8")
    (tmp_path / "linked-secret.txt").symlink_to(outside)

    scan = scan_workspace_directory(str(tmp_path)).to_dict()

    rels = {source["relative_path"] for source in scan["sources"]}
    assert "AGENTS.md" in rels
    assert "CLAUDE.md" in rels
    assert ".cursor/rules/python.mdc" in rels
    assert ".claude/agents/reviewer.md" in rels
    assert ".mcp.json" in rels
    assert ".env" not in rels
    assert "linked-secret.txt" not in rels
    assert any(source["kind"] == "hook" and source["risk"] == "blocked" for source in scan["sources"])
    agents = next(source for source in scan["sources"] if source["relative_path"] == "AGENTS.md")
    assert "[REDACTED]" in agents["content_excerpt"]
    assert scan["scan_hash"]
    mcp_source = next(source for source in scan["sources"] if source["relative_path"] == ".mcp.json")
    assert mcp_source["metadata"]["servers"][0]["env_keys"] == ["LINEAR_API_KEY"]
    assert "LINEAR_API_KEY" in mcp_source["content_excerpt"]
    assert '"x"' not in mcp_source["content_excerpt"]
    assert '"x"' not in json.dumps(mcp_source["metadata"])


def test_workspace_scanner_handles_invalid_files_ignored_dirs_and_stable_hash(tmp_path: Path) -> None:
    (tmp_path / ".codex" / "agents").mkdir(parents=True)
    (tmp_path / ".codex" / "agents" / "bad.toml").write_text("name = [", encoding="utf-8")
    (tmp_path / ".cursor" / "rules").mkdir(parents=True)
    (tmp_path / ".cursor" / "rules" / "bad.mdc").write_text(
        "---\n: nope\n---\nBody",
        encoding="utf-8",
    )
    (tmp_path / ".mcp.json").write_text("{not-json", encoding="utf-8")
    (tmp_path / "node_modules").mkdir()
    (tmp_path / "node_modules" / "AGENTS.md").write_text("ignored", encoding="utf-8")

    first = scan_workspace_directory(str(tmp_path)).to_dict()
    second = scan_workspace_directory(str(tmp_path)).to_dict()
    truncated = scan_workspace_directory(str(tmp_path), max_entries=1).to_dict()

    rels = {source["relative_path"] for source in first["sources"]}
    assert ".codex/agents/bad.toml" in rels
    assert ".cursor/rules/bad.mdc" in rels
    assert ".mcp.json" in rels
    assert "node_modules/AGENTS.md" not in rels
    assert first["scan_hash"] == second["scan_hash"]
    assert truncated["summary"]["truncated"] is True


class _WorkspaceMemDB:
    def __init__(self) -> None:
        self.workspaces: list[dict[str, Any]] = []
        self.squads: list[dict[str, Any]] = []
        self.agents: list[dict[str, Any]] = []
        self.documents: list[dict[str, Any]] = []
        self.mcp: list[dict[str, Any]] = []

    def fetch_all(self, query: str, params: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
        if "FROM cp_workspaces" in query:
            return sorted(self.workspaces, key=lambda item: item["id"])
        if "FROM cp_workspace_squads" in query:
            return []
        if "FROM cp_agent_definitions" in query and "GROUP BY" in query:
            return []
        return []

    def fetch_one(self, query: str, params: tuple[Any, ...] = ()) -> dict[str, Any] | None:
        if "FROM cp_workspaces" in query and "WHERE id" in query:
            return next((item for item in self.workspaces if item["id"] == params[0]), None)
        if "SELECT id FROM cp_workspaces" in query:
            row = next((item for item in self.workspaces if item["id"] == params[0]), None)
            return {"id": row["id"]} if row else None
        if "JOIN cp_workspaces" in query:
            agent = next((item for item in self.agents if item["id"] == params[0]), None)
            if not agent:
                return None
            workspace = next((item for item in self.workspaces if item["id"] == agent.get("workspace_id")), None)
            return {"root_path": workspace.get("root_path")} if workspace else None
        if "FROM cp_agent_definitions" in query and "WHERE id" in query:
            return next((item for item in self.agents if item["id"] == params[0]), None)
        if "FROM cp_agent_documents" in query:
            return next(
                (item for item in self.documents if item["agent_id"] == params[0] and item["kind"] == params[1]),
                None,
            )
        return None

    def execute(self, query: str, params: tuple[Any, ...] = ()) -> int:
        if "INSERT INTO cp_workspaces" in query:
            self.workspaces.append(
                {
                    "id": params[0],
                    "name": params[1],
                    "description": params[2],
                    "root_path": params[3],
                    "root_kind": params[4],
                    "scan_status": params[5],
                    "spec_json": "{}",
                    "documents_json": "{}",
                    "last_scanned_at": None,
                    "scan_hash": "",
                    "config_sources_json": "{}",
                    "import_history_json": "[]",
                    "created_at": params[6],
                    "updated_at": params[7],
                }
            )
            return 1
        if "UPDATE cp_workspaces" in query and "config_sources_json" in query:
            row = self.fetch_one("SELECT * FROM cp_workspaces WHERE id = ?", (params[7],))
            assert row is not None
            row.update(
                {
                    "root_path": params[0],
                    "root_kind": params[1],
                    "scan_status": params[2],
                    "last_scanned_at": params[3],
                    "scan_hash": params[4],
                    "config_sources_json": params[5],
                    "updated_at": params[6],
                }
            )
            return 1
        if "UPDATE cp_workspaces" in query and "documents_json" in query:
            row = self.fetch_one("SELECT * FROM cp_workspaces WHERE id = ?", (params[3],))
            assert row is not None
            row["spec_json"] = params[0]
            row["documents_json"] = params[1]
            row["updated_at"] = params[2]
            return 1
        if "UPDATE cp_workspaces SET import_history_json" in query:
            row = self.fetch_one("SELECT * FROM cp_workspaces WHERE id = ?", (params[2],))
            assert row is not None
            row["import_history_json"] = params[0]
            row["updated_at"] = params[1]
            return 1
        if "INSERT INTO cp_agent_definitions" in query:
            self.agents.append(
                {
                    "id": params[0],
                    "display_name": params[1],
                    "status": params[2],
                    "appearance_json": params[3],
                    "storage_namespace": params[4],
                    "runtime_endpoint_json": params[5],
                    "metadata_json": params[6],
                    "workspace_id": params[7],
                    "squad_id": params[8],
                    "applied_version": None,
                    "desired_version": None,
                    "created_at": params[9],
                    "updated_at": params[10],
                }
            )
            return 1
        if "INSERT INTO cp_agent_documents" in query:
            self.documents[:] = [
                item for item in self.documents if not (item["agent_id"] == params[0] and item["kind"] == params[1])
            ]
            self.documents.append(
                {"agent_id": params[0], "kind": params[1], "content_md": params[2], "updated_at": params[3]}
            )
            return 1
        return 1


@pytest.fixture
def workspace_manager(monkeypatch: pytest.MonkeyPatch) -> tuple[manager_mod.ControlPlaneManager, _WorkspaceMemDB]:
    db = _WorkspaceMemDB()
    manager = manager_mod.ControlPlaneManager.__new__(manager_mod.ControlPlaneManager)
    monkeypatch.setattr(manager, "ensure_seeded", lambda: None)
    monkeypatch.setattr(manager_mod, "fetch_all", db.fetch_all)
    monkeypatch.setattr(manager_mod, "fetch_one", db.fetch_one)
    monkeypatch.setattr(manager_mod, "execute", db.execute)
    monkeypatch.setattr(manager_mod, "now_iso", lambda: "2026-05-18T00:00:00Z")

    def create_agent_stub(payload: dict[str, Any]) -> dict[str, Any]:
        organization = payload.get("organization") or {}
        agent_id = str(payload["id"])
        db.agents.append(
            {
                "id": agent_id,
                "display_name": str(payload.get("display_name") or agent_id),
                "status": str(payload.get("status") or "paused"),
                "appearance_json": "{}",
                "storage_namespace": agent_id.lower(),
                "runtime_endpoint_json": "{}",
                "metadata_json": json.dumps(payload.get("metadata") or {}),
                "workspace_id": organization.get("workspace_id"),
                "squad_id": organization.get("squad_id"),
                "applied_version": None,
                "desired_version": None,
                "created_at": "2026-05-18T00:00:00Z",
                "updated_at": "2026-05-18T00:00:00Z",
            }
        )
        return {"id": agent_id}

    def upsert_document_stub(agent_id: str, kind: str, payload: dict[str, Any]) -> dict[str, Any]:
        db.documents.append(
            {
                "agent_id": agent_id,
                "kind": kind,
                "content_md": str(payload.get("content_md") or ""),
                "updated_at": "2026-05-18T00:00:00Z",
            }
        )
        return db.documents[-1]

    monkeypatch.setattr(manager, "create_agent", create_agent_stub)
    monkeypatch.setattr(manager, "upsert_document", upsert_document_stub)
    return manager, db


def test_workspace_import_applies_prompt_block_and_preserves_manual_text(
    workspace_manager: tuple[manager_mod.ControlPlaneManager, _WorkspaceMemDB],
    tmp_path: Path,
) -> None:
    manager, db = workspace_manager
    _write_sample_workspace(tmp_path)
    scan = manager.scan_workspace_directory({"path": str(tmp_path)})
    selected = [
        source["source_id"]
        for source in scan["sources"]
        if source["import_action"] == "append_workspace_prompt" and source["risk"] == "low"
    ]

    result = manager.import_workspace_from_directory({"path": str(tmp_path), "selectedSourceIds": selected})

    workspace = result["workspace"]
    docs = json.loads(db.workspaces[0]["documents_json"])
    assert workspace["root_path"] == str(tmp_path)
    assert "<!-- koda:workspace-import:start" in docs["system_prompt_md"]
    assert "AGENTS.md" in docs["system_prompt_md"]

    docs["system_prompt_md"] = f"Manual preface.\n\n{docs['system_prompt_md']}\n\nManual suffix."
    db.workspaces[0]["documents_json"] = json.dumps(docs)
    (tmp_path / "AGENTS.md").write_text("Updated import text.", encoding="utf-8")
    manager.rescan_workspace(workspace["id"], {})
    manager.import_workspace_config(workspace["id"], {"selectedSourceIds": selected})
    updated = json.loads(db.workspaces[0]["documents_json"])["system_prompt_md"]

    assert "Manual preface." in updated
    assert "Manual suffix." in updated
    assert updated.count("<!-- koda:workspace-import:start") == 1


def test_workspace_import_creates_paused_draft_agent(
    workspace_manager: tuple[manager_mod.ControlPlaneManager, _WorkspaceMemDB],
    tmp_path: Path,
) -> None:
    manager, db = workspace_manager
    _write_sample_workspace(tmp_path)
    scan = manager.scan_workspace_directory({"path": str(tmp_path)})
    agent_source = next(source for source in scan["sources"] if source["import_action"] == "create_agent_draft")
    result = manager.import_workspace_from_directory({"path": str(tmp_path), "selectedSourceIds": [agent_source["source_id"]]})

    assert result["import_result"]["applied"][0]["action"] == "agent_draft"
    assert db.agents[0]["status"] == "paused"
    metadata = json.loads(db.agents[0]["metadata_json"])
    assert metadata["imported_from"]["source_id"] == agent_source["source_id"]
    assert db.documents[0]["kind"] == "system_prompt_md"


@pytest.mark.asyncio
async def test_agent_set_workdir_rejects_paths_outside_active_workspace_roots(tmp_path: Path) -> None:
    runtime_root = tmp_path / "runtime"
    source_root = tmp_path / "source"
    outside = tmp_path / "outside"
    runtime_root.mkdir()
    source_root.mkdir()
    outside.mkdir()
    ctx = ToolContext(
        user_id=1,
        chat_id=1,
        work_dir=str(runtime_root),
        user_data={},
        agent=None,
        agent_mode="normal",
        source_root_path=str(source_root),
        runtime_workspace_path=str(runtime_root),
    )

    blocked = await _handle_set_workdir({"path": str(outside)}, ctx)
    allowed = await _handle_set_workdir({"path": str(source_root)}, ctx)

    assert blocked.success is False
    assert "active runtime workspace" in blocked.output
    assert allowed.success is True
