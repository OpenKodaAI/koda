"""Bootstrap helpers that hydrate worker env from the control plane."""

from __future__ import annotations

import os

from koda.logging_config import get_logger

from .manager import get_control_plane_manager
from .settings import CONTROL_PLANE_ENABLED

log = get_logger(__name__)


def apply_runtime_env_from_control_plane(agent_id: str | None) -> None:
    """Populate the current process environment from the published control-plane snapshot."""
    if not CONTROL_PLANE_ENABLED or not agent_id:
        return
    manager = get_control_plane_manager()
    manager.ensure_seeded()
    agent = manager.get_agent(agent_id)
    if agent is None:
        return
    version = agent.get("applied_version") or agent.get("desired_version")
    if not version:
        publish = manager.publish_agent(agent_id)
        version = publish["version"]
    try:
        snapshot = manager.build_runtime_snapshot(agent_id, version=int(version))
    except Exception:
        log.exception("control_plane_bootstrap_failed", agent_id=agent_id, version=version)
        return
    for key, value in snapshot.env.items():
        os.environ[key] = value
    os.environ["AGENT_ID"] = agent_id.upper()
    os.environ["CONTROL_PLANE_RUNTIME_BASE_URL"] = snapshot.runtime_base_url
    os.environ["CONTROL_PLANE_HEALTH_URL"] = snapshot.health_url
    log.info("control_plane_bootstrap_applied", agent_id=agent_id, version=snapshot.version)
