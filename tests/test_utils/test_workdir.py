"""Koda's own runtime roots are valid work dirs, also where the Docker layout puts them under /var/lib.

The compose files set HOME=/var/lib/koda/runtime/home (the default DEFAULT_WORK_DIR),
RUNTIME_EPHEMERAL_ROOT=/var/lib/koda/runtime (and so RUNTIME_ROOT_DIR) and
STATE_ROOT_DIR=/var/lib/koda/state, all under the SENSITIVE_DIRS root /var/lib. The tests
read those values from the compose files and lay them out under a temporary host root.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import pytest
import yaml

import koda.utils.workdir as workdir
from koda.config import SENSITIVE_DIRS
from koda.utils.files import resolve_work_path
from koda.utils.workdir import sensitive_dir_for, validate_work_dir

ROOT = Path(__file__).resolve().parents[2]
COMPOSE_FILES = (
    ROOT / "docker-compose.yml",
    ROOT / "packages" / "cli" / "release" / "bundle" / "docker-compose.release.yml",
)


def _compose_value(value: Any) -> str:
    """Return a compose environment value, with ``${NAME:-default}`` read as its default."""
    text = str(value)
    match = re.fullmatch(r"\$\{[A-Za-z_][A-Za-z0-9_]*:-(?P<default>[^}]*)\}", text)
    return match.group("default") if match else text


def _app_environment(compose_file: Path) -> dict[str, str]:
    services = yaml.safe_load(compose_file.read_text(encoding="utf-8"))["services"]
    return {key: _compose_value(value) for key, value in services["app"]["environment"].items()}


def _set_layout(monkeypatch: pytest.MonkeyPatch, **values: Any) -> None:
    """Set the configuration that koda.utils.workdir reads, as the app container would have it."""
    for name, value in values.items():
        monkeypatch.setitem(vars(workdir), name, value)


class DockerLayout:
    def __init__(self, host: Path, environment: dict[str, str]) -> None:
        self.host = host
        self.environment = environment

    def place(self, path: str) -> Path:
        return self.host / path.lstrip("/")


@pytest.fixture(params=COMPOSE_FILES, ids=lambda path: path.name)
def docker_layout(request: pytest.FixtureRequest, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> DockerLayout:
    environment = _app_environment(request.param)
    # The compose files set neither, so DEFAULT_WORK_DIR is HOME and RUNTIME_ROOT_DIR is RUNTIME_EPHEMERAL_ROOT.
    assert "DEFAULT_WORK_DIR" not in environment
    assert "RUNTIME_ROOT_DIR" not in environment
    # Nor these, so the browser keeps its sessions in RUNTIME_EPHEMERAL_ROOT/image-scratch/browser_sessions.
    assert "IMAGE_TEMP_DIR" not in environment
    assert "BROWSER_SESSION_DIR" not in environment
    layout = DockerLayout(tmp_path.resolve() / "host", environment)
    home = layout.place(environment["HOME"])
    runtime = layout.place(environment["RUNTIME_EPHEMERAL_ROOT"])
    state = layout.place(environment["STATE_ROOT_DIR"])
    assert home.is_relative_to(runtime)
    for directory in (
        home / "project",
        runtime / "tasks" / "7",
        state / "control_plane",
        layout.place("/var/lib/postgresql"),
        layout.place("/etc"),
    ):
        directory.mkdir(parents=True, exist_ok=True)
    (home / "project" / "main.py").write_text("print('visible')\n", encoding="utf-8")
    (state / "control_plane" / "bootstrap.txt").write_text("canary-bootstrap\n", encoding="utf-8")
    _set_layout(
        monkeypatch,
        SENSITIVE_DIRS=frozenset(str(layout.place(sensitive)) for sensitive in SENSITIVE_DIRS),
        DEFAULT_WORK_DIR=str(home),
        RUNTIME_EPHEMERAL_ROOT=runtime,
        RUNTIME_ROOT_DIR=runtime,
        STATE_ROOT_DIR=state,
        IMAGE_TEMP_DIR=runtime / "image-scratch",
        BROWSER_SESSION_DIR="",
    )
    return layout


class TestDockerRuntimeRootsAreWorkDirs:
    def test_a_scheduled_run_in_the_default_work_dir_is_not_refused(self, docker_layout: DockerLayout) -> None:
        from koda.services.queue_manager import _validate_work_dir

        home = str(docker_layout.place(docker_layout.environment["HOME"]))
        assert _validate_work_dir(home, strict=True) == home

    @pytest.mark.parametrize(
        "work_dir",
        ["{HOME}", "{HOME}/project", "{RUNTIME_EPHEMERAL_ROOT}", "{RUNTIME_EPHEMERAL_ROOT}/tasks/7"],
    )
    def test_runtime_roots_and_the_directories_below_them_are_valid(
        self, docker_layout: DockerLayout, work_dir: str
    ) -> None:
        from koda.control_plane.workspace_import import validate_workspace_root

        path = docker_layout.place(work_dir.format(**docker_layout.environment))
        validation = validate_work_dir(str(path))
        assert validation.ok, validation.reason
        assert validation.path == str(path)
        assert validate_workspace_root(str(path)) == path

    def test_the_file_tools_work_in_a_work_dir_below_the_default_one(self, docker_layout: DockerLayout) -> None:
        project = docker_layout.place(docker_layout.environment["HOME"]) / "project"
        assert resolve_work_path("main.py", str(project)).path == project / "main.py"
        assert sensitive_dir_for(str(project / "main.py"), work_dir=str(project)) is None

    @pytest.mark.parametrize(
        "work_dir",
        [
            "{STATE_ROOT_DIR}/control_plane",
            "{STATE_ROOT_DIR}",
            "/var/lib/postgresql",
            "/var/lib",
            "/etc",
        ],
    )
    def test_the_control_plane_state_and_every_other_sensitive_root_stay_refused(
        self, docker_layout: DockerLayout, work_dir: str
    ) -> None:
        path = docker_layout.place(work_dir.format(**docker_layout.environment))
        validation = validate_work_dir(str(path))
        assert not validation.ok
        assert validation.blocked, validation.reason

    def test_a_link_from_a_runtime_root_into_another_sensitive_root_is_refused(
        self, docker_layout: DockerLayout
    ) -> None:
        home = docker_layout.place(docker_layout.environment["HOME"])
        (home / "db").symlink_to(docker_layout.place("/var/lib/postgresql"))
        (home / "state").symlink_to(docker_layout.place(docker_layout.environment["STATE_ROOT_DIR"]))
        for link in ("db", "state"):
            validation = validate_work_dir(str(home / link))
            assert validation.blocked, link
            assert resolve_work_path(f"{link}/x", str(home)).path is None, link

    def test_a_runtime_root_replaced_with_a_link_into_another_sensitive_root_gets_no_waiver(
        self, docker_layout: DockerLayout
    ) -> None:
        home = docker_layout.place(docker_layout.environment["HOME"])
        (home / "project" / "main.py").unlink()
        (home / "project").rmdir()
        home.rmdir()
        home.symlink_to(docker_layout.place("/etc"))
        assert validate_work_dir(str(home)).blocked
        assert resolve_work_path("passwd", str(home)).reason == "path_sensitive_dir"


_SURFACES = pytest.mark.parametrize(
    "options",
    [{}, {"deny_sensitive_dirs": False}, {"deny_sensitive_dirs": False, "deny_sensitive_work_dir": True}],
    ids=["the file tools", "the file commands", "browser_upload"],
)


class TestTheCredentialDirsBelowTheRuntimeRootStayRefused:
    """A work dir at RUNTIME_EPHEMERAL_ROOT is valid, but the credential dirs below it are not Koda's work area.

    The compose layout keeps there the browser's saved sessions of every chat scope
    (``image-scratch/browser_sessions/<scope>/<name>.json``, with cookies and localStorage)
    and, for a process whose environment sets the app container's ``CLAUDE_CONFIG_DIR``,
    Claude Code's config dir (``claude-config``: its login, session transcripts and
    ``.claude.json``). Like the control-plane state dir, they are never waived.
    """

    @pytest.fixture
    def runtime(self, docker_layout: DockerLayout, monkeypatch: pytest.MonkeyPatch) -> Path:
        runtime = docker_layout.place(docker_layout.environment["RUNTIME_EPHEMERAL_ROOT"])
        sessions = runtime / "image-scratch" / "browser_sessions" / "222"
        sessions.mkdir(parents=True)
        (sessions / "bank.json").write_text('{"cookies": [{"name": "sid", "value": "canary-cookie"}]}\n')
        (runtime / "image-scratch" / "111_42.txt").write_text("visible scratch\n")
        claude_config = docker_layout.place(docker_layout.environment["CLAUDE_CONFIG_DIR"])
        assert claude_config.parent == runtime
        (claude_config / "projects" / "p").mkdir(parents=True)
        (claude_config / "projects" / "p" / "s.jsonl").write_text('{"canary": "transcript"}\n')
        (claude_config / ".claude.json").write_text('{"canary": "settings"}\n')
        monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(claude_config))
        return runtime

    @pytest.mark.parametrize(
        ("work_dir", "valid"),
        [
            ("", True),
            ("image-scratch", True),
            ("image-scratch/browser_sessions", False),
            ("image-scratch/browser_sessions/222", False),
            ("claude-config", False),
            ("claude-config/projects/p", False),
        ],
    )
    def test_they_are_not_work_dirs(self, runtime: Path, work_dir: str, valid: bool) -> None:
        validation = validate_work_dir(str(runtime / work_dir))
        assert validation.ok is valid, validation.reason
        assert validation.blocked is not valid

    @_SURFACES
    @pytest.mark.parametrize(
        "path",
        [
            "image-scratch/browser_sessions/222/bank.json",
            "image-scratch/browser_sessions",
            "claude-config/projects/p/s.jsonl",
            "claude-config/.claude.json",
            "{runtime}/claude-config",
            "home/../claude-config/.claude.json",
        ],
    )
    def test_a_work_dir_at_the_runtime_root_does_not_reach_them(
        self, runtime: Path, options: dict[str, bool], path: str
    ) -> None:
        resolution = resolve_work_path(path.format(runtime=runtime), str(runtime), **options)
        assert resolution.path is None
        assert resolution.reason == "path_sensitive_dir"

    def test_the_browser_saves_its_sessions_in_the_dir_they_refuse(
        self, runtime: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from koda.services.browser_manager import browser_manager

        sessions = runtime / "image-scratch" / "browser_sessions"
        assert browser_manager._get_session_dir(222) == str(sessions / "222")
        assert workdir.protected_dir_for(str(sessions / "222" / "bank.json")) == str(sessions)

        _set_layout(monkeypatch, BROWSER_SESSION_DIR=str(tmp_path / "sessions"))
        assert browser_manager._get_session_dir(222) == str(tmp_path / "sessions" / "browser_sessions" / "222")
        assert validate_work_dir(str(tmp_path / "sessions" / "browser_sessions")).blocked

    @pytest.mark.parametrize(
        ("source", "destination", "protected"),
        [
            ("image-scratch", "scratch-old", "image-scratch/browser_sessions"),
            ("image-scratch", "home/project/image-scratch", "image-scratch/browser_sessions"),
            ("image-scratch/browser_sessions", "home/sessions", "image-scratch/browser_sessions"),
            ("claude-config", "home/claude-old", "claude-config"),
            ("home/project", "image-scratch/browser_sessions", "image-scratch/browser_sessions"),
            ("home/project", "claude-config/projects/q", "claude-config"),
            ("tasks", "claude-config", "claude-config"),
            ("home/project", "tasks/7/project", None),
            ("image-scratch/111_42.txt", "home/scratch.txt", None),
            ("home/project", "image-scratch/project", None),
        ],
    )
    def test_a_move_neither_takes_them_out_of_their_place_nor_puts_data_there(
        self, runtime: Path, source: str, destination: str, protected: str | None
    ) -> None:
        from koda.utils.files import protected_move_refusal

        refusal = protected_move_refusal(str(runtime / source), str(runtime / destination))
        if protected is None:
            assert refusal is None
        else:
            assert refusal is not None
            assert f"'{runtime / protected}' is a sensitive system directory" in refusal

    @_SURFACES
    @pytest.mark.parametrize("path", ["image-scratch/111_42.txt", "home/project/main.py", "tasks/7"])
    def test_the_rest_of_the_runtime_root_stays_reachable(
        self, runtime: Path, options: dict[str, bool], path: str
    ) -> None:
        assert resolve_work_path(path, str(runtime), **options).path == runtime / path

    @pytest.mark.asyncio
    async def test_the_agent_tools_neither_read_grep_nor_upload_them(self, runtime: Path) -> None:
        from unittest.mock import AsyncMock, patch

        from koda.services.browser_manager import browser_manager
        from koda.services.tool_dispatcher import (
            ToolContext,
            _handle_browser_upload,
            _handle_file_grep,
            _handle_file_list,
            _handle_file_read,
        )

        ctx = ToolContext(
            user_id=111,
            chat_id=111,
            work_dir=str(runtime),
            user_data={"work_dir": str(runtime)},
            agent=AsyncMock(),
            agent_mode="autonomous",
        )
        session = "image-scratch/browser_sessions/222/bank.json"
        with patch("koda.services.tool_dispatcher.FILEOPS_ENABLED", True):
            reads = [
                await _handle_file_read({"path": path}, ctx)
                for path in (session, "claude-config/projects/p/s.jsonl", "claude-config/.claude.json")
            ]
            listing = await _handle_file_list({"path": "image-scratch/browser_sessions"}, ctx)
            grep = await _handle_file_grep({"pattern": "canary|visible"}, ctx)
        with (
            patch("koda.services.tool_dispatcher._check_browser_available", new_callable=AsyncMock, return_value=None),
            patch.object(browser_manager, "upload_file", new_callable=AsyncMock, return_value="Uploaded") as upload,
        ):
            uploaded = await _handle_browser_upload({"file_path": session}, ctx)

        for result in (*reads, listing, uploaded):
            assert not result.success, result.output
            assert "sensitive system directory" in result.output
            assert "canary" not in result.output
        upload.assert_not_awaited()
        assert grep.success, grep.output
        assert "canary" not in grep.output
        assert "image-scratch/111_42.txt:1: visible scratch" in grep.output

    @pytest.mark.asyncio
    @pytest.mark.parametrize("search_path", [None, "image-scratch"])
    async def test_file_search_does_not_list_the_files_inside_them(
        self, runtime: Path, search_path: str | None
    ) -> None:
        """file_search walks the tree as file_grep does, so it skips the dirs that file_grep skips."""
        from unittest.mock import AsyncMock, patch

        from koda.services.tool_dispatcher import ToolContext, _handle_file_search

        (runtime / "tasks" / "7" / "result.json").write_text("{}\n")
        (runtime / "image-scratch" / "upload.json").write_text("{}\n")
        ctx = ToolContext(
            user_id=111,
            chat_id=111,
            work_dir=str(runtime),
            user_data={"work_dir": str(runtime)},
            agent=AsyncMock(),
            agent_mode="autonomous",
        )
        params = {"pattern": "*.json*"} if search_path is None else {"pattern": "*.json*", "path": search_path}
        with patch("koda.services.tool_dispatcher.FILEOPS_ENABLED", True):
            result = await _handle_file_search(params, ctx)

        assert result.success, result.output
        assert "bank.json" not in result.output
        assert "s.jsonl" not in result.output
        assert "upload.json" in result.output
        if search_path is None:
            assert "tasks/7/result.json" in result.output


class TestTheComposeClaudeConfigDirIsRefusedWithoutItsVariable:
    """The compose files set ``CLAUDE_CONFIG_DIR`` for the app container only, and the supervisor does not pass it on.

    A worker whose agent environment lacks it, with its work dir at
    ``RUNTIME_EPHEMERAL_ROOT``, reached the control plane's Claude Code config there: its
    ``.credentials.json``, ``.claude.json`` and ``.device-keys.json`` were refused by name,
    but not its background sessions' ``daemon/`` (OAuth snapshots in ``daemon/auth/``,
    socket tokens in ``daemon/roster.json``), its ``hfi-auth.json``, a legacy
    ``.config.json`` or its session transcripts, which the credential entries name only
    below ``.claude``. The dir the compose files configure is protected whatever the
    process's environment sets.
    """

    STORES = (
        "claude-config/daemon/auth/a1b2c3.tokens.json",
        "claude-config/daemon/roster.json",
        "claude-config/hfi-auth.json",
        "claude-config/.config.json",
        "claude-config/ide/48123.lock",
        "claude-config/projects/p/s.jsonl",
    )

    @pytest.fixture
    def runtime(self, docker_layout: DockerLayout, monkeypatch: pytest.MonkeyPatch) -> Path:
        runtime = docker_layout.place(docker_layout.environment["RUNTIME_EPHEMERAL_ROOT"])
        claude_config = docker_layout.place(docker_layout.environment["CLAUDE_CONFIG_DIR"])
        for store in self.STORES:
            (runtime / store).parent.mkdir(parents=True, exist_ok=True)
            (runtime / store).write_text('{"accessToken": "canary-token"}\n', encoding="utf-8")
        (runtime / "tasks" / "7" / "result.txt").write_text("visible\n", encoding="utf-8")
        _set_layout(monkeypatch, COMPOSE_PROVIDER_CLI_CONFIG_DIRS=(str(claude_config),))
        monkeypatch.delenv("CLAUDE_CONFIG_DIR", raising=False)
        monkeypatch.delenv("CODEX_HOME", raising=False)
        return runtime

    def test_the_protected_dir_is_the_one_the_compose_files_configure(self, docker_layout: DockerLayout) -> None:
        from koda.config import COMPOSE_PROVIDER_CLI_CONFIG_DIRS, PROVIDER_CLI_CONFIG_DIR_ENV_KEYS

        variables = set(PROVIDER_CLI_CONFIG_DIR_ENV_KEYS.values())
        configured = {value for key, value in docker_layout.environment.items() if key in variables}
        assert configured
        assert configured == set(COMPOSE_PROVIDER_CLI_CONFIG_DIRS)

    @_SURFACES
    @pytest.mark.parametrize("store", STORES)
    def test_a_work_dir_at_the_runtime_root_does_not_reach_it(
        self, runtime: Path, options: dict[str, bool], store: str
    ) -> None:
        resolution = resolve_work_path(store, str(runtime), **options)
        assert resolution.path is None
        assert resolution.reason in {"path_sensitive_dir", "path_blocked_file"}
        assert resolve_work_path("tasks/7/result.txt", str(runtime), **options).path == runtime / "tasks/7/result.txt"

    def test_it_is_not_a_work_dir_and_does_not_move(self, runtime: Path) -> None:
        from koda.utils.files import protected_move_refusal

        assert validate_work_dir(str(runtime)).ok
        assert validate_work_dir(str(runtime / "claude-config")).blocked
        assert protected_move_refusal(str(runtime / "claude-config"), str(runtime / "tasks" / "cfg")) is not None
        assert protected_move_refusal(str(runtime / "tasks"), str(runtime / "tasks-old")) is None

    @pytest.mark.asyncio
    async def test_the_agent_tools_neither_read_nor_grep_it(self, runtime: Path) -> None:
        from unittest.mock import AsyncMock, patch

        from koda.services.tool_dispatcher import ToolContext, _handle_file_grep, _handle_file_read

        ctx = ToolContext(
            user_id=111,
            chat_id=111,
            work_dir=str(runtime),
            user_data={"work_dir": str(runtime)},
            agent=AsyncMock(),
            agent_mode="autonomous",
        )
        with patch("koda.services.tool_dispatcher.FILEOPS_ENABLED", True):
            reads = [await _handle_file_read({"path": store}, ctx) for store in self.STORES]
            grep = await _handle_file_grep({"pattern": "canary|visible"}, ctx)

        for read in reads:
            assert not read.success, read.output
            assert "canary" not in read.output
        assert grep.success, grep.output
        assert "canary" not in grep.output
        assert "tasks/7/result.txt:1: visible" in grep.output

    def test_every_listing_of_the_protected_dirs_names_it(self) -> None:
        """The docs that list the protected dirs name the compose dir, which the code refuses in every process.

        A listing that names only the dirs ``CLAUDE_CONFIG_DIR`` and ``CODEX_HOME`` name in the
        environment tells its reader that a worker without ``CLAUDE_CONFIG_DIR`` can read,
        move or upload from ``claude-config``, which ``browser_upload`` and the file tools refuse.
        """
        from koda.config import COMPOSE_PROVIDER_CLI_CONFIG_DIRS
        from koda.utils import files

        matrix = (ROOT / "docs" / "security" / "guardrail-test-matrix.md").read_text(encoding="utf-8")
        rows = {line.split(" | ", 1)[0]: line for line in matrix.splitlines() if line.startswith("| ")}
        listings = {
            "guardrail matrix, File operations row": rows["| File operations"],
            "guardrail matrix, Browser row": rows["| Browser"],
            "resolve_work_path": files.resolve_work_path.__doc__ or "",
            "protected_move_refusal": files.protected_move_refusal.__doc__ or "",
        }
        flat = {name: " ".join(text.split()) for name, text in listings.items()}
        assert [name for name, text in flat.items() if "CLAUDE_CONFIG_DIR" not in text] == []
        missing = [
            (name, directory)
            for name, text in flat.items()
            for directory in COMPOSE_PROVIDER_CLI_CONFIG_DIRS
            if directory not in text
        ]
        assert missing == []


class TestControlPlaneStateIsRefusedInsideAWorkDir:
    """Outside Docker the state root (~/.koda-state) sits inside the default work dir (~)."""

    @pytest.fixture
    def home(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
        home = tmp_path.resolve() / "home"
        control_plane = home / ".koda-state" / "control_plane"
        control_plane.mkdir(parents=True)
        (control_plane / "bootstrap.txt").write_text("canary-bootstrap\n", encoding="utf-8")
        (home / "notes.txt").write_text("visible\n", encoding="utf-8")
        _set_layout(
            monkeypatch,
            SENSITIVE_DIRS=frozenset({str(tmp_path.resolve() / "etc")}),
            DEFAULT_WORK_DIR=str(home),
            RUNTIME_EPHEMERAL_ROOT=tmp_path.resolve() / "koda-runtime",
            RUNTIME_ROOT_DIR=tmp_path.resolve() / "koda-runtime",
            STATE_ROOT_DIR=home / ".koda-state",
        )
        return home

    def test_it_is_not_a_work_dir(self, home: Path) -> None:
        assert validate_work_dir(str(home)).ok
        assert validate_work_dir(str(home / ".koda-state" / "control_plane")).blocked

    def test_the_file_tools_refuse_its_files(self, home: Path) -> None:
        assert resolve_work_path("notes.txt", str(home)).path == home / "notes.txt"
        resolution = resolve_work_path(".koda-state/control_plane/bootstrap.txt", str(home))
        assert resolution.path is None
        assert resolution.reason == "path_sensitive_dir"

    @pytest.mark.parametrize(
        "options",
        [
            {"deny_sensitive_dirs": False},
            {"deny_sensitive_dirs": False, "deny_sensitive_work_dir": True},
        ],
        ids=["the file commands", "browser_upload"],
    )
    @pytest.mark.parametrize(
        "path",
        [
            ".koda-state/control_plane/bootstrap.txt",
            ".koda-state/control_plane",
            "{home}/.koda-state/control_plane/bootstrap.txt",
            "link-to-control-plane/bootstrap.txt",
        ],
    )
    def test_the_file_commands_and_browser_upload_refuse_its_files_too(
        self, home: Path, options: dict[str, bool], path: str
    ) -> None:
        """It is never waived: the callers that skip the SENSITIVE_DIRS check still refuse it."""
        (home / "link-to-control-plane").symlink_to(home / ".koda-state" / "control_plane")
        resolution = resolve_work_path(path.format(home=home), str(home), **options)
        assert resolution.path is None
        assert resolution.reason == "path_sensitive_dir"
        assert resolve_work_path("notes.txt", str(home), **options).path == home / "notes.txt"
        assert resolve_work_path(".koda-state", str(home), **options).path == home / ".koda-state"

    @_SURFACES
    @pytest.mark.parametrize("variant", [".KODA-STATE", ".Koda-State"])
    def test_a_case_variant_of_its_path_is_refused_too(
        self, home: Path, options: dict[str, bool], variant: str
    ) -> None:
        """On a case-insensitive filesystem (the macOS default), a case variant opens the state dir.

        ``os.path.realpath`` keeps the case it is given, so the protected directories are
        compared ignoring case, as the credential stores are. This test filesystem is case
        sensitive, so a separate tree stands for what a case-insensitive one would open.
        """
        from koda.utils.files import protected_move_refusal

        state = str(home / ".koda-state" / "control_plane")
        control_plane = home / variant / "Control_Plane"
        control_plane.mkdir(parents=True)
        (control_plane / "bootstrap.txt").write_text("canary-bootstrap\n", encoding="utf-8")

        assert workdir.protected_dir_for(str(control_plane / "bootstrap.txt")) == state
        assert workdir.protected_dir_within(str(home / variant)) == state
        assert sensitive_dir_for(str(control_plane), work_dir=str(home)) == state
        assert validate_work_dir(str(control_plane)).blocked
        resolution = resolve_work_path(f"{variant}/Control_Plane/bootstrap.txt", str(home), **options)
        assert resolution.path is None
        assert resolution.reason == "path_sensitive_dir"
        assert protected_move_refusal(str(home / variant), str(home / "state-old")) is not None
        assert protected_move_refusal(str(home / "notes.txt"), str(control_plane / "bootstrap.txt")) is not None
        assert resolve_work_path(variant, str(home), **options).path == home / variant
        assert protected_move_refusal(str(home / "notes.txt"), str(home / variant / "notes.txt")) is None
