"""Focused tests for agent-spec prompt compilation hygiene."""

from __future__ import annotations

from koda.control_plane.agent_spec import (
    compose_agent_prompt,
    normalize_resource_access_policy,
    render_markdown_documents_from_agent_spec,
    resolve_scope_documents,
    validate_agent_spec,
)


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
                "GWS": {
                    "enabled": True,
                    "allow_actions": ["gmail.list", "drive.*"],
                    "secret_keys": ["gws_credentials_file"],
                    "allowed_domains": ["googleapis.com"],
                    "allow_private_network": False,
                }
            },
        }
    )

    assert policy["allowed_global_secret_keys"] == ["OPENAI_API_KEY"]
    assert policy["integration_grants"]["gws"] == {
        "enabled": True,
        "allow_actions": ["gmail.list", "drive.*"],
        "secret_keys": ["GWS_CREDENTIALS_FILE"],
        "allowed_domains": ["googleapis.com"],
        "allow_private_network": False,
    }


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
