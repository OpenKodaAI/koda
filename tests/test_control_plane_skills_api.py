from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest
from aiohttp import web

from koda.control_plane import api as control_plane_api
from koda.control_plane.operator_auth import OperatorAuthContext


class _JsonRequest:
    def __init__(
        self,
        payload: dict[str, Any] | None = None,
        *,
        match_info: dict[str, str] | None = None,
    ) -> None:
        self.match_info = match_info or {"agent_id": "KODA", "package_id": "safe_pack"}
        self.query: dict[str, str] = {}
        self._payload = payload or {}
        self.headers: dict[str, str] = {}
        self.can_read_body = True
        self._state: dict[str, Any] = {}

    async def json(self) -> dict[str, Any]:
        return self._payload

    def get(self, key: str, default: Any = None) -> Any:
        return self._state.get(key, default)

    def __setitem__(self, key: str, value: Any) -> None:
        self._state[key] = value


def test_skill_registry_and_eval_routes_are_registered() -> None:
    app = web.Application()
    control_plane_api.setup_control_plane_routes(app)

    routes = {(route.method, route.resource.canonical) for route in app.router.routes()}

    assert ("GET", "/api/control-plane/agents/{agent_id}/skills/registry") in routes
    assert (
        "POST",
        "/api/control-plane/agents/{agent_id}/skills/packages/{package_id}/evals/run",
    ) in routes


@pytest.mark.asyncio
async def test_skill_eval_run_route_returns_skill_eval_payload() -> None:
    expected = {
        "ok": True,
        "schema_version": "skill_eval.v1",
        "package_id": "safe_pack",
        "recommendation_status": "recommended",
    }
    request = _JsonRequest(match_info={"agent_id": "KODA", "package_id": "safe_pack"})

    with patch("koda.skills._package.run_skill_package_evals", return_value=expected) as runner:
        response = await control_plane_api.run_skill_package_evals_route(request)

    assert response.status == 201
    assert json.loads(response.text)["schema_version"] == "skill_eval.v1"
    runner.assert_called_once_with("KODA", "safe_pack")


def _operator_context() -> OperatorAuthContext:
    return OperatorAuthContext(
        auth_kind="session",
        subject_type="operator",
        user_id="user-1",
        username="owner",
        email="owner@example.com",
        display_name="Owner",
    )


def _write_review_required_package(root: Path) -> Path:
    package_dir = root / "net_pack"
    package_dir.mkdir()
    (package_dir / "koda-skill.yaml").write_text(
        """
schema_version: koda_skill.v1
id: net_pack
name: Net Pack
version: 1.0.0
description: Package that asks for network access.
author: Koda Tests
permissions:
  network: true
skills:
  - id: net_review
    name: Net Review
    instruction: Check the network notes.
    content: Read the network notes before you call anything.
""".strip(),
        encoding="utf-8",
    )
    return package_dir


@pytest.fixture
def _isolated_packages(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    from koda.services import tool_registry
    from koda.skills import _package

    monkeypatch.setattr(_package, "STATE_ROOT_DIR", tmp_path / "state")
    monkeypatch.setattr(_package, "_primary_backend", lambda _agent_id: None)
    tool_registry._DEFAULT_REGISTRY_CACHE.clear()
    yield
    tool_registry._DEFAULT_REGISTRY_CACHE.clear()


@pytest.mark.asyncio
@pytest.mark.usefixtures("_isolated_packages")
async def test_operator_install_route_accepts_a_review_bound_to_the_package_hash(tmp_path: Path) -> None:
    from koda.skills._package import get_skill_package_lock, scan_skill_package

    package_dir = _write_review_required_package(tmp_path)
    scan = scan_skill_package(package_dir, agent_id="KODA")
    assert scan.decision == "review_required"
    request = _JsonRequest(
        {
            "path": str(package_dir),
            "review_accepted": True,
            "review_note": "Network access is expected for this agent.",
            "package_hash": scan.package_hash,
        },
        match_info={"agent_id": "KODA"},
    )
    request["operator_auth"] = _operator_context()

    response = await control_plane_api.install_skill_package_route(request)

    assert response.status == 201, response.text
    review = json.loads(response.text)["lock"]["operator_review"]
    assert review["accepted"] is True
    assert review["package_hash"] == scan.package_hash
    assert review["scanner_version"] == scan.scanner_version
    assert review["reviewer"] == "owner"
    stored = get_skill_package_lock("KODA", "net_pack")
    assert stored is not None and stored["operator_review"]["package_hash"] == scan.package_hash


@pytest.mark.asyncio
@pytest.mark.usefixtures("_isolated_packages")
async def test_operator_install_route_refuses_a_review_of_another_package_hash(tmp_path: Path) -> None:
    from koda.skills._package import get_skill_package_lock, scan_skill_package

    package_dir = _write_review_required_package(tmp_path)
    reviewed_hash = scan_skill_package(package_dir, agent_id="KODA").package_hash
    # The files change after the operator saw the scan.
    (package_dir / "notes.md").write_text("added after review", encoding="utf-8")
    request = _JsonRequest(
        {
            "path": str(package_dir),
            "review_accepted": True,
            "review_note": "Network access is expected for this agent.",
            "package_hash": reviewed_hash,
        },
        match_info={"agent_id": "KODA"},
    )
    request["operator_auth"] = _operator_context()

    response = await control_plane_api.install_skill_package_route(request)

    assert response.status == 409
    assert json.loads(response.text)["error"]["code"] == "skill.review_hash_mismatch"
    assert get_skill_package_lock("KODA", "net_pack") is None


@pytest.mark.asyncio
async def test_rollback_route_answers_409_for_a_revision_whose_files_changed() -> None:
    from koda.skills._package import SkillPackageError

    error = SkillPackageError(
        "skill.package_modified",
        "Package 'safe_pack' version 1.0.0 cannot be rolled back.",
        category="non_retryable",
        user_action="Reinstall the package version you want from its source, and review it again.",
    )
    request = _JsonRequest(match_info={"agent_id": "KODA", "package_id": "safe_pack"})

    with patch("koda.skills._package.rollback_skill_package", side_effect=error):
        response = await control_plane_api.rollback_skill_package_route(request)

    assert response.status == 409
    assert json.loads(response.text)["error"]["code"] == "skill.package_modified"
