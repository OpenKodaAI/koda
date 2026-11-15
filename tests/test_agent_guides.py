"""The agent guides: one canonical CLAUDE.md per level, an AGENTS.md pointer, and true statements (TD-197, D-158)."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
WEB = ROOT / "apps" / "web"

GUIDE_PAIRS = [
    pytest.param(ROOT / "AGENTS.md", ROOT / "CLAUDE.md", id="root"),
    pytest.param(WEB / "AGENTS.md", WEB / "CLAUDE.md", id="apps-web"),
]
# The whole body of each pointer: any line added to an AGENTS.md is an instruction CLAUDE.md lacks.
POINTER_BODIES = {
    ROOT / "AGENTS.md": [
        "# Koda Repository Guide (pointer)",
        "[CLAUDE.md](CLAUDE.md) is the canonical guide for every coding agent working in this repository;"
        " this file only points to it.",
        "Read it in full before any work and follow all of it: the Obsidian vault reads, the read order,"
        " the core invariants, the safe editing rules and the required validation.",
        "Change agent instructions in CLAUDE.md, never here.",
    ],
    WEB / "AGENTS.md": [
        "# Koda Web Agent Guide (pointer)",
        "[CLAUDE.md](CLAUDE.md) in this folder is the canonical guide for every coding agent working under"
        " `apps/web/`; this file only points to it.",
        "Read it in full before any work under `apps/web/` and follow all of it: the Obsidian vault reads,"
        " the root guide, the design system and the required validation.",
        "Change agent instructions in `apps/web/CLAUDE.md`, never here.",
    ],
}
AGENTS_LINK_RE = re.compile(r"\]\(([^)\s]*AGENTS\.md)\)")

VAULT_READS = [
    'obsidian vault=Koda read path="00_Index/Koda Workspace.md"',
    'obsidian vault=Koda read path="60_Memory/Agent Operating Memory.md"',
    'obsidian vault=Koda read path="60_Memory/User Preferences.md"',
    'obsidian vault=Koda read path="60_Memory/Project Memory.md"',
    'obsidian vault=Koda search query="<topic>" limit=10',
]
FALLBACK_READER_RE = re.compile(r"^(\S*bin/koda-vault-read) ", re.MULTILINE)
SCREENSHOT_ITEM_RE = re.compile(r"^- `([\w-]+\.png)`$", re.MULTILINE)


def _content_lines(path: Path) -> list[str]:
    return [line.strip() for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


@pytest.mark.parametrize(("pointer", "canonical"), GUIDE_PAIRS)
def test_agents_md_is_only_a_pointer_to_claude_md(pointer: Path, canonical: Path) -> None:
    """AGENTS.md is the fixed pointer to the CLAUDE.md beside it: no copied line and no instruction of its own."""
    assert "](CLAUDE.md)" in pointer.read_text(encoding="utf-8")
    assert _content_lines(pointer) == POINTER_BODIES[pointer]
    assert not set(_content_lines(pointer)) & set(_content_lines(canonical))


@pytest.mark.parametrize("guide", [ROOT / "CLAUDE.md", WEB / "CLAUDE.md"], ids=["root", "apps-web"])
def test_canonical_guides_do_not_send_agents_to_an_agents_md_pointer(guide: Path) -> None:
    """Each AGENTS.md only points back to a CLAUDE.md, so no canonical guide links one as a source of rules."""
    assert AGENTS_LINK_RE.findall(guide.read_text(encoding="utf-8")) == []


@pytest.mark.parametrize("guide", [ROOT / "CLAUDE.md", WEB / "CLAUDE.md"], ids=["root", "apps-web"])
def test_canonical_guides_keep_the_vault_reading_instructions(guide: Path) -> None:
    """Both canonical guides carry the Obsidian reads, and their fallback reader is the vault's one script."""
    text = guide.read_text(encoding="utf-8")

    for command in VAULT_READS:
        assert command in text
    readers = FALLBACK_READER_RE.findall(text)
    assert len(readers) == 1
    assert (guide.parent / readers[0]).resolve() == (ROOT.parent / "bin" / "koda-vault-read").resolve()


def test_web_guide_keeps_the_instructions_its_agents_md_gave() -> None:
    """The instructions that only apps/web/AGENTS.md gave now live in apps/web/CLAUDE.md."""
    text = " ".join((WEB / "CLAUDE.md").read_text(encoding="utf-8").split())

    assert (
        "Read the root operational guide, [`../../CLAUDE.md`](../../CLAUDE.md), from the main repository root." in text
    )
    assert "Search Obsidian for task-specific context before asking the user to repeat it." in text
    assert "Inspect the relevant component, route, hook, API, and tests before editing." in text
    assert "Run narrower tests during implementation when possible." in text
    assert "Record task handoffs in the daily note or a session note." in text
    assert "Do not store secrets or raw environment values." in text


def test_docs_index_does_not_say_the_web_agents_guide_is_missing() -> None:
    """D-158: apps/web/AGENTS.md exists, so the docs index must not say it does not."""
    text = (ROOT / "docs" / "README.md").read_text(encoding="utf-8")

    assert (WEB / "AGENTS.md").is_file()
    assert "until `apps/web/AGENTS.md` exists" not in text


def test_root_guide_does_not_place_skill_templates_in_koda_skills() -> None:
    """D-158: koda/skills holds only code, and /skill reads the agent's control-plane custom skills."""
    text = " ".join((ROOT / "CLAUDE.md").read_text(encoding="utf-8").split())

    assert {path.suffix for path in (ROOT / "koda" / "skills").iterdir() if path.is_file()} == {".py"}
    assert "live in `koda/skills`" not in text
    assert "control-plane custom skills" in text


def test_demo_data_lists_only_committed_screenshots() -> None:
    """D-158: every screenshot docs/demo-data.md lists is in docs/assets/screenshots."""
    text = (ROOT / "docs" / "demo-data.md").read_text(encoding="utf-8")
    listed = SCREENSHOT_ITEM_RE.findall(text)

    assert listed
    missing = [name for name in listed if not (ROOT / "docs" / "assets" / "screenshots" / name).is_file()]
    assert missing == []
