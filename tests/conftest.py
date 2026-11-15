"""Shared test fixtures."""

import atexit
import os
import shutil
import sys
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from tests import _security_guard

# Pull in real-Postgres fixtures so any test marked
# ``@pytest.mark.postgres`` resolves the ``postgres_url`` /
# ``db_connection`` fixtures. The module also auto-skips marked
# tests when POSTGRES_TEST_DSN is not set, so a contributor without
# Postgres still gets a clean pytest run.
pytest_plugins = ["tests.postgres_fixtures"]

ROOT_DIR = Path(__file__).resolve().parents[1]

# Set env vars before importing config. Use explicit assignments so CI job-level
# environment does not change the suite's expected auth/admin fixtures.
os.environ["AGENT_TOKEN"] = "test-token-123"
os.environ["ALLOWED_USER_IDS"] = "111,222,333"
os.environ["KNOWLEDGE_ADMIN_USER_IDS"] = "111,222,333"
os.environ.setdefault("DEFAULT_WORK_DIR", tempfile.gettempdir())
# Force a neutral AGENT_ID so host shells or local .env files cannot leak
# agent-specific residue into the test suite.
os.environ["AGENT_ID"] = "AGENT_A"
os.environ["STATE_BACKEND"] = "postgres"
# Each session gets its own security guard address (see tests/_security_guard.py);
# chosen before koda.config reads SECURITY_GRPC_TARGET.
_GUARD = None if _security_guard.guard_disabled() else _security_guard.select_guard_target()


_REAL_HOME = os.path.expanduser("~")
# Koda keeps its state in STATE_ROOT_DIR, ~/.koda-state by default, and modules read it at
# import, before any per-test fixture runs. Point it at this session's own directory here so
# no test writes into the real one or shares it with a run in another checkout (D-265);
# session_state_root owns the directory and checks the run left the real one alone.
_REAL_STATE_ROOT = Path(_REAL_HOME) / ".koda-state"
_SESSION_STATE_ROOT = Path(tempfile.mkdtemp(prefix="koda-test-state-"))
atexit.register(shutil.rmtree, _SESSION_STATE_ROOT, True)
os.environ["STATE_ROOT_DIR"] = str(_SESSION_STATE_ROOT)
os.environ.pop(f"{os.environ['AGENT_ID']}_STATE_ROOT_DIR", None)


def _koda_paths_under(root: Path) -> list[str]:
    """Return the module-level path settings (UPPER_CASE names) of loaded koda modules inside ``root``.

    This does not watch the filesystem. It inspects only UPPER_CASE module attributes as they stand
    when called, so it cannot see lowercase or instance-held paths (a store object holding a path,
    ``_state_dir = Path.home() / ".koda-state"``), paths patched only for the length of one test,
    or writes made by subprocesses. A check of the real directory itself would race with other
    checkouts that still write there.
    """
    found = []
    for name, module in list(sys.modules.items()):
        if module is None or not (name == "koda" or name.startswith("koda.")):
            continue
        for attr, value in list(vars(module).items()):
            if not attr.lstrip("_").isupper() or not isinstance(value, Path | str) or not os.path.isabs(value):
                continue
            if Path(value).is_relative_to(root):
                found.append(f"{name}.{attr} = {value}")
    return found


@pytest.fixture(scope="session", autouse=True)
def session_state_root():
    """This session's STATE_ROOT_DIR; fails the run if a loaded module points into the real one.

    The end-of-session check has the blind spots listed on :func:`_koda_paths_under`.
    """
    yield _SESSION_STATE_ROOT
    leaked = _koda_paths_under(_REAL_STATE_ROOT)
    assert not leaked, f"Koda paths under the real state dir {_REAL_STATE_ROOT}: {leaked}"


@pytest.fixture(autouse=True)
def _isolate_home(tmp_path_factory: pytest.TempPathFactory, monkeypatch: pytest.MonkeyPatch):
    """Give every test its own empty HOME, so no test reads or deletes the files of whoever runs it.

    Provider disconnects remove CLI login files under ``$HOME/.claude``, ``.codex`` and
    ``.gemini`` (and under ``CLAUDE_CONFIG_DIR`` / ``CODEX_HOME``). Before this fixture a full run
    deleted the real ones. The Rust toolchain keeps its real location so a test that spawns
    ``cargo`` still finds it; session fixtures (the guard, release builds) run before this.
    """
    for key, default in (("CARGO_HOME", ".cargo"), ("RUSTUP_HOME", ".rustup")):
        if key not in os.environ:
            monkeypatch.setenv(key, os.path.join(_REAL_HOME, default))
    monkeypatch.setenv("HOME", str(tmp_path_factory.mktemp("home")))
    for key in ("CLAUDE_CONFIG_DIR", "CODEX_HOME"):
        monkeypatch.delenv(key, raising=False)


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


@pytest.fixture(autouse=True)
def _stub_provider_cli_contract_probe(request):
    """Treat the installed provider CLIs as the pinned contract versions.

    The real probe runs ``<cli> --version`` and ``--help``, so without this stub a test's
    outcome would depend on which CLIs the machine has installed. Tests marked
    ``real_cli_contract_probe`` exercise the real probe against fake CLI output instead.
    """
    if request.node.get_closest_marker("real_cli_contract_probe"):
        yield
        return
    from koda.services import provider_cli_contract

    async def _verified(provider, command, *, env=None):
        contract = provider_cli_contract.get_contract(provider)
        return provider_cli_contract.CliContractCheck(
            provider=contract.provider,
            contract_id=contract.contract_id,
            ok=True,
            observed_version=contract.pinned_version,
            version_matches=True,
        )

    with patch.object(provider_cli_contract, "verify_provider_cli", _verified):
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


_GUARD_SKIP_REASON: str | None = None


@pytest.fixture(scope="session", autouse=True)
def _security_guard_service():
    """Start this session's Rust security guard, or attach to the explicitly shared one."""
    global _GUARD_SKIP_REASON
    if _GUARD is None:
        yield
        return

    from koda import config

    if _GUARD.target != config.SECURITY_GRPC_TARGET:
        pytest.fail(
            "koda.config was imported before tests/conftest.py pinned SECURITY_GRPC_TARGET"
            f" ({config.SECURITY_GRPC_TARGET!r} != {_GUARD.target!r});"
            " a plugin or sitecustomize imports koda too early."
        )
    timeout = _security_guard.startup_timeout()
    if _GUARD.shared:
        try:
            _security_guard.wait_until_ready(_GUARD.target, timeout)
        except _security_guard.GuardUnavailable as exc:
            pytest.fail(f"{_security_guard.SHARED_TARGET_ENV}={_GUARD.target} is not reachable: {exc}")
        yield
        return

    try:
        with _security_guard.run_own_guard(ROOT_DIR, _GUARD.target, timeout):
            yield
    except _security_guard.CargoMissing:
        message = (
            "cargo is required to start the Rust security guard for the test suite;"
            f" install the Rust toolchain or set {_security_guard.SHARED_TARGET_ENV} to a running guard."
        )
        if os.environ.get("CI"):
            pytest.fail(message)
        _GUARD_SKIP_REASON = message
        pytest.skip(message)
    except _security_guard.GuardUnavailable as exc:
        pytest.fail(f"Could not start the Rust security guard service:\n{exc}")


def pytest_terminal_summary(terminalreporter):
    """Make a guard-less session impossible to mistake for a green run."""
    if _GUARD_SKIP_REASON:
        terminalreporter.write_sep("!", "ALL TESTS SKIPPED", red=True, bold=True)
        terminalreporter.write_line(_GUARD_SKIP_REASON)


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


@pytest.fixture
def execution_approved():
    """Run the test inside an approved execution context, as ``with_approval`` and scheduled jobs do.

    Opt-in only: the queue worker never sets this contextvar (D-011), so setting it for every
    test hid that bug. Use it only for tests that model an approved context.
    """
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


@pytest.fixture(autouse=True)
def _approval_store_without_postgres(request, monkeypatch):
    """Outside Postgres tests, let every approval-store write succeed and every read find nothing.

    Postgres is the only approval store (M2-E1-T2), and it raises without a database. Tests
    marked ``postgres`` use the real database; tests marked ``real_approval_store`` check the
    store's behaviour without one.
    """
    if request.node.get_closest_marker("postgres") or request.node.get_closest_marker("real_approval_store"):
        yield
        return
    from koda.state import approval_grants, pending_approvals

    for module in (approval_grants, pending_approvals):
        monkeypatch.setattr(module, "_execute", lambda _action, _query, _params: 1)
        monkeypatch.setattr(module, "_fetch_all", lambda _action, _query, _params: [])
    yield


@pytest.fixture(autouse=True)
def _reset_internal_rpc_breakers():
    """Keep process-local sidecar breaker state from leaking between tests."""
    from koda.internal_rpc.circuit_breaker import reset_registry_for_tests

    reset_registry_for_tests()
    yield
    reset_registry_for_tests()


@pytest.fixture
def unauthorized_update():
    """Create a mock Update for an unauthorized user."""
    update = MagicMock()
    update.effective_user = MagicMock()
    update.effective_user.id = 999999
    update.effective_chat = None
    update.effective_message = None
    update.message = AsyncMock()
    update.message.reply_text = AsyncMock()
    update.callback_query = None
    return update
