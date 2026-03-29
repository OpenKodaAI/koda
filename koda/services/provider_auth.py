"""Canonical provider authentication helpers and short-lived login sessions."""

from __future__ import annotations

import json
import os
import pty
import re
import select
import shlex
import shutil
import subprocess
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
_CODE_RE = re.compile(r"\b[A-Z0-9]{4,}-[A-Z0-9]{4,}\b")


@dataclass(slots=True)
class ProviderVerificationResult:
    provider_id: ProviderId
    auth_mode: ProviderAuthMode
    verified: bool
    account_label: str = ""
    plan_label: str = ""
    last_error: str = ""
    checked_via: str = "static"


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
                    try:
                        remainder = os.read(fd, 65536)
                    except BlockingIOError:
                        remainder = b""
                    if remainder:
                        self._append(remainder.decode("utf-8", "replace"))
                    break
                ready, _, _ = select.select([fd], [], [], 0.2)
                if not ready:
                    continue
                try:
                    payload = os.read(fd, 65536)
                except BlockingIOError:
                    continue
                if not payload:
                    continue
                self._append(payload.decode("utf-8", "replace"))
        finally:
            with suppress(OSError):
                os.close(fd)

    def write(self, text: str) -> None:
        if self.interactive_fd is None:
            return
        os.write(self.interactive_fd, text.encode("utf-8"))

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
    return provider_id.strip().lower() in {"claude", "codex", "gemini"}


def provider_supports_local_connection(provider_id: str) -> bool:
    return provider_id.strip().lower() == "ollama"


def provider_requires_project_id(provider_id: str) -> bool:
    return provider_id == "gemini"


def provider_default_base_url(provider_id: str, auth_mode: str = "api_key") -> str:
    normalized = provider_id.strip().lower()
    if normalized != "ollama":
        return ""
    if auth_mode == "api_key":
        return "https://ollama.com"
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
        env = {**os.environ, **dict(base_env or {})}
        base_url_key = PROVIDER_BASE_URL_ENV_KEYS["ollama"]
        return bool(str(env.get(base_url_key) or provider_default_base_url("ollama", "local")).strip())
    try:
        resolve_provider_command(provider_id, base_env=base_env)
    except (KeyError, FileNotFoundError):
        return False
    return True


def resolve_provider_command(provider_id: str, base_env: dict[str, str] | None = None) -> tuple[str, ...]:
    env = {**os.environ, **dict(base_env or {})}
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
        return (*command, "auth", "login", "--claudeai")
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

    source = {**os.environ, **dict(base_env or {})}
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

    session_id = uuid4().hex
    cwd = _resolve_work_dir(work_dir)

    if provider_id == "gemini":
        master_fd, slave_fd = pty.openpty()
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
                stdin=subprocess.DEVNULL,
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
    time.sleep(0.15)
    state = parse_login_session_state(session_id, handle)
    return handle, state


def parse_login_session_state(session_id: str, handle: _ProviderLoginProcess) -> ProviderLoginSessionState:
    text = handle.normalized_output().strip()
    returncode = handle.process.poll()
    running = returncode is None
    auth_url = ""
    user_code = ""
    message = ""
    instructions = ""
    last_error = ""
    status = "pending"

    if handle.provider_id == "claude":
        if "visit:" in text.lower():
            auth_url = _last_url(text)
        instructions = "Abra o link do Claude Code e conclua o login no navegador."
        if auth_url:
            status = "awaiting_browser"
            message = "Autorização aguardando confirmação no Claude."
    elif handle.provider_id == "codex":
        auth_url = _last_url(text)
        code_match = _CODE_RE.search(text)
        if code_match:
            user_code = code_match.group(0)
        instructions = "Abra o link do Codex e informe o código temporário."
        if auth_url:
            status = "awaiting_browser"
            message = "Autorização aguardando confirmação no ChatGPT."
    else:
        auth_url = _last_url(text)
        instructions = "Abra o link da conta Google e finalize a autorização do Gemini CLI."
        if auth_url:
            status = "awaiting_browser"
            message = "Autorização aguardando confirmação na conta Google."
        elif "Waiting for authentication" in text:
            status = "pending"
            message = "Preparando autorização do Gemini CLI."

    if not running:
        if returncode == 0:
            status = "completed"
            message = message or "Fluxo oficial de login concluído."
        else:
            status = "error"
            last_error = _friendly_provider_error(
                handle.provider_id,
                text,
                fallback=f"{handle.provider_id} login failed",
            )
            message = "O fluxo de login terminou com erro."

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
        )

    try:
        if provider_id == "claude":
            request = urllib_request.Request(
                "https://api.anthropic.com/v1/models",
                headers={
                    "x-api-key": secret,
                    "anthropic-version": "2023-06-01",
                    "User-Agent": "koda/control-plane",
                },
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
        )
    except urllib_error.HTTPError as exc:
        body = exc.read().decode("utf-8", "replace")
        return ProviderVerificationResult(
            provider_id=provider_id,
            auth_mode="api_key",
            verified=False,
            last_error=_short_http_error(exc.code, body),
            checked_via="api_key",
        )
    except Exception as exc:
        return ProviderVerificationResult(
            provider_id=provider_id,
            auth_mode="api_key",
            verified=False,
            last_error=str(exc),
            checked_via="api_key",
        )


def verify_provider_local_connection(
    provider_id: ProviderId,
    *,
    base_url: str = "",
) -> ProviderVerificationResult:
    if provider_id != "ollama":
        return ProviderVerificationResult(
            provider_id=provider_id,
            auth_mode="local",
            verified=False,
            last_error="Este provider não suporta conexão local direta.",
            checked_via="local_probe",
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
            plan_label="Servidor Ollama",
            checked_via="local_probe",
        )
    except urllib_error.HTTPError as exc:
        body = exc.read().decode("utf-8", "replace")
        return ProviderVerificationResult(
            provider_id="ollama",
            auth_mode="local",
            verified=False,
            last_error=_short_http_error(exc.code, body),
            checked_via="local_probe",
        )
    except Exception as exc:
        return ProviderVerificationResult(
            provider_id="ollama",
            auth_mode="local",
            verified=False,
            last_error=str(exc),
            checked_via="local_probe",
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
            last_error=f"{PROVIDER_TITLES[provider_id]} não suporta login por assinatura neste fluxo.",
            checked_via="runtime",
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
            if proc.returncode != 0:
                return ProviderVerificationResult(
                    provider_id=provider_id,
                    auth_mode="subscription_login",
                    verified=False,
                    last_error=_friendly_provider_error(
                        provider_id,
                        strip_ansi(proc.stderr or proc.stdout),
                        fallback="Claude CLI nao autenticado.",
                    ),
                    checked_via="auth_status",
                )
            payload = json.loads(proc.stdout or "{}")
            if not isinstance(payload, dict) or not payload.get("loggedIn"):
                return ProviderVerificationResult(
                    provider_id=provider_id,
                    auth_mode="subscription_login",
                    verified=False,
                    last_error="Claude CLI nao autenticado.",
                    checked_via="auth_status",
                )
            return ProviderVerificationResult(
                provider_id=provider_id,
                auth_mode="subscription_login",
                verified=True,
                account_label=str(payload.get("email") or payload.get("orgName") or "Claude"),
                plan_label=str(payload.get("subscriptionType") or payload.get("authMethod") or "Claude"),
                checked_via="auth_status",
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
                    last_error=_friendly_provider_error(provider_id, text, fallback="Codex CLI nao autenticado."),
                    checked_via="login_status",
                )
            if "api key" in lower:
                return ProviderVerificationResult(
                    provider_id=provider_id,
                    auth_mode="subscription_login",
                    verified=False,
                    last_error="O Codex esta autenticado via API key, nao via ChatGPT.",
                    checked_via="login_status",
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
                last_error="Gemini CLI ainda nao concluiu a autenticacao com Google.",
                checked_via="headless_probe",
            )
        if proc.returncode != 0:
            return ProviderVerificationResult(
                provider_id=provider_id,
                auth_mode="subscription_login",
                verified=False,
                last_error=_friendly_provider_error(provider_id, text, fallback="Gemini CLI nao autenticado."),
                checked_via="headless_probe",
            )
        payload = json.loads(text or "{}")
        if not isinstance(payload, dict) or payload.get("error"):
            return ProviderVerificationResult(
                provider_id=provider_id,
                auth_mode="subscription_login",
                verified=False,
                last_error=str(payload.get("error") or "Gemini CLI nao autenticado."),
                checked_via="headless_probe",
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
        )
    except FileNotFoundError as exc:
        return ProviderVerificationResult(
            provider_id=provider_id,
            auth_mode="subscription_login",
            verified=False,
            last_error=_friendly_provider_error(provider_id, f"{exc} not found on PATH"),
            checked_via="runtime",
        )
    except subprocess.TimeoutExpired:
        return ProviderVerificationResult(
            provider_id=provider_id,
            auth_mode="subscription_login",
            verified=False,
            last_error=f"{PROVIDER_TITLES[provider_id]} auth verification timed out.",
            checked_via="runtime",
        )
    except Exception as exc:
        return ProviderVerificationResult(
            provider_id=provider_id,
            auth_mode="subscription_login",
            verified=False,
            last_error=str(exc),
            checked_via="runtime",
        )


def _last_url(text: str) -> str:
    matches = _URL_RE.findall(text)
    return matches[-1] if matches else ""


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


def _friendly_provider_error(provider_id: ProviderId, text: str, *, fallback: str = "") -> str:
    normalized = strip_ansi(text or "").strip()
    lower = normalized.lower()
    if provider_id == "codex" and "enable device code authorization" in lower:
        return (
            "Ative a autorizacao por codigo de dispositivo do Codex nas configuracoes de seguranca do ChatGPT "
            "e tente novamente."
        )
    if provider_id == "claude" and "not found on path" in lower:
        return "Claude Code CLI nao encontrado no PATH do servidor."
    if provider_id == "codex" and "not found on path" in lower:
        return "Codex CLI nao encontrado no PATH do servidor."
    if provider_id == "gemini" and "not found on path" in lower:
        return "Gemini CLI nao encontrado no PATH do servidor."
    return _tail_line(normalized) or fallback or normalized


def _short_http_error(status_code: int, body: str) -> str:
    stripped = body.strip()
    if len(stripped) > 260:
        stripped = stripped[:260] + "…"
    return f"HTTP {status_code}: {stripped or 'request failed'}"
