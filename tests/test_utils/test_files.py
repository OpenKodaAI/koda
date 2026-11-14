"""Tests for file operations with path traversal protection."""

import pytest

from koda.utils.files import list_directory, resolve_work_path, safe_delete, safe_read, safe_resolve, safe_write
from koda.utils.workdir import sensitive_dir_for


class TestSafeResolve:
    def test_relative_path_inside(self, tmp_path):
        (tmp_path / "file.txt").touch()
        result = safe_resolve("file.txt", str(tmp_path))
        assert result is not None
        assert result.name == "file.txt"

    def test_absolute_path_inside(self, tmp_path):
        target = tmp_path / "file.txt"
        target.touch()
        result = safe_resolve(str(target), str(tmp_path))
        assert result is not None

    def test_traversal_blocked(self, tmp_path):
        result = safe_resolve("../../etc/passwd", str(tmp_path))
        assert result is None

    def test_absolute_path_outside(self, tmp_path):
        result = safe_resolve("/etc/passwd", str(tmp_path))
        assert result is None

    def test_subdirectory(self, tmp_path):
        sub = tmp_path / "sub"
        sub.mkdir()
        (sub / "file.txt").touch()
        result = safe_resolve("sub/file.txt", str(tmp_path))
        assert result is not None
        assert result.name == "file.txt"


class TestListDirectory:
    def test_list_work_dir(self, tmp_path):
        (tmp_path / "a.txt").write_text("hello")
        (tmp_path / "b").mkdir()
        listing, success = list_directory(None, str(tmp_path))
        assert success
        assert "a.txt" in listing
        assert "b/" in listing

    def test_list_subdirectory(self, tmp_path):
        sub = tmp_path / "sub"
        sub.mkdir()
        (sub / "file.txt").touch()
        listing, success = list_directory("sub", str(tmp_path))
        assert success
        assert "file.txt" in listing

    def test_traversal_denied(self, tmp_path):
        listing, success = list_directory("../../etc", str(tmp_path))
        assert not success
        assert "Access denied" in listing

    def test_not_found(self, tmp_path):
        listing, success = list_directory("nonexistent", str(tmp_path))
        assert not success

    def test_empty_directory(self, tmp_path):
        sub = tmp_path / "empty"
        sub.mkdir()
        listing, success = list_directory("empty", str(tmp_path))
        assert success
        assert "empty" in listing.lower()


class TestResolveWorkPathMatrix:
    """One resolver decides for the /cat-style commands and the agent file tools."""

    @pytest.fixture
    def work_dir(self, tmp_path, monkeypatch):
        work = tmp_path / "work"
        (work / "sub").mkdir(parents=True)
        (work / "a.txt").write_text("a")
        (work / "sub" / "b.txt").write_text("b")
        (work / ".env").write_text("TOKEN=secret\n")
        outside = tmp_path / "outside"
        outside.mkdir()
        (outside / "secret.txt").write_text("outside")
        (work / "escape.txt").symlink_to(outside / "secret.txt")
        (work / "innocent.txt").symlink_to(work / ".env")
        # A different tree in the process CWD must never be what a relative path means.
        cwd = tmp_path / "cwd"
        cwd.mkdir()
        (cwd / "a.txt").write_text("wrong tree")
        monkeypatch.chdir(cwd)
        return work

    @pytest.mark.parametrize(
        ("path", "expected"),
        [
            ("a.txt", "a.txt"),
            ("sub/b.txt", "sub/b.txt"),
            ("./sub/../a.txt", "a.txt"),
            ("sub/", "sub"),
            (".", ""),
            ("new/file.txt", "new/file.txt"),
            ("README.md", "README.md"),
            ("environment.py", "environment.py"),
            ("src/env.ts", "src/env.ts"),
        ],
    )
    def test_allowed_paths_resolve_under_work_dir(self, work_dir, path, expected):
        resolution = resolve_work_path(path, str(work_dir))
        assert resolution.error is None
        assert resolution.reason is None
        assert resolution.path == (work_dir / expected).resolve()

    def test_absolute_path_inside_is_allowed(self, work_dir):
        resolution = resolve_work_path(str(work_dir / "sub" / "b.txt"), str(work_dir))
        assert resolution.path == (work_dir / "sub" / "b.txt").resolve()

    def test_home_relative_path_inside_work_dir_is_allowed(self, work_dir, monkeypatch):
        monkeypatch.setenv("HOME", str(work_dir))
        resolution = resolve_work_path("~/a.txt", str(work_dir))
        assert resolution.path == (work_dir / "a.txt").resolve()

    @pytest.mark.parametrize(
        ("path", "reason"),
        [
            ("", "path_missing"),
            ("   ", "path_missing"),
            ("../outside/secret.txt", "path_outside_workdir"),
            ("sub/../../outside", "path_outside_workdir"),
            ("/etc/passwd", "path_outside_workdir"),
            ("escape.txt", "path_outside_workdir"),
            ("bad\x00name", "path_invalid"),
            (".env", "path_blocked_file"),
            (".ENV", "path_blocked_file"),
            (".env.local", "path_blocked_file"),
            (".env.production", "path_blocked_file"),
            ("sub/.env", "path_blocked_file"),
            ("prod.env", "path_blocked_file"),
            ("certs/server.PEM", "path_blocked_file"),
            ("id.key", "path_blocked_file"),
            ("store.p12", "path_blocked_file"),
            ("app.keystore", "path_blocked_file"),
            ("innocent.txt", "path_blocked_file"),
        ],
    )
    def test_refused_paths(self, work_dir, path, reason):
        resolution = resolve_work_path(path, str(work_dir))
        assert resolution.path is None
        assert resolution.reason == reason
        assert resolution.error is not None
        assert resolution.error.startswith(("Access denied", "Missing"))

    def test_absolute_secret_file_is_refused(self, work_dir):
        resolution = resolve_work_path(str(work_dir / ".env"), str(work_dir))
        assert resolution.reason == "path_blocked_file"

    def test_symlink_named_like_a_secret_file_is_refused(self, work_dir):
        (work_dir / "copy.env").symlink_to(work_dir / "a.txt")
        resolution = resolve_work_path("copy.env", str(work_dir))
        assert resolution.reason == "path_blocked_file"

    def test_sensitive_directory_is_refused_even_inside_work_dir(self):
        resolution = resolve_work_path("/etc/hosts", "/")
        assert resolution.path is None
        assert resolution.reason == "path_sensitive_dir"

    def test_sensitive_directory_matches_by_path_component(self):
        assert sensitive_dir_for("/etc") == "/etc"
        assert sensitive_dir_for("/etc/ssh/sshd_config") == "/etc"
        assert sensitive_dir_for("/etcetera/notes.txt") is None
        assert sensitive_dir_for("/home/user/project") is None

    def test_safe_resolve_keeps_its_path_or_none_contract(self, work_dir):
        assert safe_resolve("a.txt", str(work_dir)) == (work_dir / "a.txt").resolve()
        assert safe_resolve(".env", str(work_dir)) is None
        assert safe_resolve("../outside/secret.txt", str(work_dir)) is None


class TestCommandHelpersApplyTheFilePolicy:
    def test_safe_read_refuses_secret_file(self, tmp_path):
        (tmp_path / ".env").write_text("TOKEN=secret\n")
        result = safe_read(".env", str(tmp_path))
        assert "secret" not in result
        assert "blocked" in result.lower()

    def test_safe_write_refuses_secret_file(self, tmp_path):
        result = safe_write(".env", "TOKEN=x", str(tmp_path))
        assert "blocked" in result.lower()
        assert not (tmp_path / ".env").exists()

    def test_safe_delete_refuses_secret_file(self, tmp_path):
        (tmp_path / "prod.env").write_text("TOKEN=secret\n")
        result = safe_delete("prod.env", str(tmp_path))
        assert "blocked" in result.lower()
        assert (tmp_path / "prod.env").exists()


class TestWorkDirInsideSensitiveDirectory:
    """The default Docker work dir (HOME) sits under /var/lib, which SENSITIVE_DIRS lists."""

    def test_only_the_sensitive_dir_check_differs_between_tools_and_commands(self, tmp_path, monkeypatch):
        sensitive = tmp_path / "var-lib"
        work = sensitive / "koda" / "home"
        work.mkdir(parents=True)
        (work / "notes.txt").write_text("visible")
        (work / ".env").write_text("TOKEN=canary-secret\n")
        monkeypatch.setattr("koda.utils.workdir.SENSITIVE_DIRS", frozenset({str(sensitive)}))

        # File tools (default) keep refusing paths under a sensitive directory.
        assert resolve_work_path("notes.txt", str(work)).reason == "path_sensitive_dir"
        # The file commands keep working there, as before.
        assert resolve_work_path("notes.txt", str(work), deny_sensitive_dirs=False).path == work / "notes.txt"
        assert safe_read("notes.txt", str(work)) == "visible"
        # Containment and the secret-file policy apply to both.
        assert resolve_work_path(".env", str(work), deny_sensitive_dirs=False).reason == "path_blocked_file"
        assert "canary-secret" not in safe_read(".env", str(work))
        assert resolve_work_path("../../x", str(work), deny_sensitive_dirs=False).reason == "path_outside_workdir"
