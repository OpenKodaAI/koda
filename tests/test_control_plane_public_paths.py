"""The dashboard, the control plane and the OpenAPI agree on which API paths skip the operator session."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from koda.control_plane import api as control_plane_api
from koda.control_plane.onboarding import load_control_plane_openapi_spec

ROOT = Path(__file__).resolve().parents[1]
WEB_PUBLIC_PATHS = ROOT / "apps" / "web" / "src" / "lib" / "public-control-plane-paths.ts"
BACKEND_PUBLIC_PATHS = set(control_plane_api._PUBLIC_CONTROL_PLANE_API_PATHS)


def _web_public_paths() -> set[str]:
    return set(re.findall(r'"(/api/control-plane/[^"]*)"', WEB_PUBLIC_PATHS.read_text(encoding="utf-8")))


def _operations(path: str) -> dict[str, dict[str, Any]]:
    spec = load_control_plane_openapi_spec()
    return {method: operation for method, operation in spec["paths"][path].items() if isinstance(operation, dict)}


def _effective_security(operation: dict[str, Any]) -> list[dict[str, Any]]:
    return list(operation.get("security", load_control_plane_openapi_spec()["security"]))


def test_dashboard_and_control_plane_share_one_public_path_list() -> None:
    assert _web_public_paths() == BACKEND_PUBLIC_PATHS


def test_onboarding_readiness_needs_an_operator_session_everywhere() -> None:
    path = "/api/control-plane/onboarding/readiness"

    assert not control_plane_api._is_public_control_plane_api_path(path)
    assert path not in _web_public_paths()
    for operation in _operations(path).values():
        assert _effective_security(operation) == [{"bearerAuth": []}]


def test_openapi_lets_every_public_path_through_without_a_token() -> None:
    for path in BACKEND_PUBLIC_PATHS:
        for operation in _operations(path).values():
            security = _effective_security(operation)
            assert security == [] or {} in security, path


def test_openapi_marks_the_onboarding_status_bearer_as_optional() -> None:
    operation = _operations("/api/control-plane/onboarding/status")["get"]

    assert operation["security"] == [{}, {"bearerAuth": []}]
    public_shape = operation["responses"]["200"]["content"]["application/json"]["schema"]["anyOf"][0]
    assert set(public_shape["properties"]) == {"has_owner", "bootstrap_required"}
    assert public_shape["additionalProperties"] is False


def test_public_paths_match_exactly_so_a_new_subroute_needs_a_session() -> None:
    """Prefix matching would make any route added under a public path public by accident."""
    for path in BACKEND_PUBLIC_PATHS:
        assert control_plane_api._is_public_control_plane_api_path(path)
        assert not control_plane_api._is_public_control_plane_api_path(f"{path}/")
        assert not control_plane_api._is_public_control_plane_api_path(f"{path}/anything")
