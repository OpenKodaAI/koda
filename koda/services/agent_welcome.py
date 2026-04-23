"""Welcome message builder for the `/start` command and equivalent channel entry points.

The message is always rendered in English — the canonical language for Koda's
user-facing runtime strings across every channel adapter (Telegram, Slack,
Discord, WhatsApp, etc.).
"""

from __future__ import annotations

from typing import Any

from koda.config import AGENT_NAME
from koda.logging_config import get_logger

log = get_logger(__name__)


_BODY = (
    "Ready.\n"
    "\n"
    "Quick actions\n"
    "• Send a message — query the coding runtime\n"
    "• Send a photo — analyze images\n"
    "• Send a document (PDF/DOCX/TXT) — analyze contents\n"
    "• Send a voice note — transcribe\n"
    "\n"
    "Commands\n"
    "/settings · agent settings\n"
    "/newsession · new session\n"
    "/sessions · saved sessions\n"
    "/voice · voice & TTS\n"
    "/tasks · running tasks\n"
    "/cancel · cancel execution\n"
    "/help · short help\n"
    "\n"
    "Natural language also works, for example:\n"
    "• switch the provider to OpenAI\n"
    "• use gpt-5.2 as the general model\n"
    "• for images, use codex gpt-image-1.5\n"
    "• change the voice to pm_alex\n"
    "• enable supervised mode\n"
    "\n"
    "Otherwise, just ask in natural language."
)


def _format_header(display_name: str, workspace_name: str | None, squad_name: str | None) -> str:
    trail_parts = [part for part in (workspace_name, squad_name) if part]
    if trail_parts:
        trail = " / ".join(trail_parts)
        return f"{display_name} · {trail}"
    return display_name


def _resolve_agent_context(agent_id: str | None) -> tuple[str, str | None, str | None]:
    """Return `(display_name, workspace_name, squad_name)` for the current agent.

    Falls back to `AGENT_NAME` from config if the control-plane lookup fails
    for any reason — the welcome message must never crash the `/start` flow.
    """
    if not agent_id:
        return AGENT_NAME, None, None
    try:
        from koda.control_plane.manager import get_control_plane_manager

        manager = get_control_plane_manager()
        agent: Any = manager.get_agent(agent_id)
    except Exception:  # pragma: no cover - defensive: control plane unreachable
        log.exception("agent_welcome.control_plane_lookup_failed", agent_id=agent_id)
        return AGENT_NAME, None, None

    if not agent:
        return AGENT_NAME, None, None

    display_name = str(agent.get("display_name") or AGENT_NAME)
    organization = agent.get("organization") or {}
    workspace_name = organization.get("workspace_name") or None
    squad_name = organization.get("squad_name") or None
    return display_name, workspace_name, squad_name


def build_start_message(agent_id: str | None) -> str:
    """Compose the `/start` welcome message for the given agent.

    The header shows the agent's display name plus its workspace / squad
    breadcrumb when available. The body is a concise English guide listing
    the main commands and what the agent accepts as input.
    """
    display_name, workspace_name, squad_name = _resolve_agent_context(agent_id)
    header = _format_header(display_name, workspace_name, squad_name)
    return f"{header}\n{_BODY}"
