"""Tests write Koda state into the session's own STATE_ROOT_DIR, never into the real ~/.koda-state (D-265).

tests/conftest.py points STATE_ROOT_DIR at a per-session directory before koda is imported, and
its session_state_root fixture fails the run if any loaded koda module still points into the
real one. These tests pin the paths that modules derive from STATE_ROOT_DIR at import, and that
the startup import of the retired approval JSON files (whose leak of user 111 / agent-a grants
showed the problem) reads them from the session directory.
"""

from __future__ import annotations

import importlib
from pathlib import Path

import pytest

# Read at collection, before the per-test HOME isolation: the home of whoever runs the suite.
_REAL_STATE_ROOT = Path.home() / ".koda-state"

# (module, attribute) of every path a module derives from STATE_ROOT_DIR when it is imported.
_STATE_PATHS = (
    ("koda.config", "STATE_ROOT_DIR"),
    ("koda.control_plane.settings", "STATE_ROOT_DIR"),
    ("koda.control_plane.settings", "CONTROL_PLANE_MASTER_KEY_FILE"),
    ("koda.control_plane.settings", "CONTROL_PLANE_MASTER_KEY_PREVIOUS_FILE"),
    ("koda.control_plane.bootstrap_file", "_BOOTSTRAP_FILE_PATH"),
    ("koda.services.kokoro_manager", "_STATE_ROOT_DIR"),
    ("koda.services.supertonic_manager", "_STATE_ROOT_DIR"),
    ("koda.knowledge.config", "KNOWLEDGE_V2_OBJECT_STORE_ROOT"),
    ("koda.utils.workdir", "STATE_ROOT_DIR"),
)


@pytest.mark.parametrize(("module", "attr"), _STATE_PATHS)
def test_state_path_is_outside_the_real_state_dir(module: str, attr: str) -> None:
    path = Path(getattr(importlib.import_module(module), attr))
    assert not path.is_relative_to(_REAL_STATE_ROOT), f"{module}.{attr} = {path}"


def test_the_approval_json_import_reads_the_session_state_root(session_state_root: Path) -> None:
    from koda import config
    from koda.state import approval_import

    assert session_state_root == config.STATE_ROOT_DIR
    for path in approval_import._json_files():
        assert path.parent == session_state_root, path
