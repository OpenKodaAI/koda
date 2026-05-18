"""Tests for KodaSkill package scan, install, provenance, and rollback."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest

from koda.services.tool_registry import get_default_tool_registry
from koda.skills._package import (
    SkillPackageError,
    get_installed_package_skills,
    get_skill_package_lock,
    install_skill_package,
    list_skill_package_locks,
    rollback_skill_package,
    scan_skill_package,
    uninstall_skill_package,
)


def _write_safe_package(root: Path, *, version: str = "1.0.0", skill_body: str = "Read carefully.") -> Path:
    package_dir = root / "safe_pack"
    (package_dir / "skills").mkdir(parents=True, exist_ok=True)
    (package_dir / "skills" / "review.md").write_text(skill_body, encoding="utf-8")
    (package_dir / "handlers.py").write_text(
        """
async def read_notes(params, ctx):
    from koda.services.tool_dispatcher import AgentToolResult

    return AgentToolResult(tool="safe_notes", success=True, output="safe")
""".strip(),
        encoding="utf-8",
    )
    (package_dir / "koda-skill.yaml").write_text(
        f"""
schema_version: koda_skill.v1
id: safe_pack
name: Safe Pack
version: {version}
description: Safe local package for tests.
author: Koda Tests
permissions:
  filesystem:
    read:
      - skills
skills:
  - id: safe_review
    name: Safe Review
    instruction: Use the safe review checklist.
    content_path: skills/review.md
    aliases: [review]
    tags: [tests]
tools:
  - id: safe_notes
    title: Safe Notes
    category: skill_package
    description: Read local test notes.
    handler: handlers.read_notes
    access_level: read
    risk_class: read_context
    idempotency: read_only
    approval_default: allow
    timeout_seconds: 10
    args_schema:
      type: object
      properties:
        query:
          type: string
      required: []
      additionalProperties: false
""".strip(),
        encoding="utf-8",
    )
    return package_dir


@pytest.fixture(autouse=True)
def _isolated_skill_package_state(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    from koda.services import tool_registry
    from koda.skills import _package

    monkeypatch.setattr(_package, "STATE_ROOT_DIR", tmp_path / "state")
    monkeypatch.setattr(_package, "_primary_backend", lambda _agent_id: None)
    monkeypatch.setattr("koda.config.AGENT_ID", "ATLAS")
    monkeypatch.setattr(_package, "AGENT_ID", "ATLAS")
    tool_registry._DEFAULT_REGISTRY_CACHE.clear()
    yield
    tool_registry._DEFAULT_REGISTRY_CACHE.clear()


def test_scan_allows_safe_koda_skill_package(tmp_path: Path) -> None:
    package_dir = _write_safe_package(tmp_path)

    scan = scan_skill_package(package_dir, agent_id="ATLAS")

    assert scan.decision == "allow"
    assert scan.package.id == "safe_pack"
    assert scan.package.skills[0]["content"] == "Read carefully."
    assert scan.package.tools[0]["id"] == "safe_notes"
    assert "read_context" in scan.risk_classes
    assert scan.package_hash
    assert "koda-skill.yaml" in scan.file_hashes


def test_scan_denies_dangerous_python_and_unknown_risk(tmp_path: Path) -> None:
    package_dir = _write_safe_package(tmp_path)
    (package_dir / "handlers.py").write_text(
        "import subprocess\n\nasync def read_notes(params, ctx):\n    return None\n",
        encoding="utf-8",
    )
    manifest = package_dir / "koda-skill.yaml"
    manifest.write_text(
        manifest.read_text(encoding="utf-8").replace("risk_class: read_context", "risk_class: unknown"),
        encoding="utf-8",
    )

    scan = scan_skill_package(package_dir, agent_id="ATLAS")

    assert scan.decision == "deny"
    finding_ids = {finding.id for finding in scan.findings}
    assert "python.dangerous_import" in finding_ids
    assert "tool.risk.unknown" in finding_ids


def test_install_uninstall_and_runtime_skill_merge_use_lock_fallback(tmp_path: Path) -> None:
    package_dir = _write_safe_package(tmp_path)

    result = install_skill_package(package_dir, agent_id="ATLAS")

    lock = result["lock"]
    assert lock["schema_version"] == "skill_lock.v1"
    assert lock["manifest"]["schema_version"] == "koda_skill.v1"
    assert lock["installed_skills"][0]["source_package_id"] == "safe_pack"
    assert get_skill_package_lock("ATLAS", "safe_pack")["package_id"] == "safe_pack"
    assert list_skill_package_locks("ATLAS")[0]["package_id"] == "safe_pack"
    assert get_installed_package_skills("ATLAS")[0]["id"] == "safe_review"

    uninstall_skill_package("ATLAS", "safe_pack")

    assert list_skill_package_locks("ATLAS") == []


def test_reinstall_same_package_creates_rollback_revision_without_tool_conflict(tmp_path: Path) -> None:
    package_dir = _write_safe_package(tmp_path, version="1.0.0", skill_body="First body.")
    install_skill_package(package_dir, agent_id="ATLAS")
    package_dir = _write_safe_package(tmp_path, version="1.1.0", skill_body="Second body.")

    install_skill_package(package_dir, agent_id="ATLAS")
    current = get_skill_package_lock("ATLAS", "safe_pack")

    assert current["version"] == "1.1.0"
    assert current["previous_revision"]["version"] == "1.0.0"

    rolled_back = rollback_skill_package("ATLAS", "safe_pack")["lock"]

    assert rolled_back["version"] == "1.0.0"
    assert rolled_back["previous_revision"]["version"] == "1.1.0"


def test_tool_registry_includes_installed_package_tools(tmp_path: Path) -> None:
    from koda.agent_contract import resolve_integration_action

    package_dir = _write_safe_package(tmp_path)
    install_skill_package(package_dir, agent_id="ATLAS")

    registry = get_default_tool_registry(feature_flags={"plugins": True}, allowed_tool_ids={"safe_notes"})
    definition = registry.require("safe_notes")

    assert definition.source == "skill_package"
    assert definition.access_level == "read"
    assert definition.risk_class == "read_context"
    assert definition.ui_metadata["source_package_id"] == "safe_pack"
    resolution = resolve_integration_action("safe_notes", {})
    assert resolution.integration_id == "skill_package:safe_pack"
    assert resolution.access_level == "read"
    assert resolution.risk_class == "read_context"


def test_install_rejects_denied_scan(tmp_path: Path) -> None:
    package_dir = _write_safe_package(tmp_path)
    (package_dir / "postinstall.sh").write_text("echo no", encoding="utf-8")

    with pytest.raises(SkillPackageError) as exc:
        install_skill_package(package_dir, agent_id="ATLAS")

    assert exc.value.error["code"] == "skill.scan_denied"
