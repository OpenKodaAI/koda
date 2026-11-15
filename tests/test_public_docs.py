"""Tests for the public product and contributor documentation layer."""

from __future__ import annotations

import re
import tomllib
from collections.abc import Callable
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MARKDOWN_LINK_RE = re.compile(r"\[[^\]]+\]\(([^)]+)\)")
IMAGE_RE = re.compile(r"!\[[^\]]*\]\(([^)]+)\)")
HTML_ATTR_RE = re.compile(r'(?:href|src)="([^"]+)"')
INLINE_CODE_MARKDOWN_PATH_RE = re.compile(r"`([^`\s]+\.md)`")

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
    ROOT / "CONTRIBUTING.md",
    ROOT / "SECURITY.md",
    ROOT / "CODE_OF_CONDUCT.md",
]

REQUIRED_ASSETS = [
    ROOT / "docs" / "assets" / "brand" / "koda-logo.svg",
    ROOT / "docs" / "assets" / "brand" / "koda-logo.png",
    ROOT / "docs" / "assets" / "brand" / "koda-banner.png",
    ROOT / "docs" / "assets" / "brand" / "koda-og.png",
    ROOT / "docs" / "assets" / "screenshots" / "setup.png",
    ROOT / "docs" / "assets" / "diagrams" / "platform-topology.svg",
    ROOT / "docs" / "assets" / "diagrams" / "runtime-flow.svg",
]


def _local_targets(doc_path: Path) -> list[str]:
    targets: list[str] = []
    for pattern in (MARKDOWN_LINK_RE, IMAGE_RE, HTML_ATTR_RE):
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


def test_upgrade_runbook_names_only_existing_documents() -> None:
    """Each document the upgrade runbook sends operators to exists, linked or named in a code span."""
    doc_path = ROOT / "docs" / "operations" / "upgrade.md"
    text = doc_path.read_text(encoding="utf-8")
    missing = [target for target in _local_targets(doc_path) if not (doc_path.parent / target).resolve().exists()]
    missing += [
        named
        for named in INLINE_CODE_MARKDOWN_PATH_RE.findall(text)
        if not ((ROOT / named).exists() or (doc_path.parent / named).exists())
    ]
    assert not missing, f"docs/operations/upgrade.md names documents that do not exist: {missing}"


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
    assert "docs/assets/brand/koda-banner.png" in readme
    assert "docs/assets/brand/koda_hero" not in readme
    assert "Core Capabilities" in readme
    assert "Quick Install" in readme
    assert "apps/web" in readme
    assert "127.0.0.1:3000" in readme
    assert "/control-plane" in readme
    assert "/setup" in readme
    assert "runtime API" in readme
    assert "SeaweedFS" in readme


# Contributor platforms, as CONTRIBUTING.md and README.md name them, and whether a
# wheel platform tag (from uv.lock) installs on them.
_CRYPTOGRAPHY_PLATFORMS: dict[str, Callable[[str], bool]] = {
    "Apple silicon macOS": lambda tag: tag.startswith("macosx_") and tag.endswith(("_arm64", "_universal2")),
    "Intel (x86_64) macOS": lambda tag: tag.startswith("macosx_") and tag.endswith(("_x86_64", "_universal2")),
    "x86-64 Windows": lambda tag: tag == "win_amd64",
    "32-bit Windows": lambda tag: tag == "win32",
    "Windows on ARM": lambda tag: tag == "win_arm64",
}


def _locked_cryptography_wheel_tags() -> set[str]:
    lock = tomllib.loads((ROOT / "uv.lock").read_text(encoding="utf-8"))
    (package,) = [package for package in lock["package"] if package["name"] == "cryptography"]
    filenames = [wheel["url"].rsplit("/", 1)[-1].removesuffix(".whl") for wheel in package["wheels"]]
    return {tag for filename in filenames for tag in filename.split("-")[-1].split(".")}


def test_contributor_setup_names_the_platforms_without_cryptography_wheels() -> None:
    # Koda requires cryptography >= 50.0.2 for security fixes. Where uv.lock has no
    # wheel for a platform, the install builds it from source there.
    tags = _locked_cryptography_wheel_tags()
    has_wheel = {platform: any(map(covers, tags)) for platform, covers in _CRYPTOGRAPHY_PLATFORMS.items()}
    guide = (ROOT / "CONTRIBUTING.md").read_text(encoding="utf-8")
    paragraph = " ".join(next(block for block in guide.split("\n\n") if "`cryptography` 50.0.2" in block).split())
    sentences = re.split(r"(?<=\.) (?=[A-Z])", paragraph)
    wheels = " ".join(sentence for sentence in sentences if sentence.startswith("Its wheels cover"))
    source = " ".join(sentence for sentence in sentences if "builds it from source" in sentence)
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    readme_source = " ".join(line for line in readme.splitlines() if "builds `cryptography` from source" in line)
    assert wheels, "CONTRIBUTING.md must say which platforms cryptography's wheels cover"

    for platform, wheel in has_wheel.items():
        assert (platform in wheels) == wheel, platform
        assert (platform in source) != wheel, platform
        assert (platform in readme_source) != wheel, platform
    assert "on macOS, the Xcode command line tools (`xcode-select --install`)" in paragraph
    assert "brew install openssl@3 rust" in paragraph
    assert "on Windows, the Microsoft C++ Build Tools" in paragraph
    assert "(CONTRIBUTING.md#development-setup)" in readme_source
