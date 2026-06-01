"""Tests for the npm README generated from the public root README."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from sync_npm_readme import build_package_readme  # noqa: E402


def test_npm_readme_uses_current_root_banner_from_main() -> None:
    readme = build_package_readme()

    assert "https://raw.githubusercontent.com/OpenKodaAI/koda/main/docs/assets/brand/koda-banner.png" in readme
    assert "docs/assets/brand/koda_hero" not in readme
    assert "raw.githubusercontent.com/OpenKodaAI/koda/v" not in readme


def test_npm_readme_links_follow_current_main_docs() -> None:
    readme = build_package_readme()

    assert "https://github.com/OpenKodaAI/koda/blob/main/docs/install/local.md" in readme
    assert "https://github.com/OpenKodaAI/koda/blob/v" not in readme
