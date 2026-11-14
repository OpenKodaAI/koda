"""`scripts/doctor.py` reads the storage settings the way Koda receives them.

Docker Compose builds the app's Postgres DSN from `POSTGRES_*` and passes the
`S3_*` keys on as `KNOWLEDGE_V2_S3_*` (docker-compose.yml, `app.environment`),
so a `.env` generated from `.env.example` defines only the operator-facing
names. Compose keeps Postgres and SeaweedFS on its internal network, so doctor
probes them from the app container. A native install sets the runtime names
directly and may run without object storage (`OBJECT_STORAGE_REQUIRED=false`).
"""

from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path
from types import ModuleType
from typing import Any
from urllib.parse import unquote, urlparse

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
OBJECT_STORAGE_CHECKS = (
    "object_storage_endpoint",
    "object_storage_bucket",
    "object_storage_access_key",
    "object_storage_secret_key",
    "object_storage_socket",
)


def _load_script(name: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(f"{name}_under_test", REPO_ROOT / "scripts" / f"{name}.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def doctor() -> ModuleType:
    return _load_script("doctor")


def _by_name(checks: list[dict[str, Any]], name: str) -> dict[str, Any]:
    for check in checks:
        if check.get("name") == name:
            return check
    raise AssertionError(f"check {name!r} missing from results: {[c.get('name') for c in checks]}")


def _failing(payload: dict[str, Any]) -> list[str]:
    return [check["name"] for check in payload["checks"] if not check.get("ok")]


def _stub_http_and_sandbox(doctor: ModuleType, monkeypatch: pytest.MonkeyPatch) -> None:
    """The control plane and dashboard answer, so only the storage checks decide the result."""
    monkeypatch.setattr(doctor, "fetch_json", lambda *_args, **_kwargs: {"status": "healthy"})
    monkeypatch.setattr(doctor, "fetch_status", lambda *_args, **_kwargs: {"status": 200, "content_type": "text/html"})
    monkeypatch.setattr(doctor, "build_sandbox_doctor", lambda _env: {"status": "passed", "checks": []})


def _only_loopback_resolves(doctor: ModuleType, monkeypatch: pytest.MonkeyPatch) -> None:
    """This host does not resolve compose service names such as `postgres` or `seaweedfs`."""
    monkeypatch.setattr(doctor, "host_resolves", lambda host: host in {"127.0.0.1", "localhost", "::1"})


def _fake_docker(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, *, exit_code: int = 0, stderr: str = "") -> Path:
    """A `docker` on PATH that logs its working directory and arguments, prints ``stderr`` and exits with ``exit_code``.

    Each call is logged as a `cwd=<directory>` line, one line per argument, then `--`.
    """
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir(exist_ok=True)
    log = tmp_path / "docker-calls.log"
    stderr_file = tmp_path / "docker-stderr.txt"
    stderr_file.write_text(stderr, encoding="utf-8")
    script = bin_dir / "docker"
    script.write_text(
        "#!/bin/sh\n"
        f'printf "cwd=%s\\n" "$(pwd -P)" >> "{log}"\n'
        f'printf "%s\\n" "$@" >> "{log}"\n'
        f'echo "--" >> "{log}"\n'
        f'cat "{stderr_file}" >&2\n'
        f"exit {exit_code}\n",
        encoding="utf-8",
    )
    script.chmod(0o755)
    monkeypatch.setenv("PATH", f"{bin_dir}{os.pathsep}{os.environ.get('PATH', '')}")
    return log


def _docker_runs(log: Path) -> list[tuple[str, list[str]]]:
    """Each logged call as (working directory, arguments)."""
    runs: list[tuple[str, list[str]]] = []
    for line in log.read_text(encoding="utf-8").splitlines():
        if line.startswith("cwd="):
            runs.append((line.removeprefix("cwd="), []))
        elif line != "--":
            runs[-1][1].append(line)
    return runs


def _docker_calls(log: Path) -> list[list[str]]:
    return [arguments for _cwd, arguments in _docker_runs(log)]


def _generated_env(tmp_path: Path) -> Path:
    """A `.env` made the documented way: `scripts/generate_env_secrets.py` from `.env.example`."""
    generator = _load_script("generate_env_secrets")
    env_file = tmp_path / ".env"
    assert generator.main(["--env-file", str(env_file), "--template", str(REPO_ROOT / ".env.example")]) == 0
    return env_file


def test_doctor_passes_the_storage_and_dsn_checks_on_a_generated_env(
    doctor: ModuleType, monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    env_file = _generated_env(tmp_path)
    capsys.readouterr()  # the generator's own output
    env = doctor.load_env_file(env_file)
    # The generated file names only what the operator edits; compose derives the runtime settings.
    assert "KNOWLEDGE_V2_POSTGRES_DSN" not in env
    assert "KNOWLEDGE_V2_S3_ACCESS_KEY_ID" not in env
    _stub_http_and_sandbox(doctor, monkeypatch)
    _only_loopback_resolves(doctor, monkeypatch)
    log = _fake_docker(tmp_path, monkeypatch)
    # Doctor runs from somewhere else than the .env's directory.
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    monkeypatch.chdir(elsewhere)

    assert doctor.main(["--env-file", str(env_file)]) == 0
    payload = json.loads(capsys.readouterr().out)

    assert _failing(payload) == []
    assert _by_name(payload["checks"], "postgres_dsn") == {
        "name": "postgres_dsn",
        "ok": True,
        "source": ["POSTGRES_USER", "POSTGRES_PASSWORD", "POSTGRES_DB"],
    }
    assert _by_name(payload["checks"], "object_storage_access_key")["source"] == "S3_ACCESS_KEY_ID"
    assert _by_name(payload["checks"], "object_storage_secret_key")["source"] == "S3_SECRET_ACCESS_KEY"
    postgres = _by_name(payload["checks"], "postgres_socket")
    storage = _by_name(payload["checks"], "object_storage_socket")
    assert (postgres["host"], postgres["port"], postgres["via"]) == ("postgres", 5432, "docker compose exec app")
    assert (storage["host"], storage["port"], storage["via"]) == ("seaweedfs", 8333, "docker compose exec app")

    # Both probes ran inside the app container of this .env's compose project.
    calls = _docker_calls(log)
    assert [call[call.index("exec") + 4 :] for call in calls] == [
        ["-c", doctor.COMPOSE_TCP_PROBE, "postgres", "5432", "2.0"],
        ["-c", doctor.COMPOSE_TCP_PROBE, "seaweedfs", "8333", "2.0"],
    ]
    for call in calls:
        assert call[: call.index("exec") + 4] == [
            "compose",
            "--env-file",
            str(env_file.resolve()),
            "exec",
            "-T",
            "app",
            "python",
        ]
    # Compose resolves the project from the directory of the --env-file, as docs/install/local.md says.
    assert [cwd for cwd, _arguments in _docker_runs(log)] == [str(env_file.resolve().parent)] * 2
    # The probe never carries a secret.
    assert env["POSTGRES_PASSWORD"] not in log.read_text(encoding="utf-8")
    assert env["S3_SECRET_ACCESS_KEY"] not in log.read_text(encoding="utf-8")


def test_host_resolves_tells_a_resolvable_host_from_one_that_never_resolves(doctor: ModuleType) -> None:
    assert doctor.host_resolves("127.0.0.1") is True
    # RFC 6761: names under .invalid never resolve.
    assert doctor.host_resolves("koda-doctor-probe.invalid") is False


def test_probe_service_probes_from_the_app_container_only_when_this_host_cannot_resolve(
    doctor: ModuleType, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """The real resolver decides; nothing stubs host_resolves here."""
    env_file = _generated_env(tmp_path)
    log = _fake_docker(tmp_path, monkeypatch)
    direct: list[tuple[str, int]] = []
    monkeypatch.setattr(
        doctor,
        "check_socket",
        lambda host, port, **_kw: direct.append((host, port)) or {"ok": True, "host": host, "port": port},
    )

    local = doctor.probe_service("127.0.0.1", 5432, env_file=env_file)
    remote = doctor.probe_service("koda-doctor-probe.invalid", 5432, env_file=env_file)

    assert direct == [("127.0.0.1", 5432)]
    assert "via" not in local
    assert remote == {"host": "koda-doctor-probe.invalid", "port": 5432, "via": "docker compose exec app", "ok": True}
    assert [call[-3:] for call in _docker_calls(log)] == [["koda-doctor-probe.invalid", "5432", "2.0"]]


def _break_env_line(env_file: Path, key: str, line: str) -> None:
    """Replace ``key``'s line in ``env_file`` with ``line``, as an operator's hand edit would."""
    lines = env_file.read_text(encoding="utf-8").splitlines()
    index = next(i for i, text in enumerate(lines) if text.startswith(f"{key}="))
    lines[index] = line
    env_file.write_text("\n".join(lines) + "\n", encoding="utf-8")


@pytest.mark.parametrize(
    ("env_line", "secret", "compose_error"),
    [
        (
            'POSTGRES_PASSWORD="Zq9SUPERSECRETpw7Xk',
            "Zq9SUPERSECRETpw7Xk",
            'failed to read <env_file>: line <line>: unterminated quoted value "Zq9SUPERSECRETpw7Xk',
        ),
        (
            "POSTGRES_PASSWORD=P@ss${2024}x7Kq",
            "P@ss${2024}x7Kq",
            'failed to read <env_file>: Invalid template: "P@ss${2024}x7Kq"',
        ),
    ],
    ids=["unterminated-quote", "invalid-template"],
)
def test_doctor_never_prints_a_secret_from_a_compose_parse_error(
    doctor: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    env_line: str,
    secret: str,
    compose_error: str,
) -> None:
    """Compose quotes the line of a .env it cannot parse, value included; doctor must not pass that on."""
    env_file = _generated_env(tmp_path)
    capsys.readouterr()
    _break_env_line(env_file, "POSTGRES_PASSWORD", env_line)
    line = env_file.read_text(encoding="utf-8").splitlines().index(env_line) + 1
    # Doctor's own reader still accepts the value and builds a DSN to the compose host `postgres`.
    assert doctor.load_env_file(env_file)["POSTGRES_PASSWORD"] == secret
    _stub_http_and_sandbox(doctor, monkeypatch)
    _only_loopback_resolves(doctor, monkeypatch)
    _fake_docker(
        tmp_path,
        monkeypatch,
        exit_code=15,
        stderr=compose_error.replace("<env_file>", str(env_file.resolve())).replace("<line>", str(line)) + "\n",
    )

    assert doctor.main(["--env-file", str(env_file)]) == 1
    output = capsys.readouterr()

    assert secret not in output.out
    assert secret not in output.err
    postgres = _by_name(json.loads(output.out)["checks"], "postgres_socket")
    assert postgres["ok"] is False
    assert f"docker compose could not parse {env_file.resolve()}" in postgres["error"]
    # The operator can see compose's own message, on their terminal rather than in doctor's report.
    assert f"docker compose --env-file {env_file.resolve()} config -q" in postgres["error"]


def test_doctor_redacts_configured_secrets_from_other_compose_errors(
    doctor: ModuleType, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    env_file = _generated_env(tmp_path)
    env = doctor.load_env_file(env_file)
    _stub_http_and_sandbox(doctor, monkeypatch)
    _only_loopback_resolves(doctor, monkeypatch)
    _fake_docker(
        tmp_path,
        monkeypatch,
        exit_code=1,
        stderr=(
            f"Error response from daemon: exec failed for {env['POSTGRES_PASSWORD']} and "
            f"{env['S3_SECRET_ACCESS_KEY']}\n"
        ),
    )

    payload = doctor.run_doctor(env=env, base_url="http://127.0.0.1:8090", env_file=env_file)

    error = _by_name(payload["checks"], "postgres_socket")["error"]
    assert env["POSTGRES_PASSWORD"] not in error
    assert env["S3_SECRET_ACCESS_KEY"] not in error
    assert error.endswith("failed: Error response from daemon: exec failed for [redacted] and [redacted]")


def test_compose_dsn_percent_encodes_every_component(doctor: ModuleType) -> None:
    """A hand-set password with URL delimiters still parses back to the compose host and the same password."""
    password = "p/a#ss@w:rd%?"
    dsn, sources, missing = doctor.resolve_postgres_dsn(
        {"POSTGRES_USER": "ko@da", "POSTGRES_PASSWORD": password, "POSTGRES_DB": "koda/db"}
    )

    assert (sources, missing) == (["POSTGRES_USER", "POSTGRES_PASSWORD", "POSTGRES_DB"], [])
    parsed = urlparse(dsn)
    assert (parsed.hostname, parsed.port) == ("postgres", 5432)
    assert doctor.parse_postgres_target(dsn) == ("postgres", 5432)
    assert (unquote(parsed.username or ""), unquote(parsed.password or "")) == ("ko@da", password)
    assert unquote(parsed.path.removeprefix("/")) == "koda/db"
    assert doctor._dsn_password(dsn) == password


def test_doctor_reports_a_compose_service_the_app_container_cannot_reach(
    doctor: ModuleType, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    env_file = _generated_env(tmp_path)
    _stub_http_and_sandbox(doctor, monkeypatch)
    _only_loopback_resolves(doctor, monkeypatch)
    _fake_docker(tmp_path, monkeypatch, exit_code=1, stderr='service "app" is not running')

    payload = doctor.run_doctor(env=doctor.load_env_file(env_file), base_url="http://127.0.0.1:8090", env_file=env_file)

    postgres = _by_name(payload["checks"], "postgres_socket")
    assert postgres["ok"] is False
    assert 'service "app" is not running' in postgres["error"]
    assert "postgres" in postgres["error"]
    assert payload["ok"] is False


def test_doctor_without_docker_names_the_unresolvable_host(
    doctor: ModuleType, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    env_file = _generated_env(tmp_path)
    _stub_http_and_sandbox(doctor, monkeypatch)
    _only_loopback_resolves(doctor, monkeypatch)
    empty_bin = tmp_path / "empty-bin"
    empty_bin.mkdir()
    monkeypatch.setenv("PATH", str(empty_bin))

    payload = doctor.run_doctor(env=doctor.load_env_file(env_file), base_url="http://127.0.0.1:8090", env_file=env_file)

    postgres = _by_name(payload["checks"], "postgres_socket")
    assert postgres["ok"] is False
    assert "postgres does not resolve on this host" in postgres["error"]


def test_an_explicit_dsn_wins_and_is_probed_from_this_host(doctor: ModuleType, monkeypatch: pytest.MonkeyPatch) -> None:
    """A native install sets KNOWLEDGE_V2_POSTGRES_DSN itself; doctor probes that host directly."""
    _stub_http_and_sandbox(doctor, monkeypatch)
    probed: list[tuple[str, int]] = []

    def check_socket(host: str, port: int, **_kwargs: Any) -> dict[str, Any]:
        probed.append((host, port))
        return {"ok": True, "host": host, "port": port}

    monkeypatch.setattr(doctor, "check_socket", check_socket)
    env = {
        "POSTGRES_USER": "koda",
        "POSTGRES_PASSWORD": "4b1f0c2e9d8a7f6e5d4c3b2a19081726",
        "POSTGRES_DB": "koda",
        "KNOWLEDGE_V2_POSTGRES_DSN": "postgresql://koda:4b1f0c2e9d8a7f6e5d4c3b2a19081726@127.0.0.1:55432/koda",
        "OBJECT_STORAGE_REQUIRED": "false",
    }

    payload = doctor.run_doctor(env=env, base_url="http://127.0.0.1:8090")

    assert _by_name(payload["checks"], "postgres_dsn")["source"] == ["KNOWLEDGE_V2_POSTGRES_DSN"]
    assert ("127.0.0.1", 55432) in probed
    assert "via" not in _by_name(payload["checks"], "postgres_socket")


@pytest.mark.parametrize(
    ("env", "missing"),
    [
        ({}, ["POSTGRES_USER", "POSTGRES_PASSWORD", "POSTGRES_DB"]),
        ({"POSTGRES_USER": "koda", "POSTGRES_DB": "koda"}, ["POSTGRES_PASSWORD"]),
    ],
    ids=["nothing-set", "no-password"],
)
def test_doctor_names_what_is_missing_for_the_dsn(
    doctor: ModuleType, monkeypatch: pytest.MonkeyPatch, env: dict[str, str], missing: list[str]
) -> None:
    _stub_http_and_sandbox(doctor, monkeypatch)
    monkeypatch.setattr(doctor, "check_socket", lambda host, port, **_kw: {"ok": True, "host": host, "port": port})

    payload = doctor.run_doctor(env=env, base_url="http://127.0.0.1:8090")

    dsn = _by_name(payload["checks"], "postgres_dsn")
    assert dsn["ok"] is False
    assert dsn["missing"] == missing
    assert "KNOWLEDGE_V2_POSTGRES_DSN" in dsn["error"]
    assert _by_name(payload["checks"], "postgres_socket")["ok"] is False
    assert payload["ok"] is False


_NATIVE_ENV = {
    "CONTROL_PLANE_API_TOKEN": "c" * 64,
    "RUNTIME_LOCAL_UI_TOKEN": "r" * 64,
    "KNOWLEDGE_V2_POSTGRES_DSN": "postgresql://koda:4b1f0c2e9d8a7f6e5d4c3b2a19081726@127.0.0.1:5432/koda",
}


@pytest.mark.parametrize("value", ["false", "FALSE", " False "])
def test_object_storage_checks_do_not_fail_doctor_when_object_storage_is_not_required(
    doctor: ModuleType, monkeypatch: pytest.MonkeyPatch, value: str
) -> None:
    _stub_http_and_sandbox(doctor, monkeypatch)
    monkeypatch.setattr(doctor, "check_socket", lambda host, port, **_kw: {"ok": True, "host": host, "port": port})

    payload = doctor.run_doctor(env={**_NATIVE_ENV, "OBJECT_STORAGE_REQUIRED": value}, base_url="http://127.0.0.1:8090")

    assert payload["ok"] is True
    for name in OBJECT_STORAGE_CHECKS:
        check = _by_name(payload["checks"], name)
        assert check["required"] is False, name
    # Still reported, so the operator sees what is not configured.
    assert _by_name(payload["checks"], "object_storage_endpoint")["ok"] is False


def test_unreachable_optional_object_storage_is_reported_without_failing_doctor(
    doctor: ModuleType, monkeypatch: pytest.MonkeyPatch
) -> None:
    _stub_http_and_sandbox(doctor, monkeypatch)
    monkeypatch.setattr(
        doctor,
        "check_socket",
        lambda host, port, **_kw: {"ok": port != 9000, "host": host, "port": port},
    )
    env = {
        **_NATIVE_ENV,
        "OBJECT_STORAGE_REQUIRED": "false",
        "KNOWLEDGE_V2_S3_ENDPOINT_URL": "http://127.0.0.1:9000",
        "KNOWLEDGE_V2_S3_BUCKET": "koda-objects",
        "KNOWLEDGE_V2_S3_ACCESS_KEY_ID": "a1b2c3d4e5f6a7b8c9d0",
        "KNOWLEDGE_V2_S3_SECRET_ACCESS_KEY": "9f8e7d6c5b4a39281706f5e4d3c2b1a0",
    }

    payload = doctor.run_doctor(env=env, base_url="http://127.0.0.1:8090")

    socket_check = _by_name(payload["checks"], "object_storage_socket")
    assert socket_check["ok"] is False
    assert socket_check["required"] is False
    assert _by_name(payload["checks"], "object_storage_access_key")["source"] == "KNOWLEDGE_V2_S3_ACCESS_KEY_ID"
    assert payload["ok"] is True


@pytest.mark.parametrize("value", [None, "true", "TRUE"], ids=["unset", "true", "upper"])
def test_object_storage_is_required_by_default(
    doctor: ModuleType, monkeypatch: pytest.MonkeyPatch, value: str | None
) -> None:
    _stub_http_and_sandbox(doctor, monkeypatch)
    monkeypatch.setattr(doctor, "check_socket", lambda host, port, **_kw: {"ok": True, "host": host, "port": port})
    env = dict(_NATIVE_ENV)
    if value is not None:
        env["OBJECT_STORAGE_REQUIRED"] = value

    payload = doctor.run_doctor(env=env, base_url="http://127.0.0.1:8090")

    assert payload["ok"] is False
    assert _failing(payload) == list(OBJECT_STORAGE_CHECKS)
    assert all(_by_name(payload["checks"], name)["required"] is True for name in OBJECT_STORAGE_CHECKS)


def test_an_empty_object_storage_required_reads_as_the_app_reads_it(
    doctor: ModuleType, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Empty means true under Compose (`${OBJECT_STORAGE_REQUIRED:-true}`) and false on a native install.

    A native install loads `.env` itself, and Koda's `_bool_env` reads an empty value as false.
    Doctor reads a `.env` that sets KNOWLEDGE_V2_POSTGRES_DSN as a native install.
    """
    _stub_http_and_sandbox(doctor, monkeypatch)
    monkeypatch.setattr(doctor, "check_socket", lambda host, port, **_kw: {"ok": True, "host": host, "port": port})

    native = doctor.run_doctor(env={**_NATIVE_ENV, "OBJECT_STORAGE_REQUIRED": ""}, base_url="http://127.0.0.1:8090")

    assert native["object_storage_required"] is False
    assert native["ok"] is True

    env_file = _generated_env(tmp_path)
    compose_env = {**doctor.load_env_file(env_file), "OBJECT_STORAGE_REQUIRED": ""}
    _only_loopback_resolves(doctor, monkeypatch)
    _fake_docker(tmp_path, monkeypatch)

    compose = doctor.run_doctor(env=compose_env, base_url="http://127.0.0.1:8090", env_file=env_file)

    assert compose["object_storage_required"] is True
    assert all(_by_name(compose["checks"], name)["required"] is True for name in OBJECT_STORAGE_CHECKS)


@pytest.mark.parametrize(
    ("env_text", "expected"),
    [
        (
            "POSTGRES_PASSWORD=replace-with-a-random-postgres-password\n",
            "POSTGRES_PASSWORD still uses the public .env.example placeholder. Replace it with ",
        ),
        (
            "POSTGRES_PASSWORD=replace-with-a-random-postgres-password\n"
            "S3_SECRET_ACCESS_KEY=replace-with-a-random-object-storage-secret\n",
            "POSTGRES_PASSWORD, S3_SECRET_ACCESS_KEY still use the public .env.example placeholder. Replace them with ",
        ),
    ],
    ids=["one-key", "several-keys"],
)
def test_placeholder_message_agrees_with_the_number_of_keys(
    doctor: ModuleType, tmp_path: Path, env_text: str, expected: str
) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text(env_text, encoding="utf-8")

    check = doctor.check_storage_secrets(doctor.load_env_file(env_file))

    assert check["ok"] is False
    assert check["user_action"].startswith(expected)
