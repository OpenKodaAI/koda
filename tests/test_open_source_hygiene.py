"""Sanitization checks for the open source repository surface."""

from __future__ import annotations

import re
import subprocess
import tomllib
from pathlib import Path

from packaging.requirements import Requirement
from packaging.version import Version

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

SECURITY_SCAN_MANIFEST_ALLOWLIST = {
    "apps/web/package.json",
    "package.json",
    "packages/cli/package.json",
    "pnpm-lock.yaml",
    "pyproject.toml",
    "rust/Cargo.lock",
    "rust/Cargo.toml",
    "uv.lock",
}

MINIMUM_SAFE_LOCK_VERSIONS = {
    "numpy": Version("1.22.2"),
    "onnxruntime": Version("1.24.1"),
    "pillow": Version("10.2.0"),
    "protobuf": Version("4.25.8"),
    "requests": Version("2.33.0"),
    "sympy": Version("1.12"),
    "urllib3": Version("2.5.0"),
}

MINIMUM_SAFE_MANIFEST_FLOORS = {
    "kokoro-onnx": Version("0.5.0"),
    "pillow": Version("12.1.1"),
    "rapidocr-onnxruntime": Version("1.4.4"),
    "requests": Version("2.33.0"),
}

OPTIONAL_SAFE_LOCK_VERSIONS = {
    "zipp": Version("3.19.1"),
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


def _manifest_requirements() -> dict[str, Requirement]:
    pyproject_payload = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    dependencies = pyproject_payload["project"]["dependencies"]

    requirements_lines = [
        line.strip()
        for line in (ROOT / "requirements.txt").read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ]

    parsed_requirements = [Requirement(item) for item in dependencies + requirements_lines]
    return {requirement.name: requirement for requirement in parsed_requirements}


def _requirement_lower_bound(requirement: Requirement) -> Version | None:
    lower_bounds = [Version(specifier.version) for specifier in requirement.specifier if specifier.operator == ">="]
    if not lower_bounds:
        return None
    return max(lower_bounds)


def _locked_package_versions() -> dict[str, Version]:
    lock_payload = tomllib.loads((ROOT / "uv.lock").read_text(encoding="utf-8"))
    packages = lock_payload.get("package", [])
    return {
        package["name"]: Version(package["version"])
        for package in packages
        if "name" in package and "version" in package
    }


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


def test_python_manifests_and_lockfile_hold_safe_dependency_floors() -> None:
    manifest_requirements = _manifest_requirements()
    locked_versions = _locked_package_versions()

    for package_name, minimum_version in MINIMUM_SAFE_MANIFEST_FLOORS.items():
        requirement = manifest_requirements[package_name]
        lower_bound = _requirement_lower_bound(requirement)
        assert lower_bound is not None, f"{package_name} must declare an explicit lower bound"
        assert lower_bound >= minimum_version, (
            f"{package_name} lower bound regressed to {lower_bound}; expected >= {minimum_version}"
        )

    for package_name, minimum_version in MINIMUM_SAFE_LOCK_VERSIONS.items():
        locked_version = locked_versions.get(package_name)
        assert locked_version is not None, f"{package_name} must stay present in uv.lock"
        assert locked_version >= minimum_version, (
            f"{package_name} resolved version regressed to {locked_version}; expected >= {minimum_version}"
        )

    for package_name, minimum_version in OPTIONAL_SAFE_LOCK_VERSIONS.items():
        locked_version = locked_versions.get(package_name)
        if locked_version is None:
            continue
        assert locked_version >= minimum_version, (
            f"{package_name} resolved version regressed to {locked_version}; expected >= {minimum_version}"
        )
