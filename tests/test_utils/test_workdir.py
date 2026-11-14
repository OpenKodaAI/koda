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
