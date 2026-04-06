"""Tests for koda.skills._registry."""

from __future__ import annotations

import textwrap
import time
from pathlib import Path

from koda.skills._registry import SkillRegistry, _parse_skill_file

# Path to the real skills directory shipped with the repo.
SKILLS_DIR = Path(__file__).resolve().parent.parent.parent / "koda" / "skills"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _write(path: Path, text: str) -> Path:
    path.write_text(textwrap.dedent(text), encoding="utf-8")
    return path


def _make_frontmatter_skill(tmp_path: Path, filename: str = "testing.md") -> Path:
    return _write(
        tmp_path / filename,
        """\
        ---
        name: Testing Expert
        aliases:
          - test-guru
          - qa
        version: "2.1.0"
        category: engineering
        tags:
          - testing
          - quality
        triggers:
          - "\\\\btest\\\\b"
          - "\\\\bqa\\\\b"
        requires:
          - tdd
        conflicts:
          - prototype
        base_priority: 75
        max_token_budget: 3000
        model_hints:
          prefer: large
        ---
        # Testing Expert

        You are an expert tester.

        <when_to_use>
        Apply when writing or reviewing tests. Skip for throwaway scripts.
        </when_to_use>

        ## Details

        More content here.
        """,
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestLoadsExistingFiles:
    def test_loads_all_existing_md_files(self) -> None:
        registry = SkillRegistry(SKILLS_DIR, scan_interval=0)
        skills = registry.get_all()
        md_files = list(SKILLS_DIR.glob("*.md"))
        assert len(skills) == len(md_files)
        for md in md_files:
            assert md.stem in skills, f"{md.stem} not loaded"


class TestBackwardCompatNoFrontmatter:
    def test_backward_compat_no_frontmatter(self, tmp_path: Path) -> None:
        """A skill file with no YAML frontmatter gets sensible defaults."""
        _write(
            tmp_path / "plain.md",
            """\
            # Plain Skill

            You are an expert.

            <when_to_use>
            Use when needed.
            </when_to_use>

            ## Details

            More text.
            """,
        )
        defn = _parse_skill_file(tmp_path / "plain.md")
        assert defn.frontmatter_present is False
        assert defn.id == "plain"
        assert defn.name == "Plain Skill"
        assert defn.category == "general"
        assert defn.aliases == ()
        assert defn.tags == ()
        assert defn.triggers == ()
        assert defn.requires == ()
        assert defn.conflicts == ()
        assert defn.version == "1.0.0"
        assert defn.base_priority == 50
        assert defn.max_token_budget == 2000


class TestParsesYamlFrontmatter:
    def test_parses_yaml_frontmatter(self, tmp_path: Path) -> None:
        path = _make_frontmatter_skill(tmp_path)
        defn = _parse_skill_file(path)

        assert defn.frontmatter_present is True
        assert defn.id == "testing"
        assert defn.name == "Testing Expert"
        assert defn.aliases == ("test-guru", "qa")
        assert defn.version == "2.1.0"
        assert defn.category == "engineering"
        assert defn.tags == ("testing", "quality")
        assert len(defn.triggers) == 2
        assert defn.requires == ("tdd",)
        assert defn.conflicts == ("prototype",)
        assert defn.base_priority == 75
        assert defn.max_token_budget == 3000
        assert defn.model_hints == {"prefer": "large"}
        assert defn.source_path == path
        assert defn.last_modified > 0


class TestAliasIndex:
    def test_alias_index_resolves(self, tmp_path: Path) -> None:
        _make_frontmatter_skill(tmp_path)
        registry = SkillRegistry(tmp_path, scan_interval=0)

        assert registry.resolve_alias("test-guru") == "testing"
        assert registry.resolve_alias("QA") == "testing"
        assert registry.resolve_alias("nonexistent") is None


class TestWhenToUseExtraction:
    def test_when_to_use_extraction(self) -> None:
        defn = _parse_skill_file(SKILLS_DIR / "security.md")
        assert "reviewing code for security issues" in defn.when_to_use
        assert "<when_to_use>" not in defn.when_to_use

    def test_missing_when_to_use(self, tmp_path: Path) -> None:
        path = _write(tmp_path / "bare.md", "# Bare Skill\n\nNo tag here.\n")
        defn = _parse_skill_file(path)
        assert defn.when_to_use == ""
        assert defn.awareness_summary == ""


class TestAwarenessSummary:
    def test_awareness_summary_first_sentence(self) -> None:
        defn = _parse_skill_file(SKILLS_DIR / "tdd.md")
        # First sentence ends at the first period.
        assert defn.awareness_summary.endswith(".")
        assert "Apply TDD when building new features" in defn.awareness_summary

    def test_awareness_summary_no_period(self, tmp_path: Path) -> None:
        path = _write(
            tmp_path / "nop.md",
            "# No Period\n\n<when_to_use>\nUse always\n</when_to_use>\n",
        )
        defn = _parse_skill_file(path)
        assert defn.awareness_summary == "Use always"


class TestEmbeddingText:
    def test_embedding_text_concatenation(self, tmp_path: Path) -> None:
        path = _make_frontmatter_skill(tmp_path)
        defn = _parse_skill_file(path)

        assert "Testing Expert" in defn.embedding_text
        assert "test-guru" in defn.embedding_text
        assert "qa" in defn.embedding_text
        assert "Apply when writing or reviewing tests" in defn.embedding_text
        assert "testing" in defn.embedding_text
        assert "quality" in defn.embedding_text


class TestReloadDetectsNewFile:
    def test_reload_detects_new_file(self, tmp_path: Path) -> None:
        _write(tmp_path / "alpha.md", "# Alpha\n\nContent.\n")
        registry = SkillRegistry(tmp_path, scan_interval=0)
        assert "alpha" in registry.get_all()
        assert "beta" not in registry.get_all()

        _write(tmp_path / "beta.md", "# Beta\n\nContent.\n")
        changed = registry.reload_if_stale()
        assert changed is True
        assert "beta" in registry.get_all()


class TestReloadDetectsModifiedFile:
    def test_reload_detects_modified_file(self, tmp_path: Path) -> None:
        path = _write(tmp_path / "mutable.md", "# V1\n\nOriginal.\n")
        registry = SkillRegistry(tmp_path, scan_interval=0)
        assert registry.get("mutable") is not None
        assert registry.get("mutable").name == "V1"  # type: ignore[union-attr]

        # Ensure mtime changes (some filesystems have 1-second resolution).
        time.sleep(0.05)
        _write(path, "# V2\n\nUpdated.\n")
        changed = registry.reload_if_stale()
        assert changed is True
        assert registry.get("mutable").name == "V2"  # type: ignore[union-attr]


class TestReloadDetectsDeletedFile:
    def test_reload_detects_deleted_file(self, tmp_path: Path) -> None:
        path = _write(tmp_path / "ephemeral.md", "# Gone Soon\n")
        registry = SkillRegistry(tmp_path, scan_interval=0)
        assert "ephemeral" in registry.get_all()

        path.unlink()
        changed = registry.reload_if_stale()
        assert changed is True
        assert "ephemeral" not in registry.get_all()


class TestInstructionField:
    def test_instruction_field_parsed_from_frontmatter(self) -> None:
        """Verify instruction is parsed from frontmatter."""
        defn = _parse_skill_file(SKILLS_DIR / "tdd.md")
        assert defn.instruction != ""
        assert "test" in defn.instruction.lower()

    def test_output_format_enforcement_parsed(self) -> None:
        """Verify output_format_enforcement is parsed from frontmatter."""
        defn = _parse_skill_file(SKILLS_DIR / "tdd.md")
        assert defn.output_format_enforcement != ""
        assert "Red-Green-Refactor" in defn.output_format_enforcement

    def test_instruction_defaults_to_empty(self, tmp_path: Path) -> None:
        """No frontmatter instruction = empty string."""
        path = _write(
            tmp_path / "bare.md",
            "# Bare Skill\n\nNo frontmatter here.\n",
        )
        defn = _parse_skill_file(path)
        assert defn.instruction == ""
        assert defn.output_format_enforcement == ""


class TestGetNonexistent:
    def test_get_nonexistent_returns_none(self) -> None:
        registry = SkillRegistry(SKILLS_DIR, scan_interval=0)
        assert registry.get("does-not-exist") is None
