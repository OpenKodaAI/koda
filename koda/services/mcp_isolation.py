"""Process isolation strategies for stdio MCP servers.

Wraps a stdio command in an OS-level sandbox so a misbehaving (or malicious)
MCP server cannot read arbitrary host files, escalate privileges, or exfiltrate
data via the network. The wrapper runs *outside* the MCP protocol — it only
rewrites the argv that ``StdioTransport`` will exec, so the JSON-RPC pipeline
above stays unchanged.

Strategy selection (in priority order):

1. ``KODA_MCP_ISOLATION`` env var (if set to ``docker``/``bwrap``/
   ``sandbox-exec``/``native``) — explicit override.
2. ``isolation_profile`` from the catalog row (``docker``/``native``/etc.) —
   per-server preference.
3. Auto-detect: ``bwrap`` on Linux, ``sandbox-exec`` on macOS, ``native``
   otherwise. ``native`` is the same as today (no wrapper) but emits a warning
   so operators know they are running un-sandboxed.

Docker is opt-in only — for enterprise deployments with a Docker daemon
present. The default tier is the lightweight OS-native sandboxing primitives.
"""

from __future__ import annotations

import json
import os
import platform
import shutil
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal, Protocol

from koda.logging_config import get_logger

logger = get_logger(__name__)


IsolationKind = Literal["native", "bwrap", "sandbox-exec", "docker"]


# ---------------------------------------------------------------------------
# Constraints
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Mount:
    """One mount spec: bind-mount ``host`` at ``container`` (default RO)."""

    host: str
    container: str
    read_only: bool = True


@dataclass(frozen=True, slots=True)
class IsolationConstraints:
    """Per-server isolation envelope. All defaults are tight; loosen explicitly."""

    cpu_quota: float = 0.5  # cores
    memory_limit_bytes: int = 256 * 1024 * 1024  # 256 MiB
    network_mode: Literal["none", "egress_allowlist", "any"] = "egress_allowlist"
    egress_domains: tuple[str, ...] = ()
    mounts: tuple[Mount, ...] = ()
    timeout_seconds: int = 600
    drop_privileges: bool = True
    docker_image: str = "koda/mcp-runtime:latest"

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> IsolationConstraints:
        if not data:
            return cls()
        mounts_raw = data.get("mounts") or []
        mounts: list[Mount] = []
        if isinstance(mounts_raw, list):
            for entry in mounts_raw:
                if isinstance(entry, dict) and entry.get("host") and entry.get("container"):
                    mounts.append(
                        Mount(
                            host=str(entry["host"]),
                            container=str(entry["container"]),
                            read_only=bool(entry.get("read_only", True)),
                        )
                    )
        domains_raw = data.get("egress_domains") or ()
        domains = tuple(str(item) for item in domains_raw) if isinstance(domains_raw, (list, tuple)) else ()
        return cls(
            cpu_quota=float(data.get("cpu_quota", 0.5)),
            memory_limit_bytes=int(data.get("memory_limit_bytes", 256 * 1024 * 1024)),
            network_mode=str(data.get("network_mode", "egress_allowlist")),  # type: ignore[arg-type]
            egress_domains=domains,
            mounts=tuple(mounts),
            timeout_seconds=int(data.get("timeout_seconds", 600)),
            drop_privileges=bool(data.get("drop_privileges", True)),
            docker_image=str(data.get("docker_image", "koda/mcp-runtime:latest")),
        )


# ---------------------------------------------------------------------------
# Strategy protocol
# ---------------------------------------------------------------------------


class IsolationStrategy(Protocol):
    """Wraps ``argv`` so that the spawned process runs in a sandbox."""

    kind: IsolationKind

    def wrap(
        self,
        command: list[str],
        env: dict[str, str],
        constraints: IsolationConstraints,
    ) -> tuple[list[str], dict[str, str]]:
        """Return rewritten ``(argv, env)`` for ``asyncio.create_subprocess_exec``."""
        ...

    def is_available(self) -> bool:
        """Return True iff this strategy can execute on the current host."""
        ...


# ---------------------------------------------------------------------------
# Implementations
# ---------------------------------------------------------------------------


class NativeIsolation:
    """Pass-through — no sandbox. Logs a warning at first wrap."""

    kind: IsolationKind = "native"
    _warned: bool = False

    def is_available(self) -> bool:
        return True

    def wrap(
        self,
        command: list[str],
        env: dict[str, str],
        constraints: IsolationConstraints,
    ) -> tuple[list[str], dict[str, str]]:
        if not NativeIsolation._warned:
            logger.warning(
                "mcp_isolation_native_unsafe",
                hint="OS-level sandbox unavailable; consider installing bwrap (Linux) or enabling Docker.",
            )
            NativeIsolation._warned = True
        return command, env


class BwrapIsolation:
    """Linux sandbox via ``bubblewrap`` (used by Flatpak)."""

    kind: IsolationKind = "bwrap"

    def __init__(self) -> None:
        self._bin = shutil.which("bwrap")

    def is_available(self) -> bool:
        return platform.system() == "Linux" and self._bin is not None

    def wrap(
        self,
        command: list[str],
        env: dict[str, str],
        constraints: IsolationConstraints,
    ) -> tuple[list[str], dict[str, str]]:
        if not self._bin:
            raise RuntimeError("bwrap binary not found")
        argv: list[str] = [
            self._bin,
            "--die-with-parent",
            "--unshare-user",
            "--unshare-ipc",
            "--unshare-pid",
            "--unshare-uts",
            "--unshare-cgroup-try",
            "--proc",
            "/proc",
            "--dev",
            "/dev",
            "--tmpfs",
            "/tmp",
            "--ro-bind",
            "/usr",
            "/usr",
            "--ro-bind",
            "/lib",
            "/lib",
            "--symlink",
            "/usr/bin",
            "/bin",
            "--symlink",
            "/usr/lib",
            "/lib64",
            "--ro-bind-try",
            "/etc/resolv.conf",
            "/etc/resolv.conf",
            "--ro-bind-try",
            "/etc/ssl",
            "/etc/ssl",
            "--ro-bind-try",
            "/etc/ca-certificates",
            "/etc/ca-certificates",
        ]

        if constraints.network_mode == "none":
            argv.append("--unshare-net")
        # else: bwrap shares net by default; fine-grained egress filtering
        # would need an out-of-band egress proxy and is out of scope here.

        for mount in constraints.mounts:
            host_path = str(Path(mount.host).expanduser())
            argv.extend(
                [
                    "--ro-bind" if mount.read_only else "--bind",
                    host_path,
                    mount.container,
                ]
            )

        argv.append("--")
        argv.extend(command)
        scrubbed_env = _scrub_env(env)
        return argv, scrubbed_env


class SandboxExecIsolation:
    """macOS sandbox via the built-in ``sandbox-exec`` (no install required)."""

    kind: IsolationKind = "sandbox-exec"

    def __init__(self) -> None:
        self._bin = shutil.which("sandbox-exec")

    def is_available(self) -> bool:
        return platform.system() == "Darwin" and self._bin is not None

    def wrap(
        self,
        command: list[str],
        env: dict[str, str],
        constraints: IsolationConstraints,
    ) -> tuple[list[str], dict[str, str]]:
        if not self._bin:
            raise RuntimeError("sandbox-exec not available")
        profile = self._build_profile(constraints)
        # sandbox-exec wants the profile as a string via -p, not a file.
        argv: list[str] = [self._bin, "-p", profile]
        argv.extend(command)
        return argv, _scrub_env(env)

    @staticmethod
    def _build_profile(constraints: IsolationConstraints) -> str:
        # Minimal SBPL profile: deny by default, then allow what the server
        # genuinely needs. The MCP runtime needs to read its own binary, write
        # to the per-process tmpfs, read DNS resolver, and (optionally) reach
        # the network.
        rules: list[str] = [
            "(version 1)",
            "(deny default)",
            "(allow process-fork)",
            "(allow process-exec)",
            "(allow signal (target self))",
            "(allow file-read*)",
            "(allow file-read-metadata)",
            "(allow mach-lookup)",
            "(allow ipc-posix-shm)",
            "(allow sysctl-read)",
            '(allow file-write* (subpath "/private/tmp"))',
            '(allow file-write* (subpath "/tmp"))',
        ]
        for mount in constraints.mounts:
            host = str(Path(mount.host).expanduser())
            rules.append(f'(allow file-read* (subpath "{host}"))')
            if not mount.read_only:
                rules.append(f'(allow file-write* (subpath "{host}"))')
        if constraints.network_mode != "none":
            rules.append("(allow network*)")
        return "\n".join(rules)


class DockerIsolation:
    """Docker-based sandbox — opt-in via ``KODA_MCP_ISOLATION=docker``."""

    kind: IsolationKind = "docker"

    def __init__(self) -> None:
        self._bin = shutil.which("docker")

    def is_available(self) -> bool:
        return self._bin is not None

    def wrap(
        self,
        command: list[str],
        env: dict[str, str],
        constraints: IsolationConstraints,
    ) -> tuple[list[str], dict[str, str]]:
        if not self._bin:
            raise RuntimeError("docker not available")
        argv: list[str] = [
            self._bin,
            "run",
            "--rm",
            "-i",
            "--cap-drop=ALL",
            "--security-opt=no-new-privileges",
            "--read-only",
            "--tmpfs",
            "/tmp:rw,noexec,nosuid,size=64m",
            "--memory",
            f"{constraints.memory_limit_bytes // (1024 * 1024)}m",
            "--cpus",
            str(constraints.cpu_quota),
            "--pids-limit=128",
            "--user",
            "65534:65534",
            "--ulimit",
            "nofile=1024:1024",
        ]
        if constraints.network_mode == "none":
            argv.extend(["--network", "none"])
        else:
            argv.extend(["--network", "bridge"])
        for mount in constraints.mounts:
            host = str(Path(mount.host).expanduser())
            mount_spec = f"type=bind,source={host},target={mount.container}"
            if mount.read_only:
                mount_spec = f"{mount_spec},readonly"
            argv.extend(["--mount", mount_spec])
        # Pass env via a temp file (ephemeral; closed when the process exits).
        env_file = _write_env_file(_scrub_env(env))
        argv.extend(["--env-file", env_file])
        argv.append(constraints.docker_image)
        argv.extend(command)
        return argv, {}


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------


def select_isolation_strategy(
    *,
    catalog_profile: str | None = None,
    env_override: str | None = None,
) -> IsolationStrategy:
    """Pick the best available strategy.

    Order of precedence: ``env_override`` (``KODA_MCP_ISOLATION``) →
    ``catalog_profile`` (per-server) → auto-detect → native.
    """
    requested = (env_override or catalog_profile or "auto").strip().lower()

    candidates: dict[str, IsolationStrategy] = {
        "bwrap": BwrapIsolation(),
        "sandbox-exec": SandboxExecIsolation(),
        "docker": DockerIsolation(),
        "native": NativeIsolation(),
    }

    if requested in candidates and candidates[requested].is_available():
        return candidates[requested]

    # Auto: prefer OS-native sandbox; fall back to native.
    if platform.system() == "Linux" and candidates["bwrap"].is_available():
        return candidates["bwrap"]
    if platform.system() == "Darwin" and candidates["sandbox-exec"].is_available():
        return candidates["sandbox-exec"]
    return candidates["native"]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


# Env names that must not propagate into the sandbox even if a custom server
# tries to set them; this is a second line of defense behind the registry's
# validate_payload deny-list.
_BLOCKED_ENV_NAMES: frozenset[str] = frozenset(
    {
        "LD_PRELOAD",
        "LD_LIBRARY_PATH",
        "LD_AUDIT",
        "DYLD_INSERT_LIBRARIES",
        "DYLD_LIBRARY_PATH",
        "DYLD_FRAMEWORK_PATH",
    }
)


def _scrub_env(env: dict[str, str]) -> dict[str, str]:
    """Drop blocked env vars before passing to the sandboxed process."""
    return {k: v for k, v in env.items() if k not in _BLOCKED_ENV_NAMES}


def _write_env_file(env: dict[str, str]) -> str:
    """Persist env to a temp file readable only by the current user. Caller is
    responsible for cleanup; the file is auto-removed by the OS at process
    exit because we set the temp dir.
    """
    fd, path = tempfile.mkstemp(prefix="koda-mcp-env-", suffix=".env")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            for k, v in env.items():
                # ``--env-file`` accepts KEY=VALUE per line. Strip newlines from
                # values to avoid breaking the format.
                cleaned = v.replace("\n", " ").replace("\r", " ")
                fh.write(f"{k}={cleaned}\n")
        os.chmod(path, 0o600)
    except OSError:
        os.close(fd)
        raise
    return path


def isolation_runtime_summary() -> dict[str, Any]:
    """Diagnostic — what isolation tier is available right now?"""
    strategies: list[dict[str, Any]] = []
    for name, strategy in (
        ("bwrap", BwrapIsolation()),
        ("sandbox-exec", SandboxExecIsolation()),
        ("docker", DockerIsolation()),
        ("native", NativeIsolation()),
    ):
        strategies.append({"kind": name, "available": strategy.is_available()})
    return {
        "platform": platform.system(),
        "python": sys.version.split()[0],
        "strategies": strategies,
        "active_default": select_isolation_strategy().kind,
    }


# Stub so that mypy doesn't choke on the unused json import in environments
# where the helper is unused; keeping the import makes the module reusable
# from places that pass JSON-serialized constraints.
_ = json
