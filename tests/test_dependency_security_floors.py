"""Security floors for the locked Python dependency set (M1-E7-T2).

Every package below had published advisories that affect the releases under its
floor. The floor is the lowest release that fixes all of them, so neither a
re-lock nor a hand edit of ``uv.lock`` can quietly bring an affected version
back, and a direct dependency's lower bound in ``pyproject.toml`` (mirrored by
``requirements.txt``) cannot allow one either.

``pip-audit --strict`` in ``security.yml`` and ``release.yml`` stays the gate for
advisories published later. This module is the offline guard for the ones
already fixed; docs/engineering/SUPPLY_CHAIN_TRIAGE.md §3-§5 has the triage.
"""

from __future__ import annotations

import re
import tomllib
from pathlib import Path

import pytest
from packaging.requirements import Requirement
from packaging.utils import canonicalize_name
from packaging.version import Version

ROOT = Path(__file__).resolve().parents[1]

# The images that install the locked Python dependencies with their own pinned pip.
PYTHON_IMAGE_DOCKERFILES = ("Dockerfile", "Dockerfile.runtime-kernel")

# package -> (lowest release that fixes every listed advisory, advisories)
SECURITY_FLOORS: dict[str, tuple[str, str]] = {
    "aiohttp": (
        "3.14.4",
        "22 advisories, among them GHSA-5wr8-gcqf-gqf3, GHSA-2g87-pp6c-29x5 and GHSA-cq5v-8q36-5273",
    ),
    "asyncssh": ("2.24.0", "GHSA-2wxc-x7rj-hg8f, GHSA-rw4j-r22c-9gc3"),
    # 2026.10.18 fixes the advisory but also drops the unaffected emSign roots,
    # which 2026.10.19 restores.
    "certifi": ("2026.10.19", "GHSA-6q48-6c7w-9gw2"),
    "cryptography": ("48.0.1", "GHSA-537c-gmf6-5ccf"),
    "multidict": ("6.9.1", "GHSA-54p9-h82j-f925"),
    # The dev group's pip (via pip-audit) and the pip each Python image pins.
    "pip": ("26.2", "GHSA-qwm4-qh6w-59xr, GHSA-wf93-45jw-7689"),
    "pypdf": ("6.21.4", "45 advisories, among them GHSA-5849-834g-hvw5 and GHSA-jr96-gvgh-j3r4"),
    "urllib3": ("2.8.0", "GHSA-vxq7-64xx-v4gw, GHSA-8988-9cw3-xx77, GHSA-gh4c-6fx4-qh6g"),
}


def _locked_versions() -> dict[str, list[Version]]:
    lock = tomllib.loads((ROOT / "uv.lock").read_text(encoding="utf-8"))
    versions: dict[str, list[Version]] = {}
    for package in lock["package"]:
        if "version" in package:
            versions.setdefault(canonicalize_name(package["name"]), []).append(Version(package["version"]))
    return versions


def _declared_requirements() -> list[tuple[str, Requirement]]:
    project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    declared: list[tuple[str, Requirement]] = [
        ("[project.dependencies]", Requirement(spec)) for spec in project["project"]["dependencies"]
    ]
    for extra, specs in project["project"].get("optional-dependencies", {}).items():
        declared.extend((f"[project.optional-dependencies.{extra}]", Requirement(spec)) for spec in specs)
    for group, specs in project.get("dependency-groups", {}).items():
        declared.extend((f"[dependency-groups.{group}]", Requirement(spec)) for spec in specs if isinstance(spec, str))
    return declared


def _lowest_allowed(requirement: Requirement) -> Version | None:
    bounds = [Version(spec.version) for spec in requirement.specifier if spec.operator in {">=", "==", "~=", "==="}]
    return max(bounds) if bounds else None


def test_security_floor_names_are_canonical() -> None:
    assert all(name == canonicalize_name(name) for name in SECURITY_FLOORS)


@pytest.mark.parametrize("package", sorted(SECURITY_FLOORS))
def test_locked_versions_meet_security_floor(package: str) -> None:
    floor, advisories = SECURITY_FLOORS[package]
    locked = _locked_versions().get(package)

    assert locked, f"{package} is no longer in uv.lock; drop its security floor if it left the tree on purpose"
    below = [str(version) for version in locked if version < Version(floor)]
    assert not below, f"uv.lock pins {package} {below}, below the security floor {floor} ({advisories})"


def test_direct_dependency_lower_bounds_meet_security_floors() -> None:
    checked: list[str] = []
    for table, requirement in _declared_requirements():
        name = canonicalize_name(requirement.name)
        if name not in SECURITY_FLOORS:
            continue
        floor, advisories = SECURITY_FLOORS[name]
        lowest = _lowest_allowed(requirement)
        assert lowest is not None, f"{table} {requirement} has no lower bound; it must be >= {floor} ({advisories})"
        assert lowest >= Version(floor), (
            f"{table} {requirement} still allows {lowest}, below the security floor {floor} ({advisories})"
        )
        checked.append(name)

    # The direct dependencies whose floors this task raised; a rename or a
    # dropped entry must not make the check above vacuous.
    assert {"aiohttp", "asyncssh", "cryptography", "pypdf", "urllib3"} <= set(checked)


@pytest.mark.parametrize("dockerfile", PYTHON_IMAGE_DOCKERFILES)
def test_python_image_pip_pin_meets_security_floor(dockerfile: str) -> None:
    floor, advisories = SECURITY_FLOORS["pip"]
    pins = re.findall(r"\bpip==(\S+)", (ROOT / dockerfile).read_text(encoding="utf-8"))

    assert pins, f"{dockerfile} must pin the pip it installs"
    below = [pin for pin in pins if Version(pin) < Version(floor)]
    assert not below, f"{dockerfile} pins pip {below}, below the security floor {floor} ({advisories})"
