"""Focused tests for agent-spec prompt compilation hygiene."""

from __future__ import annotations

from koda.control_plane.agent_spec import compose_agent_prompt, render_markdown_documents_from_agent_spec


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
