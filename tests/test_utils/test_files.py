"""Tests for file operations with path traversal protection."""

from unittest.mock import patch

import pytest

import koda.utils.files as files_module
from koda.utils.files import list_directory, resolve_work_path, safe_delete, safe_read, safe_write
from koda.utils.workdir import sensitive_dir_for, validate_work_dir


class TestResolveWorkPathContainment:
    def test_relative_path_inside(self, tmp_path):
        (tmp_path / "file.txt").touch()
        result = resolve_work_path("file.txt", str(tmp_path)).path
        assert result is not None
        assert result.name == "file.txt"

    def test_absolute_path_inside(self, tmp_path):
        target = tmp_path / "file.txt"
        target.touch()
        result = resolve_work_path(str(target), str(tmp_path)).path
        assert result is not None

    def test_traversal_blocked(self, tmp_path):
        result = resolve_work_path("../../etc/passwd", str(tmp_path)).path
        assert result is None

    def test_absolute_path_outside(self, tmp_path):
        result = resolve_work_path("/etc/passwd", str(tmp_path)).path
        assert result is None

    def test_subdirectory(self, tmp_path):
        sub = tmp_path / "sub"
        sub.mkdir()
        (sub / "file.txt").touch()
        result = resolve_work_path("sub/file.txt", str(tmp_path)).path
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
            # Committed, secret-free templates of secret files stay readable and editable.
            (".env.example", ".env.example"),
            (".ENV.EXAMPLE", ".ENV.EXAMPLE"),
            (".env.sample", ".env.sample"),
            (".env.template", ".env.template"),
            (".env.dist", ".env.dist"),
            (".env.local.example", ".env.local.example"),
            ("sub/.env.example", "sub/.env.example"),
            ("prod.env.example", "prod.env.example"),
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
            (".env.example.local", "path_blocked_file"),
            (".env.examples", "path_blocked_file"),
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

    def test_template_name_does_not_unlock_the_secret_it_links_to(self, work_dir):
        (work_dir / ".env.example").symlink_to(work_dir / ".env")
        resolution = resolve_work_path(".env.example", str(work_dir))
        assert resolution.path is None
        assert resolution.reason == "path_blocked_file"

    def test_sensitive_directory_is_refused_even_inside_work_dir(self):
        resolution = resolve_work_path("/etc/hosts", "/")
        assert resolution.path is None
        assert resolution.reason == "path_sensitive_dir"

    def test_sensitive_directory_matches_by_path_component(self):
        assert sensitive_dir_for("/etc") == "/etc"
        assert sensitive_dir_for("/etc/ssh/sshd_config") == "/etc"
        assert sensitive_dir_for("/etcetera/notes.txt") is None
        assert sensitive_dir_for("/srv/project") is None

    def test_sensitive_roots_are_resolved_on_each_check(self, tmp_path, monkeypatch):
        """A deny root that becomes a symlink later is matched in its new resolved form."""
        real = tmp_path / "real-run"
        (real / "app").mkdir(parents=True)
        alias = tmp_path / "var-run"
        monkeypatch.setattr("koda.utils.workdir.SENSITIVE_DIRS", frozenset({str(alias)}))
        assert sensitive_dir_for(str(real / "app")) is None
        alias.symlink_to(real)
        assert sensitive_dir_for(str(real / "app")) == str(alias)

    def test_a_check_under_a_patched_realpath_does_not_leak_into_later_checks(self, tmp_path, monkeypatch):
        monkeypatch.setattr("koda.utils.workdir.SENSITIVE_DIRS", frozenset({"/etc", str(tmp_path / "unused")}))
        with patch("os.path.realpath", return_value="/workspace/projects"):
            sensitive_dir_for("/srv/project")
        assert sensitive_dir_for("/workspace/projects") is None
        assert sensitive_dir_for("/etc/ssh") == "/etc"

    def test_patched_sensitive_dirs_still_take_effect(self, tmp_path, monkeypatch):
        real = tmp_path / "real-run"
        real.mkdir()
        alias = tmp_path / "var-run"
        alias.symlink_to(real)
        monkeypatch.setattr("koda.utils.workdir.SENSITIVE_DIRS", frozenset({str(alias)}))
        assert sensitive_dir_for(str(real / "app")) == str(alias)
        assert sensitive_dir_for("/etc/ssh") is None

    def test_refused_path_carries_no_path(self, work_dir):
        assert resolve_work_path("a.txt", str(work_dir)).path == (work_dir / "a.txt").resolve()
        assert resolve_work_path(".env", str(work_dir)).path is None
        assert resolve_work_path("../outside/secret.txt", str(work_dir)).path is None

    def test_resolve_work_path_is_the_only_path_resolver(self):
        """The old per-surface resolvers are gone, so a new command or tool cannot pick the wrong one."""
        import koda.services.tool_dispatcher as tool_dispatcher

        assert not hasattr(files_module, "safe_resolve")
        assert not hasattr(tool_dispatcher, "_validate_file_path")


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

    def test_safe_read_and_write_allow_env_template(self, tmp_path):
        (tmp_path / ".env.example").write_text("TOKEN=\n")
        assert safe_read(".env.example", str(tmp_path)) == "TOKEN=\n"
        assert "Written to" in safe_write(".env.example", "TOKEN=\nNEW_SETTING=\n", str(tmp_path))
        assert (tmp_path / ".env.example").read_text() == "TOKEN=\nNEW_SETTING=\n"

    def test_safe_delete_refuses_secret_file(self, tmp_path):
        (tmp_path / "prod.env").write_text("TOKEN=secret\n")
        result = safe_delete("prod.env", str(tmp_path))
        assert "blocked" in result.lower()
        assert (tmp_path / "prod.env").exists()


class TestWorkDirInsideSensitiveDirectory:
    """The default Docker work dir (HOME=/var/lib/koda/runtime/home) sits under /var/lib, a SENSITIVE_DIRS root.

    It is the operator's DEFAULT_WORK_DIR, one of Koda's runtime roots, which may sit under a
    sensitive root (koda/utils/workdir.py::runtime_roots). It and the paths inside it are
    allowed on both surfaces; a sensitive root that does not contain it as configured stays
    denied, and the secret-file policy applies everywhere.
    """

    @pytest.fixture
    def docker_layout(self, tmp_path, monkeypatch):
        root = tmp_path.resolve()
        sensitive = root / "var-lib"
        other = root / "etc"
        work = sensitive / "koda" / "runtime" / "home"
        (work / "src").mkdir(parents=True)
        other.mkdir()
        (work / "notes.txt").write_text("visible")
        (work / "src" / "main.py").write_text("granted")
        (work / ".env").write_text("TOKEN=canary-secret\n")
        (other / "passwd").write_text("canary-passwd")
        monkeypatch.setattr("koda.utils.workdir.SENSITIVE_DIRS", frozenset({str(sensitive), str(other)}))
        monkeypatch.setattr("koda.utils.workdir.DEFAULT_WORK_DIR", str(work))
        return work, other

    def test_file_tools_allow_the_work_dir_and_paths_inside_it(self, docker_layout):
        work, _ = docker_layout
        assert resolve_work_path("notes.txt", str(work)).path == work / "notes.txt"
        assert resolve_work_path(str(work / "src" / "main.py"), str(work)).path == work / "src" / "main.py"
        assert resolve_work_path(".", str(work)).path == work
        assert resolve_work_path(str(work), str(work)).path == work

    def test_both_surfaces_give_the_same_decision(self, docker_layout):
        work, other = docker_layout
        for path in ("notes.txt", "src/main.py", ".env", "../../x", str(other / "passwd")):
            tools = resolve_work_path(path, str(work))
            commands = resolve_work_path(path, str(work), deny_sensitive_dirs=False)
            assert (tools.path, tools.reason) == (commands.path, commands.reason), path
        assert safe_read("notes.txt", str(work)) == "visible"

    def test_secret_names_and_containment_still_apply(self, docker_layout):
        work, other = docker_layout
        assert resolve_work_path(".env", str(work)).reason == "path_blocked_file"
        assert "canary-secret" not in safe_read(".env", str(work))
        assert resolve_work_path("../../x", str(work)).reason == "path_outside_workdir"
        assert resolve_work_path(str(other / "passwd"), str(work)).path is None

    def test_a_sensitive_root_inside_the_work_dir_stays_denied(self, tmp_path, monkeypatch):
        sensitive = tmp_path.resolve() / "var-lib"
        work = sensitive / "koda" / "home"
        inner = work / "etc"
        inner.mkdir(parents=True)
        (inner / "hosts").write_text("canary-hosts")
        monkeypatch.setattr("koda.utils.workdir.SENSITIVE_DIRS", frozenset({str(sensitive), str(inner)}))
        monkeypatch.setattr("koda.utils.workdir.DEFAULT_WORK_DIR", str(work))
        resolution = resolve_work_path("etc/hosts", str(work))
        assert resolution.path is None
        assert resolution.reason == "path_sensitive_dir"
        assert sensitive_dir_for(str(inner / "hosts"), work_dir=str(work)) == str(inner)
        # The one documented difference: the file commands skip the check and read it.
        assert resolve_work_path("etc/hosts", str(work), deny_sensitive_dirs=False).path == inner / "hosts"
        assert safe_read("etc/hosts", str(work)) == "canary-hosts"

    def test_the_waiver_follows_the_resolved_form_of_the_sensitive_root(self, tmp_path, monkeypatch):
        """``/var/run`` is ``/run``: a work dir under the resolved form is under the written one."""
        real = tmp_path.resolve() / "run"
        work = real / "koda"
        work.mkdir(parents=True)
        alias = tmp_path.resolve() / "var-run"
        alias.symlink_to(real)
        monkeypatch.setattr("koda.utils.workdir.SENSITIVE_DIRS", frozenset({str(alias)}))
        monkeypatch.setattr("koda.utils.workdir.DEFAULT_WORK_DIR", str(work))
        assert sensitive_dir_for(str(work / "x.txt")) == str(alias)
        assert sensitive_dir_for(str(work / "x.txt"), work_dir=str(work)) is None
        assert resolve_work_path("x.txt", str(work)).path == work / "x.txt"
        assert resolve_work_path("x.txt", str(alias / "koda")).path == work / "x.txt"

    def test_a_work_dir_outside_the_runtime_roots_gets_no_waiver(self, docker_layout, monkeypatch):
        """Only Koda's runtime roots and the dirs below them are waived; any other work dir is validated."""
        work, _ = docker_layout
        monkeypatch.setattr("koda.utils.workdir.DEFAULT_WORK_DIR", str(work.parent / "other"))
        resolution = resolve_work_path("notes.txt", str(work))
        assert resolution.path is None
        assert resolution.reason == "path_sensitive_dir"
        assert sensitive_dir_for(str(work / "notes.txt"), work_dir=str(work)) is not None

    def test_a_validated_work_dir_swapped_for_a_symlink_into_a_sensitive_root_is_not_waived(
        self, tmp_path, monkeypatch
    ):
        root = tmp_path.resolve()
        etc = root / "etc"
        etc.mkdir()
        (etc / "shadow").write_text("canary-shadow")
        (root / "home").mkdir()
        monkeypatch.setattr("koda.utils.workdir.SENSITIVE_DIRS", frozenset({str(etc)}))
        monkeypatch.setattr("koda.utils.workdir.DEFAULT_WORK_DIR", str(root / "home"))
        (root / "proj").mkdir()
        validation = validate_work_dir(str(root / "proj"))
        assert validation.ok
        (root / "proj").rmdir()
        (root / "proj").symlink_to(etc)
        for path in ("shadow", str(etc / "shadow"), "."):
            resolution = resolve_work_path(path, validation.path)
            assert resolution.reason == "path_sensitive_dir", path
        assert sensitive_dir_for(str(etc / "shadow"), work_dir=validation.path) == str(etc)

    def test_the_waiver_stays_with_the_configured_location_of_the_default_work_dir(self, docker_layout):
        """DEFAULT_WORK_DIR replaced with a symlink into another sensitive root: that root stays denied."""
        work, other = docker_layout
        (work / "notes.txt").unlink()
        (work / ".env").unlink()
        (work / "src" / "main.py").unlink()
        (work / "src").rmdir()
        work.rmdir()
        work.symlink_to(other)
        for path in ("passwd", str(other / "passwd")):
            resolution = resolve_work_path(path, str(work))
            assert resolution.path is None, path
            assert resolution.reason == "path_sensitive_dir", path


class TestCredentialStoresAreSecretFiles:
    """The CLI credential stores in a HOME (the Docker work dir) are secret files, whatever their extension."""

    @pytest.mark.parametrize(
        ("path", "entry"),
        [
            ("/srv/koda-user/.ssh/id_ed25519", ".ssh/"),
            ("/srv/koda-user/.ssh", ".ssh/"),
            ("/srv/koda-user/.SSH/id_rsa", ".ssh/"),
            ("/srv/koda-user/.gnupg/private-keys-v1.d/a.key", ".gnupg/"),
            ("/srv/app/.aws/credentials", ".aws/"),
            ("/srv/koda-user/.azure/msal_token_cache.json", ".azure/"),
            ("/srv/koda-user/.config/gcloud/credentials.db", ".config/gcloud/"),
            ("/srv/koda-user/.codex/auth.json", ".codex/auth.json"),
            ("/srv/koda-user/.gemini/oauth_creds.json", ".gemini/oauth_creds.json"),
            ("/srv/koda-user/.claude/.credentials.json", ".claude/.credentials.json"),
            ("/srv/koda-user/.config/gh/hosts.yml", ".config/gh/hosts.yml"),
            ("/srv/koda-user/.docker/config.json", ".docker/config.json"),
            ("/srv/koda-user/.kube/config", ".kube/config"),
            ("/srv/koda-user/.git-credentials", ".git-credentials"),
            ("/srv/koda-user/.netrc", ".netrc"),
            ("/srv/koda-user/_netrc", "_netrc"),
            ("/srv/koda-user/.pgpass", ".pgpass"),
            ("/srv/koda-user/project/.npmrc", ".npmrc"),
            ("/srv/koda-user/.pypirc", ".pypirc"),
        ],
    )
    def test_credential_stores_are_matched(self, path, entry):
        from koda.utils.files import blocked_credential_path

        assert blocked_credential_path(path) == entry

    @pytest.mark.parametrize(
        "path",
        [
            "/srv/koda-user/.docker/Dockerfile",
            "/srv/koda-user/.codex/config.toml",
            "/srv/koda-user/.config/gh/config.yml",
            "/srv/koda-user/.config/gcloud-tools/notes.md",
            "/srv/koda-user/project/docs/ssh.md",
            "/srv/koda-user/.sshconfig",
            "/srv/koda-user/.npmrc.example",
            "/srv/koda-user/netrc",
            "/srv/koda-user/src/kube/config",
        ],
    )
    def test_other_paths_are_not(self, path):
        from koda.utils.files import blocked_credential_path

        assert blocked_credential_path(path) is None

    @pytest.mark.parametrize("deny_sensitive_dirs", [True, False])
    def test_both_surfaces_refuse_them(self, tmp_path, deny_sensitive_dirs):
        work = tmp_path.resolve()
        (work / ".ssh").mkdir()
        (work / ".ssh" / "id_ed25519").write_text("canary-key")
        (work / ".netrc").write_text("canary-netrc")
        (work / "key.txt").symlink_to(work / ".ssh" / "id_ed25519")
        (work / "notes.txt").write_text("visible")
        for path in (".ssh/id_ed25519", ".ssh", str(work / ".netrc"), "key.txt", "src/../.netrc"):
            resolution = resolve_work_path(path, str(work), deny_sensitive_dirs=deny_sensitive_dirs)
            assert resolution.path is None, path
            assert resolution.reason == "path_blocked_file", path
            assert "credential" in (resolution.error or ""), path
        assert resolve_work_path("notes.txt", str(work), deny_sensitive_dirs=deny_sensitive_dirs).path is not None
        assert "canary" not in safe_read(".ssh/id_ed25519", str(work))
        assert "canary" not in safe_read(".netrc", str(work))


class TestFileCommandPath:
    """The one parse of a file command's path, shared by its handler and the approval gate."""

    @pytest.mark.parametrize(
        ("command", "args", "expected"),
        [
            ("write", ["notes.txt", "hello", "world"], "notes.txt"),
            ("edit", ['"src/a', 'b.txt"', "line"], '"src/a'),
            ("write", [], ""),
            ("cat", ["src/x", "/../../.git/config"], "src/x /../../.git/config"),
            ("rm", ["it's.txt"], "it's.txt"),
            ("mkdir", ["build", "out"], "build out"),
            ("file", ["report", "final.pdf"], "report final.pdf"),
            ("cat", [], ""),
            ("ls", [], "."),
            ("ls", ["src"], "src"),
        ],
    )
    def test_path_is_parsed_without_shell_splitting(self, command, args, expected):
        from koda.utils.files import file_command_path

        assert file_command_path(command, args) == expected
