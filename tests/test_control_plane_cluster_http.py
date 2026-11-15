"""Blue/green drain HTTP contract.

The deploy pipeline POSTs to ``/cluster/drain`` on each old supervisor
when the new version becomes healthy. The supervisor flips its
``draining`` flag in ``cp_supervisor_runtimes`` so that on the next
heartbeat the cluster module RELEASES every claim instead of
refreshing them. The new version then immediately picks up ownership
and the rolling deploy completes without losing in-flight work.

These tests pin the HTTP contract by driving the handlers directly —
no aiohttp test server needed since the handlers are pure functions
of ``request`` plus the supervisor's ``_cluster`` instance.
"""

from __future__ import annotations

import os
import re
import subprocess
from collections.abc import AsyncIterator
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import patch

import pytest
from aiohttp.test_utils import TestClient, TestServer

from koda.control_plane import api as control_plane_api
from koda.control_plane import rate_limit
from koda.control_plane import settings as settings_mod
from koda.control_plane.operator_auth import OperatorAuthContext
from koda.control_plane.supervisor import ControlPlaneSupervisor


class _FakeCluster:
    def __init__(self, *, enabled: bool, draining: bool = False) -> None:
        self.config = SimpleNamespace(
            enabled=enabled,
            supervisor_id="sup_test",
            version="v1",
            host="localhost",
            capacity=10,
        )
        self._draining = draining
        self.set_draining_calls: list[bool] = []

    def is_draining(self) -> bool:
        return self._draining

    def list_owned_agents(self) -> set[str]:
        return {"AGENT_A", "AGENT_B"}

    def set_draining(self, value: bool) -> bool:
        self.set_draining_calls.append(value)
        self._draining = value
        return True


def _make_supervisor(*, enabled: bool, draining: bool = False) -> ControlPlaneSupervisor:
    with patch("koda.control_plane.supervisor.get_control_plane_manager", return_value=object()):
        sup = ControlPlaneSupervisor()
    sup._cluster = _FakeCluster(enabled=enabled, draining=draining)  # type: ignore[assignment]
    return sup


@pytest.mark.asyncio
async def test_status_reports_disabled_when_cluster_off() -> None:
    supervisor = _make_supervisor(enabled=False)
    response = await supervisor._cluster_status(SimpleNamespace())  # type: ignore[arg-type]
    body = await _decode(response)
    assert body == {"enabled": False, "reason": "KODA_CLUSTER_MODE != 'cluster'"}


@pytest.mark.asyncio
async def test_status_reports_owned_count_when_enabled() -> None:
    supervisor = _make_supervisor(enabled=True)
    response = await supervisor._cluster_status(SimpleNamespace())  # type: ignore[arg-type]
    body = await _decode(response)
    assert body["enabled"] is True
    assert body["supervisor_id"] == "sup_test"
    assert body["owned_count"] == 2
    assert body["owned_agents"] == ["AGENT_A", "AGENT_B"]
    assert body["draining"] is False


@pytest.mark.asyncio
async def test_drain_flips_draining_flag_to_true() -> None:
    supervisor = _make_supervisor(enabled=True)
    response = await supervisor._cluster_drain(SimpleNamespace())  # type: ignore[arg-type]
    body = await _decode(response)
    assert body == {"applied": True, "draining": True}
    cluster: Any = supervisor._cluster  # type: ignore[assignment]
    assert cluster.set_draining_calls == [True]


@pytest.mark.asyncio
async def test_undrain_flips_draining_flag_back() -> None:
    supervisor = _make_supervisor(enabled=True, draining=True)
    response = await supervisor._cluster_undrain(SimpleNamespace())  # type: ignore[arg-type]
    body = await _decode(response)
    assert body == {"applied": True, "draining": False}
    cluster: Any = supervisor._cluster  # type: ignore[assignment]
    assert cluster.set_draining_calls == [False]


@pytest.mark.asyncio
async def test_drain_returns_409_when_cluster_disabled() -> None:
    supervisor = _make_supervisor(enabled=False)
    response = await supervisor._cluster_drain(SimpleNamespace())  # type: ignore[arg-type]
    assert response.status == 409


@pytest.mark.asyncio
async def test_undrain_returns_409_when_cluster_disabled() -> None:
    supervisor = _make_supervisor(enabled=False)
    response = await supervisor._cluster_undrain(SimpleNamespace())  # type: ignore[arg-type]
    assert response.status == 409


async def _decode(response: Any) -> dict[str, Any]:
    import json

    return json.loads(response.body.decode())


_OPERATOR_TOKEN = "cluster-operator-token"


class _StubAuthService:
    """Knows one operator bearer token and nothing else."""

    def resolve_bearer_token(self, token: str) -> OperatorAuthContext | None:
        if token != _OPERATOR_TOKEN:
            return None
        return OperatorAuthContext(
            auth_kind="session",
            subject_type="operator",
            user_id="cluster-operator",
            username="cluster-operator",
            email=None,
            display_name=None,
        )


@pytest.fixture
async def cluster_client() -> AsyncIterator[tuple[TestClient, _FakeCluster]]:
    """The supervisor's own app, with its middleware stack, in front of a fake cluster."""
    supervisor = _make_supervisor(enabled=True)
    cluster: Any = supervisor._cluster
    rate_limit.clear_limiters()
    with patch.object(control_plane_api, "_auth_service", _StubAuthService):
        async with TestClient(TestServer(supervisor.build_app())) as client:
            yield client, cluster
    rate_limit.clear_limiters()


@pytest.mark.parametrize("path", ["/cluster/drain", "/cluster/undrain"])
@pytest.mark.parametrize("authorization", [None, "Bearer ", "Bearer wrong-token", f"Basic {_OPERATOR_TOKEN}"])
async def test_drain_endpoints_refuse_a_request_without_an_operator_token(
    cluster_client: tuple[TestClient, _FakeCluster], path: str, authorization: str | None
) -> None:
    """D-033: without a valid bearer the flag never changes."""
    client, cluster = cluster_client
    headers = {"Authorization": authorization} if authorization is not None else {}

    response = await client.post(path, headers=headers)

    assert response.status == 401
    assert await response.json() == {"error": "operator session is required"}
    assert cluster.set_draining_calls == []


@pytest.mark.parametrize(("path", "draining"), [("/cluster/drain", True), ("/cluster/undrain", False)])
async def test_drain_endpoints_accept_an_operator_token(
    cluster_client: tuple[TestClient, _FakeCluster], path: str, draining: bool
) -> None:
    client, cluster = cluster_client

    response = await client.post(path, headers={"Authorization": f"Bearer {_OPERATOR_TOKEN}"})

    assert response.status == 200
    assert await response.json() == {"applied": True, "draining": draining}
    assert cluster.set_draining_calls == [draining]


async def test_cluster_status_still_answers_without_a_token(cluster_client: tuple[TestClient, _FakeCluster]) -> None:
    client, _cluster = cluster_client

    response = await client.get("/cluster/status")

    assert response.status == 200
    assert (await response.json())["supervisor_id"] == "sup_test"


_ROOT = Path(__file__).resolve().parents[1]


def _read(relative: str) -> str:
    return (_ROOT / relative).read_text(encoding="utf-8")


def test_the_drain_docs_and_the_cluster_smoke_send_a_token() -> None:
    cluster_mode = _read("docs/operations/cluster-mode.md")
    smoke = _read("scripts/cluster_smoke.sh")

    assert "unauthenticated by design" not in cluster_mode
    assert (
        "| `POST /cluster/drain` | Sets `draining=true`. Next heartbeat releases all claims. | operator bearer token |"
        in (cluster_mode)
    )
    posts = [line for line in smoke.splitlines() if "/cluster/drain" in line or "/cluster/undrain" in line]
    assert [line for line in posts if not line.lstrip().startswith("#")] == [
        'cluster_post "${target_cid}" /cluster/drain >/dev/null',
        'cluster_post "${target_cid}" /cluster/undrain >/dev/null',
    ]
    for text in (cluster_mode, _read("docs/operations/upgrade.md"), smoke):
        # The first raw list item can be a placeholder or blank, and argv is visible in ps.
        assert "CONTROL_PLANE_API_TOKEN%%,*" not in text
        assert '-H "Authorization: Bearer' not in text


# A fake curl and docker log each argument on its own line, then an end marker, and curl
# logs what it reads on stdin (-H @-).
_END = "=== end of argv ==="
_FAKE_CURL = f"""#!/bin/sh
{{ printf '%s\\n' curl "$@"; printf '%s\\n' '{_END}'; }} >> "$FAKE_LOG.argv"
{{ cat; printf '\\n'; }} >> "$FAKE_LOG.stdin"
"""
# docker exec <container> CMD...: run CMD here, as if inside the container.
_FAKE_DOCKER = f"""#!/bin/sh
{{ printf '%s\\n' docker "$@"; printf '%s\\n' '{_END}'; }} >> "$FAKE_LOG.argv"
shift 2
exec "$@"
"""

_TOKEN_LISTS = [
    "realtoken",
    "replace-with-x,realtoken",  # an unedited placeholder first
    "replace-with-a-random-token, new-token ,old-token",  # a half-edited rotation
    ",  REPLACE-WITH-x , realtoken",  # a blank item, a placeholder in another case
]


def _drain_snippet(markdown: str) -> str:
    """The documented commands from ``token=$(`` through the drain POST (or the loop around it)."""
    (block,) = [block for block in re.findall(r"```bash\n(.*?)```", markdown, re.DOTALL) if "/cluster/drain" in block]
    lines = block.splitlines()
    start = next(index for index, line in enumerate(lines) if line.startswith("token=$("))
    end = next(index for index, line in enumerate(lines) if index > start and "/cluster/drain" in line)
    if any(line.startswith("for ") for line in lines[start:end]):
        end = lines.index("done", end)
    return "\n".join(lines[start : end + 1]) + "\n"


def _run_with_fakes(tmp_path: Path, script: str, tokens: str) -> tuple[list[list[str]], list[str]]:
    """Run ``script`` in bash with the fakes first on PATH; return (each process's argv, curl's stdin lines)."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    for name, body in (("curl", _FAKE_CURL), ("docker", _FAKE_DOCKER)):
        (bin_dir / name).write_text(body, encoding="utf-8")
        (bin_dir / name).chmod(0o755)
    log = tmp_path / "fake"
    env = {
        "PATH": f"{bin_dir}{os.pathsep}{os.environ['PATH']}",
        "CONTROL_PLANE_API_TOKEN": tokens,
        "FAKE_LOG": str(log),
    }
    subprocess.run(["bash", "-c", script], env=env, check=True, timeout=30)
    records = Path(f"{log}.argv").read_text(encoding="utf-8").split(f"{_END}\n")
    argvs = [record.rstrip("\n").split("\n") for record in records if record]
    stdin = [line for line in Path(f"{log}.stdin").read_text(encoding="utf-8").splitlines() if line]
    return argvs, stdin


def _expected_header(tokens: str) -> str:
    usable, _placeholders = settings_mod.parse_api_tokens(tokens)
    return f"Authorization: Bearer {usable[0]}"


def _assert_no_token_in(argvs: list[list[str]], tokens: str) -> None:
    every_argument = "\n".join("\n".join(argv) for argv in argvs)
    for token in settings_mod.parse_api_tokens(tokens)[0]:
        assert token not in every_argument


@pytest.mark.parametrize("tokens", _TOKEN_LISTS)
@pytest.mark.parametrize(
    ("doc", "urls"),
    [
        ("docs/operations/cluster-mode.md", ["http://127.0.0.1:8090/cluster/drain"]),
        (
            "docs/operations/upgrade.md",
            ["http://supervisor-old-1:8090/cluster/drain", "http://supervisor-old-2:8090/cluster/drain"],
        ),
    ],
)
def test_the_documented_drain_sends_the_token_the_server_accepts_on_stdin(
    tmp_path: Path, doc: str, urls: list[str], tokens: str
) -> None:
    """The first token parse_api_tokens keeps, as the koda CLI sends it; never in a process's argv."""
    argvs, stdin = _run_with_fakes(tmp_path, _drain_snippet(_read(doc)), tokens)

    assert argvs == [["curl", "-fs", "-X", "POST", "-H", "@-", url] for url in urls]
    assert stdin == [_expected_header(tokens)] * len(urls)
    _assert_no_token_in(argvs, tokens)


@pytest.mark.parametrize("tokens", _TOKEN_LISTS)
@pytest.mark.parametrize("path", ["/cluster/drain", "/cluster/undrain"])
def test_the_cluster_smoke_sends_the_token_the_server_accepts_on_stdin(tmp_path: Path, path: str, tokens: str) -> None:
    smoke = _read("scripts/cluster_smoke.sh")
    function = re.search(r"^cluster_post\(\) \{\n.*?^\}\n", smoke, re.MULTILINE | re.DOTALL)
    assert function, "scripts/cluster_smoke.sh no longer defines cluster_post"
    script = f"SUPERVISOR_PORT=8090\n{function.group(0)}cluster_post supervisor-1 {path}\n"

    (docker, curl), stdin = _run_with_fakes(tmp_path, script, tokens)

    # The container's sh (dash in the python:slim image, and here) reads the token from its own env.
    assert docker[:5] == ["docker", "exec", "supervisor-1", "sh", "-c"]
    assert docker[-1] == f"http://127.0.0.1:8090{path}"
    assert curl == ["curl", "-fs", "-X", "POST", "-H", "@-", f"http://127.0.0.1:8090{path}"]
    assert stdin == [_expected_header(tokens)]
    _assert_no_token_in([docker, curl], tokens)
