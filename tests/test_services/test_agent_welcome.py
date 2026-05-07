"""Tests for the agent welcome message builder."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from koda.services.agent_welcome import build_start_message


def _stub_agent(
    *,
    display_name: str = "Pixie Copy",
    workspace_name: str | None = "Marketing",
    squad_name: str | None = "Copy Squad",
) -> dict[str, object]:
    return {
        "id": "PIXIE_COPY",
        "display_name": display_name,
        "organization": {
            "workspace_name": workspace_name,
            "squad_name": squad_name,
        },
    }


def _patched_manager(agent: dict[str, object] | None):
    manager = MagicMock()
    manager.get_agent.return_value = agent
    return patch("koda.control_plane.manager.get_control_plane_manager", return_value=manager)


class TestBuildStartMessage:
    def test_header_with_workspace_and_squad(self) -> None:
        with _patched_manager(_stub_agent()):
            message = build_start_message("PIXIE_COPY")
        assert message.startswith("Pixie Copy · Marketing / Copy Squad\n")

    def test_header_with_workspace_only(self) -> None:
        agent = _stub_agent(squad_name=None)
        with _patched_manager(agent):
            message = build_start_message("PIXIE_COPY")
        assert message.startswith("Pixie Copy · Marketing\n")

    def test_header_without_organization(self) -> None:
        agent = _stub_agent(workspace_name=None, squad_name=None)
        with _patched_manager(agent):
            message = build_start_message("PIXIE_COPY")
        assert message.startswith("Pixie Copy\nReady.")

    def test_body_in_english(self) -> None:
        with _patched_manager(_stub_agent()):
            message = build_start_message("PIXIE_COPY")
        assert "Ready." in message
        assert "Quick actions" in message
        assert "Commands" in message
        assert "/settings" in message
        assert "/newsession" in message
        assert "/help" in message
        assert "natural language" in message.lower()

    def test_falls_back_to_agent_name_when_agent_missing(self) -> None:
        with _patched_manager(None):
            message = build_start_message("missing-agent")
        # Config AGENT_NAME fallback used; header is bare display name
        first_line = message.split("\n", 1)[0]
        assert first_line  # non-empty
        assert "Ready." in message

    def test_resilient_when_control_plane_raises(self) -> None:
        manager = MagicMock()
        manager.get_agent.side_effect = RuntimeError("control plane down")
        with patch("koda.control_plane.manager.get_control_plane_manager", return_value=manager):
            message = build_start_message("any-agent")
        assert "Ready." in message
