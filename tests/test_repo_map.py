"""Tests for the deterministic repository map generator and committed output."""

from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
SCRIPT_PATH = ROOT / "scripts" / "generate_repo_map.py"
MAP_PATH = ROOT / "docs" / "ai" / "repo-map.yaml"
EXPECTED_TOP_LEVEL_KEYS = [
    "metadata",
    "entrypoints",
    "module_areas",
    "runtime_flows",
    "config_surfaces",
    "guardrails",
    "change_recipes",
    "test_targets",
    "ai_guides",
]
EXPECTED_MODULE_AREAS = {
    "application-bootstrap",
    "telegram-handlers",
    "runtime-services",
    "memory-subsystem",
    "runtime-skills-and-prompt-contracts",
    "shared-utilities",
    "developer-ai-guidance",
}
EXPECTED_RUNTIME_FLOWS = {
    "message-to-response",
    "agent-tool-loop",
    "media-inputs",
    "memory-lifecycle",
    "scheduled-automation",
}
EXPECTED_LLM_TARGETS = {"generic-llm", "codex", "claude-code"}
PATH_KEYS = {
    "canonical_map_path",
    "generator_script",
    "source_roots",
    "paths",
    "source_paths",
    "primary_paths",
    "test_paths",
    "related_tests",
    "related_docs",
    "related_skills",
    "canonical_map",
    "provider_neutral_docs",
    "codex_entrypoints",
    "claude_code_entrypoints",
    "root_docs",
    "subtree_guides",
    "reference_docs",
    "repo_skill_files",
    "repo_skill_metadata",
    "path",
}


def load_repo_map_module() -> ModuleType:
    """Load the generator module from disk without requiring package installation."""
    spec = importlib.util.spec_from_file_location("generate_repo_map", SCRIPT_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def collect_repo_paths(value: Any) -> list[str]:
    """Collect repository-relative paths from the structured map."""
    collected: list[str] = []

    if isinstance(value, dict):
        for key, item in value.items():
            if key in PATH_KEYS:
                collected.extend(normalize_path_values(item))
            else:
                collected.extend(collect_repo_paths(item))
    elif isinstance(value, list):
        for item in value:
            collected.extend(collect_repo_paths(item))

    return collected


def normalize_path_values(value: Any) -> list[str]:
    """Normalize a path field into a list of strings."""
    if isinstance(value, str):
        return [value]
    if isinstance(value, list):
        return [item for item in value if isinstance(item, str)]
    return []


def test_committed_repo_map_matches_generator_stdout() -> None:
    result = subprocess.run(
        [sys.executable, str(SCRIPT_PATH)],
        check=False,
        capture_output=True,
        text=True,
        cwd=ROOT,
    )

    assert result.returncode == 0, result.stderr
    assert MAP_PATH.read_text(encoding="utf-8") == result.stdout


def test_check_mode_succeeds_without_drift() -> None:
    result = subprocess.run(
        [sys.executable, str(SCRIPT_PATH), "--check"],
        check=False,
        capture_output=True,
        text=True,
        cwd=ROOT,
    )

    assert result.returncode == 0, result.stderr


def test_top_level_sections_are_present_in_order() -> None:
    module = load_repo_map_module()
    repo_map = module.build_repo_map()
    assert list(repo_map.keys()) == EXPECTED_TOP_LEVEL_KEYS


def test_expected_module_areas_and_runtime_flows_exist() -> None:
    module = load_repo_map_module()
    repo_map = module.build_repo_map()

    module_area_ids = {entry["id"] for entry in repo_map["module_areas"]}
    runtime_flow_ids = {entry["id"] for entry in repo_map["runtime_flows"]}

    assert EXPECTED_MODULE_AREAS.issubset(module_area_ids)
    assert EXPECTED_RUNTIME_FLOWS.issubset(runtime_flow_ids)


def test_repo_map_declares_provider_compatibility() -> None:
    module = load_repo_map_module()
    repo_map = module.build_repo_map()

    llm_targets = set(repo_map["metadata"]["llm_targets"])
    ai_guides = repo_map["ai_guides"]

    assert EXPECTED_LLM_TARGETS.issubset(llm_targets)
    assert "README.md" in ai_guides["provider_neutral_docs"]
    assert "docs/ai/repo-map.yaml" in ai_guides["provider_neutral_docs"]
    assert "docs/ai/llm-compatibility.md" in ai_guides["provider_neutral_docs"]
    assert "AGENTS.md" in ai_guides["codex_entrypoints"]
    assert "CLAUDE.md" in ai_guides["claude_code_entrypoints"]


def test_referenced_repo_paths_exist() -> None:
    module = load_repo_map_module()
    repo_map = module.build_repo_map()

    for path_string in collect_repo_paths(repo_map):
        resolved = ROOT / path_string
        assert resolved.exists(), f"Missing referenced path in repo-map: {path_string}"


def test_ignored_directories_and_artifacts_do_not_leak_into_map() -> None:
    module = load_repo_map_module()
    repo_map = module.build_repo_map()
    path_strings = collect_repo_paths(repo_map)

    disallowed_roots = (".git", ".venv", "venv", ".pytest_cache", ".mypy_cache", ".ruff_cache")
    disallowed_prefixes = (
        "tmp_images",
        "agent_memory_",
        "agent_history_",
        "control_plane_runtime",
        "runtime_agent_a",
        "runtime_smoke",
        "smoke-workspace",
        ".knowledge_v2_store",
    )

    for path_string in path_strings:
        assert not path_string.endswith(".db"), f"Unexpected database artifact leaked into map: {path_string}"
        assert not path_string.endswith(".log"), f"Unexpected log artifact leaked into map: {path_string}"
        assert not path_string.startswith(disallowed_prefixes), f"Unexpected temp path leaked into map: {path_string}"
        assert not any(path_string == root or path_string.startswith(f"{root}/") for root in disallowed_roots), (
            f"Unexpected ignored root leaked into map: {path_string}"
        )
