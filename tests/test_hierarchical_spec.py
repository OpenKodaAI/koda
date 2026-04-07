"""Tests for the hierarchical prompt spec system (Workspace -> Squad -> Agent)."""

from __future__ import annotations

import json
import re
from typing import Any
from unittest.mock import MagicMock

import pytest

from koda.control_plane.agent_spec import (
    merge_hierarchical_documents,
    merge_hierarchical_spec,
    normalize_squad_spec,
    normalize_workspace_spec,
)

# ---------------------------------------------------------------------------
# normalize_workspace_spec
# ---------------------------------------------------------------------------


class TestNormalizeWorkspaceSpec:
    def test_filters_to_allowed_sections(self) -> None:
        spec: dict[str, Any] = {
            "hard_rules": {
                "non_negotiables": ["Always respond in formal tone"],
                "forbidden_actions": ["Do not delete production data"],
                "security_rules": ["Never expose API keys"],
                "extra_field": "should be removed",
            },
            "response_policy": {
                "language": "pt-BR",
                "citation_policy": "always cite sources",
                "quality_bar": "high",
            },
            "model_policy": {
                "allowed_providers": ["openai", "anthropic"],
                "max_budget_usd": 100.0,
                "max_total_budget_usd": 500.0,
            },
            "resource_access_policy": {
                "integration_grants": ["jira", "slack"],
            },
            # These should be stripped
            "operating_instructions": {"default_workflow": "scrum"},
            "tool_policy": {"allowed_categories": ["dev"]},
        }
        result = normalize_workspace_spec(spec)
        assert "hard_rules" in result
        assert "non_negotiables" in result["hard_rules"]
        assert "forbidden_actions" in result["hard_rules"]
        assert "security_rules" in result["hard_rules"]
        assert "extra_field" not in result["hard_rules"]
        assert "response_policy" in result
        assert result["response_policy"]["language"] == "pt-BR"
        assert "model_policy" in result
        assert result["model_policy"]["allowed_providers"] == ["openai", "anthropic"]
        assert "resource_access_policy" in result
        # Sections not in WORKSPACE_SPEC_FIELDS should be gone
        assert "operating_instructions" not in result
        assert "tool_policy" not in result

    def test_empty_spec_returns_empty(self) -> None:
        assert normalize_workspace_spec({}) == {}

    def test_strips_empty_values(self) -> None:
        spec: dict[str, Any] = {
            "hard_rules": {
                "non_negotiables": [],
                "forbidden_actions": "",
            },
        }
        result = normalize_workspace_spec(spec)
        assert result == {}


# ---------------------------------------------------------------------------
# normalize_squad_spec
# ---------------------------------------------------------------------------


class TestNormalizeSquadSpec:
    def test_filters_to_allowed_sections(self) -> None:
        spec: dict[str, Any] = {
            "operating_instructions": {
                "default_workflow": "kanban",
                "execution_heuristics": "fast iteration",
                "handoff_expectations": "document before handoff",
            },
            "interaction_style": {
                "tone": "professional",
                "collaboration_style": "async",
                "writing_style": "concise",
            },
            "tool_policy": {
                "allowed_categories": ["dev", "ops"],
                "allowed_tool_ids": ["shell_exec", "git_status"],
            },
            "knowledge_policy": {
                "enabled": True,
                "max_results": 10,
            },
            "hard_rules": {
                "approval_requirements": ["Must have manager approval for deploys"],
                "non_negotiables": ["should be filtered out"],
            },
            # Should be removed
            "model_policy": {"allowed_providers": ["openai"]},
            "response_policy": {"language": "en"},
        }
        result = normalize_squad_spec(spec)
        assert "operating_instructions" in result
        assert result["operating_instructions"]["default_workflow"] == "kanban"
        assert "interaction_style" in result
        assert result["interaction_style"]["tone"] == "professional"
        assert "tool_policy" in result
        assert result["tool_policy"]["allowed_categories"] == ["dev", "ops"]
        assert "knowledge_policy" in result
        assert "hard_rules" in result
        assert "approval_requirements" in result["hard_rules"]
        assert "non_negotiables" not in result["hard_rules"]
        # Sections not allowed at squad level
        assert "model_policy" not in result
        assert "response_policy" not in result

    def test_knowledge_policy_allows_all_fields(self) -> None:
        spec: dict[str, Any] = {
            "knowledge_policy": {
                "enabled": True,
                "max_results": 10,
                "custom_field": "should be kept",
            },
        }
        result = normalize_squad_spec(spec)
        assert result["knowledge_policy"]["custom_field"] == "should be kept"


# ---------------------------------------------------------------------------
# merge_hierarchical_spec
# ---------------------------------------------------------------------------


class TestMergeHierarchicalSpec:
    def test_lists_concatenate_across_levels(self) -> None:
        workspace_spec: dict[str, Any] = {
            "hard_rules": {
                "non_negotiables": ["WS rule 1", "WS rule 2"],
            },
        }
        squad_spec: dict[str, Any] = {
            "hard_rules": {
                "non_negotiables": ["SQ rule 1"],
            },
        }
        agent_spec: dict[str, Any] = {
            "hard_rules": {
                "non_negotiables": ["AG rule 1"],
            },
        }
        result = merge_hierarchical_spec(workspace_spec, squad_spec, agent_spec)
        merged_rules = result["hard_rules"]["non_negotiables"]
        assert "WS rule 1" in merged_rules
        assert "WS rule 2" in merged_rules
        assert "SQ rule 1" in merged_rules
        assert "AG rule 1" in merged_rules
        # Workspace items come first, then squad, then agent
        assert merged_rules.index("WS rule 1") < merged_rules.index("SQ rule 1")
        assert merged_rules.index("SQ rule 1") < merged_rules.index("AG rule 1")

    def test_scalars_most_specific_wins(self) -> None:
        workspace_spec: dict[str, Any] = {
            "response_policy": {
                "language": "pt-BR",
                "quality_bar": "high",
            },
        }
        squad_spec: dict[str, Any] = {
            "response_policy": {
                "language": "en",
            },
        }
        agent_spec: dict[str, Any] = {
            "response_policy": {
                "language": "fr",
            },
        }
        result = merge_hierarchical_spec(workspace_spec, squad_spec, agent_spec)
        # Agent value wins over squad over workspace
        assert result["response_policy"]["language"] == "fr"
        # Workspace value present when not overridden
        assert result["response_policy"]["quality_bar"] == "high"

    def test_agent_without_squad(self) -> None:
        workspace_spec: dict[str, Any] = {
            "hard_rules": {"non_negotiables": ["WS rule"]},
        }
        agent_spec: dict[str, Any] = {
            "hard_rules": {"non_negotiables": ["AG rule"]},
        }
        result = merge_hierarchical_spec(workspace_spec, None, agent_spec)
        merged_rules = result["hard_rules"]["non_negotiables"]
        assert "WS rule" in merged_rules
        assert "AG rule" in merged_rules

    def test_agent_without_workspace(self) -> None:
        agent_spec: dict[str, Any] = {
            "hard_rules": {"non_negotiables": ["AG rule"]},
            "response_policy": {"language": "en"},
        }
        result = merge_hierarchical_spec(None, None, agent_spec)
        assert result["hard_rules"]["non_negotiables"] == ["AG rule"]
        assert result["response_policy"]["language"] == "en"

    def test_empty_specs_at_all_levels(self) -> None:
        result = merge_hierarchical_spec({}, {}, {})
        assert result == {}

    def test_workspace_only_fields_propagate(self) -> None:
        workspace_spec: dict[str, Any] = {
            "model_policy": {"allowed_providers": ["openai"]},
        }
        agent_spec: dict[str, Any] = {}
        result = merge_hierarchical_spec(workspace_spec, None, agent_spec)
        assert result["model_policy"]["allowed_providers"] == ["openai"]

    def test_documents_key_not_merged_into_spec(self) -> None:
        workspace_spec: dict[str, Any] = {
            "documents": {"identity_md": "workspace identity"},
        }
        agent_spec: dict[str, Any] = {
            "documents": {"identity_md": "agent identity"},
        }
        result = merge_hierarchical_spec(workspace_spec, None, agent_spec)
        # documents key should be untouched (agent value preserved, not merged via spec merge)
        assert result["documents"]["identity_md"] == "agent identity"

    def test_deduplicates_list_items(self) -> None:
        workspace_spec: dict[str, Any] = {
            "hard_rules": {"non_negotiables": ["shared rule", "WS only"]},
        }
        agent_spec: dict[str, Any] = {
            "hard_rules": {"non_negotiables": ["shared rule", "AG only"]},
        }
        result = merge_hierarchical_spec(workspace_spec, None, agent_spec)
        rules = result["hard_rules"]["non_negotiables"]
        assert rules.count("shared rule") == 1


# ---------------------------------------------------------------------------
# merge_hierarchical_documents
# ---------------------------------------------------------------------------


class TestMergeHierarchicalDocuments:
    def test_layout_documents_include_origin_markers(self) -> None:
        ws_docs = {"identity_md": "Workspace identity"}
        sq_docs = {"identity_md": "Squad identity"}
        ag_docs = {"identity_md": "Agent identity"}
        result = merge_hierarchical_documents(ws_docs, sq_docs, ag_docs)
        assert "<!-- origin:workspace -->" in result["identity_md"]
        assert "<!-- origin:squad -->" in result["identity_md"]
        assert "<!-- origin:agent -->" in result["identity_md"]
        assert "Workspace identity" in result["identity_md"]
        assert "Squad identity" in result["identity_md"]
        assert "Agent identity" in result["identity_md"]

    def test_only_agent_docs(self) -> None:
        ag_docs = {"identity_md": "Agent identity"}
        result = merge_hierarchical_documents(None, None, ag_docs)
        assert "<!-- origin:agent -->" in result["identity_md"]
        assert "Agent identity" in result["identity_md"]

    def test_empty_documents(self) -> None:
        result = merge_hierarchical_documents(None, None, {})
        assert result == {}

    def test_non_layout_docs_concatenate_without_markers(self) -> None:
        ws_docs = {"voice_prompt_md": "workspace voice"}
        ag_docs = {"voice_prompt_md": "agent voice"}
        result = merge_hierarchical_documents(ws_docs, None, ag_docs)
        assert "<!-- origin:" not in result["voice_prompt_md"]
        assert "workspace voice" in result["voice_prompt_md"]
        assert "agent voice" in result["voice_prompt_md"]

    def test_workspace_only_documents(self) -> None:
        ws_docs = {"rules_md": "WS rules"}
        result = merge_hierarchical_documents(ws_docs, None, {})
        assert "WS rules" in result["rules_md"]

    def test_missing_levels_handled_gracefully(self) -> None:
        ag_docs = {"soul_md": "Agent soul", "instructions_md": "Agent instructions"}
        result = merge_hierarchical_documents(None, None, ag_docs)
        assert "Agent soul" in result["soul_md"]
        assert "Agent instructions" in result["instructions_md"]


# ---------------------------------------------------------------------------
# Prompt budget origin detection
# ---------------------------------------------------------------------------


class TestPromptBudgetOrigin:
    def test_origin_detection_for_merged_document(self) -> None:
        from koda.services.prompt_budget import preview_compiled_prompt

        documents = {
            "identity_md": "<!-- origin:workspace -->\nWS identity\n\n<!-- origin:agent -->\nAG identity",
            "rules_md": "Agent-only rules",
        }
        result = preview_compiled_prompt(
            compiled_prompt="test prompt",
            documents=documents,
            agent_id="test",
        )
        segments = result["segments"]
        identity_seg = next(s for s in segments if s["segment_id"] == "identity_md")
        rules_seg = next(s for s in segments if s["segment_id"] == "rules_md")
        assert identity_seg["origin"] == "merged"
        assert rules_seg["origin"] == "agent"

    def test_origin_workspace_only(self) -> None:
        from koda.services.prompt_budget import preview_compiled_prompt

        documents = {
            "identity_md": "<!-- origin:workspace -->\nWS identity",
        }
        result = preview_compiled_prompt(
            compiled_prompt="test prompt",
            documents=documents,
            agent_id="test",
        )
        seg = result["segments"][0]
        assert seg["origin"] == "workspace"


# ---------------------------------------------------------------------------
# API endpoint tests (mock manager)
# ---------------------------------------------------------------------------


class TestWorkspaceSpecAPI:
    @pytest.fixture()
    def mock_manager(self) -> MagicMock:
        return MagicMock()

    def test_get_workspace_spec_calls_manager(self, mock_manager: MagicMock) -> None:
        mock_manager.get_workspace_spec.return_value = {"spec": {}, "documents": {}}
        result = mock_manager.get_workspace_spec("ws-1")
        mock_manager.get_workspace_spec.assert_called_once_with("ws-1")
        assert result == {"spec": {}, "documents": {}}

    def test_update_workspace_spec_normalizes(self, mock_manager: MagicMock) -> None:
        payload = {
            "spec": {
                "hard_rules": {"non_negotiables": ["rule 1"]},
                "operating_instructions": {"should": "be filtered"},
            },
            "documents": {"identity_md": "ws identity"},
        }
        mock_manager.update_workspace_spec.return_value = {
            "spec": {},
            "documents": {"system_prompt_md": "ws identity"},
        }
        result = mock_manager.update_workspace_spec("ws-1", payload)
        mock_manager.update_workspace_spec.assert_called_once_with("ws-1", payload)
        assert result["spec"] == {}
        assert "system_prompt_md" in result["documents"]

    def test_get_squad_spec_calls_manager(self, mock_manager: MagicMock) -> None:
        mock_manager.get_squad_spec.return_value = {"spec": {}, "documents": {}}
        result = mock_manager.get_squad_spec("ws-1", "sq-1")
        mock_manager.get_squad_spec.assert_called_once_with("ws-1", "sq-1")
        assert result == {"spec": {}, "documents": {}}

    def test_update_squad_spec_normalizes(self, mock_manager: MagicMock) -> None:
        payload = {
            "spec": {
                "tool_policy": {"allowed_categories": ["dev"]},
                "model_policy": {"should": "be filtered"},
            },
            "documents": {},
        }
        mock_manager.update_squad_spec.return_value = {
            "spec": {},
            "documents": {"system_prompt_md": "dev"},
        }
        result = mock_manager.update_squad_spec("ws-1", "sq-1", payload)
        mock_manager.update_squad_spec.assert_called_once_with("ws-1", "sq-1", payload)
        assert result["spec"] == {}
        assert "system_prompt_md" in result["documents"]


# ---------------------------------------------------------------------------
# Integration: normalize + merge round-trip
# ---------------------------------------------------------------------------


class TestNormalizeMergeRoundTrip:
    def test_full_hierarchy_round_trip(self) -> None:
        raw_ws = {
            "hard_rules": {
                "non_negotiables": ["Always be safe"],
                "security_rules": ["No secrets in logs"],
            },
            "response_policy": {"language": "pt-BR"},
        }
        raw_sq = {
            "operating_instructions": {"default_workflow": "scrum"},
            "hard_rules": {"approval_requirements": ["Manager sign-off"]},
        }
        raw_agent: dict[str, Any] = {
            "hard_rules": {"non_negotiables": ["Agent specific rule"]},
            "response_policy": {"language": "en"},
            "operating_instructions": {"execution_heuristics": "fast"},
        }

        ws_normalized = normalize_workspace_spec(raw_ws)
        sq_normalized = normalize_squad_spec(raw_sq)
        merged = merge_hierarchical_spec(ws_normalized, sq_normalized, raw_agent)

        # Lists from workspace and agent merge
        assert "Always be safe" in merged["hard_rules"]["non_negotiables"]
        assert "Agent specific rule" in merged["hard_rules"]["non_negotiables"]
        # Squad approval_requirements present
        assert "Manager sign-off" in merged["hard_rules"]["approval_requirements"]
        # Scalar: agent wins
        assert merged["response_policy"]["language"] == "en"
        # Squad operating_instructions merged with agent
        assert merged["operating_instructions"]["default_workflow"] == "scrum"
        assert merged["operating_instructions"]["execution_heuristics"] == "fast"
        # Workspace security_rules present
        assert "No secrets in logs" in merged["hard_rules"]["security_rules"]


# ---------------------------------------------------------------------------
# In-memory DB stub for integration tests (#4)
# ---------------------------------------------------------------------------


class _DictRow(dict):
    def __getitem__(self, key: str) -> Any:
        return super().__getitem__(key)


class _HierarchyMemDB:
    """Minimal in-memory DB that supports workspace/squad spec CRUD."""

    def __init__(self) -> None:
        self.tables: dict[str, list[dict[str, Any]]] = {
            "cp_workspaces": [],
            "cp_workspace_squads": [],
            "cp_agent_definitions": [],
        }

    def fetch_one(self, query: str, params: tuple[Any, ...] = ()) -> Any | None:
        rows = self.fetch_all(query, params)
        return rows[0] if rows else None

    def fetch_all(self, query: str, params: tuple[Any, ...] = ()) -> list[Any]:
        table = self._extract_table(query)
        if table is None:
            return []
        rows = self.tables.get(table, [])
        where_cols = re.findall(r"(\w+)\s*=\s*\?", query)
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
            return [_DictRow(r) for r in filtered]
        return [_DictRow(r) for r in rows]

    def execute(self, query: str, params: tuple[Any, ...] = ()) -> int:
        q = query.strip().upper()
        if q.startswith("UPDATE"):
            return self._handle_update(query, params)
        return 0

    def _handle_update(self, query: str, params: tuple[Any, ...]) -> int:
        table = self._extract_table(query)
        if table is None:
            return 0
        set_match = re.search(r"SET\s+(.+?)\s+WHERE", query, re.I | re.S)
        if not set_match:
            return 0
        set_cols = re.findall(r"(\w+)\s*=\s*\?", set_match.group(1))
        where_part = query[set_match.end() :]
        where_cols = re.findall(r"(\w+)\s*=\s*\?", where_part)
        set_values = params[: len(set_cols)]
        where_values = params[len(set_cols) :]
        updated = 0
        for row in self.tables.get(table, []):
            match = all(j >= len(where_values) or row.get(col) == where_values[j] for j, col in enumerate(where_cols))
            if match:
                for j, col in enumerate(set_cols):
                    if j < len(set_values):
                        row[col] = set_values[j]
                updated += 1
        return updated

    @staticmethod
    def _extract_table(query: str) -> str | None:
        m = re.search(r"(?:FROM|INTO|UPDATE|DELETE\s+FROM)\s+(\w+)", query, re.I)
        return m.group(1) if m else None


def _seed_hierarchy(db: _HierarchyMemDB) -> None:
    """Seed a workspace, squad, and agent with workspace/squad specs."""
    db.tables["cp_workspaces"].append(
        _DictRow(
            {
                "id": "ws-acme",
                "name": "Acme Corp",
                "description": "",
                "color": "",
                "spec_json": json.dumps(
                    {
                        "hard_rules": {
                            "non_negotiables": ["Never expose PII"],
                            "forbidden_actions": ["Delete production data"],
                            "security_rules": ["Encrypt at rest"],
                        },
                        "response_policy": {"language": "pt-BR", "quality_bar": "high"},
                        "model_policy": {"allowed_providers": ["anthropic", "openai"]},
                        # This should be stripped by normalize_workspace_spec
                        "operating_instructions": {"default_workflow": "should be stripped"},
                    }
                ),
                "documents_json": json.dumps({"identity_md": "Acme Corp compliance guide"}),
                "created_at": "2026-01-01T00:00:00Z",
                "updated_at": "2026-01-01T00:00:00Z",
            }
        )
    )
    db.tables["cp_workspace_squads"].append(
        _DictRow(
            {
                "id": "sq-eng",
                "workspace_id": "ws-acme",
                "name": "Engineering",
                "description": "",
                "color": "",
                "spec_json": json.dumps(
                    {
                        "tool_policy": {"allowed_categories": ["dev", "ops"]},
                        "interaction_style": {"tone": "professional"},
                        "hard_rules": {"approval_requirements": ["PR review required"]},
                        # This should be stripped by normalize_squad_spec
                        "model_policy": {"max_budget_usd": 999},
                    }
                ),
                "documents_json": json.dumps({"instructions_md": "Engineering playbook"}),
                "created_at": "2026-01-01T00:00:00Z",
                "updated_at": "2026-01-01T00:00:00Z",
            }
        )
    )
    db.tables["cp_agent_definitions"].append(
        _DictRow(
            {
                "id": "bot-alpha",
                "workspace_id": "ws-acme",
                "squad_id": "sq-eng",
            }
        )
    )


@pytest.fixture()
def hierarchy_manager(monkeypatch: pytest.MonkeyPatch):
    """Create a ControlPlaneManager backed by an in-memory DB with seeded hierarchy."""
    import koda.control_plane.manager as manager_mod

    db = _HierarchyMemDB()
    _seed_hierarchy(db)
    monkeypatch.setattr(manager_mod, "fetch_one", db.fetch_one)
    monkeypatch.setattr(manager_mod, "fetch_all", db.fetch_all)
    monkeypatch.setattr(manager_mod, "execute", db.execute)
    monkeypatch.setattr(manager_mod, "now_iso", lambda: "2026-04-01T00:00:00Z")
    monkeypatch.setattr(manager_mod, "json_dump", json.dumps)
    monkeypatch.setattr(manager_mod, "CONTROL_PLANE_AUTO_IMPORT", False)
    mgr = object.__new__(manager_mod.ControlPlaneManager)
    mgr._seeding_legacy_state = False
    mgr._elevenlabs_voice_cache = {}
    mgr._ollama_model_cache = {}
    mgr._provider_login_processes = {}
    mgr._provider_download_threads = {}
    return mgr, db


# ---------------------------------------------------------------------------
# #4: Integration tests with real manager CRUD
# ---------------------------------------------------------------------------


class TestManagerIntegrationCRUD:
    def test_get_workspace_spec(self, hierarchy_manager) -> None:
        mgr, _ = hierarchy_manager
        result = mgr.get_workspace_spec("ws-acme")
        assert result["spec"] == {}
        prompt = result["documents"]["system_prompt_md"]
        assert "Never expose PII" in prompt
        assert "Acme Corp compliance guide" in prompt

    def test_update_workspace_spec_strips_disallowed_fields(self, hierarchy_manager) -> None:
        mgr, _ = hierarchy_manager
        payload = {
            "spec": {
                "hard_rules": {"non_negotiables": ["New global rule"]},
                "operating_instructions": {"default_workflow": "scrum"},  # NOT allowed
                "tool_policy": {"allowed_categories": ["dev"]},  # NOT allowed
            },
            "documents": {"rules_md": "Updated rules"},
        }
        result = mgr.update_workspace_spec("ws-acme", payload)
        assert result["spec"] == {}
        assert "New global rule" in result["documents"]["system_prompt_md"]
        assert "Updated rules" in result["documents"]["system_prompt_md"]
        persisted = mgr.get_workspace_spec("ws-acme")
        assert persisted["spec"] == {}
        assert "New global rule" in persisted["documents"]["system_prompt_md"]

    def test_get_squad_spec(self, hierarchy_manager) -> None:
        mgr, _ = hierarchy_manager
        result = mgr.get_squad_spec("ws-acme", "sq-eng")
        assert result["spec"] == {}
        prompt = result["documents"]["system_prompt_md"]
        assert "Engineering playbook" in prompt
        assert "dev" in prompt
        assert "ops" in prompt

    def test_update_squad_spec_strips_disallowed_fields(self, hierarchy_manager) -> None:
        mgr, _ = hierarchy_manager
        payload = {
            "spec": {
                "interaction_style": {"tone": "casual"},
                "model_policy": {"allowed_providers": ["openai"]},  # NOT allowed
                "response_policy": {"language": "en"},  # NOT allowed
            },
            "documents": {},
        }
        result = mgr.update_squad_spec("ws-acme", "sq-eng", payload)
        assert result["spec"] == {}
        assert "casual" in result["documents"]["system_prompt_md"]

    def test_squad_spec_requires_matching_workspace(self, hierarchy_manager) -> None:
        mgr, db = hierarchy_manager
        # Add a squad in a different workspace
        db.tables["cp_workspace_squads"].append(
            _DictRow(
                {
                    "id": "sq-other",
                    "workspace_id": "ws-other",
                    "name": "Other Squad",
                    "description": "",
                    "color": "",
                    "spec_json": "{}",
                    "documents_json": "{}",
                    "created_at": "2026-01-01T00:00:00Z",
                    "updated_at": "2026-01-01T00:00:00Z",
                }
            )
        )
        with pytest.raises(ValueError, match="squad_id must belong to the selected workspace"):
            mgr.get_squad_spec("ws-acme", "sq-other")


# ---------------------------------------------------------------------------
# #5: Budget test with 3-level merged prompt
# ---------------------------------------------------------------------------


class TestBudgetThreeLevelMerge:
    def test_three_level_merged_prompt_within_budget(self) -> None:
        """A prompt built from all three hierarchy levels must fit the context window."""
        from koda.control_plane.agent_spec import compose_agent_prompt
        from koda.services.prompt_budget import (
            PromptBudgetPlanner,
            PromptSegment,
        )

        # Build realistic merged documents from all three levels
        ws_docs = {
            "rules_md": (
                "<!-- origin:workspace -->\n"
                "# Global Compliance Rules\n\n" + "\n".join(f"- Rule {i}: Do not violate policy {i}" for i in range(50))
            ),
        }
        sq_docs = {
            "rules_md": (
                "<!-- origin:squad -->\n"
                "# Squad Rules\n\n" + "\n".join(f"- Squad rule {i}: Follow procedure {i}" for i in range(30))
            ),
            "instructions_md": (
                "<!-- origin:squad -->\n"
                "# Engineering Playbook\n\n"
                "Follow the standard development workflow for all tasks."
            ),
        }
        ag_docs = {
            "rules_md": (
                "<!-- origin:agent -->\n"
                "# Agent-Specific Rules\n\n"
                "- Never deploy on Fridays\n"
                "- Always run tests before commit"
            ),
            "identity_md": (
                "<!-- origin:agent -->\n"
                "# Agent Identity\n\n"
                "You are a senior engineering assistant specialized in code review."
            ),
            "instructions_md": (
                "<!-- origin:agent -->\n"
                "# Agent Instructions\n\n"
                "When reviewing code, focus on correctness, security, and performance."
            ),
        }
        merged_docs = merge_hierarchical_documents(ws_docs, sq_docs, ag_docs)

        # Compose the agent prompt from merged documents
        compiled_prompt = compose_agent_prompt(merged_docs)
        assert compiled_prompt, "compiled prompt should not be empty"

        # Run through budget planner
        segments = [
            PromptSegment(
                segment_id="immutable_base_policy",
                text="You are a helpful assistant. Follow all rules.",
                category="base",
                priority=0,
                drop_policy="hard_floor",
            ),
            PromptSegment(
                segment_id="agent_contract",
                text=compiled_prompt,
                category="identity",
                priority=10,
                drop_policy="hard_floor",
            ),
        ]

        planner = PromptBudgetPlanner(context_window=200_000)
        result = planner.compile(
            provider="anthropic",
            model="claude-sonnet-4-20250514",
            segments=segments,
        )

        # The merged prompt must fit within budget
        assert result.within_budget, (
            f"3-level merged prompt exceeded budget: {result.compiled_tokens} tokens > {result.max_input_tokens} max"
        )
        assert result.gate_reason is None
        assert len(result.dropped_segments) == 0

        # Verify all three origins are present in the compiled output
        assert "<!-- origin:workspace -->" in result.compiled_prompt
        assert "<!-- origin:squad -->" in result.compiled_prompt
        assert "<!-- origin:agent -->" in result.compiled_prompt

    def test_large_hierarchy_triggers_budget_compression(self) -> None:
        """When hierarchy content is massive, budget planner drops discretionary segments."""
        from koda.services.prompt_budget import PromptBudgetPlanner, PromptSegment

        # Create an oversized prompt that would exceed a small context window
        huge_rules = "\n".join(f"- Rule {i}: " + "x" * 200 for i in range(500))
        segments = [
            PromptSegment(
                segment_id="base",
                text="Base prompt.",
                category="base",
                priority=0,
                drop_policy="hard_floor",
            ),
            PromptSegment(
                segment_id="huge_hierarchy_rules",
                text=huge_rules,
                category="identity",
                priority=50,
                drop_policy="drop",
            ),
            PromptSegment(
                segment_id="low_priority_extra",
                text="This should be dropped for budget." * 100,
                category="extras",
                priority=90,
                drop_policy="drop",
            ),
        ]

        # Use a very small context window to force budget pressure
        planner = PromptBudgetPlanner(context_window=8_000)
        result = planner.compile(
            provider="anthropic",
            model="claude-sonnet-4-20250514",
            segments=segments,
        )

        # Budget planner should have dropped or compressed segments
        assert len(result.dropped_segments) > 0 or result.compiled_tokens <= result.max_input_tokens


# ---------------------------------------------------------------------------
# #6: Squad with mismatched workspace_id excluded from merge
# ---------------------------------------------------------------------------


class TestResolveHierarchicalSpecSquadMismatch:
    def test_squad_with_wrong_workspace_excluded(self, hierarchy_manager) -> None:
        """A squad whose workspace_id doesn't match the agent's is excluded from merge."""
        mgr, db = hierarchy_manager

        # Create agent whose squad points to a different workspace
        db.tables["cp_agent_definitions"].append(
            _DictRow(
                {
                    "id": "bot-orphan",
                    "workspace_id": "ws-acme",
                    "squad_id": "sq-foreign",
                }
            )
        )
        # Squad exists but belongs to ws-other, not ws-acme
        db.tables["cp_workspace_squads"].append(
            _DictRow(
                {
                    "id": "sq-foreign",
                    "workspace_id": "ws-other",
                    "name": "Foreign Squad",
                    "description": "",
                    "color": "",
                    "spec_json": json.dumps({"tool_policy": {"allowed_categories": ["should-not-appear"]}}),
                    "documents_json": "{}",
                    "created_at": "2026-01-01T00:00:00Z",
                    "updated_at": "2026-01-01T00:00:00Z",
                }
            )
        )

        agent_spec: dict[str, Any] = {
            "hard_rules": {"non_negotiables": ["Agent rule"]},
        }
        agent_row = db.fetch_one("SELECT * FROM cp_agent_definitions WHERE id = ?", ("bot-orphan",))
        result = mgr._resolve_hierarchical_spec(agent_spec, agent_row)

        prompt = str(result.get("documents", {}).get("system_prompt_md") or "")
        assert "Never expose PII" in prompt
        assert "should-not-appear" not in json.dumps(result)

    def test_agent_without_workspace_or_squad(self, hierarchy_manager) -> None:
        """An agent with no workspace/squad returns the agent spec unchanged."""
        mgr, db = hierarchy_manager

        db.tables["cp_agent_definitions"].append(
            _DictRow(
                {
                    "id": "bot-solo",
                    "workspace_id": None,
                    "squad_id": None,
                }
            )
        )

        agent_spec: dict[str, Any] = {
            "hard_rules": {"non_negotiables": ["Solo rule"]},
            "response_policy": {"language": "en"},
        }
        agent_row = db.fetch_one("SELECT * FROM cp_agent_definitions WHERE id = ?", ("bot-solo",))
        result = mgr._resolve_hierarchical_spec(agent_spec, agent_row)

        # Should be effectively unchanged
        assert result["hard_rules"]["non_negotiables"] == ["Solo rule"]
        assert result["response_policy"]["language"] == "en"
