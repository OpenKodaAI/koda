"""Shared settings for the control plane."""

from __future__ import annotations

import os
import re
import tempfile
from pathlib import Path

from dotenv import load_dotenv

ROOT_DIR = Path(__file__).resolve().parents[2]
load_dotenv(ROOT_DIR / ".env")


def _resolve_path(raw: str, *, relative_to: Path) -> Path:
    path = Path(raw).expanduser()
    if not path.is_absolute():
        path = relative_to / path
    return path


STATE_ROOT_DIR: Path = Path(os.environ.get("STATE_ROOT_DIR", str(Path.home() / ".koda-state"))).expanduser()
RUNTIME_EPHEMERAL_ROOT: Path = Path(
    os.environ.get(
        "RUNTIME_EPHEMERAL_ROOT",
        str(Path(tempfile.gettempdir()) / "koda-runtime" / "control-plane"),
    )
).expanduser()

CONTROL_PLANE_ENABLED: bool = os.environ.get("CONTROL_PLANE_ENABLED", "true").lower() == "true"
KODA_ENV: str = os.environ.get("KODA_ENV", os.environ.get("NODE_ENV", "development")).strip().lower()
IS_PRODUCTION: bool = KODA_ENV == "production"
_ALLOW_LOOPBACK_BOOTSTRAP_RAW: str = os.environ.get("ALLOW_LOOPBACK_BOOTSTRAP", "").strip().lower()
if _ALLOW_LOOPBACK_BOOTSTRAP_RAW == "":
    ALLOW_LOOPBACK_BOOTSTRAP: bool = not IS_PRODUCTION
else:
    ALLOW_LOOPBACK_BOOTSTRAP = _ALLOW_LOOPBACK_BOOTSTRAP_RAW == "true"
    if ALLOW_LOOPBACK_BOOTSTRAP and IS_PRODUCTION:
        raise RuntimeError(
            "ALLOW_LOOPBACK_BOOTSTRAP=true is not allowed when KODA_ENV=production. "
            "Bootstrap the owner account via the bootstrap file instead."
        )
CONTROL_PLANE_BOOTSTRAP_CODE_SEED: str = os.environ.get("CONTROL_PLANE_BOOTSTRAP_CODE", "").strip()
CONTROL_PLANE_OPERATOR_PASSWORD_MIN_LENGTH: int = int(
    os.environ.get("CONTROL_PLANE_OPERATOR_PASSWORD_MIN_LENGTH", "12")
)
CONTROL_PLANE_RECOVERY_CODES_PER_USER: int = int(os.environ.get("CONTROL_PLANE_RECOVERY_CODES_PER_USER", "10"))
CONTROL_PLANE_MASTER_KEY: str = os.environ.get("CONTROL_PLANE_MASTER_KEY", "")
CONTROL_PLANE_MASTER_KEY_FILE: Path = _resolve_path(
    os.environ.get("CONTROL_PLANE_MASTER_KEY_FILE", str(STATE_ROOT_DIR / "control_plane" / ".master.key")),
    relative_to=STATE_ROOT_DIR,
)
CONTROL_PLANE_RUNTIME_DIR: Path = _resolve_path(
    os.environ.get("CONTROL_PLANE_RUNTIME_DIR", str(RUNTIME_EPHEMERAL_ROOT / "snapshots")),
    relative_to=RUNTIME_EPHEMERAL_ROOT,
)
CONTROL_PLANE_INLINE_RUNTIME_ASSETS: bool = (
    os.environ.get("CONTROL_PLANE_INLINE_RUNTIME_ASSETS", "true").lower() == "true"
)
CONTROL_PLANE_BIND: str = os.environ.get("CONTROL_PLANE_BIND", "127.0.0.1")
CONTROL_PLANE_PORT: int = int(os.environ.get("CONTROL_PLANE_PORT", "8090"))
CONTROL_PLANE_AUTH_MODE: str = os.environ.get("CONTROL_PLANE_AUTH_MODE", "token").strip().lower()
_ALLOWED_CONTROL_PLANE_AUTH_MODES: frozenset[str] = frozenset({"token", "open", "development"})
if CONTROL_PLANE_AUTH_MODE not in _ALLOWED_CONTROL_PLANE_AUTH_MODES:
    raise RuntimeError(
        f"Unknown CONTROL_PLANE_AUTH_MODE={CONTROL_PLANE_AUTH_MODE!r}. "
        f"Expected one of: {sorted(_ALLOWED_CONTROL_PLANE_AUTH_MODES)}. "
        "Refusing to boot to avoid a silent fail-open."
    )
if IS_PRODUCTION and CONTROL_PLANE_AUTH_MODE in {"development", "open"}:
    raise RuntimeError(
        f"CONTROL_PLANE_AUTH_MODE={CONTROL_PLANE_AUTH_MODE!r} is forbidden in production. "
        "Set CONTROL_PLANE_AUTH_MODE=token (default) for public deployments."
    )
CONTROL_PLANE_API_TOKEN: str = os.environ.get("CONTROL_PLANE_API_TOKEN", "")
CONTROL_PLANE_API_TOKENS: list[str] = [t.strip() for t in CONTROL_PLANE_API_TOKEN.split(",") if t.strip()]
CONTROL_PLANE_BOOTSTRAP_CODE_TTL_SECONDS: int = int(os.environ.get("CONTROL_PLANE_BOOTSTRAP_CODE_TTL_SECONDS", "900"))
CONTROL_PLANE_REGISTRATION_TOKEN_TTL_SECONDS: int = int(
    os.environ.get("CONTROL_PLANE_REGISTRATION_TOKEN_TTL_SECONDS", "1800")
)
CONTROL_PLANE_OPERATOR_SESSION_TTL_SECONDS: int = int(
    os.environ.get("CONTROL_PLANE_OPERATOR_SESSION_TTL_SECONDS", str(7 * 24 * 60 * 60))
)
CONTROL_PLANE_OPERATOR_TOKEN_TTL_DAYS: int = int(os.environ.get("CONTROL_PLANE_OPERATOR_TOKEN_TTL_DAYS", "90"))
CONTROL_PLANE_OPERATOR_LOGIN_MAX_FAILURES: int = int(os.environ.get("CONTROL_PLANE_OPERATOR_LOGIN_MAX_FAILURES", "5"))
CONTROL_PLANE_OPERATOR_LOGIN_LOCKOUT_SECONDS: int = int(
    os.environ.get("CONTROL_PLANE_OPERATOR_LOGIN_LOCKOUT_SECONDS", "900")
)

CONTROL_PLANE_MASTER_KEY_PREVIOUS: str = os.environ.get("CONTROL_PLANE_MASTER_KEY_PREVIOUS", "")
CONTROL_PLANE_MASTER_KEY_PREVIOUS_FILE: Path = _resolve_path(
    os.environ.get(
        "CONTROL_PLANE_MASTER_KEY_PREVIOUS_FILE",
        str(STATE_ROOT_DIR / "control_plane" / ".master-previous.key"),
    ),
    relative_to=STATE_ROOT_DIR,
)
CONTROL_PLANE_POLL_INTERVAL_SECONDS: float = float(os.environ.get("CONTROL_PLANE_POLL_INTERVAL_SECONDS", "5.0"))
CONTROL_PLANE_RESTART_GRACE_SECONDS: float = float(os.environ.get("CONTROL_PLANE_RESTART_GRACE_SECONDS", "15.0"))
CONTROL_PLANE_STARTUP_GRACE_SECONDS: float = float(os.environ.get("CONTROL_PLANE_STARTUP_GRACE_SECONDS", "2.0"))
CONTROL_PLANE_AUTO_IMPORT: bool = os.environ.get("CONTROL_PLANE_AUTO_IMPORT", "false").lower() == "true"
CONTROL_PLANE_SKIP_DEFAULT_SEED: bool = os.environ.get("CONTROL_PLANE_SKIP_DEFAULT_SEED", "false").lower() == "true"

CONTROL_PLANE_RATE_LIMIT: int = int(os.environ.get("CONTROL_PLANE_RATE_LIMIT", "120"))
CONTROL_PLANE_AUTH_FAILURE_RATE_LIMIT: int = int(os.environ.get("CONTROL_PLANE_AUTH_FAILURE_RATE_LIMIT", "5"))

AGENT_SECTIONS: tuple[str, ...] = (
    "general",
    "appearance",
    "identity",
    "prompting",
    "providers",
    "tools",
    "access",
    "integrations",
    "memory",
    "knowledge",
    "runtime",
    "scheduler",
)

DOCUMENT_KINDS: tuple[str, ...] = (
    "identity_md",
    "soul_md",
    "system_prompt_md",
    "instructions_md",
    "rules_md",
    "voice_prompt_md",
    "image_prompt_md",
    "memory_extraction_prompt_md",
)

SECRET_KEY_RE = re.compile(
    r"(^|_)(TOKEN|PASSWORD|SECRET|API_KEY|PRIVATE_KEY|CLIENT_KEY|POSTGRES_URL)($|_)",
    re.I,
)


def looks_like_secret_key(key: str) -> bool:
    return bool(SECRET_KEY_RE.search(str(key or "").strip().upper()))


DASHBOARD_PATH = ROOT_DIR.parent / "koda-dashboard"
DASHBOARD_AGENT_CONSTANTS_PATH = DASHBOARD_PATH / "src" / "lib" / "agent-constants.ts"
