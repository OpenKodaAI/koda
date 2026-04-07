"""Tests for the public product and contributor documentation layer."""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MARKDOWN_LINK_RE = re.compile(r"\[[^\]]+\]\(([^)]+)\)")
IMAGE_RE = re.compile(r"!\[[^\]]*\]\(([^)]+)\)")

PUBLIC_DOCS = [
    ROOT / "README.md",
    ROOT / "docs" / "README.md",
    ROOT / "docs" / "install" / "local.md",
    ROOT / "docs" / "install" / "vps.md",
    ROOT / "docs" / "config" / "reference.md",
    ROOT / "docs" / "security" / "README.md",
    ROOT / "docs" / "security" / "assessment.md",
    ROOT / "docs" / "security" / "threat-model.md",
    ROOT / "docs" / "security" / "asvs-remediation-matrix.md",
    ROOT / "docs" / "security" / "operations-baseline.md",
    ROOT / "docs" / "architecture" / "overview.md",
    ROOT / "docs" / "architecture" / "runtime.md",
    ROOT / "docs" / "reference" / "api.md",
    ROOT / "docs" / "reference" / "releases.md",
    ROOT / "CONTRIBUTING.md",
    ROOT / "SECURITY.md",
    ROOT / "CODE_OF_CONDUCT.md",
]

REQUIRED_ASSETS = [
    ROOT / "docs" / "assets" / "brand" / "koda-logo.svg",
    ROOT / "docs" / "assets" / "brand" / "koda-logo.png",
    ROOT / "docs" / "assets" / "brand" / "koda-hero.png",
    ROOT / "docs" / "assets" / "brand" / "koda-og.png",
    ROOT / "docs" / "assets" / "screenshots" / "setup.png",
    ROOT / "docs" / "assets" / "diagrams" / "platform-topology.svg",
    ROOT / "docs" / "assets" / "diagrams" / "runtime-flow.svg",
]


def _local_targets(doc_path: Path) -> list[str]:
    targets: list[str] = []
    for pattern in (MARKDOWN_LINK_RE, IMAGE_RE):
        for target in pattern.findall(doc_path.read_text(encoding="utf-8")):
            if "://" in target or target.startswith("mailto:"):
                continue
            targets.append(target.split("#", 1)[0])
    return [target for target in targets if target]


def test_public_docs_exist() -> None:
    missing = [path.relative_to(ROOT).as_posix() for path in PUBLIC_DOCS if not path.exists()]
    assert not missing, f"Missing public docs: {missing}"


def test_public_assets_exist() -> None:
    missing = [path.relative_to(ROOT).as_posix() for path in REQUIRED_ASSETS if not path.exists()]
    assert not missing, f"Missing public assets: {missing}"


def test_readme_and_docs_index_have_valid_local_links() -> None:
    for doc_path in (ROOT / "README.md", ROOT / "docs" / "README.md"):
        for target in _local_targets(doc_path):
            resolved = (doc_path.parent / target).resolve()
            assert resolved.exists(), f"Broken local link in {doc_path.relative_to(ROOT)}: {target}"


def test_public_docs_use_current_branding() -> None:
    banned = tuple(
        bytes.fromhex(token).decode("utf-8")
        for token in (
            "636c617564655f626f74",
            "436c6175646520426f74",
            "636c617564652d74656c656772616d2d626f74",
        )
    )
    for doc_path in PUBLIC_DOCS:
        text = doc_path.read_text(encoding="utf-8")
        for token in banned:
            assert token not in text, f"Found legacy branding in {doc_path.relative_to(ROOT)}: {token}"


def test_readme_covers_public_entrypoints() -> None:
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    assert "Koda" in readme
    assert "Core Capabilities" in readme
    assert "Installation Paths" in readme
    assert "apps/web" in readme
    assert "127.0.0.1:3000" in readme
    assert "/control-plane/setup" in readme
    assert "/control-plane" in readme
    assert "/setup" in readme
    assert "/api/control-plane/agents/*" in readme
    assert "SeaweedFS" in readme
