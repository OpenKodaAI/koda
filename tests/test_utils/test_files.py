"""Tests for file operations with path traversal protection."""

import os
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
            ("/srv/koda-user/.gemini/mcp-oauth-tokens.json", ".gemini/mcp-oauth-tokens.json"),
            ("/srv/koda-user/.gemini/google_accounts.json", ".gemini/google_accounts.json"),
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
            ("/srv/koda-user/.claude.json", ".claude.json"),
            ("/srv/koda-user/.Claude.json", ".claude.json"),
            ("/srv/koda-user/.claude-custom-oauth.json", ".claude-custom-oauth.json"),
            ("/srv/koda-user/.claude-staging-oauth.json", ".claude-staging-oauth.json"),
            ("/srv/koda-user/.claude-local-oauth.json", ".claude-local-oauth.json"),
            ("/srv/koda-user/.claude/.config.json", ".claude/.config.json"),
            ("/srv/koda-user/.claude.json.backup", ".claude.json"),
            ("/srv/koda-user/.claude-custom-oauth.json.backup", ".claude-custom-oauth.json"),
            ("/srv/koda-user/.claude/.config.json.backup", ".claude/.config.json"),
            ("/srv/koda-user/.claude/backups/.claude.json.backup.1763100000000", ".claude.json"),
            ("/srv/koda-user/.claude/backups/.config.json.backup.1763100000000", ".claude/backups/"),
            ("/srv/koda-user/.claude/backups", ".claude/backups/"),
            ("/srv/koda-user/.claude/.device-keys.json", ".device-keys.json"),
            ("/srv/secure-storage/.device-keys.json", ".device-keys.json"),
            ("/srv/koda-user/.claude/daemon/auth/a1b2c3.tokens.json", ".claude/daemon/"),
            ("/srv/koda-user/.claude/daemon/auth/a1b2c3.json", ".claude/daemon/"),
            ("/srv/koda-user/.claude/daemon/roster.json", ".claude/daemon/"),
            ("/srv/koda-user/.claude/daemon/roster.json.corrupt.1763100000000", ".claude/daemon/"),
            ("/srv/koda-user/.claude/daemon/dispatch/a1b2c3.json", ".claude/daemon/"),
            ("/srv/koda-user/.claude/daemon/sign-in/a1b2c3.json", ".claude/daemon/"),
            ("/srv/koda-user/.claude/daemon/control.key.tmp.1a2b", ".claude/daemon/"),
            ("/srv/koda-user/.claude/daemon", ".claude/daemon/"),
            ("/srv/koda-user/.claude/ide/48123.lock", ".claude/ide/"),
            ("/srv/koda-user/.claude/ide", ".claude/ide/"),
            ("/srv/koda-user/.claude/bridge-spawn/session_01/mcp-config.json", ".claude/bridge-spawn/"),
            ("/srv/koda-user/.claude/hfi-auth.json", ".claude/hfi-auth.json"),
            ("/srv/koda-user/.claude/remote/.oauth_token", ".claude/remote/.oauth_token"),
            ("/srv/koda-user/.claude/remote/.api_key", ".claude/remote/.api_key"),
            ("/srv/koda-user/.claude/remote/.session_ingress_token", ".session_ingress_token"),
            ("/srv/runner/_sessions/s1.claude-config/.session_ingress_token.e3", ".session_ingress_token"),
            ("/srv/runner/_sessions/s1.claude-config/.session_ingress_token.e3.tmp.42.a1", ".session_ingress_token"),
            ("/srv/koda-user/.SESSION_INGRESS_TOKEN.E12", ".session_ingress_token"),
            ("/srv/koda-user/.config/anthropic/credentials/default.json", ".config/anthropic/credentials/"),
            ("/srv/koda-user/.config/anthropic/credentials/federation/fed-x-1.json", ".config/anthropic/credentials/"),
            ("/srv/koda-user/.config/anthropic/credentials", ".config/anthropic/credentials/"),
            ("/srv/koda-user/.config/Anthropic/Credentials/work.json", ".config/anthropic/credentials/"),
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
            "/srv/koda-user/.claude/settings.json",
            "/srv/koda-user/.claude/CLAUDE.md",
            "/srv/koda-user/.claude/projects/p/session.jsonl",
            "/srv/koda-user/.claude/daemon.log",
            "/srv/koda-user/.claude/ide-notes.md",
            "/srv/koda-user/project/ide/48123.lock",
            "/srv/koda-user/project/bridge-spawn/config.json",
            "/srv/koda-user/project/.mcp.json",
            "/srv/koda-user/project/.config.json",
            "/srv/koda-user/project/claude.json",
            "/srv/koda-user/.claude.json.example",
            "/srv/koda-user/.claude.json.backupx",
            "/srv/koda-user/.claude.jsonl",
            "/srv/koda-user/project/.config.json.tmp.a1b2c3d4",
            "/srv/koda-user/.claude/hfi-auth.json.example",
            "/srv/koda-user/.config/anthropic/configs/default.json",
            "/srv/koda-user/.config/anthropic/active_config",
            "/srv/koda-user/.session_ingress_tokens",
            "/srv/koda-user/.session_ingress_token_old",
            "/srv/koda-user/session_ingress_token.e3",
        ],
    )
    def test_other_paths_are_not(self, path):
        from koda.utils.files import blocked_credential_path

        assert blocked_credential_path(path) is None

    @pytest.mark.parametrize(
        ("provider", "config_dir"), [("claude", ".claude"), ("codex", ".codex"), ("gemini", ".gemini")]
    )
    def test_every_file_the_provider_logout_deletes_is_a_credential_store(self, provider, config_dir):
        """Koda's own logout (``disconnect_provider_connection``) names the CLI credential files; all are refused."""
        from koda.control_plane.manager import _PROVIDER_CREDENTIAL_FILES
        from koda.utils.files import blocked_credential_path

        names = _PROVIDER_CREDENTIAL_FILES[provider]
        assert names
        for name in names:
            assert blocked_credential_path(f"/srv/koda-user/{config_dir}/{name}") == f"{config_dir}/{name}"
        assert set(_PROVIDER_CREDENTIAL_FILES) == {"claude", "codex", "gemini"}

    @pytest.mark.parametrize(
        "options",
        [{}, {"deny_sensitive_dirs": False}, {"deny_sensitive_dirs": False, "deny_sensitive_work_dir": True}],
        ids=["the file tools", "the file commands", "browser_upload"],
    )
    def test_claude_codes_other_credential_files_in_home_are_refused_and_kept_on_logout(
        self, tmp_path, monkeypatch, options
    ):
        """With ``CLAUDE_CONFIG_DIR`` unset, Claude Code keeps more than its login in the default work dir ``~``.

        ``~/.claude.json`` holds the /login managed API key (``primaryApiKey``), and the
        pinned CLI keeps copies of it, device private keys and background-session tokens
        beside it. The file layer refuses each of them; Koda's logout deletes only the
        login, since the global config is also the operator's own settings.
        """
        import koda.control_plane.manager as manager_mod
        from koda.config import CLAUDE_CODE_CREDENTIAL_PATHS

        home = tmp_path.resolve() / "home"
        stores = [entry + "x.json" if entry.endswith("/") else entry for entry in CLAUDE_CODE_CREDENTIAL_PATHS]
        for store in [*stores, ".claude/.credentials.json", ".claude/settings.json", "project/main.py"]:
            (home / store).parent.mkdir(parents=True, exist_ok=True)
            (home / store).write_text('{"primaryApiKey": "sk-ant-canary"}\n')
        monkeypatch.setenv("HOME", str(home))

        for store in stores:
            resolution = resolve_work_path(store, str(home), **options)
            assert resolution.path is None, store
            assert resolution.reason == "path_blocked_file", store
        for visible in (".claude/settings.json", "project/main.py"):
            assert resolve_work_path(visible, str(home), **options).path == home / visible

        manager_mod.ControlPlaneManager._wipe_provider_credential_files(
            object.__new__(manager_mod.ControlPlaneManager), "claude"
        )
        assert not (home / ".claude" / ".credentials.json").exists()
        assert [store for store in stores if not (home / store).exists()] == []

    def test_the_guardrail_matrix_lists_exactly_the_refused_credential_paths(self):
        """The File operations row lists every ``FILEOPS_BLOCKED_CREDENTIAL_PATHS`` entry, and nothing else."""
        import re
        from pathlib import Path

        from koda.config import FILEOPS_BLOCKED_CREDENTIAL_PATHS

        matrix = (Path(__file__).resolve().parents[2] / "docs/security/guardrail-test-matrix.md").read_text()
        row = next(line for line in matrix.splitlines() if line.startswith("| File operations |"))
        start = row.index("(`FILEOPS_BLOCKED_CREDENTIAL_PATHS`")
        listing = row[start : row.index(")", start)]
        named = re.findall(r"`([^`]+)`", listing)[1:]
        assert sorted(named) == sorted(FILEOPS_BLOCKED_CREDENTIAL_PATHS)
        directories, files = listing.split(" directories with everything below them", 1)
        assert sorted(re.findall(r"`([^`]+/)`", directories)) == sorted(
            entry for entry in FILEOPS_BLOCKED_CREDENTIAL_PATHS if entry.endswith("/")
        )
        assert not re.findall(r"`([^`]+/)`", files)

    def test_the_guardrail_matrix_names_exactly_the_copies_refused_with_a_credential_file(self):
        """The File operations row names every ``FILEOPS_CREDENTIAL_COPY_SUFFIXES`` entry, and nothing else."""
        import re
        from pathlib import Path

        from koda.config import FILEOPS_CREDENTIAL_COPY_SUFFIXES

        matrix = (Path(__file__).resolve().parents[2] / "docs/security/guardrail-test-matrix.md").read_text()
        row = next(line for line in matrix.splitlines() if line.startswith("| File operations |"))
        start = row.index("Each file entry also refuses the copies a CLI writes of that file")
        clause = row[row.index(" followed by ", start) : row.index(" and, optionally,", start)]
        assert sorted(re.findall(r"`([^`]+)`", clause)) == sorted(FILEOPS_CREDENTIAL_COPY_SUFFIXES)

    def test_the_guardrail_matrix_names_exactly_the_credential_name_prefixes(self):
        """The File operations row names every ``FILEOPS_CREDENTIAL_NAME_PREFIXES`` entry, and nothing else."""
        import re
        from pathlib import Path

        from koda.config import FILEOPS_CREDENTIAL_NAME_PREFIXES

        matrix = (Path(__file__).resolve().parents[2] / "docs/security/guardrail-test-matrix.md").read_text()
        row = next(line for line in matrix.splitlines() if line.startswith("| File operations |"))
        start = row.index("(`koda/config.py::FILEOPS_CREDENTIAL_NAME_PREFIXES`:")
        listing = row[start : row.index(")", start)]
        assert sorted(re.findall(r"`([^`]+)`", listing)[1:]) == sorted(FILEOPS_CREDENTIAL_NAME_PREFIXES)

    def test_the_guardrail_matrix_cites_its_credential_tests_by_name(self):
        """Every test the File operations row cites exists, and the row cites the tests that pin it by name."""
        import ast
        import re
        from pathlib import Path

        root = Path(__file__).resolve().parents[2]
        matrix = (root / "docs/security/guardrail-test-matrix.md").read_text()
        row = next(line for line in matrix.splitlines() if line.startswith("| File operations |"))
        cells = [cell.strip() for cell in row.strip().strip("|").split(" | ")]
        assert len(cells) == 3
        cited = re.findall(r"`(tests/[^`]+)`", cells[2])
        for test_id in cited:
            path, *names = test_id.split("::")
            scope = ast.parse((root / path).read_text()).body
            for name in names:
                node = next(
                    (
                        node
                        for node in scope
                        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef) and node.name == name
                    ),
                    None,
                )
                assert node is not None, test_id
                scope = getattr(node, "body", [])
        own = "tests/test_utils/test_files.py::TestCredentialStoresAreSecretFiles"
        for name in (
            "test_the_guardrail_matrix_lists_exactly_the_refused_credential_paths",
            "test_the_guardrail_matrix_names_exactly_the_copies_refused_with_a_credential_file",
            "test_the_guardrail_matrix_names_exactly_the_credential_name_prefixes",
            "test_the_guardrail_matrix_cites_its_credential_tests_by_name",
        ):
            assert f"{own}::{name}" in cited, name

    @pytest.mark.parametrize(
        ("copy", "entry"),
        [
            (".claude.json.backup", ".claude.json"),
            (".claude-custom-oauth.json.backup", ".claude-custom-oauth.json"),
            (".claude.json.tmp.a1b2c3d4", ".claude.json"),
            (".claude.json.tmp.4242.a1b2c3d4e5f6", ".claude.json"),
            (".claude/.config.json.backup", ".claude/.config.json"),
            (".claude/.config.json.tmp.a1b2c3d4", ".claude/.config.json"),
            (".claude/backups/.claude.json.backup.1763100000000", ".claude.json"),
            (".claude/backups/.claude.json.corrupted.1763100000000", ".claude.json"),
            ("claude-config/backups/.claude.json.backup.1763100000000", ".claude.json"),
            ("claude-config/backups/.claude.json.corrupted.1763100000000", ".claude.json"),
            ("claude-config/backups/.claude-staging-oauth.json.corrupted.1763100000000", ".claude-staging-oauth.json"),
            ("claude-config/.CLAUDE.JSON.BACKUP", ".claude.json"),
            (".device-keys.json.tmp.a1b2c3d4", ".device-keys.json"),
            (".codex/auth.json.tmp.a1b2c3d4", ".codex/auth.json"),
            (".netrc.backup", ".netrc"),
        ],
    )
    @pytest.mark.parametrize(
        "options",
        [{}, {"deny_sensitive_dirs": False}, {"deny_sensitive_dirs": False, "deny_sensitive_work_dir": True}],
        ids=["the file tools", "the file commands", "browser_upload"],
    )
    def test_the_copies_a_cli_writes_of_a_credential_file_are_refused_wherever_they_sit(
        self, tmp_path, monkeypatch, options, copy, entry
    ):
        """Claude Code writes copies of its global config, with ``primaryApiKey``, beside it and into its backups.

        ``<name>.backup`` beside it, ``<name>.backup.<ts>`` and ``<name>.corrupted.<ts>`` in
        its config dir's ``backups/`` (``$CLAUDE_CONFIG_DIR/backups/`` where that is set, as
        ``claude-config`` is for the compose app container only, not for a worker whose work
        dir is the runtime root), and ``<name>.tmp.<hex>`` while it writes it, left behind
        by a crash. Each is refused by the name of the file it copies, wherever it sits.
        """
        home = tmp_path.resolve() / "home"
        for path in (copy, ".claude.json.example", "claude-config/backups/notes.txt"):
            (home / path).parent.mkdir(parents=True, exist_ok=True)
            (home / path).write_text('{"primaryApiKey": "sk-ant-canary"}\n')
        monkeypatch.setenv("HOME", str(home))

        resolution = resolve_work_path(copy, str(home), **options)
        assert resolution.path is None
        assert resolution.reason == "path_blocked_file"
        assert f"'{entry}' is a credential store" in (resolution.error or "")
        for visible in (".claude.json.example", "claude-config/backups/notes.txt"):
            assert resolve_work_path(visible, str(home), **options).path == home / visible

    @pytest.mark.parametrize(
        ("copy", "extension"),
        [
            (".claude/daemon-bak/control.key.tmp.1a2b", ".key"),
            (".claude/sessions/4242.0f1e2d3c.key.tmp.a1b2c3d4", ".key"),
            (".claude/sessions/4242.0f1e2d3c.key.tmp", ".key"),
            ("ca/key.pem.tmp.4242", ".pem"),
            ("certs/server.PEM.backup", ".pem"),
            ("store.p12.corrupted.1763100000000", ".p12"),
            ("prod.env.backup", ".env"),
            ("deploy/prod.env.tmp.4242.a1b2c3", ".env"),
        ],
    )
    @pytest.mark.parametrize(
        "options",
        [{}, {"deny_sensitive_dirs": False}, {"deny_sensitive_dirs": False, "deny_sensitive_work_dir": True}],
        ids=["the file tools", "the file commands", "browser_upload"],
    )
    def test_the_copies_a_cli_writes_of_a_blocked_file_are_refused_as_that_file(
        self, tmp_path, monkeypatch, options, copy, extension
    ):
        """A blocked file's copy carries the copy's suffix as its own extension, but holds the same secret.

        Claude Code writes each key through ``<name>.tmp.<hex>`` (its CA writes ``key.pem``
        through ``key.pem.tmp.<pid>``), which a crash mid-write leaves beside it, so
        ``control.key.tmp.1a2b`` holds the daemon's control key. Each copy is refused as the
        file it copies; a template's copy and a name that only starts like a copy suffix are not.
        """
        home = tmp_path.resolve() / "home"
        visible = ["certs/server.key.example.backup", "notes/control.key.tmpx", "build.tmp", "a.key.txt"]
        for path in (copy, *visible):
            (home / path).parent.mkdir(parents=True, exist_ok=True)
            (home / path).write_text("canary-key\n")
        monkeypatch.setenv("HOME", str(home))

        assert files_module.blocked_file_suffix(os.path.basename(copy)) == extension
        resolution = resolve_work_path(copy, str(home), **options)
        assert resolution.path is None
        assert resolution.reason == "path_blocked_file"
        assert f"files with extension '{extension}' are blocked" in (resolution.error or "")
        for path in visible:
            assert files_module.blocked_file_suffix(os.path.basename(path)) is None, path
            assert resolve_work_path(path, str(home), **options).path == home / path, path

    @pytest.mark.parametrize(
        "template",
        [
            ".env.backup.example",
            ".env.tmp.sample",
            ".env.corrupted.template",
            "prod.env.backup.dist",
            "deploy/prod.ENV.tmp.Example",
            "certs/server.key.backup.example",
        ],
    )
    @pytest.mark.parametrize(
        "options",
        [{}, {"deny_sensitive_dirs": False}, {"deny_sensitive_dirs": False, "deny_sensitive_work_dir": True}],
        ids=["the file tools", "the file commands", "browser_upload"],
    )
    def test_a_template_named_like_a_copy_stays_readable(self, tmp_path, options, template):
        """A name whose final extension is a template suffix is a committed template, even with a copy suffix before it.

        ``.env.backup.example`` holds the copy suffix ``.backup`` followed by a dot, but its
        final extension says it is the template, as ``.env.example`` is. The copy check
        must not take that exemption away: file_read, file_edit and /cat read it, while the
        copy itself (``.env.backup``, ``prod.env.backup``) stays refused.
        """
        work = tmp_path.resolve() / "work"
        (work / template).parent.mkdir(parents=True, exist_ok=True)
        (work / template).write_text("TOKEN=\n")
        copy = os.path.join(os.path.dirname(template), os.path.splitext(os.path.basename(template))[0])
        (work / copy).write_text("TOKEN=canary\n")

        assert files_module.blocked_file_suffix(os.path.basename(template)) is None
        assert resolve_work_path(template, str(work), **options).path == work / template
        assert files_module.blocked_file_suffix(os.path.basename(copy)) is not None
        assert resolve_work_path(copy, str(work), **options).reason == "path_blocked_file"

    @pytest.mark.parametrize(
        ("env", "stores"),
        [
            (
                {"ANTHROPIC_CONFIG_DIR": "profiles"},
                ["profiles/credentials/default.json", "profiles/credentials/federation/fed-x-1.json"],
            ),
            (
                {"XDG_CONFIG_HOME": "xdg"},
                ["xdg/anthropic/credentials/default.json", "xdg/anthropic/credentials/federation/fed-x-1.json"],
            ),
            (
                {"ANTHROPIC_CONFIG_DIR": "profiles", "XDG_CONFIG_HOME": "xdg"},
                ["profiles/credentials/default.json", "xdg/anthropic/credentials/default.json"],
            ),
            ({"CLAUDE_CODE_FEDERATION_CACHE_DIR": "fed-cache"}, ["fed-cache/fed-x-1.json"]),
        ],
        ids=["ANTHROPIC_CONFIG_DIR", "XDG_CONFIG_HOME", "both", "CLAUDE_CODE_FEDERATION_CACHE_DIR"],
    )
    @pytest.mark.parametrize(
        "options",
        [{}, {"deny_sensitive_dirs": False}, {"deny_sensitive_dirs": False, "deny_sensitive_work_dir": True}],
        ids=["the file tools", "the file commands", "browser_upload"],
    )
    def test_the_anthropic_profile_store_is_refused_where_the_environment_moves_it(
        self, tmp_path, monkeypatch, options, env, stores
    ):
        """Claude Code keeps an Anthropic profile's OAuth tokens in ``<config dir>/credentials/``.

        The config dir is ``ANTHROPIC_CONFIG_DIR``, else ``$XDG_CONFIG_HOME/anthropic``, else
        ``~/.config/anthropic`` (refused by name), and the federation token cache is
        ``CLAUDE_CODE_FEDERATION_CACHE_DIR`` where that is set. Each location the environment
        names is refused, wherever it is; the profile's settings beside it are not.
        """
        home = tmp_path.resolve() / "home"
        visible = [path.replace("/credentials/", "/configs/") for path in stores if "/credentials/" in path]
        for path in [*stores, *visible, "notes.txt"]:
            (home / path).parent.mkdir(parents=True, exist_ok=True)
            (home / path).write_text('{"refresh_token": "canary-refresh"}\n')
        monkeypatch.setenv("HOME", str(home))
        for key in ("ANTHROPIC_CONFIG_DIR", "XDG_CONFIG_HOME", "CLAUDE_CODE_FEDERATION_CACHE_DIR"):
            monkeypatch.delenv(key, raising=False)
        for path in stores:
            assert resolve_work_path(path, str(home), **options).path == home / path, path
        for key, value in env.items():
            monkeypatch.setenv(key, str(home / value))

        for path in stores:
            resolution = resolve_work_path(path, str(home), **options)
            assert resolution.path is None, path
            assert resolution.reason == "path_sensitive_dir", path
            assert not validate_work_dir(str((home / path).parent)).ok, path
        for path in [*visible, "notes.txt"]:
            assert resolve_work_path(path, str(home), **options).path == home / path, path

    @pytest.mark.parametrize(("provider", "env_key"), [("claude", "CLAUDE_CONFIG_DIR"), ("codex", "CODEX_HOME")])
    @pytest.mark.parametrize(
        "options",
        [{}, {"deny_sensitive_dirs": False}, {"deny_sensitive_dirs": False, "deny_sensitive_work_dir": True}],
        ids=["the file tools", "the file commands", "browser_upload"],
    )
    def test_where_the_environment_moves_a_cli_config_dir_its_login_is_refused_there_too(
        self, tmp_path, monkeypatch, provider, env_key, options
    ):
        """``CLAUDE_CONFIG_DIR`` and ``CODEX_HOME`` move a CLI's login out of HOME, under any name.

        Koda's own logout deletes the credential files there, so the file layer refuses them
        there too, with the rest of that config dir (settings, session transcripts).
        """
        import koda.control_plane.manager as manager_mod
        from koda.control_plane.manager import _PROVIDER_CREDENTIAL_FILES

        home = tmp_path.resolve() / "home"
        config_dir = home / f"{provider}-home"
        (config_dir / "sessions").mkdir(parents=True)
        (config_dir / "sessions" / "rollout.jsonl").write_text('{"canary": "transcript"}\n')
        (home / "notes.txt").write_text("visible\n")
        names = _PROVIDER_CREDENTIAL_FILES[provider]
        for name in names:
            (config_dir / name).write_text('{"tokens": {"access_token": "canary-token"}}\n')
        monkeypatch.setenv("HOME", str(home))
        monkeypatch.setenv(env_key, str(config_dir))

        for path in (*(f"{provider}-home/{name}" for name in names), f"{provider}-home/sessions/rollout.jsonl"):
            resolution = resolve_work_path(path, str(home), **options)
            assert resolution.path is None, path
            assert resolution.reason in {"path_sensitive_dir", "path_blocked_file"}, path
        assert resolve_work_path("notes.txt", str(home), **options).path == home / "notes.txt"
        assert validate_work_dir(str(config_dir)).blocked

        manager = object.__new__(manager_mod.ControlPlaneManager)
        manager._wipe_provider_credential_files(provider)
        assert [name for name in names if (config_dir / name).exists()] == []
        assert (config_dir / "sessions" / "rollout.jsonl").exists()

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
