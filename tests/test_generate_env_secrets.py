"""scripts/generate_env_secrets.py: safe, idempotent secret generation for manual installs."""

from __future__ import annotations

import importlib.util
import stat
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location("generate_env_secrets", ROOT / "scripts" / "generate_env_secrets.py")
assert _spec and _spec.loader
gen = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(gen)

AUTH_KEYS = ("CONTROL_PLANE_API_TOKEN", "RUNTIME_LOCAL_UI_TOKEN", "WEB_OPERATOR_SESSION_SECRET")


def _env_values(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if line and not line.startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            values[key] = value
    return values


@pytest.fixture
def workdir(tmp_path: Path) -> Path:
    (tmp_path / ".env.example").write_text((ROOT / ".env.example").read_text(encoding="utf-8"), encoding="utf-8")
    return tmp_path


def _run(workdir: Path, *extra: str) -> int:
    return gen.main(["--env-file", str(workdir / ".env"), "--template", str(workdir / ".env.example"), *extra])


def test_new_install_replaces_every_placeholder_with_private_file(workdir: Path) -> None:
    assert _run(workdir) == 0

    env = workdir / ".env"
    assert stat.S_IMODE(env.stat().st_mode) == 0o600
    assert "replace-with-" not in "\n".join(
        line for line in env.read_text(encoding="utf-8").splitlines() if not line.startswith("#")
    )
    values = _env_values(env)
    for key in (*AUTH_KEYS, "POSTGRES_PASSWORD", "S3_SECRET_ACCESS_KEY"):
        assert len(values[key]) >= 32, key
    assert len(values["S3_ACCESS_KEY_ID"]) == 20
    assert values["S3_ACCESS_KEY_ID"].isalnum()


def test_rerun_never_changes_existing_values(workdir: Path) -> None:
    assert _run(workdir) == 0
    first = (workdir / ".env").read_text(encoding="utf-8")

    assert _run(workdir) == 0

    assert (workdir / ".env").read_text(encoding="utf-8") == first


def test_existing_install_replaces_only_auth_placeholders_by_default(workdir: Path) -> None:
    env = workdir / ".env"
    text = (workdir / ".env.example").read_text(encoding="utf-8")
    env.write_text(text.replace("CONTROL_PLANE_PORT=8090", "CONTROL_PLANE_PORT=9999"), encoding="utf-8")

    assert _run(workdir) == 0

    values = _env_values(env)
    for key in AUTH_KEYS:
        assert not values[key].startswith("replace-with-"), key
    # Storage credentials must keep matching data already on disk.
    assert values["POSTGRES_PASSWORD"].startswith("replace-with-")
    assert values["S3_SECRET_ACCESS_KEY"].startswith("replace-with-")
    assert values["CONTROL_PLANE_PORT"] == "9999"
    assert stat.S_IMODE(env.stat().st_mode) == 0o600


def test_existing_install_replaces_storage_placeholders_with_all_flag(workdir: Path) -> None:
    env = workdir / ".env"
    env.write_text((workdir / ".env.example").read_text(encoding="utf-8"), encoding="utf-8")

    assert _run(workdir, "--all") == 0

    values = _env_values(env)
    assert not values["POSTGRES_PASSWORD"].startswith("replace-with-")
    assert not values["S3_ACCESS_KEY_ID"].startswith("replace-with-")


def test_temp_file_does_not_follow_a_planted_symlink(workdir: Path) -> None:
    victim = workdir / "victim.txt"
    victim.write_text("keep me", encoding="utf-8")
    (workdir / "..env.tmp").symlink_to(victim)
    (workdir / ".env.tmp").symlink_to(victim)

    assert _run(workdir) == 0

    assert victim.read_text(encoding="utf-8") == "keep me"
    assert not (workdir / ".env").is_symlink()


def test_remaining_placeholders_detects_forms_koda_rejects() -> None:
    text = "\n".join(
        [
            'QUOTED="replace-with-a-random-token"',
            "UPPER=REPLACE-WITH-something",
            "export EXPORTED=replace-with-x",
            "COMMENTED=replace-with-y # todo",
            "# IGNORED=replace-with-z",
            "REAL=0123456789abcdef",
        ]
    )

    assert gen.remaining_placeholders(text) == ["QUOTED", "UPPER", "EXPORTED", "COMMENTED"]


def test_comment_lines_are_left_untouched() -> None:
    placeholder = "CONTROL_PLANE_API_TOKEN=replace-with-a-random-token"
    text = f"# {placeholder}\n{placeholder}\n"

    updated, replaced = gen.fill_placeholders(text)

    assert replaced == ["CONTROL_PLANE_API_TOKEN"]
    assert updated.startswith(f"# {placeholder}\n")
