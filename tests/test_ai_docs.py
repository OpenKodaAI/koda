"""Contract tests for the AI-friendly repository guidance layer."""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

REQUIRED_AI_FILES = [
    "README.md",
    "AGENTS.md",
    "CLAUDE.md",
    "koda/AGENTS.md",
    "koda/CLAUDE.md",
    "koda/services/AGENTS.md",
    "koda/services/CLAUDE.md",
    "koda/memory/AGENTS.md",
    "koda/memory/CLAUDE.md",
    "tests/AGENTS.md",
    "tests/CLAUDE.md",
    "docs/ai/llm-compatibility.md",
    "docs/ai/architecture-overview.md",
    "docs/ai/runtime-flows.md",
    "docs/ai/configuration-and-prompts.md",
    "docs/ai/change-playbook.md",
    "docs/ai/repo-map.yaml",
]

SKILL_NAMES = [
    "repo-orientation",
    "runtime-flow-changes",
    "memory-pipeline-changes",
    "integration-and-safety-changes",
]

LINK_RE = re.compile(r"\[[^\]]+\]\(([^)]+)\)")
FRONTMATTER_RE = re.compile(r"^---\n(.*?)\n---\n", re.DOTALL)
ROOT_ENTRYPOINTS = ("README.md", "AGENTS.md", "CLAUDE.md")
PROVIDER_ENTRYPOINTS = ("AGENTS.md", "CLAUDE.md")


def test_required_ai_files_exist() -> None:
    missing = [path for path in REQUIRED_AI_FILES if not (ROOT / path).exists()]
    assert not missing, f"Missing AI guidance files: {missing}"


def test_skill_folders_have_required_files() -> None:
    for skill_name in SKILL_NAMES:
        skill_dir = ROOT / "docs" / "ai" / "skills" / skill_name
        assert skill_dir.is_dir(), f"Missing skill directory: {skill_dir}"
        assert (skill_dir / "SKILL.md").is_file(), f"Missing SKILL.md for {skill_name}"
        assert (skill_dir / "agents" / "openai.yaml").is_file(), f"Missing agents/openai.yaml for {skill_name}"


def test_skill_frontmatter_has_required_keys_and_no_todos() -> None:
    for skill_name in SKILL_NAMES:
        skill_path = ROOT / "docs" / "ai" / "skills" / skill_name / "SKILL.md"
        text = skill_path.read_text(encoding="utf-8")
        match = FRONTMATTER_RE.match(text)
        assert match, f"Missing YAML frontmatter in {skill_path}"
        frontmatter = match.group(1)
        assert re.search(r"^name:\s*.+$", frontmatter, re.MULTILINE), f"Missing name in {skill_path}"
        assert re.search(r"^description:\s*.+$", frontmatter, re.MULTILINE), f"Missing description in {skill_path}"
        assert "[TODO" not in text, f"Unfinished TODO marker left in {skill_path}"


def test_root_ai_entrypoints_link_to_existing_repo_paths() -> None:
    for relative_path in ROOT_ENTRYPOINTS:
        doc_path = ROOT / relative_path
        text = doc_path.read_text(encoding="utf-8")
        links = LINK_RE.findall(text)
        assert links, f"No markdown links found in {doc_path}"
        for target in links:
            if "://" in target or target.startswith("mailto:"):
                continue
            target_path = target.split("#", 1)[0]
            assert target_path, f"Empty local link target in {doc_path}: {target}"
            resolved = (doc_path.parent / target_path).resolve()
            assert resolved.exists(), f"Broken local link in {doc_path}: {target}"


def test_root_ai_entrypoints_reference_repo_map() -> None:
    for relative_path in ROOT_ENTRYPOINTS:
        doc_path = ROOT / relative_path
        text = doc_path.read_text(encoding="utf-8")
        assert "docs/ai/repo-map.yaml" in text, f"Missing repo-map reference in {doc_path}"


def test_provider_entrypoints_reference_llm_compatibility() -> None:
    for relative_path in PROVIDER_ENTRYPOINTS:
        doc_path = ROOT / relative_path
        text = doc_path.read_text(encoding="utf-8")
        assert "docs/ai/llm-compatibility.md" in text, f"Missing LLM compatibility reference in {doc_path}"
