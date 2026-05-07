"""Tests for the PR dependency review helper used by the security workflow."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = ROOT / "scripts" / "review_dependency_changes.py"


def load_module() -> ModuleType:
    spec = importlib.util.spec_from_file_location("review_dependency_changes", SCRIPT_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_python_dependency_review_blocks_direct_url_sources() -> None:
    module = load_module()
    old_snapshot = module.parse_python_snapshot(
        """
        [project]
        dependencies = ["requests>=2"]
        """
    )
    new_snapshot = module.parse_python_snapshot(
        """
        [project]
        dependencies = ["requests>=2", "evil @ https://example.com/evil.whl"]
        """
    )

    failures = module.python_dependency_change_details(old_snapshot, new_snapshot)

    assert failures == ["project dependency: evil @ https://example.com/evil.whl"]


def test_python_dependency_review_blocks_uv_path_sources() -> None:
    module = load_module()
    old_snapshot = module.parse_python_snapshot(
        """
        [project]
        dependencies = ["requests>=2"]
        """
    )
    new_snapshot = module.parse_python_snapshot(
        """
        [project]
        dependencies = ["requests>=2"]

        [tool.uv.sources]
        localpkg = { path = "../localpkg" }
        """
    )

    failures = module.python_dependency_change_details(old_snapshot, new_snapshot)

    assert failures == ['tool.uv.sources.localpkg: {"path":"../localpkg"}']


def test_node_dependency_review_ignores_non_dependency_package_json_changes() -> None:
    module = load_module()
    old_snapshot = module.parse_node_snapshot(
        """
        {"name":"koda-web","scripts":{"dev":"next dev"},"dependencies":{"next":"16.1.7"}}
        """
    )
    new_snapshot = module.parse_node_snapshot(
        """
        {"name":"koda-web","scripts":{"dev":"next dev","build":"next build"},"dependencies":{"next":"16.1.7"}}
        """
    )

    failures = module.node_dependency_change_details(old_snapshot, new_snapshot, Path("apps/web/package.json"))

    assert failures == []
    assert old_snapshot == new_snapshot


def test_node_dependency_review_blocks_git_sources() -> None:
    module = load_module()
    old_snapshot = module.parse_node_snapshot("""{"dependencies":{"react":"19.2.3"}}""")
    new_snapshot = module.parse_node_snapshot(
        """{"dependencies":{"react":"19.2.3","bad-lib":"github:someone/bad-lib#main"}}"""
    )

    failures = module.node_dependency_change_details(old_snapshot, new_snapshot, Path("apps/web/package.json"))

    assert failures == ["apps/web/package.json::dependencies.bad-lib -> github:someone/bad-lib#main"]


def test_cargo_dependency_review_allows_internal_workspace_paths_only() -> None:
    module = load_module()
    old_snapshot = module.parse_cargo_snapshot(
        """
        [dependencies]
        anyhow = "1"
        """
    )
    new_snapshot = module.parse_cargo_snapshot(
        """
        [dependencies]
        anyhow = "1"
        koda-proto = { path = "../koda-proto" }
        """
    )

    failures = module.cargo_dependency_change_details(
        old_snapshot,
        new_snapshot,
        Path("rust/koda-runtime-kernel/Cargo.toml"),
    )

    assert failures == []


def test_cargo_dependency_review_blocks_git_sources() -> None:
    module = load_module()
    old_snapshot = module.parse_cargo_snapshot(
        """
        [dependencies]
        anyhow = "1"
        """
    )
    new_snapshot = module.parse_cargo_snapshot(
        """
        [dependencies]
        anyhow = "1"
        suspicious = { git = "https://github.com/example/suspicious", rev = "1234" }
        """
    )

    failures = module.cargo_dependency_change_details(
        old_snapshot,
        new_snapshot,
        Path("rust/koda-runtime-kernel/Cargo.toml"),
    )

    assert failures == ["rust/koda-runtime-kernel/Cargo.toml::dependencies.suspicious uses git source"]


def test_lockfile_requirements_trigger_only_for_dependency_semantic_changes() -> None:
    module = load_module()

    failures = module.lockfile_requirements(
        {Path("apps/web/package.json"), Path("README.md")},
        changed_python=False,
        changed_node_manifests=[Path("apps/web/package.json")],
        changed_cargo_manifests=[],
    )

    assert failures == ["apps/web/package.json changed dependency inputs but pnpm-lock.yaml was not updated"]


def test_lockfile_requirements_allow_unrelated_manifest_edits() -> None:
    module = load_module()

    failures = module.lockfile_requirements(
        {Path("README.md")},
        changed_python=False,
        changed_node_manifests=[],
        changed_cargo_manifests=[],
    )

    assert failures == []
