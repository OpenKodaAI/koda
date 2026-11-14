"""AG-04 (ADR-002 §2.4 L1): the agent worker is non-dumpable and writes no core files.

The worker's environment holds the Postgres DSN, the S3 secret, granted secrets
and runtime tokens, and every process it starts (provider CLIs, MCP stdio
servers, governed shell and git) runs as the same uid. Unless the worker is
non-dumpable, any of those processes can read ``/proc/<worker>/environ``.

The EACCES proof runs both the worker and the reading sibling as one
unprivileged uid: root (or any holder of ``CAP_SYS_PTRACE``) can read every
``environ`` whatever the worker does, so a root reader would prove nothing.
"""

from __future__ import annotations

import ast
import ctypes
import json
import os
import pwd
import resource
import secrets
import select
import shutil
import subprocess
import sys
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

import pytest

ROOT_DIR = Path(__file__).resolve().parents[2]
ENTRYPOINT = ROOT_DIR / "koda" / "__main__.py"

linux_only = pytest.mark.skipif(not sys.platform.startswith("linux"), reason="PR_SET_DUMPABLE is Linux-only")

_CAP_SYS_PTRACE = 19
# <linux/prctl.h>
PR_GET_DUMPABLE = 3
PR_SET_DUMPABLE = 4


# --------------------------------------------------------------------------- #
#  The entrypoint hardens before it does anything else                         #
# --------------------------------------------------------------------------- #


@pytest.mark.security
def test_entrypoint_hardens_before_any_other_statement() -> None:
    """``python -m koda`` and the ``koda-runtime-worker`` script both execute this
    module body, so the call must come before every other import and statement."""
    body = ast.parse(ENTRYPOINT.read_text(encoding="utf-8")).body
    assert isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant), "module docstring first"

    first, second = body[1], body[2]
    assert isinstance(first, ast.ImportFrom), ast.dump(first)
    assert first.module == "koda.process_hygiene"
    assert [alias.name for alias in first.names] == ["harden_process"]

    assert isinstance(second, ast.Expr) and isinstance(second.value, ast.Call), ast.dump(second)
    func = second.value.func
    assert isinstance(func, ast.Name) and func.id == "harden_process"
    assert not second.value.args and not second.value.keywords


# --------------------------------------------------------------------------- #
#  Real processes                                                              #
# --------------------------------------------------------------------------- #

# Prints the dumpable state and the core limit of a fresh interpreter, after
# optionally running the entrypoint module body (``import koda.__main__`` runs
# it without calling ``main()``).
_PROBE = r"""
import ctypes, json, resource, sys
if sys.argv[1] == "worker":
    import koda.__main__  # noqa: F401
zero = ctypes.c_ulong(0)
dumpable = ctypes.CDLL(None, use_errno=True).prctl(3, zero, zero, zero, zero)
print(json.dumps({"dumpable": dumpable, "core": list(resource.getrlimit(resource.RLIMIT_CORE))}))
"""


def _child_env(**extra: str) -> dict[str, str]:
    env = {"PATH": os.environ.get("PATH", "/usr/bin:/bin"), "PYTHONPATH": str(ROOT_DIR), "LC_ALL": "C"}
    env.update(extra)
    return env


def _probe(mode: str) -> dict[str, Any]:
    result = subprocess.run(
        [sys.executable, "-c", _PROBE, mode],
        cwd=ROOT_DIR,
        env=_child_env(),
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    payload: dict[str, Any] = json.loads(result.stdout.strip().splitlines()[-1])
    return payload


@linux_only
@pytest.mark.security
def test_entrypoint_makes_worker_non_dumpable_with_core_dumps_off() -> None:
    control = _probe("control")
    worker = _probe("worker")

    # A fresh interpreter starts dumpable: the test can see the difference.
    assert control["dumpable"] == 1
    assert worker["dumpable"] == 0
    # Soft and hard limit 0: children inherit it and cannot raise it again.
    assert worker["core"] == [0, 0]


# A process that holds a canary in its environment and stays alive. When it
# starts as root it drops to the throwaway uid first (see _same_uid_identity).
_TARGET = r"""
import ctypes, os, sys, time
mode, uid, gid = sys.argv[1], int(sys.argv[2]), int(sys.argv[3])
libc = ctypes.CDLL(None, use_errno=True)
zero = ctypes.c_ulong(0)
if os.geteuid() != uid:
    # The interpreter and its stdlib can sit where the throwaway uid cannot read
    # them (uv keeps Python under /root, mode 0700), so load the entrypoint's
    # imports while still root, then forget the module so it runs again below.
    import koda.__main__
    del sys.modules["koda.__main__"]
    try:
        os.setgroups([])
        os.setresgid(gid, gid, gid)
        os.setresuid(uid, uid, uid)
    except PermissionError as exc:
        print("skip:", exc, flush=True)
        sys.exit(0)
    # Changing credentials makes the kernel mark the process non-dumpable by
    # itself. Restore the state of a process exec'd directly as this uid, so
    # only the entrypoint can make the difference between control and worker.
    if libc.prctl(4, ctypes.c_ulong(1), zero, zero, zero) != 0:
        raise OSError(ctypes.get_errno(), "prctl(PR_SET_DUMPABLE, 1)")
if mode == "worker":
    import koda.__main__  # noqa: F401
print("ready", os.getuid(), libc.prctl(3, zero, zero, zero, zero), flush=True)
time.sleep(120)
"""


def _has_cap_sys_ptrace() -> bool:
    for line in Path("/proc/self/status").read_text(encoding="ascii").splitlines():
        if line.startswith("CapEff:"):
            return bool(int(line.split()[1], 16) & (1 << _CAP_SYS_PTRACE))
    return False


def _throwaway_ids() -> tuple[int, int]:
    """A uid/gid pair no account uses, so nothing else shares it by accident."""
    for candidate in range(61_000, 62_000):
        try:
            pwd.getpwuid(candidate)
        except KeyError:
            return candidate, candidate
    pytest.skip("no unused uid in 61000-61999 for a throwaway user")


def _same_uid_identity() -> tuple[int, int]:
    """The unprivileged uid both the worker and the sibling run as."""
    if os.geteuid() == 0:
        return _throwaway_ids()
    if _has_cap_sys_ptrace():
        pytest.skip("this non-root test process holds CAP_SYS_PTRACE, so it is not an unprivileged sibling")
    return os.getuid(), os.getgid()


@contextmanager
def _target(mode: str, uid: int, gid: int, canary: str) -> Iterator[tuple[int, int]]:
    proc = subprocess.Popen(
        [sys.executable, "-c", _TARGET, mode, str(uid), str(gid)],
        cwd=ROOT_DIR,
        env=_child_env(KODA_AG04_CANARY=canary),
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        assert proc.stdout is not None
        ready, _, _ = select.select([proc.stdout], [], [], 60)
        line = proc.stdout.readline().strip() if ready else ""
        if line.startswith("skip:"):
            pytest.skip(f"cannot switch to throwaway uid {uid}: {line[5:].strip()}")
        if not line.startswith("ready "):
            proc.kill()
            _, stderr = proc.communicate(timeout=10)
            pytest.fail(f"{mode} target did not start: {line!r} {stderr}")
        _, target_uid, dumpable = line.split()
        assert int(target_uid) == uid
        yield proc.pid, int(dumpable)
    finally:
        proc.kill()
        proc.communicate(timeout=10)


def _sibling_reads_environ(pid: int, uid: int, gid: int) -> subprocess.CompletedProcess[bytes]:
    cat = shutil.which("cat")
    if cat is None:
        pytest.skip("cat is not on PATH")
    drop: dict[str, Any] = {"user": uid, "group": gid, "extra_groups": []} if os.geteuid() == 0 else {}
    return subprocess.run(
        [cat, f"/proc/{pid}/environ"],
        env={"LC_ALL": "C"},
        capture_output=True,
        timeout=30,
        check=False,
        **drop,
    )


def _process_uid(pid: int) -> int:
    for line in Path(f"/proc/{pid}/status").read_text(encoding="ascii").splitlines():
        if line.startswith("Uid:"):
            return int(line.split()[1])
    raise AssertionError(f"no Uid line for {pid}")


@linux_only
@pytest.mark.security
def test_same_uid_sibling_cannot_read_worker_environ() -> None:
    uid, gid = _same_uid_identity()
    canary = f"ag04-{secrets.token_hex(8)}"

    # Control: without the entrypoint, a same-uid sibling reads the secret.
    with _target("control", uid, gid, canary) as (pid, dumpable):
        assert dumpable == 1
        assert _process_uid(pid) == uid
        leaked = _sibling_reads_environ(pid, uid, gid)
        assert leaked.returncode == 0, leaked.stderr
        assert canary.encode() in leaked.stdout

    # Worker: after the entrypoint module ran, the same read is refused.
    with _target("worker", uid, gid, canary) as (pid, dumpable):
        assert _process_uid(pid) == uid
        refused = _sibling_reads_environ(pid, uid, gid)
        assert canary.encode() not in refused.stdout, "a same-uid sibling read the worker's environment"
        assert refused.returncode != 0
        assert b"Permission denied" in refused.stderr, refused.stderr
        assert dumpable == 0


# --------------------------------------------------------------------------- #
#  Fail closed (fakes: the pytest process itself is never hardened here)      #
# --------------------------------------------------------------------------- #


class _FakeLibc:
    def __init__(self, *, set_result: int = 0, get_result: int = 0) -> None:
        self.calls: list[tuple[int, int]] = []
        self._set_result = set_result
        self._get_result = get_result

    def prctl(self, option: int, arg2: ctypes.c_ulong, *_rest: ctypes.c_ulong) -> int:
        self.calls.append((option, arg2.value))
        return self._set_result if option == PR_SET_DUMPABLE else self._get_result


@pytest.fixture
def fake_os(monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    from koda import process_hygiene

    state: dict[str, Any] = {"module": process_hygiene, "libc": _FakeLibc(), "rlimits": []}
    monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.setattr(process_hygiene.ctypes, "CDLL", lambda *_a, **_k: state["libc"])

    def _setrlimit(which: int, limits: tuple[int, int]) -> None:
        state["rlimits"].append((which, limits))

    monkeypatch.setattr(process_hygiene.resource, "setrlimit", _setrlimit)
    return state


@pytest.mark.security
def test_harden_process_disables_dumpable_and_core_dumps(fake_os: dict[str, Any]) -> None:
    fake_os["module"].harden_process()

    assert fake_os["libc"].calls == [(PR_SET_DUMPABLE, 0), (PR_GET_DUMPABLE, 0)]
    assert fake_os["rlimits"] == [(resource.RLIMIT_CORE, (0, 0))]


@pytest.mark.security
def test_harden_process_fails_closed_when_prctl_fails(fake_os: dict[str, Any]) -> None:
    fake_os["libc"] = _FakeLibc(set_result=-1)

    with pytest.raises(fake_os["module"].ProcessHardeningError, match="PR_SET_DUMPABLE"):
        fake_os["module"].harden_process()
    assert fake_os["rlimits"] == []


@pytest.mark.security
def test_harden_process_fails_closed_when_still_dumpable(fake_os: dict[str, Any]) -> None:
    fake_os["libc"] = _FakeLibc(get_result=1)

    with pytest.raises(fake_os["module"].ProcessHardeningError, match="still dumpable"):
        fake_os["module"].harden_process()


@pytest.mark.security
def test_harden_process_fails_closed_without_prctl(monkeypatch: pytest.MonkeyPatch, fake_os: dict[str, Any]) -> None:
    def _no_libc(*_a: object, **_k: object) -> object:
        raise OSError("libc not found")

    monkeypatch.setattr(fake_os["module"].ctypes, "CDLL", _no_libc)

    with pytest.raises(fake_os["module"].ProcessHardeningError, match="prctl"):
        fake_os["module"].harden_process()


@pytest.mark.security
def test_harden_process_fails_closed_when_core_limit_is_refused(
    monkeypatch: pytest.MonkeyPatch, fake_os: dict[str, Any]
) -> None:
    def _refuse(_which: int, _limits: tuple[int, int]) -> None:
        raise ValueError("not allowed to lower the limit")

    monkeypatch.setattr(fake_os["module"].resource, "setrlimit", _refuse)

    with pytest.raises(fake_os["module"].ProcessHardeningError, match="RLIMIT_CORE"):
        fake_os["module"].harden_process()


@pytest.mark.security
def test_harden_process_skips_prctl_off_linux(monkeypatch: pytest.MonkeyPatch, fake_os: dict[str, Any]) -> None:
    monkeypatch.setattr(sys, "platform", "darwin")

    fake_os["module"].harden_process()

    assert fake_os["libc"].calls == []
    assert fake_os["rlimits"] == [(resource.RLIMIT_CORE, (0, 0))]
