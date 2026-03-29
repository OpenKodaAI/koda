"""Sanitization checks for the open source repository surface."""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

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
