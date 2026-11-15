"""Helpers for the public control-plane onboarding surface."""

from __future__ import annotations

import json
from typing import Any, cast

from .settings import ROOT_DIR

_OPENAPI_PATH = ROOT_DIR / "docs" / "openapi" / "control-plane.json"


def load_control_plane_openapi_spec() -> dict[str, Any]:
    """Load the maintained public OpenAPI description for onboarding/control-plane APIs."""
    payload = json.loads(_OPENAPI_PATH.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("control-plane OpenAPI document must be a JSON object")
    return cast(dict[str, Any], payload)
