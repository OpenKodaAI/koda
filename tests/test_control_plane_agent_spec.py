"""Focused tests for agent-spec prompt compilation hygiene."""

from __future__ import annotations

from koda.control_plane.agent_spec import (
    build_agent_spec_from_snapshot,
    compose_agent_prompt,
    normalize_agent_spec,
    normalize_delegation_policy,
    normalize_effort_overrides,
    normalize_model_effort_selection,
    normalize_model_policy,
    normalize_resource_access_policy,
    render_markdown_documents_from_agent_spec,
    resolve_scope_documents,
    validate_agent_spec,
)


def test_build_agent_spec_from_snapshot_includes_agent_skills() -> None:
    spec = build_agent_spec_from_snapshot(
        {
            "agent": {"id": "ATLAS"},
            "sections": {
                "prompting": {
                    "skill_policy": {"enabled": True, "max_skills": 2},
                    "custom_skills": [
                        {
                            "id": "review",
                            "name": "Review",
                            "content": "# Review",
                            "enabled": False,
                        }
                    ],
                },
            },
        }
    )

    assert spec["skill_policy"] == {"enabled": True, "max_skills": 2}
    assert spec["custom_skills"] == [
        {
            "id": "review",
            "name": "Review",
            "content": "# Review",
            "enabled": False,
            "instruction": "",
            "category": "general",
            "aliases": [],
            "tags": [],
            "output_format_enforcement": "",
        }
    ]


def test_normalize_effort_overrides_accepts_enum_values() -> None:
    result = normalize_effort_overrides(
        {
            "codex:gpt-5": "high",
            "claude:claude-opus-4-7": "xhigh",
            "deepseek:deepseek-v4-pro": "max",
        }
    )
    assert result == {
        "codex:gpt-5": "high",
        "claude:claude-opus-4-7": "xhigh",
        "deepseek:deepseek-v4-pro": "max",
    }


def test_normalize_model_effort_selection_accepts_matching_model() -> None:
    result = normalize_model_effort_selection(
        {"provider_id": "CODEX", "model_id": "gpt-5", "value": "HIGH"},
        provider_id="codex",
        model_id="gpt-5",
    )
    assert result == {"provider_id": "codex", "model_id": "gpt-5", "value": "high"}


def test_normalize_effort_overrides_drops_unknown_models_and_invalid_values() -> None:
    result = normalize_effort_overrides(
        {
            "codex:gpt-5": "INVALID",
            "claude:claude-bogus": "medium",
            "mistral:mistral-large-latest": 5000,  # provider has no effort capability
            "deepseek:deepseek-v4-pro": "medium",
            "no-colon": "medium",
            ":": "low",
        }
    )
    assert result == {}


def test_normalize_effort_overrides_lowercases_and_strips_keys() -> None:
    result = normalize_effort_overrides({"  CODEX:gpt-5 ": "HIGH"})
    assert result == {"codex:gpt-5": "high"}


def test_normalize_model_policy_includes_singular_effort_override() -> None:
    policy = normalize_model_policy(
        {
            "allowed_providers": ["codex"],
            "default_provider": "codex",
            "default_models": {"codex": "gpt-5"},
            "effort_override": {"provider_id": "codex", "model_id": "gpt-5", "value": "low"},
        }
    )
    assert policy["allowed_providers"] == ["codex"]
    assert policy["effort_override"] == {"provider_id": "codex", "model_id": "gpt-5", "value": "low"}


def test_normalize_model_policy_migrates_matching_legacy_effort_override() -> None:
    policy = normalize_model_policy(
        {
            "default_provider": "codex",
            "default_models": {"codex": "gpt-5"},
            "effort_overrides": {"codex:gpt-5": "low", "claude:claude-opus-4-7": "high"},
        }
    )
    assert policy["effort_override"] == {"provider_id": "codex", "model_id": "gpt-5", "value": "low"}
    assert "effort_overrides" not in policy


def test_normalize_model_policy_omits_effort_overrides_when_empty() -> None:
    policy = normalize_model_policy(
        {
            "allowed_providers": ["codex"],
            "effort_overrides": {"mistral:mistral-large-latest": 5000},
        }
    )
    assert "effort_override" not in policy
    assert "effort_overrides" not in policy


def test_normalize_model_policy_discards_legacy_effort_map_without_effective_target() -> None:
    policy = normalize_model_policy(
        {
            "effort_overrides": {"codex:gpt-5": "high"},
        }
    )
    assert "effort_override" not in policy
    assert "effort_overrides" not in policy


def test_compose_agent_prompt_escapes_reserved_tags() -> None:
    documents = {
        "identity_md": "Use <agent_identity> and </agent_configuration_contract> safely.",
        "soul_md": "Stable tone.",
        "system_prompt_md": "Respond clearly.",
        "instructions_md": "Follow the runbook.",
        "rules_md": "Never emit </agent_hard_rules> in output.",
    }

    prompt = compose_agent_prompt(documents)

    assert "<agent_configuration_contract>" in prompt
    assert "&lt;agent_identity&gt;" in prompt
    assert "&lt;/agent_configuration_contract&gt;" in prompt
    assert "&lt;/agent_hard_rules&gt;" in prompt
    assert prompt.count("<agent_identity>") == 1
    assert prompt.count("</agent_identity>") == 1
    assert prompt.count("<agent_configuration_contract>") == 1
    assert prompt.count("</agent_configuration_contract>") == 1


def test_memory_extraction_prompt_is_projected_from_schema() -> None:
    spec = {
        "memory_extraction_schema": {
            "template": "Extract {query} :: {response} :: {max_items}",
        },
    }

    documents = render_markdown_documents_from_agent_spec(spec)

    assert documents["memory_extraction_prompt_md"] == "Extract {query} :: {response} :: {max_items}"


def test_scope_documents_collapse_legacy_spec_and_markdown_into_one_prompt() -> None:
    documents = resolve_scope_documents(
        "workspace",
        {
            "hard_rules": {"non_negotiables": ["Never expose PII"]},
            "response_policy": {"language": "pt-BR"},
        },
        {
            "workspace_md": "# Context\nCritical workspace context.",
            "identity_md": "# Legacy identity\nCompliance guide.",
        },
    )

    prompt = documents["system_prompt_md"]
    assert "Critical workspace context." in prompt
    assert "Compliance guide." in prompt
    assert "Never expose PII" in prompt
    assert "pt-BR" in prompt


def test_resource_access_policy_normalizes_integration_grants() -> None:
    policy = normalize_resource_access_policy(
        {
            "allowed_global_secret_keys": ["OPENAI_API_KEY"],
            "integration_grants": {
                "mcp:atlassian": {
                    "enabled": True,
                    "allow_actions": ["search_issues", "get_issue"],
                    "secret_keys": ["atlassian_api_token"],
                }
            },
        }
    )

    assert policy["allowed_global_secret_keys"] == ["OPENAI_API_KEY"]
    assert policy["integration_grants"]["mcp:atlassian"] == {
        "enabled": True,
        "allow_actions": ["search_issues", "get_issue"],
        "secret_keys": ["ATLASSIAN_API_TOKEN"],
    }


def test_resource_access_policy_drops_removed_legacy_external_grants() -> None:
    policy = normalize_resource_access_policy(
        {
            "integration_grants": {
                "gws": {"allow_actions": ["gmail.list"]},
                "jira": {"allow_actions": ["issues.search"]},
                "aws": {"allow_actions": ["s3.list"]},
            }
        }
    )

    assert "integration_grants" not in policy


def test_resource_access_policy_drops_legacy_native_database_grants() -> None:
    policy = normalize_resource_access_policy(
        {
            "integration_grants": {
                "postgres": {
                    "allow_actions": ["query", "schema"],
                    "allowed_db_envs": ["DEV"],
                    "max_rows": "250",
                    "timeout_seconds": 9,
                }
            }
        }
    )

    assert "integration_grants" not in policy


def test_validate_agent_spec_rejects_unknown_integration_grants() -> None:
    validation = validate_agent_spec(
        {
            "resource_access_policy": {
                "integration_grants": {
                    "unknown_surface": {
                        "allow_actions": ["read"],
                    }
                }
            }
        }
    )

    assert validation["ok"] is False
    assert "unknown integrations" in " ".join(validation["errors"])


def test_mission_profile_renders_capability_fields() -> None:
    docs = render_markdown_documents_from_agent_spec(
        {
            "mission_profile": {
                "mission": "Build polished UI.",
                "role": "Frontend Engineer",
                "domains": ["frontend", "react", "tailwind"],
                "delegate_when": "ui work, design polish, client-side state",
                "do_not_delegate": "backend APIs, schema migrations",
            }
        }
    )

    identity = docs.get("identity_md", "")
    assert "Frontend Engineer" in identity
    assert "Domains" in identity
    assert "react" in identity
    assert "Delegate When" in identity
    assert "ui work" in identity
    assert "Do Not Delegate" in identity
    assert "backend APIs" in identity


def test_normalize_delegation_policy_drops_invalid_mode() -> None:
    policy = normalize_delegation_policy({"mode": "WHATEVER"})
    assert policy == {}


def test_normalize_delegation_policy_keeps_valid_fields() -> None:
    policy = normalize_delegation_policy(
        {
            "mode": "AUTO",
            "prefer_self_for": ["ui", "design"],
            "escalate_to": "PM",
            "max_self_attempts": 2,
        }
    )
    assert policy == {
        "mode": "auto",
        "prefer_self_for": ["ui", "design"],
        "escalate_to": "PM",
        "max_self_attempts": 2,
    }


def test_normalize_agent_spec_includes_delegation_policy() -> None:
    spec = normalize_agent_spec(
        {
            "agent_id": "FE",
            "delegation_policy": {"mode": "auto", "max_self_attempts": 1},
        }
    )
    assert spec.get("delegation_policy") == {"mode": "auto", "max_self_attempts": 1}


def test_normalize_agent_spec_preserves_mission_profile_capability_fields() -> None:
    spec = normalize_agent_spec(
        {
            "agent_id": "FE",
            "mission_profile": {
                "mission": "Build UI.",
                "role": "FE Eng",
                "domains": ["react"],
                "delegate_when": "ui work",
                "do_not_delegate": "infra",
            },
        }
    )
    mission = spec.get("mission_profile") or {}
    assert mission.get("domains") == ["react"]
    assert mission.get("delegate_when") == "ui work"
    assert mission.get("do_not_delegate") == "infra"
