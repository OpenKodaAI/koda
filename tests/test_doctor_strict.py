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
import re
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


# A stack where every basic check except the storage-placeholder one passes, so a
# test can tell that check's effect on the overall result apart from the rest.
_HEALTHY_ENV: dict[str, str] = {
    "CONTROL_PLANE_API_TOKEN": "c" * 64,
    "RUNTIME_LOCAL_UI_TOKEN": "r" * 64,
    "KNOWLEDGE_V2_POSTGRES_DSN": "postgresql://koda:4b1f0c2e9d8a7f6e5d4c3b2a19081726@127.0.0.1:5432/koda",
    "KNOWLEDGE_V2_S3_ENDPOINT_URL": "http://127.0.0.1:8333",
    "KNOWLEDGE_V2_S3_BUCKET": "koda-objects",
    "KNOWLEDGE_V2_S3_ACCESS_KEY_ID": "a1b2c3d4e5f6a7b8c9d0",
    "KNOWLEDGE_V2_S3_SECRET_ACCESS_KEY": "9f8e7d6c5b4a39281706f5e4d3c2b1a0",
}
_PLACEHOLDER_STORAGE_ENV = (
    "POSTGRES_PASSWORD=replace-with-a-random-postgres-password\n"
    "S3_ACCESS_KEY_ID=replace-with-a-random-object-storage-access-key\n"
    "S3_SECRET_ACCESS_KEY='REPLACE-WITH-a-random-object-storage-secret'\n"
)


def _stub_reachable_stack(doctor_module, monkeypatch: pytest.MonkeyPatch) -> None:
    """Every socket, HTTP and sandbox probe passes, so only the env-driven checks decide ``ok``."""
    monkeypatch.setattr(
        doctor_module, "check_socket", lambda host, port, **_kw: {"ok": True, "host": host, "port": port}
    )
    monkeypatch.setattr(doctor_module, "fetch_json", lambda *_args, **_kwargs: {"status": "ok"})
    monkeypatch.setattr(
        doctor_module, "fetch_status", lambda *_args, **_kwargs: {"status": 200, "content_type": "text/html"}
    )
    monkeypatch.setattr(doctor_module, "build_sandbox_doctor", lambda _env: {"status": "passed", "checks": []})


def _healthy_doctor(doctor_module, monkeypatch: pytest.MonkeyPatch, env: dict[str, str]) -> dict:
    _stub_reachable_stack(doctor_module, monkeypatch)
    return doctor_module.run_doctor(env={**_HEALTHY_ENV, **env}, base_url="http://127.0.0.1:8090")


def _failing_checks(result: dict) -> list[str]:
    return [c["name"] for c in result["checks"] if not c.get("ok")]


def _healthy_env_text() -> str:
    return "".join(f"{key}={value}\n" for key, value in _HEALTHY_ENV.items())


def test_healthy_stub_stack_passes_doctor(doctor_module, monkeypatch: pytest.MonkeyPatch) -> None:
    """Baseline for the tests below: without placeholders nothing fails."""
    result = _healthy_doctor(doctor_module, monkeypatch, {})
    assert _failing_checks(result) == []
    assert result["ok"] is True


def test_doctor_fails_on_placeholder_postgres_and_s3_secrets(
    doctor_module, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text(_PLACEHOLDER_STORAGE_ENV)
    result = _healthy_doctor(doctor_module, monkeypatch, doctor_module.load_env_file(env_file))

    check = _by_name(result["checks"], "storage_secrets_not_placeholders")
    assert check["ok"] is False
    assert result["ok"] is False
    # The placeholders are the only problem with this stack, so they alone fail doctor.
    assert _failing_checks(result) == ["storage_secrets_not_placeholders"]
    assert check["placeholder_keys"] == ["POSTGRES_PASSWORD", "S3_ACCESS_KEY_ID", "S3_SECRET_ACCESS_KEY"]
    assert check["rotation_command"] == "python3 scripts/generate_env_secrets.py --all"
    assert check["rotation_command"] in check["user_action"]
    assert "docs/install/local.md#rotating-placeholder-postgres-and-object-storage-secrets" in check["user_action"]
    # Names only: the check never echoes a secret value.
    assert "replace-with-" not in json.dumps(check).lower()


def test_doctor_cli_exits_nonzero_only_while_storage_secrets_are_placeholders(
    doctor_module, monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _stub_reachable_stack(doctor_module, monkeypatch)
    env_file = tmp_path / ".env"
    env_file.write_text(_healthy_env_text() + _PLACEHOLDER_STORAGE_ENV)

    assert doctor_module.main(["--env-file", str(env_file)]) == 1
    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is False
    assert _failing_checks(payload) == ["storage_secrets_not_placeholders"]

    env_file.write_text(
        _healthy_env_text()
        + "POSTGRES_PASSWORD=4b1f0c2e9d8a7f6e5d4c3b2a19081726\n"
        + "S3_ACCESS_KEY_ID=a1b2c3d4e5f6a7b8c9d0\n"
        + "S3_SECRET_ACCESS_KEY=9f8e7d6c5b4a39281706f5e4d3c2b1a0\n"
    )
    assert doctor_module.main(["--env-file", str(env_file)]) == 0
    assert json.loads(capsys.readouterr().out)["ok"] is True


def test_doctor_rotation_command_clears_every_placeholder_form_it_reports(
    doctor_module, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Following doctor's rotation_command must make the check pass for every form doctor flags."""
    spec = importlib.util.spec_from_file_location(
        "generate_env_secrets_under_test", REPO_ROOT / "scripts" / "generate_env_secrets.py"
    )
    assert spec is not None and spec.loader is not None
    generator = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(generator)

    env_file = tmp_path / ".env"
    env_file.write_text(
        'POSTGRES_PASSWORD="replace-with-a-random-postgres-password"\n'
        "export S3_ACCESS_KEY_ID=REPLACE-WITH-a-random-object-storage-access-key\n"
        "S3_SECRET_ACCESS_KEY=replace-with-a-random-object-storage-secret # rotate me\n"
    )
    before = _healthy_doctor(doctor_module, monkeypatch, doctor_module.load_env_file(env_file))
    check = _by_name(before["checks"], "storage_secrets_not_placeholders")
    assert check["placeholder_keys"] == ["POSTGRES_PASSWORD", "S3_ACCESS_KEY_ID", "S3_SECRET_ACCESS_KEY"]
    assert check["rotation_command"].endswith("generate_env_secrets.py --all")

    assert generator.main(["--env-file", str(env_file), "--template", str(tmp_path / "missing"), "--all"]) == 0

    rotated = doctor_module.load_env_file(env_file)
    after = _healthy_doctor(doctor_module, monkeypatch, rotated)
    assert _by_name(after["checks"], "storage_secrets_not_placeholders")["ok"] is True
    assert after["ok"] is True
    # docs/install/local.md feeds `sed -n 's/^POSTGRES_PASSWORD=//p' .env` to ALTER USER, so that must
    # read back exactly the password Compose (and doctor) take from the rotated file.
    sed_value = re.search(r"^POSTGRES_PASSWORD=(.*)$", env_file.read_text(), re.MULTILINE)
    assert sed_value is not None
    assert sed_value.group(1) == rotated["POSTGRES_PASSWORD"]


def test_load_env_file_strips_the_export_prefix(doctor_module, tmp_path: Path) -> None:
    """Docker Compose reads ``export KEY=value``, so doctor must see KEY, not ``export KEY``."""
    env_file = tmp_path / ".env"
    env_file.write_text(
        "export POSTGRES_PASSWORD=replace-with-a-random-postgres-password\n"
        "export  CONTROL_PLANE_API_TOKEN='replace-with-a-random-token'\n"
        "EXPORTER_URL=http://collector:4318\n"
    )
    env = doctor_module.load_env_file(env_file)

    assert env == {
        "POSTGRES_PASSWORD": "replace-with-a-random-postgres-password",
        "CONTROL_PLANE_API_TOKEN": "replace-with-a-random-token",
        "EXPORTER_URL": "http://collector:4318",
    }
    check = doctor_module.check_storage_secrets(env)
    assert check["ok"] is False
    assert check["placeholder_keys"] == ["POSTGRES_PASSWORD"]
    strict = doctor_module.run_strict_hardening(env, env_file=env_file)
    assert _by_name(strict, "control_plane_api_token_strong")["ok"] is False


def test_doctor_reads_the_derived_runtime_storage_settings(doctor_module, monkeypatch: pytest.MonkeyPatch) -> None:
    env = {
        "KNOWLEDGE_V2_POSTGRES_DSN": "postgresql://koda:replace-with-a-random-postgres-password@db:5432/koda",
        "KNOWLEDGE_V2_S3_SECRET_ACCESS_KEY": "replace-with-a-random-object-storage-secret",
    }
    result = _healthy_doctor(doctor_module, monkeypatch, env)
    check = _by_name(result["checks"], "storage_secrets_not_placeholders")
    assert check["ok"] is False
    assert check["placeholder_keys"] == ["POSTGRES_PASSWORD", "S3_SECRET_ACCESS_KEY"]
    assert result["ok"] is False
    # The generator only rewrites values that start with the placeholder, so doctor says to edit these by hand.
    assert "KNOWLEDGE_V2_POSTGRES_DSN" in check["user_action"]


def test_doctor_storage_secret_check_passes_for_generated_values(
    doctor_module, monkeypatch: pytest.MonkeyPatch
) -> None:
    env = {
        "POSTGRES_PASSWORD": "4b1f0c2e9d8a7f6e5d4c3b2a19081726",
        "S3_ACCESS_KEY_ID": "a1b2c3d4e5f6a7b8c9d0",
        "S3_SECRET_ACCESS_KEY": "9f8e7d6c5b4a39281706f5e4d3c2b1a0",
    }
    result = _healthy_doctor(doctor_module, monkeypatch, env)
    check = _by_name(result["checks"], "storage_secrets_not_placeholders")
    assert check == {"name": "storage_secrets_not_placeholders", "ok": True, "placeholder_keys": []}
    assert result["ok"] is True


def test_doctor_storage_secret_sources_match_the_runtime_config(doctor_module) -> None:
    """doctor runs on the host without Koda's dependencies, so it keeps its own copy of the table."""
    from koda import config as config_mod

    assert doctor_module.STORAGE_SECRET_ENV_SOURCES == config_mod.STORAGE_SECRET_ENV_SOURCES
    assert doctor_module.PLACEHOLDER_SECRET_PREFIX == config_mod.PLACEHOLDER_SECRET_PREFIX
    assert config_mod.PLACEHOLDER_SECRET_ROTATION_URL.endswith(doctor_module.PLACEHOLDER_SECRET_ROTATION_DOC)
