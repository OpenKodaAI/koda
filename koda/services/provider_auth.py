"""Canonical provider authentication helpers and short-lived login sessions."""

from __future__ import annotations

import base64
import fcntl
import json
import os
import pty
import re
import select
import shlex
import shutil
import struct
import subprocess
import tempfile
import termios
import threading
import time
from contextlib import suppress
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal, cast
from urllib import error as urllib_error
from urllib import parse as urllib_parse
from urllib import request as urllib_request
from uuid import uuid4

ProviderId = Literal["claude", "codex", "gemini", "elevenlabs", "ollama"]
ProviderAuthMode = Literal["api_key", "subscription_login", "local"]

MANAGED_PROVIDER_IDS: tuple[ProviderId, ...] = ("claude", "codex", "gemini", "elevenlabs", "ollama")
PROVIDER_API_KEY_ENV_KEYS: dict[ProviderId, str] = {
    "claude": "ANTHROPIC_API_KEY",
    "codex": "OPENAI_API_KEY",
    "gemini": "GEMINI_API_KEY",
    "elevenlabs": "ELEVENLABS_API_KEY",
    "ollama": "OLLAMA_API_KEY",
}
PROVIDER_AUTH_TOKEN_ENV_KEYS: dict[str, str] = {
    "claude": "ANTHROPIC_AUTH_TOKEN",
}
PROVIDER_AUTH_MODE_ENV_KEYS: dict[ProviderId, str] = {
    "claude": "CLAUDE_AUTH_MODE",
    "codex": "CODEX_AUTH_MODE",
    "gemini": "GEMINI_AUTH_MODE",
    "elevenlabs": "ELEVENLABS_AUTH_MODE",
    "ollama": "OLLAMA_AUTH_MODE",
}
PROVIDER_VERIFIED_ENV_KEYS: dict[ProviderId, str] = {
    "claude": "CLAUDE_CONNECTION_VERIFIED",
    "codex": "CODEX_CONNECTION_VERIFIED",
    "gemini": "GEMINI_CONNECTION_VERIFIED",
    "elevenlabs": "ELEVENLABS_CONNECTION_VERIFIED",
    "ollama": "OLLAMA_CONNECTION_VERIFIED",
}
PROVIDER_PROJECT_ENV_KEYS: dict[ProviderId, str] = {
    "gemini": "GOOGLE_CLOUD_PROJECT",
}
PROVIDER_BASE_URL_ENV_KEYS: dict[ProviderId, str] = {
    "ollama": "OLLAMA_BASE_URL",
}
PROVIDER_TITLES: dict[ProviderId, str] = {
    "claude": "Anthropic",
    "codex": "OpenAI",
    "gemini": "Google",
    "elevenlabs": "ElevenLabs",
    "ollama": "Ollama",
}

_ANSI_ESCAPE_RE = re.compile(r"\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])")
_URL_RE = re.compile(r"https://[^\s)]+")
_URL_CONTINUATION_RE = re.compile(r"^[A-Za-z0-9\-._~:/?#\[\]@!$&'()*+,;=%]+$")
_CODE_RE = re.compile(r"\b[A-Z0-9]{4,}(?:-[A-Z0-9]{4,})+\b")


@dataclass(slots=True)
class ProviderVerificationResult:
    provider_id: ProviderId
    auth_mode: ProviderAuthMode
    verified: bool
    account_label: str = ""
    plan_label: str = ""
    last_error: str = ""
    checked_via: str = "static"
    auth_expired: bool = False
    details: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class ProviderLoginSessionState:
    session_id: str
    provider_id: ProviderId
    auth_mode: ProviderAuthMode
    status: str
    command: str
    auth_url: str = ""
    user_code: str = ""
    message: str = ""
    instructions: str = ""
    output_preview: str = ""
    last_error: str = ""
    code_verifier: str = ""


@dataclass(slots=True)
class _ProviderLoginProcess:
    """One live login subprocess owned by the server process only."""

    provider_id: ProviderId
    auth_mode: ProviderAuthMode
    command: tuple[str, ...]
    process: subprocess.Popen[Any]
    interactive_fd: int | None = None
    auto_steps: dict[str, bool] = field(default_factory=dict)
    created_at: float = field(default_factory=time.monotonic)
    work_dir: str = ""
    allow_workspace_trust: bool = False
    _chunks: list[str] = field(default_factory=list)
    _lock: threading.Lock = field(default_factory=threading.Lock)
    _reader: threading.Thread | None = None

    def start(self) -> None:
        if self.interactive_fd is None and self.process.stdout is None:
            return
        target = self._read_from_pty if self.interactive_fd is not None else self._read_from_pipe
        self._reader = threading.Thread(target=target, name=f"{self.provider_id}-login-reader", daemon=True)
        self._reader.start()

    def _append(self, text: str) -> None:
        if not text:
            return
        with self._lock:
            self._chunks.append(text)
        if self.provider_id == "gemini":
            self._maybe_automate_gemini()

    def _read_from_pipe(self) -> None:
        assert self.process.stdout is not None
        try:
            while True:
                chunk = self.process.stdout.readline()
                if not chunk:
                    break
                self._append(chunk)
        finally:
            with suppress(Exception):
                self.process.stdout.close()

    def _read_from_pty(self) -> None:
        assert self.interactive_fd is not None
        fd = self.interactive_fd
        os.set_blocking(fd, False)
        try:
            while True:
                if self.process.poll() is not None:
                    with suppress(OSError, BlockingIOError):
                        remainder = os.read(fd, 65536)
                        if remainder:
                            self._append(remainder.decode("utf-8", "replace"))
                    break
                try:
                    ready, _, _ = select.select([fd], [], [], 0.2)
                except (OSError, ValueError):
                    # fd was closed (EBADF) or became invalid — the subprocess
                    # tore down its PTY slave. Nothing more to read.
                    break
                if not ready:
                    continue
                try:
                    payload = os.read(fd, 65536)
                except BlockingIOError:
                    continue
                except OSError:
                    # Typical EIO (errno 5) on Linux when the slave side closes
                    # between the ``select`` return and the ``read`` call. Treat
                    # it as a graceful end-of-stream rather than crashing the
                    # reader thread.
                    break
                if not payload:
                    continue
                self._append(payload.decode("utf-8", "replace"))
        finally:
            with suppress(OSError):
                os.close(fd)

    def write(self, text: str) -> None:
        if self.interactive_fd is not None:
            with suppress(OSError):
                os.write(self.interactive_fd, text.replace("\n", "\r").encode("utf-8"))
        elif self.process.stdin is not None:
            try:
                self.process.stdin.write(text)
                self.process.stdin.flush()
            except (OSError, BrokenPipeError):
                pass

    def output_text(self) -> str:
        with self._lock:
            return "".join(self._chunks)

    def normalized_output(self) -> str:
        return strip_ansi(self.output_text())

    def terminate(self) -> None:
        if self.process.poll() is None:
            self.process.terminate()
            try:
                self.process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.process.kill()
        if self.interactive_fd is not None:
            with suppress(OSError):
                os.close(self.interactive_fd)

    def _maybe_automate_gemini(self) -> None:
        text = self.normalized_output()
        if (
            self.allow_workspace_trust
            and "Do you trust the files in this folder?" in text
            and not self.auto_steps.get("trust_folder")
        ):
            self.write("1\n")
            self.auto_steps["trust_folder"] = True
            return
        if "How would you like to authenticate for this project?" in text and not self.auto_steps.get("select_sign_in"):
            self.write("1\n")
            self.auto_steps["select_sign_in"] = True
            return
        if "Do you want to continue?" in text and not self.auto_steps.get("open_browser"):
            self.write("1\n")
            self.auto_steps["open_browser"] = True


def strip_ansi(text: str) -> str:
    return _ANSI_ESCAPE_RE.sub("", text)


def provider_supports_api_key(provider_id: str) -> bool:
    return provider_id.strip().lower() in (*MANAGED_PROVIDER_IDS,)


def provider_supports_subscription_login(provider_id: str) -> bool:
    # Claude Code ships ``claude setup-token`` for headless environments: it
    # prints the OAuth URL, accepts the authorization code on stdin and writes
    # a long-lived token to CLAUDE_CONFIG_DIR. Koda spawns the CLI in a PTY,
    # relays the URL to the UI and forwards the pasted code to stdin, so the
    # browser step still happens against Anthropic directly — Koda only wraps
    # the subprocess stdio, which the CLI is explicitly designed for.
    return provider_id.strip().lower() in {"claude", "codex", "gemini"}


def provider_supports_local_connection(provider_id: str) -> bool:
    # Ollama runs as a self-hosted endpoint. Claude keeps a ``local`` fallback
    # for operators who already authenticated the CLI on the host (mounted
    # CLAUDE_CONFIG_DIR) and just want Koda to detect it.
    return provider_id.strip().lower() in {"ollama", "claude"}


def provider_requires_project_id(provider_id: str) -> bool:
    return provider_id == "gemini"


def _running_inside_container() -> bool:
    """Best-effort detection of whether this process runs inside a container.

    Looks at the signals Docker/Kubernetes leave on the filesystem:
    `/.dockerenv` (Docker) or a cgroup entry mentioning docker/kubepods.
    Used to switch the Ollama default from ``localhost`` (unreachable from
    inside a container) to ``host.docker.internal`` (resolves to the host
    on Docker Desktop and on Linux when the compose file adds the
    ``host-gateway`` alias — see ``docker-compose.yml``).
    """
    import os

    if os.path.exists("/.dockerenv"):
        return True
    try:
        with open("/proc/1/cgroup", encoding="utf-8") as handle:
            cgroup_content = handle.read()
    except OSError:
        return False
    return any(token in cgroup_content for token in ("docker", "kubepods", "containerd"))


def provider_default_base_url(provider_id: str, auth_mode: str = "api_key") -> str:
    normalized = provider_id.strip().lower()
    if normalized != "ollama":
        return ""
    if auth_mode == "api_key":
        return "https://ollama.com"
    # Inside a container, `localhost` is the container itself — Ollama lives
    # on the host (or in a sibling container). Prefer the Docker host alias.
    if _running_inside_container():
        return "http://host.docker.internal:11434"
    return "http://localhost:11434"


def ollama_api_url(base_url: str, path: str, *, auth_mode: str = "local") -> str:
    base = base_url.strip() or provider_default_base_url("ollama", auth_mode)
    normalized = base.rstrip("/")
    if normalized.endswith("/api"):
        normalized = normalized[:-4]
    return f"{normalized}/api/{path.lstrip('/')}"


def provider_command_present(provider_id: str, base_env: dict[str, str] | None = None) -> bool:
    if provider_id.strip().lower() == "elevenlabs":
        return True
    if provider_id.strip().lower() == "kokoro":
        return True
    if provider_id.strip().lower() == "whispercpp":
        env = {**os.environ, **dict(base_env or {})}
        whisper_enabled = str(env.get("WHISPER_ENABLED") or "true").strip().lower()
        if whisper_enabled in {"false", "0", "no"}:
            return False
        whisper_bin = str(env.get("WHISPER_BIN") or "whisper-cli").strip() or "whisper-cli"
        whisper_model = str(env.get("WHISPER_MODEL") or "").strip() or str(
            Path.home() / ".cache" / "whisper-cpp" / "models" / "ggml-large-v3-turbo-q5_0.bin"
        )
        return (
            bool(shutil.which(whisper_bin, path=env.get("PATH")))
            and bool(whisper_model)
            and Path(whisper_model).expanduser().exists()
        )
    if provider_id.strip().lower() == "ollama":
        env = _provider_command_env(base_env)
        base_url_key = PROVIDER_BASE_URL_ENV_KEYS["ollama"]
        return bool(str(env.get(base_url_key) or provider_default_base_url("ollama", "local")).strip())
    try:
        resolve_provider_command(provider_id, base_env=base_env)
    except (KeyError, FileNotFoundError):
        return False
    return True


def _provider_command_env(base_env: dict[str, str] | None = None) -> dict[str, str]:
    env: dict[str, str] = {}
    for key in ("PATH", "HOME", "LANG", "LC_ALL", "LC_CTYPE", "TZ", "TMPDIR", "TMP", "TEMP"):
        value = os.environ.get(key)
        if value is not None:
            env[key] = value
    env.update({str(key): str(value) for key, value in dict(base_env or {}).items()})
    return env


def resolve_provider_command(provider_id: str, base_env: dict[str, str] | None = None) -> tuple[str, ...]:
    env = _provider_command_env(base_env)
    normalized = provider_id.strip().lower()
    if normalized not in MANAGED_PROVIDER_IDS:
        raise KeyError(provider_id)
    if normalized == "elevenlabs":
        raise KeyError(provider_id)
    if normalized == "ollama":
        if shutil.which("ollama", path=env.get("PATH")):
            return ("ollama",)
        raise FileNotFoundError("ollama")
    if normalized == "claude":
        if shutil.which("claude", path=env.get("PATH")):
            return ("claude",)
        raise FileNotFoundError("claude")
    if normalized == "codex":
        configured = str(env.get("CODEX_BIN") or "codex").strip()
        parts = tuple(shlex.split(configured))
        executable = parts[0] if parts else "codex"
        if shutil.which(executable, path=env.get("PATH")):
            return parts or ("codex",)
        raise FileNotFoundError(executable)

    configured = str(env.get("GEMINI_BIN") or "").strip()
    if configured:
        parts = tuple(shlex.split(configured))
        executable = parts[0] if parts else ""
        if executable and shutil.which(executable, path=env.get("PATH")):
            return parts
        raise FileNotFoundError(executable or "gemini")
    if shutil.which("gemini", path=env.get("PATH")):
        return ("gemini",)
    if shutil.which("npx", path=env.get("PATH")):
        return ("npx", "-y", "@google/gemini-cli")
    raise FileNotFoundError("gemini")


def provider_login_command(
    provider_id: ProviderId,
    *,
    project_id: str = "",
    base_env: dict[str, str] | None = None,
) -> tuple[str, ...]:
    command = resolve_provider_command(provider_id, base_env=base_env)
    if provider_id == "claude":
        # ``setup-token`` is the headless-friendly variant of ``auth login``:
        # it writes a long-lived OAuth token to CLAUDE_CONFIG_DIR and exits
        # cleanly, which matches how Koda uses the CLI (one-shot spawns, no
        # persistent interactive session).
        return (*command, "setup-token")
    if provider_id == "codex":
        return (*command, "login", "--device-auth")
    if provider_id in {"elevenlabs", "ollama"}:
        raise ValueError(f"{PROVIDER_TITLES[provider_id]} does not support subscription login")
    del project_id
    return command


def provider_logout_command(
    provider_id: ProviderId,
    *,
    base_env: dict[str, str] | None = None,
) -> tuple[str, ...] | None:
    if provider_id == "ollama":
        return None
    command = resolve_provider_command(provider_id, base_env=base_env)
    if provider_id == "claude":
        return (*command, "auth", "logout")
    if provider_id == "codex":
        return (*command, "logout")
    if provider_id == "elevenlabs":
        return None
    return None


def build_provider_process_env(
    provider_id: ProviderId,
    *,
    auth_mode: ProviderAuthMode,
    api_key: str = "",
    project_id: str = "",
    base_url: str = "",
    base_env: dict[str, str] | None = None,
) -> dict[str, str]:
    from koda.services.provider_env import build_llm_subprocess_env

    source = _provider_command_env(base_env)
    env = build_llm_subprocess_env(source, provider=provider_id)
    if provider_id == "codex":
        configured_bin = str(source.get("CODEX_BIN") or "").strip()
        if configured_bin:
            env["CODEX_BIN"] = configured_bin
    if provider_id == "gemini":
        configured_bin = str(source.get("GEMINI_BIN") or "").strip()
        if configured_bin:
            env["GEMINI_BIN"] = configured_bin
    if provider_id == "ollama":
        resolved_base_url = base_url.strip() or str(source.get(PROVIDER_BASE_URL_ENV_KEYS["ollama"]) or "").strip()
        if not resolved_base_url:
            resolved_base_url = provider_default_base_url("ollama", auth_mode)
        env[PROVIDER_BASE_URL_ENV_KEYS["ollama"]] = resolved_base_url
    env[PROVIDER_AUTH_MODE_ENV_KEYS[provider_id]] = auth_mode

    api_key_env_key = PROVIDER_API_KEY_ENV_KEYS[provider_id]
    if auth_mode == "api_key":
        if api_key:
            env[api_key_env_key] = api_key
    else:
        env.pop(api_key_env_key, None)
        if provider_id == "gemini":
            env.pop("GOOGLE_API_KEY", None)

    if provider_id == "gemini":
        if project_id:
            env["GOOGLE_CLOUD_PROJECT"] = project_id
        elif auth_mode == "api_key":
            env.pop("GOOGLE_CLOUD_PROJECT", None)

    return env


def _resolve_work_dir(work_dir: str | None = None) -> str:
    if not work_dir:
        return os.getcwd()
    path = Path(work_dir)
    path.mkdir(parents=True, exist_ok=True)
    return str(path)


def _set_pty_window_size(fd: int, rows: int = 48, cols: int = 240) -> None:
    with suppress(OSError):
        fcntl.ioctl(fd, termios.TIOCSWINSZ, struct.pack("HHHH", rows, cols, 0, 0))


def start_login_process(
    provider_id: ProviderId,
    *,
    project_id: str = "",
    base_env: dict[str, str] | None = None,
    work_dir: str | None = None,
) -> tuple[_ProviderLoginProcess, ProviderLoginSessionState]:
    command = provider_login_command(provider_id, project_id=project_id, base_env=base_env)
    env = build_provider_process_env(
        provider_id,
        auth_mode="subscription_login",
        project_id=project_id,
        base_env=base_env,
    )
    # PTY-spawned CLIs (Claude, Gemini) need TERM so they detect an
    # interactive terminal and keep waiting for user input instead of
    # printing the auth URL and exiting immediately.
    if "TERM" not in env:
        env["TERM"] = "xterm-256color"

    session_id = uuid4().hex
    cwd = _resolve_work_dir(work_dir)

    if provider_id == "claude":
        master_fd, slave_fd = pty.openpty()
        _set_pty_window_size(master_fd)
        _set_pty_window_size(slave_fd)
        process = subprocess.Popen(
            command,
            stdin=slave_fd,
            stdout=slave_fd,
            stderr=slave_fd,
            cwd=cwd,
            env=env,
            close_fds=True,
        )
        os.close(slave_fd)
        handle = _ProviderLoginProcess(
            provider_id=provider_id,
            auth_mode="subscription_login",
            command=command,
            process=process,
            interactive_fd=master_fd,
            work_dir=cwd,
        )
    elif provider_id == "gemini":
        master_fd, slave_fd = pty.openpty()
        _set_pty_window_size(master_fd)
        _set_pty_window_size(slave_fd)
        process = subprocess.Popen(
            command,
            stdin=slave_fd,
            stdout=slave_fd,
            stderr=slave_fd,
            cwd=cwd,
            env=env,
            close_fds=True,
        )
        os.close(slave_fd)
        handle = _ProviderLoginProcess(
            provider_id=provider_id,
            auth_mode="subscription_login",
            command=command,
            process=process,
            interactive_fd=master_fd,
            work_dir=cwd,
            allow_workspace_trust=bool(work_dir),
        )
    else:
        process = cast(
            subprocess.Popen[Any],
            subprocess.Popen(
                command,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                cwd=cwd,
                env=env,
                close_fds=True,
            ),
        )
        handle = _ProviderLoginProcess(
            provider_id=provider_id,
            auth_mode="subscription_login",
            command=command,
            process=process,
            work_dir=cwd,
        )

    handle.start()
    deadline = time.monotonic() + (2.5 if provider_id in {"claude", "codex", "gemini"} else 0.15)
    state = parse_login_session_state(session_id, handle)
    while time.monotonic() < deadline:
        if state.auth_url or state.user_code or state.status == "error":
            break
        time.sleep(0.05)
        state = parse_login_session_state(session_id, handle)
    return handle, state


def parse_login_session_state(session_id: str, handle: _ProviderLoginProcess) -> ProviderLoginSessionState:
    text = handle.normalized_output().strip()
    compact_text = " ".join(text.split())
    compact_lower = compact_text.lower()
    returncode = handle.process.poll()
    running = returncode is None
    auth_url = ""
    user_code = ""
    message = ""
    instructions = ""
    last_error = ""
    status = "pending"

    if handle.provider_id == "claude":
        auth_url = _last_url(text)
        code_match = _CODE_RE.search(text)
        if code_match:
            user_code = code_match.group(0)
        # Rewrite callback URL to use the control-plane OAuth relay so
        # the browser callback reaches the CLI subprocess inside Docker.
        if auth_url:
            auth_url, internal_callback = _rewrite_auth_callback_for_relay(auth_url, session_id)
            if internal_callback:
                _OAUTH_RELAY_TARGETS[session_id] = internal_callback
        instructions = "Abra o link do Claude Code e conclua o login no navegador."
        if user_code:
            instructions += " Se a Anthropic exibir um Authentication Code, cole-o no campo abaixo."
        if auth_url and (
            "visit" in text.lower()
            or "browser" in text.lower()
            or "paste code here if prompted" in compact_lower
            or bool(user_code)
        ):
            status = "awaiting_browser"
            message = "Authorize in the browser to complete the Anthropic login."
        if "oauth error:" in compact_lower or "invalid code" in compact_lower:
            status = "awaiting_browser"
            last_error = "Claude Code rejected the authentication code. Copy the complete code and try again."
            message = last_error
        elif "press enter to retry" in compact_lower:
            status = "awaiting_browser"
            message = "Claude Code requested another attempt. Generate a new code in the browser and submit it again."
    elif handle.provider_id == "codex":
        auth_url = _last_url(text)
        code_match = _CODE_RE.search(text)
        if code_match:
            user_code = code_match.group(0)
        instructions = "Open the Codex link and enter the temporary code."
        if auth_url:
            status = "awaiting_browser"
            message = "Authorization waiting for confirmation in ChatGPT."
    else:
        auth_url = _last_url(text)
        instructions = "Open the Google account link and complete Gemini CLI authorization."
        if auth_url:
            status = "awaiting_browser"
            message = "Authorization waiting for confirmation in the Google account."
        elif "Waiting for authentication" in text:
            status = "pending"
            message = "Preparing Gemini CLI authorization."

    if not running:
        if returncode == 0:
            if handle.provider_id in {"claude", "codex", "gemini"} and (auth_url or user_code):
                status = "awaiting_browser"
                message = message or "Authorize in the browser to complete the login."
            else:
                status = "completed"
                message = message or "Official login flow completed."
        else:
            status = "error"
            last_error = _friendly_provider_error(
                handle.provider_id,
                text,
                fallback=f"{handle.provider_id} login failed",
            )
            message = "The login flow ended with an error."

    return ProviderLoginSessionState(
        session_id=session_id,
        provider_id=handle.provider_id,
        auth_mode=handle.auth_mode,
        status=status,
        command=" ".join(handle.command),
        auth_url=auth_url,
        user_code=user_code,
        message=message,
        instructions=instructions,
        output_preview=_truncate_output(text),
        last_error=last_error,
    )


def run_provider_logout(
    provider_id: ProviderId,
    *,
    base_env: dict[str, str] | None = None,
    work_dir: str | None = None,
) -> tuple[bool, str]:
    command = provider_logout_command(provider_id, base_env=base_env)
    if command is None:
        return False, "logout not supported"
    env = build_provider_process_env(
        provider_id,
        auth_mode="subscription_login",
        base_env=base_env,
    )
    try:
        proc = subprocess.run(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            timeout=15,
            env=env,
            cwd=_resolve_work_dir(work_dir),
            check=False,
        )
    except FileNotFoundError:
        return False, f"{command[0]} not found on PATH"
    except subprocess.TimeoutExpired:
        return False, f"{provider_id} logout timed out"
    output = strip_ansi(proc.stdout or "").strip()
    return proc.returncode == 0, output


def verify_provider_api_key(
    provider_id: ProviderId,
    api_key: str,
    *,
    project_id: str = "",
    base_url: str = "",
) -> ProviderVerificationResult:
    secret = api_key.strip()
    if not secret:
        return ProviderVerificationResult(
            provider_id=provider_id,
            auth_mode="api_key",
            verified=False,
            last_error="API key ausente.",
            checked_via="api_key",
            details={},
        )

    try:
        if provider_id == "claude":
            # Support both API key (x-api-key) and OAuth token (Bearer).
            is_oauth_token = secret.startswith("sk-ant-oat")
            headers: dict[str, str] = {"anthropic-version": "2023-06-01", "User-Agent": "koda/control-plane"}
            if is_oauth_token:
                headers["Authorization"] = f"Bearer {secret}"
            else:
                headers["x-api-key"] = secret
            request = urllib_request.Request(
                "https://api.anthropic.com/v1/models",
                headers=headers,
            )
            with urllib_request.urlopen(request, timeout=10) as response:
                payload = json.loads(response.read().decode("utf-8"))
            return ProviderVerificationResult(
                provider_id=provider_id,
                auth_mode="api_key",
                verified=bool(payload),
                account_label="Anthropic Console",
                plan_label="API key",
                checked_via="api_key",
                details={"provider": "claude"},
            )

        if provider_id == "codex":
            request = urllib_request.Request(
                "https://api.openai.com/v1/models",
                headers={
                    "Authorization": f"Bearer {secret}",
                    "User-Agent": "koda/control-plane",
                },
            )
            with urllib_request.urlopen(request, timeout=10) as response:
                payload = json.loads(response.read().decode("utf-8"))
            return ProviderVerificationResult(
                provider_id=provider_id,
                auth_mode="api_key",
                verified=bool(payload),
                account_label="OpenAI Platform",
                plan_label="API key",
                checked_via="api_key",
                details={"provider": "codex"},
            )

        if provider_id == "elevenlabs":
            request = urllib_request.Request(
                "https://api.elevenlabs.io/v1/models",
                headers={
                    "xi-api-key": secret,
                    "User-Agent": "koda/control-plane",
                },
            )
            with urllib_request.urlopen(request, timeout=10) as response:
                payload = json.loads(response.read().decode("utf-8"))
            return ProviderVerificationResult(
                provider_id=provider_id,
                auth_mode="api_key",
                verified=bool(payload),
                account_label="ElevenLabs",
                plan_label="API key",
                checked_via="api_key",
                details={"provider": "elevenlabs"},
            )

        if provider_id == "ollama":
            request = urllib_request.Request(
                ollama_api_url(base_url, "tags", auth_mode="api_key"),
                headers={
                    "Authorization": f"Bearer {secret}",
                    "User-Agent": "koda/control-plane",
                },
            )
            with urllib_request.urlopen(request, timeout=10) as response:
                payload = json.loads(response.read().decode("utf-8"))
            return ProviderVerificationResult(
                provider_id=provider_id,
                auth_mode="api_key",
                verified=bool(payload),
                account_label="Ollama Cloud",
                plan_label="API key",
                checked_via="api_key",
                details={"provider": "ollama"},
            )

        query = urllib_parse.urlencode({"key": secret})
        request = urllib_request.Request(
            f"https://generativelanguage.googleapis.com/v1beta/models?{query}",
            headers={"User-Agent": "koda/control-plane"},
        )
        with urllib_request.urlopen(request, timeout=10) as response:
            payload = json.loads(response.read().decode("utf-8"))
        account_label = "Google AI Studio"
        if project_id.strip():
            account_label = f"{account_label} · {project_id.strip()}"
        return ProviderVerificationResult(
            provider_id=provider_id,
            auth_mode="api_key",
            verified=bool(payload),
            account_label=account_label,
            plan_label="Gemini API key",
            checked_via="api_key",
            details={"project_id": project_id},
        )
    except urllib_error.HTTPError as exc:
        body = exc.read().decode("utf-8", "replace")
        return ProviderVerificationResult(
            provider_id=provider_id,
            auth_mode="api_key",
            verified=False,
            last_error=_short_http_error(exc.code, body),
            checked_via="api_key",
            auth_expired=exc.code in {401, 403} or _looks_like_auth_expired(body),
            details={"http_status": exc.code},
        )
    except Exception as exc:
        return ProviderVerificationResult(
            provider_id=provider_id,
            auth_mode="api_key",
            verified=False,
            last_error=str(exc),
            checked_via="api_key",
            auth_expired=_looks_like_auth_expired(str(exc)),
            details={},
        )


def _verify_claude_local_cli(
    *,
    base_env: dict[str, str] | None = None,
    work_dir: str | None = None,
) -> ProviderVerificationResult:
    """Check whether the ``claude`` CLI on the local machine is already authenticated."""
    try:
        cmd = (*resolve_provider_command("claude", base_env=base_env), "auth", "status", "--json")
    except (KeyError, FileNotFoundError):
        return ProviderVerificationResult(
            provider_id="claude",
            auth_mode="local",
            verified=False,
            last_error="Claude Code CLI not found. Install with: npm install -g @anthropic-ai/claude-code",
            checked_via="local_cli",
        )
    env = build_provider_process_env(
        "claude",
        auth_mode="local",
        base_env=base_env,
    )
    env["TERM"] = "xterm-256color"
    cwd = _resolve_work_dir(work_dir)
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=8, env=env, cwd=cwd, check=False)
        stdout_text = strip_ansi(proc.stdout or "").strip()
        payload: dict[str, Any] | None = None
        with suppress(json.JSONDecodeError):
            parsed = json.loads(stdout_text or "{}")
            if isinstance(parsed, dict):
                payload = parsed
        if payload and payload.get("loggedIn"):
            return ProviderVerificationResult(
                provider_id="claude",
                auth_mode="local",
                verified=True,
                account_label=str(payload.get("email") or payload.get("orgName") or "Claude CLI"),
                plan_label=str(payload.get("subscriptionType") or payload.get("authMethod") or "Local CLI"),
                checked_via="local_cli",
            )
        return ProviderVerificationResult(
            provider_id="claude",
            auth_mode="local",
            verified=False,
            last_error="Claude Code CLI not authenticated. Run 'claude auth login' in your terminal first.",
            checked_via="local_cli",
        )
    except Exception as exc:
        return ProviderVerificationResult(
            provider_id="claude",
            auth_mode="local",
            verified=False,
            last_error=f"Error verifying Claude CLI: {exc}",
            checked_via="local_cli",
        )


def verify_provider_local_connection(
    provider_id: ProviderId,
    *,
    base_url: str = "",
    base_env: dict[str, str] | None = None,
    work_dir: str | None = None,
) -> ProviderVerificationResult:
    if provider_id == "claude":
        return _verify_claude_local_cli(base_env=base_env, work_dir=work_dir)
    if provider_id != "ollama":
        return ProviderVerificationResult(
            provider_id=provider_id,
            auth_mode="local",
            verified=False,
            last_error="This provider does not support direct local connection.",
            checked_via="local_probe",
            details={},
        )

    resolved_base_url = base_url.strip() or provider_default_base_url("ollama", "local")
    try:
        request = urllib_request.Request(
            ollama_api_url(resolved_base_url, "tags", auth_mode="local"),
            headers={"User-Agent": "koda/control-plane"},
        )
        with urllib_request.urlopen(request, timeout=10) as response:
            payload = json.loads(response.read().decode("utf-8"))
        return ProviderVerificationResult(
            provider_id="ollama",
            auth_mode="local",
            verified=bool(payload),
            account_label=resolved_base_url,
            plan_label="Ollama server",
            checked_via="local_probe",
            details={"base_url": resolved_base_url},
        )
    except urllib_error.HTTPError as exc:
        body = exc.read().decode("utf-8", "replace")
        return ProviderVerificationResult(
            provider_id="ollama",
            auth_mode="local",
            verified=False,
            last_error=_short_http_error(exc.code, body),
            checked_via="local_probe",
            auth_expired=exc.code in {401, 403} or _looks_like_auth_expired(body),
            details={"http_status": exc.code, "base_url": resolved_base_url},
        )
    except Exception as exc:
        raw_error = str(exc)
        # Surface actionable guidance when the most common Docker / local dev
        # failure modes happen (connection refused, timeout, DNS failure).
        # The raw errno stays in `details.raw_error` for operators who need it.
        lowered = raw_error.lower()
        reachability_markers = (
            "connection refused",
            "[errno 111]",
            "[errno -2]",  # name or service not known
            "[errno -3]",  # temporary failure in name resolution
            "name or service not known",
            "nodename nor servname",
            "timed out",
            "timeout",
            "no route to host",
        )
        friendly_error = raw_error
        if any(marker in lowered for marker in reachability_markers):
            in_container = _running_inside_container()
            hints = [
                "Could not reach Ollama.",
                f"URL attempted: {resolved_base_url}.",
            ]
            if in_container:
                hints.append(
                    "Koda is running in a container. Use http://host.docker.internal:11434 "
                    "for Ollama on the host (Docker Desktop macOS/Windows; on Linux the compose "
                    "already adds host-gateway), or http://<service-name>:11434 if Ollama runs "
                    "in another container on the same network."
                )
            else:
                hints.append("Confirm Ollama is running (ollama serve) and listening on http://localhost:11434.")
            friendly_error = " ".join(hints)
        return ProviderVerificationResult(
            provider_id="ollama",
            auth_mode="local",
            verified=False,
            last_error=friendly_error,
            checked_via="local_probe",
            auth_expired=_looks_like_auth_expired(raw_error),
            details={"base_url": resolved_base_url, "raw_error": raw_error},
        )


def verify_provider_subscription_login(
    provider_id: ProviderId,
    *,
    project_id: str = "",
    base_env: dict[str, str] | None = None,
    work_dir: str | None = None,
) -> ProviderVerificationResult:
    if provider_id in {"elevenlabs", "ollama"}:
        return ProviderVerificationResult(
            provider_id=provider_id,
            auth_mode="subscription_login",
            verified=False,
            last_error=f"{PROVIDER_TITLES[provider_id]} does not support subscription login in this flow.",
            checked_via="runtime",
            details={},
        )
    env = build_provider_process_env(
        provider_id,
        auth_mode="subscription_login",
        project_id=project_id,
        base_env=base_env,
    )
    cwd = _resolve_work_dir(work_dir)
    try:
        if provider_id == "claude":
            command = (*resolve_provider_command("claude", base_env=env), "auth", "status", "--json")
            proc = subprocess.run(
                command,
                capture_output=True,
                text=True,
                timeout=8,
                env=env,
                cwd=cwd,
                check=False,
            )
            stdout_text = strip_ansi(proc.stdout or "").strip()
            stderr_text = strip_ansi(proc.stderr or "").strip()
            payload: dict[str, Any] | None = None
            with suppress(json.JSONDecodeError):
                parsed = json.loads(stdout_text or "{}")
                if isinstance(parsed, dict):
                    payload = parsed
            if payload is not None:
                if not payload.get("loggedIn"):
                    return ProviderVerificationResult(
                        provider_id=provider_id,
                        auth_mode="subscription_login",
                        verified=False,
                        last_error=(
                            "Claude CLI not authenticated yet. "
                            "Complete authorization in the browser and submit the Authentication Code if requested."
                        ),
                        checked_via="auth_status",
                        auth_expired=False,
                        details={"stdout": stdout_text},
                    )
                return ProviderVerificationResult(
                    provider_id=provider_id,
                    auth_mode="subscription_login",
                    verified=True,
                    account_label=str(payload.get("email") or payload.get("orgName") or "Claude"),
                    plan_label=str(payload.get("subscriptionType") or payload.get("authMethod") or "Claude"),
                    checked_via="auth_status",
                    details={"stdout": stdout_text},
                )
            if proc.returncode != 0:
                return ProviderVerificationResult(
                    provider_id=provider_id,
                    auth_mode="subscription_login",
                    verified=False,
                    last_error=_friendly_provider_error(
                        provider_id,
                        stderr_text or stdout_text,
                        fallback="Claude CLI not authenticated.",
                    ),
                    checked_via="auth_status",
                    auth_expired=_looks_like_auth_expired(stderr_text or stdout_text),
                    details={"returncode": proc.returncode, "stdout": stdout_text, "stderr": stderr_text},
                )
            payload = json.loads(stdout_text or "{}")
            if not isinstance(payload, dict) or not payload.get("loggedIn"):
                return ProviderVerificationResult(
                    provider_id=provider_id,
                    auth_mode="subscription_login",
                    verified=False,
                    last_error="Claude CLI not authenticated.",
                    checked_via="auth_status",
                    auth_expired=_looks_like_auth_expired(stdout_text),
                    details={"stdout": stdout_text},
                )
            return ProviderVerificationResult(
                provider_id=provider_id,
                auth_mode="subscription_login",
                verified=True,
                account_label=str(payload.get("email") or payload.get("orgName") or "Claude"),
                plan_label=str(payload.get("subscriptionType") or payload.get("authMethod") or "Claude"),
                checked_via="auth_status",
                details={"stdout": stdout_text},
            )

        if provider_id == "codex":
            command = (*resolve_provider_command("codex", base_env=env), "login", "status")
            proc = subprocess.run(
                command,
                capture_output=True,
                text=True,
                timeout=8,
                env=env,
                cwd=cwd,
                check=False,
            )
            text = strip_ansi(proc.stdout or proc.stderr or "").strip()
            lower = text.lower()
            if proc.returncode != 0 or "logged in" not in lower:
                return ProviderVerificationResult(
                    provider_id=provider_id,
                    auth_mode="subscription_login",
                    verified=False,
                    last_error=_friendly_provider_error(provider_id, text, fallback="Codex CLI not authenticated."),
                    checked_via="login_status",
                    auth_expired=_looks_like_auth_expired(text),
                    details={"stdout": text},
                )
            if "api key" in lower:
                return ProviderVerificationResult(
                    provider_id=provider_id,
                    auth_mode="subscription_login",
                    verified=False,
                    last_error="Codex is authenticated via API key, not via ChatGPT.",
                    checked_via="login_status",
                    auth_expired=False,
                    details={"stdout": text},
                )
            plan = "ChatGPT"
            if "chatgpt" in text:
                plan = text
            return ProviderVerificationResult(
                provider_id=provider_id,
                auth_mode="subscription_login",
                verified=True,
                account_label="OpenAI / ChatGPT",
                plan_label=plan,
                checked_via="login_status",
                details={"stdout": text},
            )

        command = (
            *resolve_provider_command("gemini", base_env=env),
            "-p",
            "Reply with OK only.",
            "--output-format",
            "json",
        )
        proc = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=20,
            env=env,
            cwd=cwd,
            check=False,
        )
        text = strip_ansi(proc.stdout or proc.stderr or "").strip()
        if "Opening authentication page in your browser" in text or "Waiting for authentication" in text:
            return ProviderVerificationResult(
                provider_id=provider_id,
                auth_mode="subscription_login",
                verified=False,
                last_error="Gemini CLI has not yet completed authentication with Google.",
                checked_via="headless_probe",
                auth_expired=False,
                details={"stdout": text},
            )
        if proc.returncode != 0:
            return ProviderVerificationResult(
                provider_id=provider_id,
                auth_mode="subscription_login",
                verified=False,
                last_error=_friendly_provider_error(provider_id, text, fallback="Gemini CLI not authenticated."),
                checked_via="headless_probe",
                auth_expired=_looks_like_auth_expired(text),
                details={"stdout": text},
            )
        payload = json.loads(text or "{}")
        if not isinstance(payload, dict) or payload.get("error"):
            return ProviderVerificationResult(
                provider_id=provider_id,
                auth_mode="subscription_login",
                verified=False,
                last_error=str(payload.get("error") or "Gemini CLI not authenticated."),
                checked_via="headless_probe",
                auth_expired=_looks_like_auth_expired(str(payload.get("error") or text)),
                details={"stdout": text},
            )
        account_label = "Google account"
        if project_id.strip():
            account_label = f"{account_label} · {project_id.strip()}"
        return ProviderVerificationResult(
            provider_id=provider_id,
            auth_mode="subscription_login",
            verified=True,
            account_label=account_label,
            plan_label="Sign in with Google",
            checked_via="headless_probe",
            details={"stdout": text},
        )
    except FileNotFoundError as exc:
        return ProviderVerificationResult(
            provider_id=provider_id,
            auth_mode="subscription_login",
            verified=False,
            last_error=_friendly_provider_error(provider_id, f"{exc} not found on PATH"),
            checked_via="runtime",
            details={},
        )
    except subprocess.TimeoutExpired:
        return ProviderVerificationResult(
            provider_id=provider_id,
            auth_mode="subscription_login",
            verified=False,
            last_error=f"{PROVIDER_TITLES[provider_id]} auth verification timed out.",
            checked_via="runtime",
            details={},
        )
    except Exception as exc:
        return ProviderVerificationResult(
            provider_id=provider_id,
            auth_mode="subscription_login",
            verified=False,
            last_error=str(exc),
            checked_via="runtime",
            auth_expired=_looks_like_auth_expired(str(exc)),
            details={},
        )


def _last_url(text: str) -> str:
    lines = [raw_line.strip() for raw_line in text.splitlines()]
    urls: list[str] = []
    idx = 0

    while idx < len(lines):
        line = lines[idx]
        if not line:
            idx += 1
            continue

        match = _URL_RE.search(line)
        if not match:
            idx += 1
            continue

        current = match.group(0)
        idx += 1

        while idx < len(lines):
            continuation = lines[idx]
            if not continuation:
                idx += 1
                continue
            if continuation.startswith("https://"):
                break
            if _URL_CONTINUATION_RE.fullmatch(continuation):
                current += continuation
                idx += 1
                continue
            break

        urls.append(current)

    return urls[-1] if urls else ""


# ---------------------------------------------------------------------------
# OAuth relay: rewrite CLI callback URLs so they go through the control plane
# ---------------------------------------------------------------------------

_OAUTH_RELAY_TARGETS: dict[str, str] = {}
"""Maps session_id → internal callback URL (http://localhost:PORT/...)."""


def _is_running_in_docker() -> bool:
    """Return True if the process is running inside a Docker container."""
    if os.environ.get("RUNNING_IN_DOCKER", "").strip().lower() in {"1", "true", "yes"}:
        return True
    return Path("/.dockerenv").exists()


def get_oauth_relay_target(session_id: str) -> str | None:
    """Return the internal callback URL for a relay session."""
    return _OAUTH_RELAY_TARGETS.get(session_id)


def clear_oauth_relay_target(session_id: str) -> None:
    _OAUTH_RELAY_TARGETS.pop(session_id, None)


def _rewrite_auth_callback_for_relay(auth_url: str, session_id: str) -> tuple[str, str]:
    """Rewrite a CLI auth URL to route the callback through the control plane relay.

    Returns (rewritten_url, internal_callback_url). If no rewrite is needed,
    returns (original_url, "").
    """
    # The relay is only needed inside Docker where localhost from the container
    # is not reachable by the host browser.  On macOS / bare-metal the CLI's
    # localhost callback server is directly accessible, and rewriting
    # redirect_uri breaks OAuth token exchange (redirect_uri mismatch).
    if not _is_running_in_docker():
        return auth_url, ""
    try:
        parsed = urllib_parse.urlparse(auth_url)
        qs = urllib_parse.parse_qs(parsed.query, keep_blank_values=True)

        # Look for a callback/redirect_uri parameter pointing to localhost
        for param_name in ("callback", "redirect_uri", "redirect"):
            values = qs.get(param_name, [])
            if not values:
                continue
            callback_url = values[0]
            if "localhost" not in callback_url and "127.0.0.1" not in callback_url:
                continue

            # Found a localhost callback — rewrite it
            internal_callback = callback_url
            cp_port = os.environ.get("CONTROL_PLANE_PORT", "8090")
            relay_url = f"http://localhost:{cp_port}/api/control-plane/oauth-relay/{session_id}"

            # Replace the callback parameter in the auth URL
            qs[param_name] = [relay_url]
            new_query = urllib_parse.urlencode(qs, doseq=True)
            rewritten = urllib_parse.urlunparse(parsed._replace(query=new_query))
            return rewritten, internal_callback

    except Exception:
        pass

    return auth_url, ""


def _truncate_output(text: str, limit: int = 1400) -> str:
    stripped = text.strip()
    if len(stripped) <= limit:
        return stripped
    return stripped[: limit - 1] + "…"


def _tail_line(text: str) -> str:
    for line in reversed(text.splitlines()):
        stripped = line.strip()
        if stripped:
            return stripped
    return ""


def _looks_like_auth_expired(text: str) -> bool:
    normalized = str(text or "").lower()
    return any(token in normalized for token in ("invalid_grant", "expired", "unauthorized", "forbidden", "reauth"))


def _base64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")


# ---------------------------------------------------------------------------
# Claude direct OAuth PKCE — bypass CLI subprocess entirely
# ---------------------------------------------------------------------------

_CLAUDE_OAUTH_CLIENT_ID = "9d1c250a-e61b-44d9-88ed-5944d1962f5e"
_CLAUDE_OAUTH_AUTH_URL = "https://claude.com/cai/oauth/authorize"
_CLAUDE_OAUTH_TOKEN_URL = "https://platform.claude.com/v1/oauth/token"
_CLAUDE_OAUTH_API_KEY_URL = "https://api.anthropic.com/api/oauth/claude_cli/create_api_key"
_CLAUDE_OAUTH_REDIRECT_URI = "https://platform.claude.com/oauth/code/callback"
_CLAUDE_OAUTH_SCOPES = (
    "org:create_api_key user:profile user:inference user:sessions:claude_code user:mcp_servers user:file_upload"
)


def _generate_pkce_pair() -> tuple[str, str]:
    """Generate a PKCE code_verifier and code_challenge (S256)."""
    import hashlib
    import secrets

    verifier = secrets.token_urlsafe(48)
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    challenge = _base64url_encode(digest)
    return verifier, challenge


def start_claude_direct_oauth(session_id: str) -> ProviderLoginSessionState:
    """Start a Claude OAuth flow without the CLI subprocess.

    Returns a session state with the auth URL and the code_verifier stored
    for later exchange.
    """
    verifier, challenge = _generate_pkce_pair()
    state_param = _base64url_encode(os.urandom(32))

    params = urllib_parse.urlencode(
        {
            "code": "true",
            "client_id": _CLAUDE_OAUTH_CLIENT_ID,
            "response_type": "code",
            "redirect_uri": _CLAUDE_OAUTH_REDIRECT_URI,
            "scope": _CLAUDE_OAUTH_SCOPES,
            "code_challenge": challenge,
            "code_challenge_method": "S256",
            "state": state_param,
        }
    )
    auth_url = f"{_CLAUDE_OAUTH_AUTH_URL}?{params}"

    return ProviderLoginSessionState(
        session_id=session_id,
        provider_id="claude",
        auth_mode="subscription_login",
        status="awaiting_browser",
        command="direct_oauth",
        auth_url=auth_url,
        message="Authorize in the browser to complete the Anthropic login.",
        instructions=(
            "Open the link and authorize in the browser. Paste the full code (including the '#') in the field below."
        ),
        code_verifier=verifier,
    )


def exchange_claude_oauth_code(
    raw_code: str,
    code_verifier: str,
) -> ProviderVerificationResult:
    """Exchange an OAuth authorization code for a Claude API key.

    *raw_code* is expected in the ``AUTH_CODE#STATE`` format used by
    Anthropic's callback page.
    """
    # Split the code by '#' — Anthropic's page shows auth_code#state
    parts = raw_code.strip().split("#", 1)
    auth_code = parts[0]
    state_param = parts[1] if len(parts) > 1 else ""
    if not auth_code:
        return ProviderVerificationResult(
            provider_id="claude",
            auth_mode="subscription_login",
            verified=False,
            last_error="Empty authentication code. Paste the full code from the Anthropic page.",
            checked_via="direct_oauth",
        )

    # Step 1: exchange code for access token.
    # Anthropic's token endpoint requires JSON with the ``state`` field.
    token_body: dict[str, Any] = {
        "grant_type": "authorization_code",
        "code": auth_code,
        "redirect_uri": _CLAUDE_OAUTH_REDIRECT_URI,
        "client_id": _CLAUDE_OAUTH_CLIENT_ID,
        "code_verifier": code_verifier,
    }
    if state_param:
        token_body["state"] = state_param
    token_payload = json.dumps(token_body).encode("utf-8")

    try:
        token_req = urllib_request.Request(
            _CLAUDE_OAUTH_TOKEN_URL,
            data=token_payload,
            headers={
                "Content-Type": "application/json",
                "User-Agent": "koda/control-plane",
            },
            method="POST",
        )
        with urllib_request.urlopen(token_req, timeout=15) as resp:
            token_data = json.loads(resp.read().decode("utf-8"))
    except urllib_error.HTTPError as exc:
        body = exc.read().decode("utf-8", "replace")
        return ProviderVerificationResult(
            provider_id="claude",
            auth_mode="subscription_login",
            verified=False,
            last_error=f"OAuth code exchange failed: {exc.code} — {body[:200]}",
            checked_via="direct_oauth",
            details={"http_status": exc.code, "body": body[:500]},
        )
    except Exception as exc:
        return ProviderVerificationResult(
            provider_id="claude",
            auth_mode="subscription_login",
            verified=False,
            last_error=f"OAuth exchange error: {exc}",
            checked_via="direct_oauth",
        )

    access_token = str(token_data.get("access_token") or "").strip()
    if not access_token:
        return ProviderVerificationResult(
            provider_id="claude",
            auth_mode="subscription_login",
            verified=False,
            last_error="Anthropic did not return an access_token. Please try again.",
            checked_via="direct_oauth",
        )

    # Step 2: try to mint a permanent API key.
    # The endpoint expects null body with only Authorization: Bearer header.
    api_key = ""
    try:
        api_key_req = urllib_request.Request(
            _CLAUDE_OAUTH_API_KEY_URL,
            headers={"Authorization": f"Bearer {access_token}"},
            method="POST",
        )
        with urllib_request.urlopen(api_key_req, timeout=15) as resp:
            api_key_data = json.loads(resp.read().decode("utf-8"))
        api_key = str(api_key_data.get("raw_key") or "").strip()
    except Exception:
        pass  # Fall through to auth_token path below.

    if api_key:
        return ProviderVerificationResult(
            provider_id="claude",
            auth_mode="api_key",
            verified=True,
            account_label="Claude (Subscription)",
            plan_label="Subscription",
            checked_via="direct_oauth",
            details={"api_key": api_key},
        )

    # API key creation failed (e.g. user lacks org:create_api_key scope).
    # Fall back to using the OAuth access_token directly — the Claude CLI
    # accepts it via ANTHROPIC_AUTH_TOKEN as a Bearer token.
    return ProviderVerificationResult(
        provider_id="claude",
        auth_mode="subscription_login",
        verified=True,
        account_label="Claude (Subscription)",
        plan_label="Subscription",
        checked_via="direct_oauth",
        details={"auth_token": access_token},
    )


def _mint_google_service_account_token(credentials_path: str) -> dict[str, Any]:
    path = Path(credentials_path).expanduser()
    payload = json.loads(path.read_text(encoding="utf-8"))
    client_email = str(payload.get("client_email") or "").strip()
    private_key = str(payload.get("private_key") or "").strip()
    token_uri = str(payload.get("token_uri") or "https://oauth2.googleapis.com/token").strip()
    project_id = str(payload.get("project_id") or "").strip()
    if not client_email:
        raise ValueError("service account JSON missing client_email")
    if not private_key:
        raise ValueError("service account JSON missing private_key")
    if not project_id:
        raise ValueError("service account JSON missing project_id")

    header = {"alg": "RS256", "typ": "JWT"}
    now = int(time.time())
    assertion_payload = {
        "iss": client_email,
        "scope": "https://www.googleapis.com/auth/cloud-platform",
        "aud": token_uri,
        "iat": now,
        "exp": now + 3600,
    }
    signing_input = ".".join(
        (
            _base64url_encode(json.dumps(header, separators=(",", ":"), ensure_ascii=True).encode("utf-8")),
            _base64url_encode(json.dumps(assertion_payload, separators=(",", ":"), ensure_ascii=True).encode("utf-8")),
        )
    )

    with tempfile.NamedTemporaryFile("w", delete=False) as tmp_key:
        tmp_key.write(private_key)
        private_key_path = tmp_key.name

    try:
        proc = subprocess.run(
            [
                "openssl",
                "dgst",
                "-sha256",
                "-sign",
                private_key_path,
                "-binary",
            ],
            input=signing_input.encode("utf-8"),
            capture_output=True,
            check=False,
        )
        if proc.returncode != 0:
            raise RuntimeError(strip_ansi((proc.stderr or b"").decode("utf-8", "replace")).strip() or "openssl failed")
        assertion = ".".join((signing_input, _base64url_encode(proc.stdout or b"")))
        body = urllib_parse.urlencode(
            {
                "grant_type": "urn:ietf:params:oauth:grant-type:jwt-bearer",
                "assertion": assertion,
            }
        ).encode("utf-8")
        request = urllib_request.Request(
            token_uri,
            data=body,
            headers={
                "Content-Type": "application/x-www-form-urlencoded",
                "User-Agent": "koda/control-plane",
            },
            method="POST",
        )
        with urllib_request.urlopen(request, timeout=10) as response:
            token_payload = json.loads(response.read().decode("utf-8"))
        if not isinstance(token_payload, dict) or not token_payload.get("access_token"):
            raise RuntimeError("service account token mint returned no access_token")
        return {
            "token_payload": token_payload,
            "client_email": client_email,
            "project_id": project_id,
            "token_uri": token_uri,
        }
    finally:
        with suppress(OSError):
            os.unlink(private_key_path)


def _friendly_provider_error(provider_id: ProviderId, text: str, *, fallback: str = "") -> str:
    normalized = strip_ansi(text or "").strip()
    lower = normalized.lower()
    if provider_id == "codex" and "enable device code authorization" in lower:
        return "Enable Codex device-code authorization in ChatGPT security settings and try again."
    if provider_id == "claude" and "not found on path" in lower:
        return "Claude Code CLI not found on the server PATH."
    if provider_id == "codex" and "not found on path" in lower:
        return "Codex CLI not found on the server PATH."
    if provider_id == "gemini" and "not found on path" in lower:
        return "Gemini CLI not found on the server PATH."
    return _tail_line(normalized) or fallback or normalized


def _short_http_error(status_code: int, body: str) -> str:
    stripped = body.strip()
    if len(stripped) > 260:
        stripped = stripped[:260] + "…"
    return f"HTTP {status_code}: {stripped or 'request failed'}"
