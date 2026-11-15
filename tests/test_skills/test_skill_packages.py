"""Tests for KodaSkill package scan, install, provenance, and rollback."""

from __future__ import annotations

import hashlib
import sys
from collections.abc import Iterator
from pathlib import Path

import pytest

from koda.services.tool_registry import ToolRegistryError, get_default_tool_registry
from koda.skills._package import (
    SkillPackageError,
    ensure_installed_package_tools_registered,
    get_installed_package_skills,
    get_skill_package_lock,
    install_skill_package,
    list_skill_package_locks,
    list_skill_registry,
    rollback_skill_package,
    run_skill_package_evals,
    scan_skill_package,
    uninstall_skill_package,
)


def _write_safe_package(
    root: Path,
    *,
    version: str = "1.0.0",
    skill_body: str = "Read carefully.",
    eval_block: str = "",
) -> Path:
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
{eval_block}
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
    from koda.services.metrics import SKILL_PACKAGE_EVENTS

    metric_child = SKILL_PACKAGE_EVENTS.labels(
        agent_id="ATLAS",
        event="install",
        decision="allow",
        recommendation_status="unreviewed",
    )
    before = float(metric_child._value.get()) if hasattr(metric_child, "_value") else 0.0
    package_dir = _write_safe_package(tmp_path)

    result = install_skill_package(package_dir, agent_id="ATLAS")

    lock = result["lock"]
    assert lock["schema_version"] == "skill_lock.v1"
    assert lock["manifest"]["schema_version"] == "koda_skill.v1"
    assert lock["installed_skills"][0]["source_package_id"] == "safe_pack"
    assert lock["recommendation_status"] == "unreviewed"
    assert lock["skill_evals"] == []
    assert lock["trust_summary"]["recommended"] is False
    assert lock["run_graph_evidence"]["node_type"] == "runtime_event"
    assert get_skill_package_lock("ATLAS", "safe_pack")["package_id"] == "safe_pack"
    assert list_skill_package_locks("ATLAS")[0]["package_id"] == "safe_pack"
    assert get_installed_package_skills("ATLAS")[0]["id"] == "safe_review"

    uninstall_skill_package("ATLAS", "safe_pack")

    assert list_skill_package_locks("ATLAS") == []
    after = float(metric_child._value.get()) if hasattr(metric_child, "_value") else 0.0
    if after > before:
        assert after == before + 1


def test_manifest_evals_are_normalized_evaluated_and_gate_recommendation(tmp_path: Path) -> None:
    eval_block = """
tests:
  evals:
    - id: safe-pack-required
      required: true
      case:
        schema_version: eval_case.v1
        case_key: skill:safe_pack:required
        metadata:
          expected_tool_ids: [safe_notes]
          source_tool_ids: [safe_notes]
          expected_policy_codes: []
          source_policy_codes: []
          source_status: completed
          source_replay_mode: offline
evals:
  - id: safe-pack-optional
    required: false
    case:
      schema_version: eval_case.v1
      case_key: skill:safe_pack:optional
      metadata:
        expected_tool_ids: []
        source_tool_ids: []
        source_status: completed
        source_replay_mode: offline
"""
    package_dir = _write_safe_package(tmp_path, eval_block=eval_block)

    result = install_skill_package(package_dir, agent_id="ATLAS")

    lock = result["lock"]
    assert [item["schema_version"] for item in lock["skill_evals"]] == ["skill_eval.v1", "skill_eval.v1"]
    assert lock["skill_evals"][0]["result"]["status"] == "passed"
    assert lock["eval_summary"]["required_passed_all"] is True
    assert lock["recommendation_status"] == "recommended"
    registry = list_skill_registry("ATLAS")
    assert registry["schema_version"] == "skill_registry.v1"
    assert registry["items"][0]["recommendation_status"] == "recommended"
    assert registry["items"][0]["run_graph_evidence"]["node_type"] == "runtime_event"


def test_required_eval_failure_prevents_recommendation_and_run_updates_lock(tmp_path: Path) -> None:
    eval_block = """
tests:
  evals:
    - id: safe-pack-required
      required: true
      case:
        schema_version: eval_case.v1
        case_key: skill:safe_pack:required
        metadata:
          expected_tool_ids: [safe_notes]
          source_tool_ids: []
          source_status: completed
          source_replay_mode: offline
"""
    package_dir = _write_safe_package(tmp_path, eval_block=eval_block)
    install_skill_package(package_dir, agent_id="ATLAS")

    result = run_skill_package_evals("ATLAS", "safe_pack")

    assert result["schema_version"] == "skill_eval.v1"
    assert result["skill_evals"][0]["result"]["status"] == "failed"
    assert result["recommendation_status"] == "eval_failed"
    assert get_skill_package_lock("ATLAS", "safe_pack")["recommendation_status"] == "eval_failed"


def test_reinstall_same_package_creates_rollback_revision_without_tool_conflict(tmp_path: Path) -> None:
    package_dir = _write_safe_package(tmp_path / "v1", version="1.0.0", skill_body="First body.")
    install_skill_package(package_dir, agent_id="ATLAS")
    package_dir = _write_safe_package(tmp_path / "v2", version="1.1.0", skill_body="Second body.")

    install_skill_package(package_dir, agent_id="ATLAS")
    current = get_skill_package_lock("ATLAS", "safe_pack")

    assert current["version"] == "1.1.0"
    assert current["previous_revision"]["version"] == "1.0.0"

    rolled_back = rollback_skill_package("ATLAS", "safe_pack")["lock"]

    assert rolled_back["version"] == "1.0.0"
    assert rolled_back["previous_revision"]["version"] == "1.1.0"
    assert rolled_back["run_graph_evidence"]["payload"]["event_type"] == "skill_package.rollback"


def test_rollback_refuses_a_revision_whose_files_no_longer_match_and_asks_for_a_reinstall(tmp_path: Path) -> None:
    """D-037: a rollback swaps lock metadata only, so the files on disk must still be the approved ones."""
    package_dir = _write_safe_package(tmp_path, version="1.0.0", skill_body="First body.")
    install_skill_package(package_dir, agent_id="ATLAS")
    # The update overwrites the same directory, so the 1.0.0 files are gone.
    _write_safe_package(tmp_path, version="1.1.0", skill_body="Second body.")
    install_skill_package(package_dir, agent_id="ATLAS")

    with pytest.raises(SkillPackageError) as exc:
        rollback_skill_package("ATLAS", "safe_pack")

    assert exc.value.error["code"] == "skill.package_modified"
    assert "reinstall" in exc.value.error["user_action"].lower()
    assert exc.value.error["integrity"]["status"] == "modified"
    assert get_skill_package_lock("ATLAS", "safe_pack")["version"] == "1.1.0"


@pytest.fixture
def plugin_registry(monkeypatch: pytest.MonkeyPatch) -> Iterator[object]:
    from koda import plugins
    from koda.plugins.registry import PluginRegistry
    from koda.skills import _package

    registry = PluginRegistry()
    monkeypatch.setattr(plugins, "get_registry", lambda: registry)
    monkeypatch.setattr(_package, "PLUGIN_SYSTEM_ENABLED", True)
    monkeypatch.setattr(_package, "_REGISTERED_PACKAGE_IDS", set())
    yield registry


def test_untouched_package_loads_and_a_package_changed_after_approval_refuses_to_load(
    tmp_path: Path, plugin_registry: object
) -> None:
    """D-037: package code loads only while its files hash to the approved package_hash."""
    from koda.plugins.registry import PluginRegistry
    from koda.skills import _package

    assert isinstance(plugin_registry, PluginRegistry)
    package_dir = _write_safe_package(tmp_path)
    lock = install_skill_package(package_dir, agent_id="ATLAS")["lock"]

    assert plugin_registry.get_handler("safe_notes") is not None
    # Loading again (a restart or a reload) still matches: loading wrote nothing into the package.
    refused = ensure_installed_package_tools_registered("ATLAS", force=True)
    assert plugin_registry.get_handler("safe_notes") is not None
    assert refused == {}
    assert list_skill_registry("ATLAS")["items"][0]["integrity"]["status"] == "verified"

    (package_dir / "handlers.py").write_text(
        (package_dir / "handlers.py").read_text(encoding="utf-8") + "\n# changed after approval\n",
        encoding="utf-8",
    )
    refused = ensure_installed_package_tools_registered("ATLAS", force=True)

    assert plugin_registry.get_handler("safe_notes") is None
    assert refused["safe_pack"]["status"] == "modified"
    assert refused["safe_pack"]["approved_package_hash"] == lock["package_hash"]
    assert refused["safe_pack"]["current_package_hash"] != lock["package_hash"]
    assert list_skill_registry("ATLAS")["items"][0]["integrity"]["status"] == "modified"

    # A fresh process does not load it either.
    _package._REGISTERED_PACKAGE_IDS.clear()
    refused = ensure_installed_package_tools_registered("ATLAS")
    assert plugin_registry.get_handler("safe_notes") is None
    assert "safe_pack" in refused


def test_unregister_removes_the_handler_modules_of_a_package_whose_directory_name_is_not_its_id(
    tmp_path: Path, plugin_registry: object
) -> None:
    """D-291: the handler modules are named and removed by the same prefix, from the package id."""
    from koda.plugins.registry import PluginRegistry

    assert isinstance(plugin_registry, PluginRegistry)
    package_dir = _write_safe_package(tmp_path).rename(tmp_path / "checkout_of_safe_pack")
    install_skill_package(package_dir, agent_id="ATLAS")
    root = str(package_dir.resolve())

    def package_modules() -> list[str]:
        return [
            name
            for name, module in list(sys.modules.items())
            if str(getattr(module, "__file__", "") or "").startswith(root)
        ]

    assert package_modules()

    assert plugin_registry.unregister("safe_pack") is None

    assert package_modules() == []


def test_files_pushed_past_the_file_budget_do_not_hide_a_change(tmp_path: Path, plugin_registry: object) -> None:
    """Files the hash cannot cover (beyond the scanner's file budget) count as a change."""
    from koda.plugins.registry import PluginRegistry

    assert isinstance(plugin_registry, PluginRegistry)
    package_dir = _write_safe_package(tmp_path)
    install_skill_package(package_dir, agent_id="ATLAS")
    # 198 cache entries sort before the 3 approved files, so a new file after them is past the budget.
    cache = package_dir / "__pycache__"
    cache.mkdir(exist_ok=True)
    for index in range(198):
        (cache / f"filler{index:03}.{sys.implementation.cache_tag}.pyc").write_bytes(b"")
    (package_dir / "zz_shadow.py").write_text("print('outside the hash')\n", encoding="utf-8")

    refused = ensure_installed_package_tools_registered("ATLAS", force=True)

    assert plugin_registry.get_handler("safe_notes") is None
    assert refused["safe_pack"]["status"] == "modified"


def test_package_code_loads_from_source_never_from_a_planted_bytecode_cache(
    tmp_path: Path, plugin_registry: object
) -> None:
    """Bytecode caches are not part of the package hash, so they must never be what runs."""
    import importlib.util
    import py_compile

    from koda.plugins.registry import PluginRegistry

    assert isinstance(plugin_registry, PluginRegistry)
    package_dir = _write_safe_package(tmp_path)
    install_skill_package(package_dir, agent_id="ATLAS")
    evil_source = tmp_path / "evil.py"
    evil_source.write_text("async def read_notes(params, ctx):\n    return 'evil'\n", encoding="utf-8")
    py_compile.compile(
        str(evil_source),
        cfile=importlib.util.cache_from_source(str(package_dir / "handlers.py")),
        invalidation_mode=py_compile.PycInvalidationMode.UNCHECKED_HASH,
    )

    refused = ensure_installed_package_tools_registered("ATLAS", force=True)

    handler = plugin_registry.get_handler("safe_notes")
    assert handler is not None
    assert "evil" not in handler.__code__.co_consts
    assert "safe" in handler.__code__.co_consts
    assert refused == {}


_LAZY_IMPORT_HANDLER = """
import sys
from pathlib import Path


async def read_notes(params, ctx):
    package_dir = str(Path(__file__).parent)
    sys.path.insert(0, package_dir)
    try:
        import safe_pack_notes
    finally:
        sys.path.remove(package_dir)
    from koda.services.tool_dispatcher import AgentToolResult

    return AgentToolResult(tool="safe_notes", success=True, output=safe_pack_notes.NOTES)
""".lstrip()


def test_a_module_package_code_imports_at_tool_call_time_never_loads_from_a_planted_cache(
    tmp_path: Path, plugin_registry: object
) -> None:
    """D-273: package modules load from source after registration too, when a handler imports them lazily."""
    import asyncio
    import importlib.util
    import py_compile

    from koda.plugins.registry import PluginRegistry

    assert isinstance(plugin_registry, PluginRegistry)
    package_dir = _write_safe_package(tmp_path)
    (package_dir / "handlers.py").write_text(_LAZY_IMPORT_HANDLER, encoding="utf-8")
    (package_dir / "safe_pack_notes.py").write_text('NOTES = "safe"\n', encoding="utf-8")
    install_skill_package(package_dir, agent_id="ATLAS")
    handler = plugin_registry.get_handler("safe_notes")
    assert handler is not None
    assert "safe_pack_notes" not in sys.modules

    # After registration, a cache is planted for the module the handler imports at call time.
    evil_source = tmp_path / "evil_notes.py"
    evil_source.write_text('NOTES = "evil"\n', encoding="utf-8")
    py_compile.compile(
        str(evil_source),
        cfile=importlib.util.cache_from_source(str(package_dir / "safe_pack_notes.py")),
        invalidation_mode=py_compile.PycInvalidationMode.UNCHECKED_HASH,
    )
    try:
        result = asyncio.run(handler({}, None))
    finally:
        sys.modules.pop("safe_pack_notes", None)

    assert result.output == "safe"


_BY_FILE_LOCATION_HANDLER = """
import importlib.machinery
import importlib.util
from pathlib import Path


async def read_notes(params, ctx):
    notes_path = str(Path(__file__).with_name("safe_pack_notes.py"))
    if params.get("route") == "loader":
        loader = importlib.machinery.SourceFileLoader("safe_pack_notes_by_loader", notes_path)
        spec = importlib.util.spec_from_loader(loader.name, loader)
    else:
        spec = importlib.util.spec_from_file_location("safe_pack_notes_by_file", notes_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    from koda.services.tool_dispatcher import AgentToolResult

    return AgentToolResult(tool="safe_notes", success=True, output=module.NOTES)
""".lstrip()


@pytest.mark.parametrize("route", ["spec_from_file_location", "loader"])
def test_a_module_package_code_loads_by_file_location_never_loads_from_a_planted_cache(
    tmp_path: Path, plugin_registry: object, route: str
) -> None:
    """D-273: a sibling loaded by file location, past the import system's finders, loads from source too."""
    import asyncio
    import importlib.util
    import py_compile

    from koda.plugins.registry import PluginRegistry

    assert isinstance(plugin_registry, PluginRegistry)
    package_dir = _write_safe_package(tmp_path)
    (package_dir / "handlers.py").write_text(_BY_FILE_LOCATION_HANDLER, encoding="utf-8")
    (package_dir / "safe_pack_notes.py").write_text('NOTES = "safe"\n', encoding="utf-8")
    install_skill_package(package_dir, agent_id="ATLAS")
    handler = plugin_registry.get_handler("safe_notes")
    assert handler is not None

    evil_source = tmp_path / "evil_notes.py"
    evil_source.write_text('NOTES = "evil"\n', encoding="utf-8")
    py_compile.compile(
        str(evil_source),
        cfile=importlib.util.cache_from_source(str(package_dir / "safe_pack_notes.py")),
        invalidation_mode=py_compile.PycInvalidationMode.UNCHECKED_HASH,
    )
    result = asyncio.run(handler({"route": route}, None))

    assert result.output == "safe"


def test_an_import_outside_every_package_searches_the_path_once_after_a_package_registers(
    tmp_path: Path, plugin_registry: object, monkeypatch: pytest.MonkeyPatch
) -> None:
    """D-273: keeping package code source-only adds no second path search to every other import."""
    import importlib.machinery

    install_skill_package(_write_safe_package(tmp_path), agent_id="ATLAS")
    real_find_spec = importlib.machinery.PathFinder.find_spec
    searches: list[str] = []

    def counting_find_spec(fullname: str, path: object = None, target: object = None) -> object:
        if fullname == "koda_no_such_module_d273":
            searches.append(fullname)
        return real_find_spec(fullname, path, target)  # type: ignore[arg-type]

    monkeypatch.setattr(importlib.machinery.PathFinder, "find_spec", counting_find_spec)
    with pytest.raises(ImportError):
        import koda_no_such_module_d273  # type: ignore[import-not-found]  # noqa: F401

    assert searches == ["koda_no_such_module_d273"]


def test_a_handler_rewritten_between_the_hash_and_the_load_runs_the_hashed_bytes(
    tmp_path: Path, plugin_registry: object, monkeypatch: pytest.MonkeyPatch
) -> None:
    """D-292: the handler runs from the bytes the integrity check hashed, not from a later read of the file."""
    from koda.plugins.registry import PluginRegistry
    from koda.skills import _package

    assert isinstance(plugin_registry, PluginRegistry)
    package_dir = _write_safe_package(tmp_path)
    install_skill_package(package_dir, agent_id="ATLAS")
    real_verify = _package.verify_skill_package_integrity

    def verify_then_rewrite(lock: dict, **kwargs: object) -> dict:
        integrity = real_verify(lock, **kwargs)  # type: ignore[arg-type]
        (package_dir / "handlers.py").write_text(_EVIL_HANDLER, encoding="utf-8")
        return integrity

    monkeypatch.setattr(_package, "verify_skill_package_integrity", verify_then_rewrite)
    refused = ensure_installed_package_tools_registered("ATLAS", force=True)

    assert refused == {}
    handler = plugin_registry.get_handler("safe_notes")
    assert handler is not None
    assert "evil" not in handler.__code__.co_consts
    assert "safe" in handler.__code__.co_consts


def test_a_module_changed_after_registration_runs_its_hashed_bytes_and_the_reload_reports_it_modified(
    tmp_path: Path, plugin_registry: object, monkeypatch: pytest.MonkeyPatch
) -> None:
    """D-292: a module package code imports at tool-call time loads from the hashed bytes; plugin_reload re-verifies."""
    import asyncio

    from koda.plugins.registry import PluginRegistry
    from koda.skills import _package

    assert isinstance(plugin_registry, PluginRegistry)
    audits: list[str] = []
    monkeypatch.setattr(_package, "_REPORTED_MODIFIED_PACKAGES", set())
    monkeypatch.setattr(_package, "_emit_package_audit", lambda event_type, *_args: audits.append(event_type))
    package_dir = _write_safe_package(tmp_path)
    (package_dir / "handlers.py").write_text(_LAZY_IMPORT_HANDLER, encoding="utf-8")
    (package_dir / "safe_pack_notes.py").write_text('NOTES = "safe"\n', encoding="utf-8")
    install_skill_package(package_dir, agent_id="ATLAS")
    handler = plugin_registry.get_handler("safe_notes")
    assert handler is not None

    (package_dir / "safe_pack_notes.py").write_text('NOTES = "changed after registration"\n', encoding="utf-8")
    # A tool call does not register the package again; what it imports is what was hashed.
    assert ensure_installed_package_tools_registered("ATLAS") == {}
    assert plugin_registry.get_handler("safe_notes") is handler
    try:
        result = asyncio.run(handler({}, None))
    finally:
        sys.modules.pop("safe_pack_notes", None)
    assert result.output == "safe"

    # plugin_reload registers it again, which verifies the files first.
    refused = ensure_installed_package_tools_registered("ATLAS", force=True)

    assert refused["safe_pack"]["status"] == "modified"
    assert "skill_package.modified" in audits
    assert plugin_registry.get_handler("safe_notes") is None


def test_a_module_added_to_a_package_after_registration_is_refused_at_tool_call_time(
    tmp_path: Path, plugin_registry: object
) -> None:
    """D-292: a package file that was not hashed never loads, even after the package registered."""
    import asyncio

    from koda.plugins.registry import PluginRegistry

    assert isinstance(plugin_registry, PluginRegistry)
    package_dir = _write_safe_package(tmp_path)
    (package_dir / "handlers.py").write_text(_LAZY_IMPORT_HANDLER, encoding="utf-8")
    install_skill_package(package_dir, agent_id="ATLAS")
    handler = plugin_registry.get_handler("safe_notes")
    assert handler is not None

    (package_dir / "safe_pack_notes.py").write_text('NOTES = "added after registration"\n', encoding="utf-8")
    try:
        with pytest.raises(ImportError, match="not a verified file"):
            asyncio.run(handler({}, None))
    finally:
        sys.modules.pop("safe_pack_notes", None)


_EXTENSION_MODULE = getattr(__import__("zlib"), "__file__", None)


@pytest.mark.parametrize("kind", ["bytecode", "extension"])
def test_a_compiled_module_in_a_package_is_refused_at_tool_call_time(
    tmp_path: Path, plugin_registry: object, kind: str
) -> None:
    """D-292: a compiled module is read from disk when it loads, after the check, so package code never loads one."""
    import asyncio
    import py_compile

    from koda.plugins.registry import PluginRegistry

    assert isinstance(plugin_registry, PluginRegistry)
    package_dir = _write_safe_package(tmp_path)
    if kind == "bytecode":
        (package_dir / "handlers.py").write_text(_LAZY_IMPORT_HANDLER, encoding="utf-8")
        notes_source = tmp_path / "notes_source.py"
        notes_source.write_text('NOTES = "compiled"\n', encoding="utf-8")
        py_compile.compile(str(notes_source), cfile=str(package_dir / "safe_pack_notes.pyc"))
    else:
        if _EXTENSION_MODULE is None:
            pytest.skip("zlib is built into this interpreter")
        extension = package_dir / Path(_EXTENSION_MODULE).name
        extension.write_bytes(Path(_EXTENSION_MODULE).read_bytes())
        (package_dir / "handlers.py").write_text(
            "import importlib.util\nfrom pathlib import Path\n\n\n"
            "async def read_notes(params, ctx):\n"
            f"    path = Path(__file__).with_name({extension.name!r})\n"
            '    spec = importlib.util.spec_from_file_location("zlib", path)\n'
            "    return importlib.util.module_from_spec(spec)\n",
            encoding="utf-8",
        )
    install_skill_package(package_dir, agent_id="ATLAS")
    handler = plugin_registry.get_handler("safe_notes")
    assert handler is not None

    try:
        with pytest.raises(ImportError, match="verified .py sources only"):
            asyncio.run(handler({}, None))
    finally:
        sys.modules.pop("safe_pack_notes", None)


def test_the_registry_does_not_reload_a_skill_package_from_its_files(tmp_path: Path, plugin_registry: object) -> None:
    """D-292: a skill package registers again only through the lock, which verifies its files first."""
    from koda.plugins.registry import PluginRegistry

    assert isinstance(plugin_registry, PluginRegistry)
    package_dir = _write_safe_package(tmp_path)
    (package_dir / "koda-skill.yaml").unlink()
    (package_dir / "plugin.yaml").write_text(
        "name: safe_pack\nversion: 1.0.0\ntools:\n  - id: safe_notes\n    handler: handlers.read_notes\n"
        "    read_only: true\n",
        encoding="utf-8",
    )
    install_skill_package(package_dir, agent_id="ATLAS")
    assert plugin_registry.get_handler("safe_notes") is not None
    (package_dir / "handlers.py").write_text(
        "async def read_notes(params, ctx):\n    return 'changed after approval'\n", encoding="utf-8"
    )

    err = plugin_registry.reload("safe_pack")

    assert err is not None
    handler = plugin_registry.get_handler("safe_notes")
    assert handler is None or "changed after approval" not in handler.__code__.co_consts


_EVIL_HANDLER = """
async def read_notes(params, ctx):
    import subprocess

    subprocess.run(["echo", "evil"])
    return "evil"
""".lstrip()


def test_a_handler_under_pycache_is_hashed_and_a_change_to_it_refuses_to_load(
    tmp_path: Path, plugin_registry: object
) -> None:
    """D-037: a .py source in a __pycache__ directory is package code like any other, so the hash covers it."""
    from koda.plugins.registry import PluginRegistry

    assert isinstance(plugin_registry, PluginRegistry)
    package_dir = _write_safe_package(tmp_path)
    manifest = package_dir / "koda-skill.yaml"
    manifest.write_text(
        manifest.read_text(encoding="utf-8").replace(
            "handler: handlers.read_notes", "handler: __pycache__.tool.read_notes"
        ),
        encoding="utf-8",
    )
    (package_dir / "__pycache__").mkdir()
    (package_dir / "handlers.py").rename(package_dir / "__pycache__" / "tool.py")
    lock = install_skill_package(package_dir, agent_id="ATLAS")["lock"]
    assert plugin_registry.get_handler("safe_notes") is not None
    assert "__pycache__/tool.py" in scan_skill_package(package_dir, agent_id="ATLAS").file_hashes

    (package_dir / "__pycache__" / "tool.py").write_text(_EVIL_HANDLER, encoding="utf-8")
    refused = ensure_installed_package_tools_registered("ATLAS", force=True)

    assert plugin_registry.get_handler("safe_notes") is None
    assert refused["safe_pack"]["status"] == "modified"
    assert refused["safe_pack"]["current_package_hash"] != lock["package_hash"]
    assert list_skill_registry("ATLAS")["items"][0]["integrity"]["status"] == "modified"


def test_only_the_bytecode_cache_files_python_writes_are_left_out_of_the_hash(
    tmp_path: Path, plugin_registry: object
) -> None:
    """A cache file Python writes (<module>.<tag>[.opt-N].pyc) is left out; any other file under __pycache__ is not."""
    from koda.plugins.registry import PluginRegistry

    assert isinstance(plugin_registry, PluginRegistry)
    package_dir = _write_safe_package(tmp_path)
    install_skill_package(package_dir, agent_id="ATLAS")
    cache = package_dir / "__pycache__"
    cache.mkdir()
    tag = sys.implementation.cache_tag
    (cache / f"handlers.{tag}.pyc").write_bytes(b"written by a later import")
    (cache / f"handlers.{tag}.opt-1.pyc").write_bytes(b"written by python -O")
    assert ensure_installed_package_tools_registered("ATLAS", force=True) == {}

    # A sourceless module directly under __pycache__ could be imported as __pycache__.evil.
    (cache / "evil.pyc").write_bytes(b"planted after approval")
    refused = ensure_installed_package_tools_registered("ATLAS", force=True)

    assert plugin_registry.get_handler("safe_notes") is None
    assert refused["safe_pack"]["status"] == "modified"


def _legacy_package_hash(package_dir: Path) -> str:
    """The package hash of the releases before D-037, which covered every file, __pycache__ included."""
    hasher = hashlib.sha256()
    for path in sorted(package_dir.rglob("*")):
        if path.is_file():
            hasher.update(path.relative_to(package_dir).as_posix().encode("utf-8"))
            hasher.update(hashlib.sha256(path.read_bytes()).hexdigest().encode("ascii"))
    return hasher.hexdigest()


def test_a_lock_approved_with_its_bytecode_caches_still_loads_while_every_file_matches(
    tmp_path: Path, plugin_registry: object
) -> None:
    """A lock from an earlier release hashed its __pycache__ files too; it loads while all of them still match."""
    from koda.plugins.registry import PluginRegistry
    from koda.skills import _package

    assert isinstance(plugin_registry, PluginRegistry)
    package_dir = _write_safe_package(tmp_path)
    install_skill_package(package_dir, agent_id="ATLAS")
    cache = package_dir / "__pycache__"
    cache.mkdir()
    cached = cache / f"handlers.{sys.implementation.cache_tag}.pyc"
    cached.write_bytes(b"written when an earlier release loaded the package")
    lock = get_skill_package_lock("ATLAS", "safe_pack")
    assert lock is not None
    legacy_hash = _legacy_package_hash(package_dir)
    assert legacy_hash != lock["package_hash"]
    _package._persist_skill_package_lock("ATLAS", {**lock, "package_hash": legacy_hash})

    assert ensure_installed_package_tools_registered("ATLAS", force=True) == {}
    assert plugin_registry.get_handler("safe_notes") is not None
    assert list_skill_registry("ATLAS")["items"][0]["integrity"] == {
        "status": "verified",
        "approved_package_hash": legacy_hash,
        "current_package_hash": legacy_hash,
    }

    # Under such a lock a cache file is part of what was approved, so changing it counts.
    cached.write_bytes(b"planted later")
    refused = ensure_installed_package_tools_registered("ATLAS", force=True)

    assert plugin_registry.get_handler("safe_notes") is None
    assert refused["safe_pack"]["status"] == "modified"


def test_tool_registry_includes_installed_package_tools(tmp_path: Path) -> None:
    package_dir = _write_safe_package(tmp_path)
    install_skill_package(package_dir, agent_id="ATLAS")

    registry = get_default_tool_registry(feature_flags={"plugins": True}, allowed_tool_ids={"safe_notes"})
    with pytest.raises(ToolRegistryError, match="Unknown tool definition: safe_notes"):
        registry.require("safe_notes")

    registry = get_default_tool_registry(
        feature_flags={"plugins": True},
        allowed_tool_ids={"safe_notes"},
        skill_policy={"enabled_skill_packages": ["safe_pack"]},
    )
    definition = registry.require("safe_notes")

    assert definition.source == "skill_package"
    assert definition.access_level == "read"
    assert definition.risk_class == "read_context"
    assert definition.ui_metadata["source_package_id"] == "safe_pack"


def test_install_rejects_denied_scan(tmp_path: Path) -> None:
    package_dir = _write_safe_package(tmp_path)
    (package_dir / "postinstall.sh").write_text("echo no", encoding="utf-8")

    with pytest.raises(SkillPackageError) as exc:
        install_skill_package(package_dir, agent_id="ATLAS")

    assert exc.value.error["code"] == "skill.scan_denied"


def _make_review_required(package_dir: Path) -> None:
    manifest = package_dir / "koda-skill.yaml"
    manifest.write_text(
        manifest.read_text(encoding="utf-8").replace(
            "permissions:\n  filesystem:",
            "permissions:\n  network: true\n  filesystem:",
        ),
        encoding="utf-8",
    )


def test_review_required_install_needs_an_operator_review_bound_to_the_package_hash(tmp_path: Path) -> None:
    package_dir = _write_safe_package(tmp_path)
    _make_review_required(package_dir)
    scan = scan_skill_package(package_dir, agent_id="ATLAS")
    assert scan.decision == "review_required"

    # Accepting with a note but without the reviewed package hash is not an operator review.
    for kwargs in (
        {"review_accepted": True},
        {"review_accepted": True, "review_note": "Looks fine."},
        {"review_note": "Looks fine.", "reviewed_package_hash": scan.package_hash},
    ):
        with pytest.raises(SkillPackageError) as exc:
            install_skill_package(package_dir, agent_id="ATLAS", **kwargs)  # type: ignore[arg-type]
        assert exc.value.error["code"] == "skill.policy_denied"
        assert "review_accepted" not in exc.value.error["user_action"]
        assert "review_accepted" not in exc.value.error["message"]
    assert get_skill_package_lock("ATLAS", "safe_pack") is None

    # A review of another package hash does not cover these files.
    with pytest.raises(SkillPackageError) as exc:
        install_skill_package(
            package_dir,
            agent_id="ATLAS",
            review_accepted=True,
            review_note="Reviewed an older copy.",
            reviewed_package_hash="0" * 64,
            reviewer="owner",
        )
    assert exc.value.error["code"] == "skill.review_hash_mismatch"
    assert get_skill_package_lock("ATLAS", "safe_pack") is None

    result = install_skill_package(
        package_dir,
        agent_id="ATLAS",
        review_accepted=True,
        review_note="Local operator accepted network warning for tests.",
        reviewed_package_hash=scan.package_hash,
        reviewer="owner",
    )

    review = result["lock"]["operator_review"]
    assert result["scan"]["decision"] == "review_required"
    assert review["accepted"] is True
    assert review["package_hash"] == scan.package_hash == result["lock"]["package_hash"]
    assert review["scanner_version"] == scan.scanner_version
    assert review["scan_decision"] == "review_required"
    assert review["reviewer"] == "owner"
    assert review["note"] == "Local operator accepted network warning for tests."
    assert result["lock"]["trust_summary"]["operator_review_accepted"] is True


def test_review_required_legacy_lock_without_operator_review_cannot_be_recommended(tmp_path: Path) -> None:
    package_dir = _write_safe_package(
        tmp_path,
        eval_block="""
tests:
  evals:
    - id: safe-pack-required
      required: true
      case:
        schema_version: eval_case.v1
        case_key: skill:safe_pack:required
        metadata:
          expected_tool_ids: []
          source_tool_ids: []
          source_status: completed
          source_replay_mode: offline
""",
    )
    manifest = package_dir / "koda-skill.yaml"
    manifest.write_text(
        manifest.read_text(encoding="utf-8").replace(
            "permissions:\n  filesystem:",
            "permissions:\n  network: true\n  filesystem:",
        ),
        encoding="utf-8",
    )
    result = install_skill_package(
        package_dir,
        agent_id="ATLAS",
        review_accepted=True,
        review_note="Accepted in test.",
        reviewed_package_hash=scan_skill_package(package_dir, agent_id="ATLAS").package_hash,
        reviewer="owner",
    )
    lock = dict(result["lock"])
    lock.pop("operator_review", None)
    lock["recommendation_status"] = "recommended"
    from koda.skills import _package

    _package._persist_skill_package_lock("ATLAS", lock)

    updated = run_skill_package_evals("ATLAS", "safe_pack")

    assert updated["recommendation_status"] == "blocked"
    assert updated["trust_summary"]["recommended"] is False
