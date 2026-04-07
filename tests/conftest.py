"""Shared test fixtures."""

import os
import subprocess
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import grpc
import pytest

ROOT_DIR = Path(__file__).resolve().parents[1]

# Set env vars before importing config
os.environ.setdefault("AGENT_TOKEN", "test-token-123")
os.environ.setdefault("ALLOWED_USER_IDS", "111,222,333")
os.environ.setdefault("DEFAULT_WORK_DIR", tempfile.gettempdir())
# Force a neutral AGENT_ID so host shells or local .env files cannot leak
# agent-specific residue into the test suite.
os.environ["AGENT_ID"] = "AGENT_A"
os.environ["STATE_BACKEND"] = "postgres"


@pytest.fixture(autouse=True)
def _isolate_runtime_env():
    """Keep runtime-scoped env vars from leaking across tests."""
    tracked_keys = (
        "AGENT_ID",
        "CONTROL_PLANE_ACTIVE_VERSION",
        "CONTROL_PLANE_RUNTIME_BASE_URL",
        "CONTROL_PLANE_HEALTH_URL",
    )
    original = {key: os.environ.get(key) for key in tracked_keys}
    for key in tracked_keys:
        os.environ.pop(key, None)
    yield
    for key, previous in original.items():
        if previous is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = previous


@pytest.fixture(autouse=True)
def _default_state_backend():
    """Keep the default suite in explicit postgres-first mode."""
    with patch("koda.config.STATE_BACKEND", "postgres"):
        yield


@pytest.fixture(scope="session", autouse=True)
def _no_repo_root_database_residue():
    """Fail closed if tests leak local database artifacts into the repository root."""
    patterns = ("agent_history*.db", "agent_history*.db-wal", "agent_history*.db-shm", "control_plane.db")
    before = {path.resolve() for pattern in patterns for path in ROOT_DIR.glob(pattern)}
    yield
    after = {path.resolve() for pattern in patterns for path in ROOT_DIR.glob(pattern)}
    leaked = sorted(after - before)
    for path in leaked:
        path.unlink(missing_ok=True)
    leaked_names = ", ".join(str(path.name) for path in leaked)
    assert not leaked, f"Unexpected repo-root database artifacts created during tests: {leaked_names}"


@pytest.fixture(scope="session", autouse=True)
def _security_guard_service():
    """Make the Rust security guard service available to the test suite."""
    if os.environ.get("KODA_SKIP_SECURITY_GUARD_SERVICE", "").strip() == "1":
        yield
        return

    from koda import config
    from koda.internal_rpc.common import resolve_grpc_target

    target, _transport = resolve_grpc_target(config.SECURITY_GRPC_TARGET)
    channel = grpc.insecure_channel(target)
    startup_timeout = float(
        os.environ.get("KODA_SECURITY_GUARD_STARTUP_TIMEOUT", "90" if os.environ.get("CI") else "20")
    )
    try:
        grpc.channel_ready_future(channel).result(timeout=0.5)
        yield
        return
    except Exception:
        pass

    root = Path(__file__).resolve().parents[1]
    env = dict(os.environ)
    env["SECURITY_GRPC_TARGET"] = target
    with tempfile.NamedTemporaryFile(mode="w+", encoding="utf-8") as log_file:
        proc = subprocess.Popen(
            [
                "cargo",
                "run",
                "-p",
                "koda-security-service",
                "--manifest-path",
                str(root / "rust" / "Cargo.toml"),
            ],
            cwd=root,
            env=env,
            stdout=log_file,
            stderr=log_file,
            text=True,
        )
        try:
            grpc.channel_ready_future(channel).result(timeout=startup_timeout)
        except Exception:
            if proc.poll() is None:
                proc.terminate()
                try:
                    proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    proc.kill()
            log_file.flush()
            log_file.seek(0)
            log_excerpt = log_file.read().strip()
            tail = "\n".join(log_excerpt.splitlines()[-40:])
            pytest.fail(
                "Timed out while starting the Rust security guard service"
                f" after {startup_timeout:.0f}s.\n{tail or 'No service logs were captured.'}"
            )
        try:
            yield
        finally:
            if proc.poll() is None:
                proc.terminate()
                try:
                    proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    proc.kill()


@pytest.fixture
def mock_update():
    """Create a mock Telegram Update object."""
    update = MagicMock()
    update.effective_user = MagicMock()
    update.effective_user.id = 111
    update.effective_chat = MagicMock()
    update.effective_chat.id = 111
    update.message = AsyncMock()
    update.message.reply_text = AsyncMock()
    update.message.reply_photo = AsyncMock()
    update.message.reply_video = AsyncMock()
    update.message.reply_document = AsyncMock()
    update.message.reply_animation = AsyncMock()
    update.message.reply_audio = AsyncMock()
    update.message.reply_voice = AsyncMock()
    update.message.text = "test query"
    update.message.caption = None
    update.message.photo = None
    update.message.document = None
    update.message.message_id = 12345
    update.message.reply_to_message = None
    update.callback_query = None
    update.effective_message = update.message
    return update


@pytest.fixture
def mock_context():
    """Create a mock context with user_data."""
    context = MagicMock()
    context.user_data = {}
    context.args = []
    context.bot = AsyncMock()
    context.bot.send_message = AsyncMock()
    context.bot.send_photo = AsyncMock()
    context.bot.send_video = AsyncMock()
    context.bot.send_document = AsyncMock()
    context.bot.send_animation = AsyncMock()
    context.bot.send_audio = AsyncMock()
    context.bot.send_voice = AsyncMock()
    context.bot.send_chat_action = AsyncMock()
    return context


@pytest.fixture
def approved_context(mock_context):
    """Create a mock context suitable for approved write-handler tests."""
    return mock_context


@pytest.fixture(autouse=True)
def _auto_approve_execution():
    """Auto-set the execution_approved contextvar for all tests."""
    from koda.utils.approval import _execution_approved

    token = _execution_approved.set(True)
    yield
    _execution_approved.reset(token)


@pytest.fixture(autouse=True)
def _reset_approval_runtime_state():
    """Keep approval/pending-op globals isolated across tests."""
    from koda.utils.approval import _APPROVAL_GRANTS, _PENDING_AGENT_CMD_OPS, _PENDING_OPS

    _PENDING_OPS.clear()
    _PENDING_AGENT_CMD_OPS.clear()
    _APPROVAL_GRANTS.clear()
    yield
    _PENDING_OPS.clear()
    _PENDING_AGENT_CMD_OPS.clear()
    _APPROVAL_GRANTS.clear()


@pytest.fixture
def unauthorized_update():
    """Create a mock Update for an unauthorized user."""
    update = MagicMock()
    update.effective_user = MagicMock()
    update.effective_user.id = 999999
    update.message = AsyncMock()
    update.message.reply_text = AsyncMock()
    update.callback_query = None
    return update
