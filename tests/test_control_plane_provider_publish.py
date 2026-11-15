"""Publishing an agent whose model policy names an unknown provider fails (M6-E3-T2, D-157)."""

from __future__ import annotations

from collections.abc import Iterator

import pytest

from koda.control_plane import database as control_plane_db
from koda.control_plane.manager import ControlPlaneManager

pytestmark = [pytest.mark.postgres]

_AGENT_ID = "PROVIDER_ID_PUBLISH"


@pytest.fixture
def manager(migrated_postgres: str) -> Iterator[ControlPlaneManager]:
    manager = ControlPlaneManager()
    manager.create_agent({"id": _AGENT_ID})
    yield manager
    for table in ("cp_agent_sections", "cp_agent_documents"):
        control_plane_db.execute(f"DELETE FROM {table} WHERE agent_id = ?", (_AGENT_ID,))
    control_plane_db.execute("DELETE FROM cp_agent_definitions WHERE id = ?", (_AGENT_ID,))


def test_unknown_provider_id_fails_publish(manager: ControlPlaneManager) -> None:
    manager.put_model_policy(_AGENT_ID, {"policy": {"default_models": {"claudee": "claude-sonnet-4-6"}}})

    error = "model_policy.default_models contains unknown providers: claudee"
    assert error in manager.publish_checks(_AGENT_ID)["errors"]
    with pytest.raises(ValueError, match=error):
        manager.publish_agent(_AGENT_ID)


def test_known_provider_ids_raise_no_provider_error(manager: ControlPlaneManager) -> None:
    manager.put_model_policy(_AGENT_ID, {"policy": {"default_models": {"claude": "claude-sonnet-4-6"}}})

    assert not [error for error in manager.publish_checks(_AGENT_ID)["errors"] if "unknown providers" in error]
