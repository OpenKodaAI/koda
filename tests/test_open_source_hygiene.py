"""Sanitization checks for the open source repository surface."""

from __future__ import annotations

import re
import subprocess
import tomllib
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent


def _decode_hex_literals(*encoded_values: str) -> tuple[str, ...]:
    """Keep the denylist neutral in-source while matching known private identifiers."""
    return tuple(bytes.fromhex(value).decode("utf-8") for value in encoded_values)


BANNED_LITERALS = _decode_hex_literals(
    "4d415350",
    "4149525f434f4d50415353",
    "41495220434f4d50415353",
    "4c554259",
    "4c756279",
    "5279616e20456c6f79",
    "6d6174682e656c6f7940686f746d61696c2e636f6d",
    "7279616e2d6d662d656c6f79",
    "636c617564652d74656c656772616d2d626f74",
    "636c617564652d626f742d64617368626f617264",
)

ABSOLUTE_MACHINE_PATHS = (
    re.compile(r"/Users/[A-Za-z0-9._-]+"),
    re.compile(r"/home/[A-Za-z0-9._-]+"),
)

BINARY_SUFFIXES = {
    ".png",
    ".jpg",
    ".jpeg",
    ".gif",
    ".pdf",
    ".woff",
    ".woff2",
    ".ttf",
    ".ico",
    ".zip",
}

DISALLOWED_TRACKED_PATH_PATTERNS = (
    re.compile(r"(^|/)\.env$"),
    re.compile(r"(^|/)\.coverage(\..+)?$"),
    re.compile(r"(^|/)\.pytest_cache(/|$)"),
    re.compile(r"(^|/)\.mypy_cache(/|$)"),
    re.compile(r"(^|/)\.ruff_cache(/|$)"),
    re.compile(r"(^|/)node_modules(/|$)"),
    re.compile(r"(^|/)\.next(/|$)"),
    re.compile(r"(^|/)output(/|$)"),
    re.compile(r"(^|/)__pycache__(/|$)"),
    re.compile(r"(^|/).*\.egg-info(/|$)"),
    re.compile(r"(^|/).*\.db$"),
    re.compile(r"(^|/).*\.sqlite3?$"),
    re.compile(r"(^|/).*\.pickle$"),
)

# Root-level scripts have only ever been another vendor's minified desktop-app bundles
# (D-128). JavaScript belongs to a workspace package under apps/ or packages/.
ROOT_SCRIPT_SUFFIXES = frozenset({".js", ".mjs", ".cjs"})

CHANGELOG = ROOT / "CHANGELOG.md"
CHANGELOG_TITLE = "# Changelog"
# Keep a Changelog 1.1.0: one section per release, newest first, under these change types.
CHANGELOG_CHANGE_TYPES = frozenset({"Added", "Changed", "Deprecated", "Removed", "Fixed", "Security"})
CHANGELOG_RELEASE_HEADING = re.compile(
    r"^\[(?P<version>Unreleased|\d+\.\d+\.\d+)\](?: - (?P<date>\d{4}-\d{2}-\d{2}))?$"
)
MARKDOWN_HEADING = re.compile(r"^(?P<marks>#{1,6})\s+(?P<text>.+?)\s*#*\s*$")
MARKDOWN_FENCE = re.compile(r"^\s*(```|~~~)")
MARKDOWN_LINK_REFERENCE = re.compile(r"^\[(?P<label>[^\]]+)\]:\s+(?P<url>\S+)\s*$")

SECURITY_SCAN_MANIFEST_ALLOWLIST = {
    "apps/web/package.json",
    "package.json",
    "packages/cli/package.json",
    # Provider CLIs pinned for the images (ADR-002 AG-02): scanned by Snyk --all-projects,
    # by npm audit in security.yml/release.yml, and by the Trivy image scans.
    "packages/provider-clis/package-lock.json",
    "packages/provider-clis/package.json",
    "pnpm-lock.yaml",
    "pyproject.toml",
    "rust/Cargo.lock",
    "rust/Cargo.toml",
    "rust/koda-command-guard/Cargo.lock",
    "rust/koda-command-guard/pyproject.toml",
    "uv.lock",
}


def _tracked_repo_files() -> list[Path]:
    result = subprocess.run(
        ["git", "ls-files", "-z"],
        check=True,
        capture_output=True,
        cwd=ROOT,
    )
    files = [Path(item.decode("utf-8")) for item in result.stdout.split(b"\x00") if item]
    return [
        ROOT / path for path in files if path != Path("tests/test_open_source_hygiene.py") and (ROOT / path).exists()
    ]


def _read_text_if_applicable(path: Path) -> str | None:
    if path.suffix.lower() in BINARY_SUFFIXES:
        return None
    data = path.read_bytes()
    if b"\x00" in data:
        return None
    return data.decode("utf-8", errors="ignore")


def test_repo_contains_no_banned_private_identifiers() -> None:
    violations: list[str] = []
    for path in _tracked_repo_files():
        text = _read_text_if_applicable(path)
        if text is None:
            continue
        rel = path.relative_to(ROOT).as_posix()
        for literal in BANNED_LITERALS:
            if literal in text:
                violations.append(f"{rel}: {literal}")
    assert not violations, "Found banned private identifiers:\n" + "\n".join(sorted(violations))


def test_repo_contains_no_absolute_machine_paths() -> None:
    violations: list[str] = []
    for path in _tracked_repo_files():
        text = _read_text_if_applicable(path)
        if text is None:
            continue
        rel = path.relative_to(ROOT).as_posix()
        for pattern in ABSOLUTE_MACHINE_PATHS:
            match = pattern.search(text)
            if match:
                violations.append(f"{rel}: {match.group(0)}")
    assert not violations, "Found absolute machine-specific paths:\n" + "\n".join(sorted(violations))


def test_repo_tracks_no_local_runtime_or_cache_artifacts() -> None:
    violations: list[str] = []
    for path in _tracked_repo_files():
        rel = path.relative_to(ROOT).as_posix()
        if rel == ".env.example":
            continue
        for pattern in DISALLOWED_TRACKED_PATH_PATTERNS:
            if pattern.search(rel):
                violations.append(rel)
                break
    assert not violations, "Tracked local/runtime/cache artifacts must not be committed:\n" + "\n".join(
        sorted(violations)
    )


def test_repo_root_tracks_no_javascript_files() -> None:
    root_scripts = sorted(
        path.name
        for path in _tracked_repo_files()
        if path.parent == ROOT and path.suffix.lower() in ROOT_SCRIPT_SUFFIXES
    )
    assert not root_scripts, (
        "JavaScript must not be tracked at the repository root; it belongs to a workspace package "
        "under apps/ or packages/ (D-128: the root only ever held a vendor's minified bundles):\n"
        + "\n".join(root_scripts)
    )


def _markdown_headings(text: str) -> list[tuple[int, int, str]]:
    """(line number, level, text) of each ATX heading outside fenced code blocks."""
    headings: list[tuple[int, int, str]] = []
    in_fence = False
    for number, line in enumerate(text.splitlines(), start=1):
        if MARKDOWN_FENCE.match(line):
            in_fence = not in_fence
            continue
        match = None if in_fence else MARKDOWN_HEADING.match(line)
        if match:
            headings.append((number, len(match.group("marks")), match.group("text")))
    return headings


def _is_changelog(path: Path) -> bool:
    """CHANGELOG.md in any directory and any case; not other files that mention changelogs."""
    return path.suffix.lower() == ".md" and path.stem.lower() == "changelog"


def _tracked_changelogs() -> list[Path]:
    return [path for path in _tracked_repo_files() if _is_changelog(path)]


def _changelog_title_violations(rel: str, text: str) -> list[str]:
    violations: list[str] = []
    first_line = next((line.strip() for line in text.splitlines() if line.strip()), "")
    if first_line != CHANGELOG_TITLE:
        violations.append(f"{rel}:1: starts with {first_line!r}, not {CHANGELOG_TITLE!r}")
    for number, level, heading in _markdown_headings(text):
        if level == 1 and f"# {heading}" != CHANGELOG_TITLE:
            violations.append(f"{rel}:{number}: foreign title {heading!r}")
    preamble = text.split("\n## ", 1)[0]
    if "koda" not in preamble.lower():
        violations.append(f"{rel}: the text above the first release does not name Koda")
    return violations


def _version_key(version: str) -> tuple[int, ...]:
    return tuple(int(part) for part in version.split("."))


def _changelog_releases(text: str) -> list[tuple[str, str | None]]:
    releases: list[tuple[str, str | None]] = []
    for _, level, heading in _markdown_headings(text):
        match = CHANGELOG_RELEASE_HEADING.match(heading) if level == 2 else None
        if match:
            releases.append((match.group("version"), match.group("date")))
    return releases


def test_tracked_changelogs_carry_no_foreign_title() -> None:
    """A changelog is Koda's own: titled `# Changelog`, with no other product's heading (D-084)."""
    changelogs = _tracked_changelogs()
    assert CHANGELOG in changelogs, "CHANGELOG.md must be tracked at the repository root"
    violations = [
        violation
        for path in changelogs
        for violation in _changelog_title_violations(
            path.relative_to(ROOT).as_posix(), path.read_text(encoding="utf-8")
        )
    ]
    assert not violations, "Changelogs must be Koda's own:\n" + "\n".join(violations)


@pytest.mark.parametrize(
    ("rel", "expected"),
    [
        ("CHANGELOG.md", True),
        ("packages/cli/CHANGELOG.md", True),
        ("docs/changelog.md", True),
        ("scripts/changelog_check.py", False),
        ("docs/reference/changelog-policy.md", False),
        ("apps/web/src/lib/changelog.ts", False),
    ],
)
def test_changelog_title_check_covers_markdown_changelogs_only(rel: str, expected: bool) -> None:
    assert _is_changelog(Path(rel)) is expected


FOREIGN_CHANGELOG_PROBES = {
    "foreign-title": "# @googleworkspace/cli\n\n## 0.22.0\n\n- Add a command.\n",
    "second-title": "# Changelog\n\nAll notable changes to Koda.\n\n# @googleworkspace/cli\n",
    "no-product": "# Changelog\n\nAll notable changes to this project.\n\n## [1.0.0] - 2026-01-01\n",
}


@pytest.mark.parametrize("text", FOREIGN_CHANGELOG_PROBES.values(), ids=FOREIGN_CHANGELOG_PROBES.keys())
def test_changelog_title_check_flags_foreign_changelogs(text: str) -> None:
    assert _changelog_title_violations("CHANGELOG.md", text)


def test_changelog_title_check_accepts_a_package_changelog() -> None:
    text = "# Changelog\n\nAll notable changes to @openkodaai/koda.\n\n## [1.0.0] - 2026-01-01\n"
    assert _changelog_title_violations("packages/cli/CHANGELOG.md", text) == []


def test_changelog_follows_keep_a_changelog() -> None:
    text = CHANGELOG.read_text(encoding="utf-8")
    violations: list[str] = []
    releases: list[tuple[int, str, str | None]] = []
    change_types_in_release: set[str] = set()
    entries_under: dict[tuple[str, str], int] = {}
    current_release: str | None = None
    current_type: str | None = None
    lines = text.splitlines()
    headings = {number: (level, heading) for number, level, heading in _markdown_headings(text)}
    for number, line in enumerate(lines, start=1):
        if number in headings:
            level, heading = headings[number]
            if level == 2:
                match = CHANGELOG_RELEASE_HEADING.match(heading)
                if not match:
                    violations.append(f"{number}: release heading {heading!r} is not [Unreleased] or [X.Y.Z] - DATE")
                    current_release = None
                    continue
                version, date = match.group("version"), match.group("date")
                if (version == "Unreleased") != (date is None):
                    violations.append(f"{number}: only [Unreleased] goes without a date: {heading!r}")
                releases.append((number, version, date))
                current_release, current_type = version, None
                change_types_in_release = set()
            elif level == 3:
                if current_release is None:
                    violations.append(f"{number}: change type {heading!r} is outside a release")
                elif heading not in CHANGELOG_CHANGE_TYPES:
                    violations.append(f"{number}: {heading!r} is not one of {sorted(CHANGELOG_CHANGE_TYPES)}")
                elif heading in change_types_in_release:
                    violations.append(f"{number}: {heading!r} appears twice in [{current_release}]")
                else:
                    change_types_in_release.add(heading)
                    current_type = heading
                    entries_under[(current_release, heading)] = 0
            elif level > 3:
                violations.append(f"{number}: heading level {level} is deeper than a change type: {heading!r}")
        elif line.startswith("- ") and current_release is not None and current_type is not None:
            entries_under[(current_release, current_type)] += 1

    violations.extend(
        f"[{release}] {change_type} has no entries"
        for (release, change_type), count in entries_under.items()
        if count == 0
    )
    versions = [version for _, version, _ in releases]
    if not versions or versions[0] != "Unreleased":
        violations.append(f"the first release section must be [Unreleased], found {versions[:1]}")
    if versions.count("Unreleased") > 1:
        violations.append("[Unreleased] appears more than once")
    released = [(version, date) for _, version, date in releases if version != "Unreleased"]
    for (newer, newer_date), (older, older_date) in zip(released, released[1:], strict=False):
        if _version_key(newer) <= _version_key(older):
            violations.append(f"[{newer}] is listed above [{older}]; releases go newest first")
        if newer_date is not None and older_date is not None and newer_date < older_date:
            violations.append(f"[{newer}] is dated {newer_date}, before [{older}] ({older_date})")
    references = {
        match.group("label"): match.group("url")
        for match in (MARKDOWN_LINK_REFERENCE.match(line) for line in lines)
        if match
    }
    for version in versions:
        url = references.get(version)
        if url is None or not url.startswith("https://"):
            violations.append(f"[{version}] has no https link reference")
    assert not violations, "CHANGELOG.md does not follow Keep a Changelog:\n" + "\n".join(violations)


def test_changelog_newest_release_is_the_project_version() -> None:
    """Bumping pyproject.toml moves the [Unreleased] entries under the new version's heading."""
    project_version = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]["version"]
    released = [version for version, _ in _changelog_releases(CHANGELOG.read_text(encoding="utf-8"))]
    released = [version for version in released if version != "Unreleased"]
    newest = released[0] if released else None
    assert newest == project_version, (
        f"CHANGELOG.md's newest release is {newest!r} but pyproject.toml is at {project_version!r}"
    )


def test_tracked_package_manager_manifests_are_whitelisted_for_security_scans() -> None:
    manifests = {
        path.relative_to(ROOT).as_posix()
        for path in _tracked_repo_files()
        if path.name
        in {
            "Cargo.lock",
            "Cargo.toml",
            "composer.json",
            "composer.lock",
            "package-lock.json",
            "package.json",
            "pnpm-lock.yaml",
            "pyproject.toml",
            "uv.lock",
            "yarn.lock",
        }
    }

    manifest_names = {Path(path).name for path in manifests}
    allowed_manifests = {
        path
        for path in manifests
        if path in SECURITY_SCAN_MANIFEST_ALLOWLIST or (path.startswith("rust/") and path.endswith("/Cargo.toml"))
    }

    assert "composer.json" not in manifest_names
    assert "composer.lock" not in manifest_names
    assert manifests <= allowed_manifests, sorted(manifests - allowed_manifests)


def test_legacy_requirements_mirrors_runtime_dependencies() -> None:
    """Keep Snyk's legacy requirements.txt discovery aligned with pyproject.toml."""
    project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    runtime_dependencies = project["project"]["dependencies"]
    legacy_requirements = [
        line.strip()
        for line in (ROOT / "requirements.txt").read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.startswith("#")
    ]

    assert legacy_requirements == runtime_dependencies
