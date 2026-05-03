"""Phase F — verify the doctor.py --strict hardening gate.

The strict gate matches ``docs/operations/hardening.md``. These tests
pin the contract: each check fails loud when the expected condition
isn't met, and the overall doctor exit code reflects ANY failed
check. A future refactor that drops a check would surface immediately.
"""

from __future__ import annotations

import importlib.util
import os
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture(scope="module")
def doctor_module():
    """Load scripts/doctor.py as a module so we can call its
    functions directly without spawning a subprocess."""
    spec = importlib.util.spec_from_file_location("doctor_under_test", REPO_ROOT / "scripts" / "doctor.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _by_name(checks: list[dict], name: str) -> dict:
    for c in checks:
        if c.get("name") == name:
            return c
    raise AssertionError(f"check {name!r} missing from results: {[c.get('name') for c in checks]}")


def test_strong_token_check_passes_for_random_32_byte_value(doctor_module, tmp_path: Path) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text("CONTROL_PLANE_API_TOKEN=" + ("x" * 64) + "\n")
    env_file.chmod(0o600)
    env = doctor_module.load_env_file(env_file)
    checks = doctor_module.run_strict_hardening(env, env_file=env_file)
    assert _by_name(checks, "control_plane_api_token_strong")["ok"] is True


def test_strong_token_check_fails_for_default_placeholder(doctor_module, tmp_path: Path) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text("CONTROL_PLANE_API_TOKEN=replace-with-a-random-token\n")
    env = doctor_module.load_env_file(env_file)
    checks = doctor_module.run_strict_hardening(env, env_file=env_file)
    assert _by_name(checks, "control_plane_api_token_strong")["ok"] is False


def test_browser_private_network_disabled_by_default(doctor_module, tmp_path: Path) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text("# no browser config\n")
    env = doctor_module.load_env_file(env_file)
    checks = doctor_module.run_strict_hardening(env, env_file=env_file)
    assert _by_name(checks, "browser_private_network_disabled")["ok"] is True


def test_browser_private_network_enabled_fails_strict(doctor_module, tmp_path: Path) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text("BROWSER_ALLOW_PRIVATE_NETWORK=true\n")
    env = doctor_module.load_env_file(env_file)
    checks = doctor_module.run_strict_hardening(env, env_file=env_file)
    assert _by_name(checks, "browser_private_network_disabled")["ok"] is False


def test_audit_retention_under_90_days_fails(doctor_module, tmp_path: Path) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text("AUDIT_RETENTION_DAYS=30\n")
    env = doctor_module.load_env_file(env_file)
    checks = doctor_module.run_strict_hardening(env, env_file=env_file)
    assert _by_name(checks, "audit_retention_at_least_90_days")["ok"] is False


def test_loopback_bootstrap_must_be_disabled_in_production(doctor_module, tmp_path: Path) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text("ALLOW_LOOPBACK_BOOTSTRAP=true\n")
    env = doctor_module.load_env_file(env_file)
    checks = doctor_module.run_strict_hardening(env, env_file=env_file)
    assert _by_name(checks, "loopback_bootstrap_disabled_in_production")["ok"] is False


def test_allowed_user_ids_required(doctor_module, tmp_path: Path) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text("ALLOWED_USER_IDS=\n")
    env = doctor_module.load_env_file(env_file)
    checks = doctor_module.run_strict_hardening(env, env_file=env_file)
    assert _by_name(checks, "allowed_user_ids_set")["ok"] is False
    env_file.write_text("ALLOWED_USER_IDS=123,456\n")
    env = doctor_module.load_env_file(env_file)
    checks = doctor_module.run_strict_hardening(env, env_file=env_file)
    assert _by_name(checks, "allowed_user_ids_set")["ok"] is True


def test_strict_emits_all_expected_check_names(doctor_module, tmp_path: Path) -> None:
    """A future refactor that drops a check should surface here. The
    list mirrors the hardening checklist."""
    env_file = tmp_path / ".env"
    env_file.write_text("\n")
    env = doctor_module.load_env_file(env_file)
    checks = doctor_module.run_strict_hardening(env, env_file=env_file)
    names = {c["name"] for c in checks}
    expected = {
        "state_root_owner_only_perms",
        "master_key_perms_0600",
        "env_file_perms_0600",
        "control_plane_api_token_strong",
        "web_operator_session_secret_strong",
        "runtime_local_ui_token_strong",
        "allowed_user_ids_set",
        "loopback_bootstrap_disabled_in_production",
        "browser_private_network_disabled",
        "audit_retention_at_least_90_days",
    }
    if os.uname().sysname == "Linux":
        expected.add("cgroup_root_writable_for_isolation")
    missing = expected - names
    assert not missing, f"--strict dropped checks: {missing}"


def test_argparse_accepts_strict_flag(doctor_module) -> None:
    parser = doctor_module._build_parser()
    args = parser.parse_args(["--strict"])
    assert args.strict is True
    args = parser.parse_args([])
    assert args.strict is False
