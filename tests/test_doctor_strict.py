"""Verify the doctor.py --strict hardening gate.

The strict gate matches ``docs/operations/hardening.md``. These tests
pin the contract: each check fails loud when the expected condition
isn't met, and the overall doctor exit code reflects ANY failed
check. A future refactor that drops a check would surface immediately.
"""

from __future__ import annotations

import importlib.util
import json
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


def test_strong_token_check_rejects_uppercase_placeholder(doctor_module, tmp_path: Path) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text("CONTROL_PLANE_API_TOKEN=REPLACE-WITH-" + ("x" * 40) + "\n")
    env = doctor_module.load_env_file(env_file)
    checks = doctor_module.run_strict_hardening(env, env_file=env_file)
    assert _by_name(checks, "control_plane_api_token_strong")["ok"] is False


def test_basic_token_checks_do_not_accept_placeholders(doctor_module, monkeypatch: pytest.MonkeyPatch) -> None:
    # Socket probes are irrelevant here; HTTP probes hit a closed local port and fail fast.
    monkeypatch.setattr(doctor_module, "check_socket", lambda *_args, **_kwargs: {"ok": False})
    env = {
        "CONTROL_PLANE_API_TOKEN": "replace-with-a-random-token",
        "RUNTIME_LOCAL_UI_TOKEN": "replace-with-a-random-runtime-token",
    }
    result = doctor_module.run_doctor(env=env, base_url="http://127.0.0.1:1")
    assert _by_name(result["checks"], "control_plane_api_token")["ok"] is False
    assert _by_name(result["checks"], "runtime_local_ui_token")["ok"] is False


def _offline_doctor(doctor_module, monkeypatch: pytest.MonkeyPatch, env: dict[str, str]) -> dict:
    # Socket probes are irrelevant here; HTTP probes hit a closed local port and fail fast.
    monkeypatch.setattr(doctor_module, "check_socket", lambda *_args, **_kwargs: {"ok": False})
    return doctor_module.run_doctor(env=env, base_url="http://127.0.0.1:1")


def test_doctor_fails_on_placeholder_postgres_and_s3_secrets(
    doctor_module, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text(
        "POSTGRES_PASSWORD=replace-with-a-random-postgres-password\n"
        "S3_ACCESS_KEY_ID=replace-with-a-random-object-storage-access-key\n"
        "S3_SECRET_ACCESS_KEY='REPLACE-WITH-a-random-object-storage-secret'\n"
    )
    result = _offline_doctor(doctor_module, monkeypatch, doctor_module.load_env_file(env_file))

    check = _by_name(result["checks"], "storage_secrets_not_placeholders")
    assert check["ok"] is False
    assert result["ok"] is False
    assert check["placeholder_keys"] == ["POSTGRES_PASSWORD", "S3_ACCESS_KEY_ID", "S3_SECRET_ACCESS_KEY"]
    assert check["rotation_command"] == "python3 scripts/generate_env_secrets.py --all"
    assert check["rotation_command"] in check["user_action"]
    assert "docs/install/local.md#rotating-placeholder-postgres-and-object-storage-secrets" in check["user_action"]
    # Names only: the check never echoes a secret value.
    assert "replace-with-" not in json.dumps(check).lower()


def test_doctor_reads_the_derived_runtime_storage_settings(doctor_module, monkeypatch: pytest.MonkeyPatch) -> None:
    env = {
        "KNOWLEDGE_V2_POSTGRES_DSN": "postgresql://koda:replace-with-a-random-postgres-password@db:5432/koda",
        "KNOWLEDGE_V2_S3_SECRET_ACCESS_KEY": "replace-with-a-random-object-storage-secret",
    }
    check = _by_name(_offline_doctor(doctor_module, monkeypatch, env)["checks"], "storage_secrets_not_placeholders")
    assert check["ok"] is False
    assert check["placeholder_keys"] == ["POSTGRES_PASSWORD", "S3_SECRET_ACCESS_KEY"]


def test_doctor_storage_secret_check_passes_for_generated_values(
    doctor_module, monkeypatch: pytest.MonkeyPatch
) -> None:
    env = {
        "POSTGRES_PASSWORD": "4b1f0c2e9d8a7f6e5d4c3b2a19081726",
        "S3_ACCESS_KEY_ID": "a1b2c3d4e5f6a7b8c9d0",
        "S3_SECRET_ACCESS_KEY": "9f8e7d6c5b4a39281706f5e4d3c2b1a0",
    }
    check = _by_name(_offline_doctor(doctor_module, monkeypatch, env)["checks"], "storage_secrets_not_placeholders")
    assert check == {"name": "storage_secrets_not_placeholders", "ok": True, "placeholder_keys": []}


def test_doctor_storage_secret_sources_match_the_runtime_config(doctor_module) -> None:
    """doctor runs on the host without Koda's dependencies, so it keeps its own copy of the table."""
    from koda import config as config_mod

    assert doctor_module.STORAGE_SECRET_ENV_SOURCES == config_mod.STORAGE_SECRET_ENV_SOURCES
    assert doctor_module.PLACEHOLDER_SECRET_PREFIX == config_mod.PLACEHOLDER_SECRET_PREFIX
    assert config_mod.PLACEHOLDER_SECRET_ROTATION_URL.endswith(doctor_module.PLACEHOLDER_SECRET_ROTATION_DOC)
