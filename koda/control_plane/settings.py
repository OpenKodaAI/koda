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
CONTROL_PLANE_API_TOKEN: str = os.environ.get("CONTROL_PLANE_API_TOKEN", "")
CONTROL_PLANE_POLL_INTERVAL_SECONDS: float = float(os.environ.get("CONTROL_PLANE_POLL_INTERVAL_SECONDS", "5.0"))
CONTROL_PLANE_RESTART_GRACE_SECONDS: float = float(os.environ.get("CONTROL_PLANE_RESTART_GRACE_SECONDS", "15.0"))
CONTROL_PLANE_STARTUP_GRACE_SECONDS: float = float(os.environ.get("CONTROL_PLANE_STARTUP_GRACE_SECONDS", "2.0"))
CONTROL_PLANE_AUTO_IMPORT: bool = os.environ.get("CONTROL_PLANE_AUTO_IMPORT", "false").lower() == "true"

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
