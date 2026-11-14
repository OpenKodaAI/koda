"""Tests for filesystem tool handlers."""

import os
from unittest.mock import AsyncMock, patch

import pytest

from koda.services import tool_dispatcher
from koda.services.tool_dispatcher import (
    ToolContext,
    _resolve_file_path,
)


@pytest.fixture(autouse=True)
def _fresh_tool_rate_window():
    """execute_tool counts calls per user and minute; each test starts with an empty window."""
    tool_dispatcher._tool_rate_windows.clear()
    yield
    tool_dispatcher._tool_rate_windows.clear()


def _make_ctx(work_dir: str, **overrides) -> ToolContext:
    defaults = dict(
        user_id=111,
        chat_id=111,
        work_dir=work_dir,
        user_data={
            "work_dir": work_dir,
            "model": "claude-sonnet-4-6",
            "session_id": "s",
            "total_cost": 0.0,
            "query_count": 0,
        },
        agent=AsyncMock(),
        agent_mode="autonomous",
    )
    defaults.update(overrides)
    return ToolContext(**defaults)


class TestResolveFilePath:
    def test_empty_path(self):
        assert _resolve_file_path("", "/tmp/work").error is not None

    def test_path_within_workdir(self, tmp_path):
        assert _resolve_file_path(str(tmp_path / "foo.txt"), str(tmp_path)).error is None

    def test_path_outside_workdir(self, tmp_path):
        err = _resolve_file_path("/etc/passwd", str(tmp_path)).error
        assert err is not None
        assert "outside" in err or "not allowed" in err

    def test_blocked_extension(self, tmp_path):
        err = _resolve_file_path(str(tmp_path / "secrets.env"), str(tmp_path)).error
        assert err is not None
        assert "blocked" in err.lower()


class TestFileReadHandler:
    @pytest.mark.asyncio
    async def test_read_existing_file(self, tmp_path):
        f = tmp_path / "hello.txt"
        f.write_text("line1\nline2\nline3\n")
        from koda.services.tool_dispatcher import _handle_file_read

        ctx = _make_ctx(str(tmp_path))
        with patch("koda.services.tool_dispatcher.FILEOPS_ENABLED", True):
            result = await _handle_file_read({"path": str(f)}, ctx)
        assert result.success
        assert "line1" in result.output

    @pytest.mark.asyncio
    async def test_read_with_offset_and_limit(self, tmp_path):
        f = tmp_path / "lines.txt"
        f.write_text("line1\nline2\nline3\nline4\nline5\n")
        from koda.services.tool_dispatcher import _handle_file_read

        ctx = _make_ctx(str(tmp_path))
        with patch("koda.services.tool_dispatcher.FILEOPS_ENABLED", True):
            result = await _handle_file_read({"path": str(f), "offset": 1, "limit": 2}, ctx)
        assert result.success
        assert "line2" in result.output
        assert "line3" in result.output
        assert "line4" not in result.output

    @pytest.mark.asyncio
    async def test_read_nonexistent(self, tmp_path):
        from koda.services.tool_dispatcher import _handle_file_read

        ctx = _make_ctx(str(tmp_path))
        with patch("koda.services.tool_dispatcher.FILEOPS_ENABLED", True):
            result = await _handle_file_read({"path": str(tmp_path / "nope.txt")}, ctx)
        assert not result.success

    @pytest.mark.asyncio
    async def test_disabled(self, tmp_path):
        from koda.services.tool_dispatcher import _handle_file_read

        ctx = _make_ctx(str(tmp_path))
        with patch("koda.services.tool_dispatcher.FILEOPS_ENABLED", False):
            result = await _handle_file_read({"path": "x"}, ctx)
        assert not result.success
        assert "not enabled" in result.output


class TestFileWriteHandler:
    @pytest.mark.asyncio
    async def test_write_new_file(self, tmp_path):
        from koda.services.tool_dispatcher import _handle_file_write

        ctx = _make_ctx(str(tmp_path))
        target = str(tmp_path / "new.txt")
        with patch("koda.services.tool_dispatcher.FILEOPS_ENABLED", True):
            result = await _handle_file_write({"path": target, "content": "hello"}, ctx)
        assert result.success
        assert os.path.isfile(target)
        with open(target) as fh:
            assert fh.read() == "hello"

    @pytest.mark.asyncio
    async def test_write_missing_content(self, tmp_path):
        from koda.services.tool_dispatcher import _handle_file_write

        ctx = _make_ctx(str(tmp_path))
        with patch("koda.services.tool_dispatcher.FILEOPS_ENABLED", True):
            result = await _handle_file_write({"path": str(tmp_path / "x.txt")}, ctx)
        assert not result.success
        assert "content" in result.output.lower()


class TestFileEditHandler:
    @pytest.mark.asyncio
    async def test_replace_string(self, tmp_path):
        f = tmp_path / "code.py"
        f.write_text("foo = 1\nbar = 2\n")
        from koda.services.tool_dispatcher import _handle_file_edit

        ctx = _make_ctx(str(tmp_path))
        with patch("koda.services.tool_dispatcher.FILEOPS_ENABLED", True):
            result = await _handle_file_edit({"path": str(f), "old_string": "foo = 1", "new_string": "foo = 42"}, ctx)
        assert result.success
        assert "foo = 42" in f.read_text()

    @pytest.mark.asyncio
    async def test_ambiguous_match(self, tmp_path):
        f = tmp_path / "dup.txt"
        f.write_text("aaa\naaa\n")
        from koda.services.tool_dispatcher import _handle_file_edit

        ctx = _make_ctx(str(tmp_path))
        with patch("koda.services.tool_dispatcher.FILEOPS_ENABLED", True):
            result = await _handle_file_edit({"path": str(f), "old_string": "aaa", "new_string": "bbb"}, ctx)
        assert not result.success
        assert "2 times" in result.output

    @pytest.mark.asyncio
    async def test_replace_all(self, tmp_path):
        f = tmp_path / "dup.txt"
        f.write_text("aaa\naaa\n")
        from koda.services.tool_dispatcher import _handle_file_edit

        ctx = _make_ctx(str(tmp_path))
        with patch("koda.services.tool_dispatcher.FILEOPS_ENABLED", True):
            result = await _handle_file_edit(
                {"path": str(f), "old_string": "aaa", "new_string": "bbb", "replace_all": True}, ctx
            )
        assert result.success
        assert f.read_text() == "bbb\nbbb\n"


class TestFileDeleteHandler:
    @pytest.mark.asyncio
    async def test_delete_file(self, tmp_path):
        f = tmp_path / "del.txt"
        f.write_text("bye")
        from koda.services.tool_dispatcher import _handle_file_delete

        ctx = _make_ctx(str(tmp_path))
        with patch("koda.services.tool_dispatcher.FILEOPS_ENABLED", True):
            result = await _handle_file_delete({"path": str(f)}, ctx)
        assert result.success
        assert not os.path.exists(str(f))

    @pytest.mark.asyncio
    async def test_delete_nonexistent(self, tmp_path):
        from koda.services.tool_dispatcher import _handle_file_delete

        ctx = _make_ctx(str(tmp_path))
        with patch("koda.services.tool_dispatcher.FILEOPS_ENABLED", True):
            result = await _handle_file_delete({"path": str(tmp_path / "nope.txt")}, ctx)
        assert not result.success


class TestFileListHandler:
    @pytest.mark.asyncio
    async def test_list_dir(self, tmp_path):
        (tmp_path / "a.txt").write_text("a")
        (tmp_path / "b.txt").write_text("b")
        (tmp_path / "subdir").mkdir()
        from koda.services.tool_dispatcher import _handle_file_list

        ctx = _make_ctx(str(tmp_path))
        with patch("koda.services.tool_dispatcher.FILEOPS_ENABLED", True):
            result = await _handle_file_list({"path": str(tmp_path)}, ctx)
        assert result.success
        assert "a.txt" in result.output
        assert "[d] subdir" in result.output


class TestFileSearchHandler:
    @pytest.mark.asyncio
    async def test_search_pattern(self, tmp_path):
        (tmp_path / "foo.py").write_text("x")
        (tmp_path / "bar.txt").write_text("y")
        from koda.services.tool_dispatcher import _handle_file_search

        ctx = _make_ctx(str(tmp_path))
        with patch("koda.services.tool_dispatcher.FILEOPS_ENABLED", True):
            result = await _handle_file_search({"pattern": "*.py", "path": str(tmp_path)}, ctx)
        assert result.success
        assert "foo.py" in result.output
        assert "bar.txt" not in result.output


class TestFileGrepHandler:
    @pytest.mark.asyncio
    async def test_grep_content(self, tmp_path):
        (tmp_path / "code.py").write_text("# TODO: fix this\nprint('ok')\n")
        from koda.services.tool_dispatcher import _handle_file_grep

        ctx = _make_ctx(str(tmp_path))
        with patch("koda.services.tool_dispatcher.FILEOPS_ENABLED", True):
            result = await _handle_file_grep({"pattern": "TODO", "path": str(tmp_path)}, ctx)
        assert result.success
        assert "TODO" in result.output

    @pytest.mark.asyncio
    async def test_grep_invalid_regex(self, tmp_path):
        from koda.services.tool_dispatcher import _handle_file_grep

        ctx = _make_ctx(str(tmp_path))
        with patch("koda.services.tool_dispatcher.FILEOPS_ENABLED", True):
            result = await _handle_file_grep({"pattern": "[invalid", "path": str(tmp_path)}, ctx)
        assert not result.success
        assert "Invalid regex" in result.output


class TestFileMoveHandler:
    @pytest.mark.asyncio
    async def test_move_file(self, tmp_path):
        src = tmp_path / "old.txt"
        src.write_text("data")
        dst = str(tmp_path / "new.txt")
        from koda.services.tool_dispatcher import _handle_file_move

        ctx = _make_ctx(str(tmp_path))
        with patch("koda.services.tool_dispatcher.FILEOPS_ENABLED", True):
            result = await _handle_file_move({"source": str(src), "destination": dst}, ctx)
        assert result.success
        assert os.path.isfile(dst)
        assert not os.path.exists(str(src))

    @pytest.mark.asyncio
    async def test_move_missing_params(self, tmp_path):
        from koda.services.tool_dispatcher import _handle_file_move

        ctx = _make_ctx(str(tmp_path))
        with patch("koda.services.tool_dispatcher.FILEOPS_ENABLED", True):
            result = await _handle_file_move({"source": str(tmp_path / "x")}, ctx)
        assert not result.success


class TestFileInfoHandler:
    @pytest.mark.asyncio
    async def test_file_info(self, tmp_path):
        f = tmp_path / "info.txt"
        f.write_text("hello")
        from koda.services.tool_dispatcher import _handle_file_info

        ctx = _make_ctx(str(tmp_path))
        with patch("koda.services.tool_dispatcher.FILEOPS_ENABLED", True):
            result = await _handle_file_info({"path": str(f)}, ctx)
        assert result.success
        assert "5 bytes" in result.output
        assert "file" in result.output

    @pytest.mark.asyncio
    async def test_info_nonexistent(self, tmp_path):
        from koda.services.tool_dispatcher import _handle_file_info

        ctx = _make_ctx(str(tmp_path))
        with patch("koda.services.tool_dispatcher.FILEOPS_ENABLED", True):
            result = await _handle_file_info({"path": str(tmp_path / "nope.txt")}, ctx)
        assert not result.success


class TestSecretFilesAreBlocked:
    def test_dotenv_absolute_path_is_blocked(self, tmp_path):
        err = _resolve_file_path(str(tmp_path / ".env"), str(tmp_path)).error
        assert err is not None
        assert "blocked" in err.lower()

    def test_dotenv_variant_is_blocked(self, tmp_path):
        err = _resolve_file_path(str(tmp_path / ".env.production"), str(tmp_path)).error
        assert err is not None
        assert "blocked" in err.lower()

    @pytest.mark.asyncio
    async def test_file_read_refuses_dotenv(self, tmp_path):
        (tmp_path / ".env").write_text("TOKEN=canary-secret\n")
        from koda.services.tool_dispatcher import _handle_file_read

        ctx = _make_ctx(str(tmp_path))
        with patch("koda.services.tool_dispatcher.FILEOPS_ENABLED", True):
            result = await _handle_file_read({"path": str(tmp_path / ".env")}, ctx)
        assert not result.success
        assert "canary-secret" not in result.output

    @pytest.mark.asyncio
    async def test_grep_skips_secret_files_and_symlink_escapes(self, tmp_path):
        work = tmp_path / "work"
        work.mkdir()
        outside = tmp_path / "outside"
        outside.mkdir()
        (work / ".env").write_text("TOKEN=canary-env\n")
        (work / "prod.env").write_text("TOKEN=canary-prod\n")
        (outside / "secret.txt").write_text("TOKEN=canary-outside\n")
        (work / "linked.txt").symlink_to(outside / "secret.txt")
        (work / "code.py").write_text("TOKEN = read_from_vault()\n")
        from koda.services.tool_dispatcher import _handle_file_grep

        ctx = _make_ctx(str(work))
        with patch("koda.services.tool_dispatcher.FILEOPS_ENABLED", True):
            result = await _handle_file_grep({"pattern": "TOKEN", "path": "."}, ctx)
        assert result.success
        assert "code.py" in result.output
        assert "canary" not in result.output

    @pytest.mark.asyncio
    async def test_grep_skips_secret_files_in_subdirectories_and_secret_named_symlinks(self, tmp_path):
        work = tmp_path / "work"
        (work / "config").mkdir(parents=True)
        (work / "config" / "server.pem").write_text("TOKEN=canary-pem\n")
        (work / "config" / ".env.local").write_text("TOKEN=canary-local\n")
        (work / "notes.txt").write_text("TOKEN=canary-via-link\n")
        (work / "alias.key").symlink_to(work / "notes.txt")
        (work / "safe-link.txt").symlink_to(work / "config" / "server.pem")
        from koda.services.tool_dispatcher import _handle_file_grep

        ctx = _make_ctx(str(work))
        with patch("koda.services.tool_dispatcher.FILEOPS_ENABLED", True):
            result = await _handle_file_grep({"pattern": "TOKEN", "path": "."}, ctx)
        assert result.success
        assert "canary-pem" not in result.output
        assert "canary-local" not in result.output
        assert "notes.txt:1:" in result.output
        assert "alias.key" not in result.output
        assert "safe-link.txt" not in result.output

    @pytest.mark.asyncio
    async def test_grep_prunes_sensitive_directories_below_the_search_root(self, tmp_path, monkeypatch):
        work = tmp_path / "work"
        (work / "etc").mkdir(parents=True)
        (work / "src").mkdir()
        (work / "etc" / "shadow.txt").write_text("TOKEN=canary-sensitive\n")
        (work / "src" / "app.py").write_text("TOKEN = vault()\n")
        monkeypatch.setattr("koda.utils.workdir.SENSITIVE_DIRS", frozenset({str(work / "etc")}))
        from koda.services.tool_dispatcher import _handle_file_grep

        ctx = _make_ctx(str(work))
        with patch("koda.services.tool_dispatcher.FILEOPS_ENABLED", True):
            result = await _handle_file_grep({"pattern": "TOKEN", "path": "."}, ctx)
        assert result.success
        assert "app.py" in result.output
        assert "canary-sensitive" not in result.output

    @pytest.mark.asyncio
    async def test_grep_runs_the_full_resolver_only_for_symlinked_files(self, tmp_path):
        """A regular file below the checked root needs only the name check; the walk stays cheap."""
        work = tmp_path / "work"
        (work / "pkg").mkdir(parents=True)
        for index in range(40):
            (work / "pkg" / f"mod{index}.py").write_text(f"VALUE = {index}\n")
        (work / "linked.py").symlink_to(work / "pkg" / "mod0.py")
        from koda.services import tool_dispatcher
        from koda.services.tool_dispatcher import _handle_file_grep

        ctx = _make_ctx(str(work))
        with (
            patch("koda.services.tool_dispatcher.FILEOPS_ENABLED", True),
            patch.object(tool_dispatcher, "resolve_work_path", wraps=tool_dispatcher.resolve_work_path) as resolver,
        ):
            result = await _handle_file_grep({"pattern": "VALUE", "path": "."}, ctx)
        assert result.success
        assert "pkg/mod39.py:1: VALUE = 39" in result.output
        assert "linked.py:1: VALUE = 0" in result.output
        # One call for the search root, one for the symlinked file; none per regular file.
        assert [call.args[0] for call in resolver.call_args_list] == [".", str(work / "linked.py")]

    @pytest.mark.asyncio
    async def test_grep_does_not_log_a_warning_per_skipped_secret_file(self, tmp_path):
        work = tmp_path / "work"
        work.mkdir()
        for index in range(20):
            (work / f"fixture{index}.pem").write_text("-----BEGIN-----\n")
        (work / "code.py").write_text("x = 1\n")
        from koda.services.tool_dispatcher import _handle_file_grep

        ctx = _make_ctx(str(work))
        with (
            patch("koda.services.tool_dispatcher.FILEOPS_ENABLED", True),
            patch("koda.utils.files.log") as files_log,
        ):
            result = await _handle_file_grep({"pattern": "BEGIN", "path": "."}, ctx)
        assert result.success
        assert "No matches" in result.output
        files_log.warning.assert_not_called()


class TestEnvTemplatesStayEditable:
    """`.env.example` is the committed template, not the secret: agents must keep updating it."""

    @pytest.mark.asyncio
    async def test_file_read_and_edit_allow_env_example(self, tmp_path):
        (tmp_path / ".env.example").write_text("TOKEN=\n")
        from koda.services.tool_dispatcher import _handle_file_edit, _handle_file_read

        ctx = _make_ctx(str(tmp_path))
        with patch("koda.services.tool_dispatcher.FILEOPS_ENABLED", True):
            read = await _handle_file_read({"path": ".env.example"}, ctx)
            edit = await _handle_file_edit(
                {"path": ".env.example", "old_string": "TOKEN=\n", "new_string": "TOKEN=\nNEW_SETTING=\n"}, ctx
            )
        assert read.success, read.output
        assert "TOKEN=" in read.output
        assert edit.success, edit.output
        assert (tmp_path / ".env.example").read_text() == "TOKEN=\nNEW_SETTING=\n"

    @pytest.mark.asyncio
    async def test_grep_searches_env_example_but_not_env(self, tmp_path):
        (tmp_path / ".env.example").write_text("TOKEN=placeholder\n")
        (tmp_path / ".env").write_text("TOKEN=canary-secret\n")
        (tmp_path / "sub").mkdir()
        (tmp_path / "sub" / ".env.sample").write_text("TOKEN=sample\n")
        from koda.services.tool_dispatcher import _handle_file_grep

        ctx = _make_ctx(str(tmp_path))
        with patch("koda.services.tool_dispatcher.FILEOPS_ENABLED", True):
            result = await _handle_file_grep({"pattern": "TOKEN", "path": "."}, ctx)
        assert result.success
        assert ".env.example:1: TOKEN=placeholder" in result.output
        assert "sub/.env.sample:1: TOKEN=sample" in result.output
        assert "canary-secret" not in result.output


class TestDocumentedRelativePathsResolveUnderWorkDir:
    """The tool prompt documents paths relative to the work directory (D-066)."""

    @pytest.fixture
    def work(self, tmp_path, monkeypatch):
        work = tmp_path / "work"
        (work / "src").mkdir(parents=True)
        (work / "src" / "main.py").write_text("# TODO: work tree\nfoo = 1\n")
        (work / "temp.txt").write_text("temp")
        (work / "old.txt").write_text("old")
        # The process CWD holds a decoy tree with the same layout.
        decoy = tmp_path / "decoy"
        (decoy / "src").mkdir(parents=True)
        (decoy / "src" / "main.py").write_text("# TODO: decoy tree\nfoo = 1\n")
        (decoy / "temp.txt").write_text("decoy")
        (decoy / "old.txt").write_text("decoy")
        monkeypatch.chdir(decoy)
        return work

    async def _call(self, handler_name: str, params: dict, work):
        from koda.services import tool_dispatcher

        handler = getattr(tool_dispatcher, handler_name)
        with patch("koda.services.tool_dispatcher.FILEOPS_ENABLED", True):
            return await handler(params, _make_ctx(str(work)))

    @pytest.mark.asyncio
    async def test_file_read(self, work):
        result = await self._call("_handle_file_read", {"path": "src/main.py"}, work)
        assert result.success, result.output
        assert "work tree" in result.output

    @pytest.mark.asyncio
    async def test_file_write(self, work, tmp_path):
        result = await self._call("_handle_file_write", {"path": "output.txt", "content": "Hello world"}, work)
        assert result.success, result.output
        assert (work / "output.txt").read_text() == "Hello world"
        assert not (tmp_path / "decoy" / "output.txt").exists()

    @pytest.mark.asyncio
    async def test_file_edit(self, work, tmp_path):
        result = await self._call(
            "_handle_file_edit", {"path": "src/main.py", "old_string": "foo = 1", "new_string": "foo = 2"}, work
        )
        assert result.success, result.output
        assert "foo = 2" in (work / "src" / "main.py").read_text()
        assert "foo = 1" in (tmp_path / "decoy" / "src" / "main.py").read_text()

    @pytest.mark.asyncio
    async def test_file_list(self, work):
        result = await self._call("_handle_file_list", {"path": "src/"}, work)
        assert result.success, result.output
        assert "main.py" in result.output

    @pytest.mark.asyncio
    async def test_file_list_defaults_to_work_dir(self, work):
        result = await self._call("_handle_file_list", {}, work)
        assert result.success, result.output
        assert "[d] src" in result.output

    @pytest.mark.asyncio
    async def test_file_search(self, work):
        result = await self._call("_handle_file_search", {"pattern": "*.py", "path": "src/"}, work)
        assert result.success, result.output
        assert "main.py" in result.output

    @pytest.mark.asyncio
    async def test_file_grep(self, work):
        result = await self._call("_handle_file_grep", {"pattern": "TODO", "path": "src/", "glob": "*.py"}, work)
        assert result.success, result.output
        assert "work tree" in result.output
        assert "decoy" not in result.output

    @pytest.mark.asyncio
    async def test_file_delete(self, work, tmp_path):
        result = await self._call("_handle_file_delete", {"path": "temp.txt"}, work)
        assert result.success, result.output
        assert not (work / "temp.txt").exists()
        assert (tmp_path / "decoy" / "temp.txt").exists()

    @pytest.mark.asyncio
    async def test_file_move(self, work, tmp_path):
        result = await self._call("_handle_file_move", {"source": "old.txt", "destination": "new.txt"}, work)
        assert result.success, result.output
        assert (work / "new.txt").read_text() == "old"
        assert (tmp_path / "decoy" / "old.txt").exists()

    @pytest.mark.asyncio
    async def test_file_info(self, work):
        result = await self._call("_handle_file_info", {"path": "src/main.py"}, work)
        assert result.success, result.output
        assert f"Path: {(work / 'src' / 'main.py').resolve()}" in result.output

    @pytest.mark.asyncio
    async def test_relative_traversal_is_still_refused(self, work):
        result = await self._call("_handle_file_read", {"path": "../decoy/temp.txt"}, work)
        assert not result.success
        assert "outside" in result.output


class TestPathScopedGrantsSeeResolvedFileToolPaths:
    """A fileops ``allowed_paths`` grant sees the path a file tool touches, as /cat's gate does."""

    @pytest.fixture
    def work(self, tmp_path, monkeypatch):
        work = (tmp_path / "work").resolve()
        (work / "src").mkdir(parents=True)
        (work / "src" / "main.py").write_text("TOKEN = 'granted'\n")
        (work / "top.txt").write_text("TOKEN = 'canary-outside-grant'\n")
        monkeypatch.chdir(tmp_path)
        return work

    @staticmethod
    def _grant(*allowed_paths) -> dict:
        return {"integration_grants": {"fileops": {"enabled": True, "allowed_paths": [str(p) for p in allowed_paths]}}}

    async def _execute(self, tool: str, params: dict, work, *allowed_paths):
        from koda.services.tool_dispatcher import AgentToolCall, execute_tool

        with (
            patch("koda.services.tool_dispatcher.AGENT_RESOURCE_ACCESS_POLICY", self._grant(*allowed_paths)),
            patch("koda.services.execution_policy.AGENT_TOOL_POLICY", {"allowed_tool_ids": [tool]}),
            patch("koda.services.execution_policy.FILEOPS_ENABLED", True),
            patch("koda.services.tool_dispatcher.FILEOPS_ENABLED", True),
        ):
            return await execute_tool(AgentToolCall(tool, params, ""), _make_ctx(str(work)))

    def test_policy_params_carry_the_resolved_paths(self, work):
        from koda.services.tool_dispatcher import AgentToolCall, _policy_params_for_call

        ctx = _make_ctx(str(work))
        read = _policy_params_for_call(AgentToolCall("file_read", {"path": "src/../src/main.py", "offset": 2}, ""), ctx)
        assert read == {"path": str(work / "src" / "main.py"), "offset": 2}
        move = _policy_params_for_call(
            AgentToolCall("file_move", {"source": "src/main.py", "destination": "out/main.py"}, ""), ctx
        )
        assert move == {"source": str(work / "src" / "main.py"), "destination": str(work / "out" / "main.py")}
        assert _policy_params_for_call(AgentToolCall("file_list", {}, ""), ctx) == {"path": str(work)}

    @pytest.mark.asyncio
    async def test_relative_path_inside_the_grant_is_allowed(self, work):
        result = await self._execute("file_grep", {"pattern": "TOKEN", "path": "src"}, work, work / "src")
        assert result.success, result.output
        assert "granted" in result.output
        assert "canary-outside-grant" not in result.output

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        ("tool", "params"),
        [("file_list", {}), ("file_search", {"pattern": "*.txt"}), ("file_grep", {"pattern": "TOKEN"})],
    )
    async def test_tools_that_default_to_the_work_dir_are_checked_against_it(self, work, tool, params):
        refused = await self._execute(tool, params, work, work / "src")
        assert not refused.success
        assert "outside the granted scope" in refused.output
        assert "top.txt" not in refused.output

        granted = await self._execute(tool, params, work, work)
        assert granted.success, granted.output
        assert "top.txt" in granted.output

    def test_file_move_grant_covers_both_ends(self, work):
        from koda.agent_contract import evaluate_integration_grant

        grant = self._grant(work / "src")
        inside = evaluate_integration_grant(
            "file_move", {"source": str(work / "src" / "main.py"), "destination": str(work / "src" / "b.py")}, grant
        )
        assert inside.allowed
        out_of_grant = evaluate_integration_grant(
            "file_move", {"source": str(work / "src" / "main.py"), "destination": str(work / "main.py")}, grant
        )
        assert not out_of_grant.allowed
        assert out_of_grant.reason == "path_not_granted"
        into_grant = evaluate_integration_grant(
            "file_move", {"source": str(work / "top.txt"), "destination": str(work / "src" / "top.txt")}, grant
        )
        assert not into_grant.allowed
        assert into_grant.reason == "path_not_granted"

    @pytest.mark.asyncio
    async def test_file_move_out_of_the_grant_is_refused(self, work):
        """The source is inside the grant; the destination is not."""
        result = await self._execute(
            "file_move", {"source": str(work / "src" / "main.py"), "destination": "main.py"}, work, work / "src"
        )
        assert not result.success
        assert "outside the granted scope" in result.output
        assert (work / "src" / "main.py").exists()
        assert not (work / "main.py").exists()

    @pytest.mark.asyncio
    async def test_grep_does_not_follow_a_symlink_out_of_the_granted_search_root(self, work):
        """A link inside the grant to a file elsewhere in the work dir is refused, as /cat and file_read refuse it."""
        (work / "src" / "link-to-top.txt").symlink_to(work / "top.txt")
        (work / "src" / "alias.py").symlink_to(work / "src" / "main.py")
        result = await self._execute("file_grep", {"pattern": "TOKEN", "path": "src"}, work, work / "src")
        assert result.success, result.output
        assert "canary-outside-grant" not in result.output
        assert "link-to-top.txt" not in result.output
        assert "main.py:1: TOKEN = 'granted'" in result.output
        # A link that stays inside the search root is still followed.
        assert "alias.py:1: TOKEN = 'granted'" in result.output
        refused = await self._execute("file_read", {"path": "src/link-to-top.txt"}, work, work / "src")
        assert not refused.success
        assert "outside the granted scope" in refused.output

    @pytest.mark.asyncio
    async def test_grep_keeps_every_file_it_reads_inside_the_search_root(self, work):
        """Without a grant too: the search root, not only the work dir, bounds what grep prints."""
        from koda.services.tool_dispatcher import _handle_file_grep

        (work / "src" / "link-to-top.txt").symlink_to(work / "top.txt")
        with patch("koda.services.tool_dispatcher.FILEOPS_ENABLED", True):
            scoped = await _handle_file_grep({"pattern": "TOKEN", "path": "src"}, _make_ctx(str(work)))
            whole = await _handle_file_grep({"pattern": "TOKEN", "path": "."}, _make_ctx(str(work)))
        assert scoped.success, scoped.output
        assert "canary-outside-grant" not in scoped.output
        assert "src/link-to-top.txt:1: TOKEN = 'canary-outside-grant'" in whole.output


class TestGrantRootsWrittenThroughASymlink:
    """``allowed_paths`` entries are canonicalised like the call path, so a symlinked grant root still matches."""

    @pytest.fixture
    def linked_work(self, tmp_path, monkeypatch):
        real = (tmp_path / "work").resolve()
        (real / "src").mkdir(parents=True)
        (real / "src" / "main.py").write_text("granted-source\n")
        (real / "top.txt").write_text("canary-top\n")
        link = tmp_path / "link"
        link.symlink_to(real)
        monkeypatch.chdir(tmp_path)
        return link

    @staticmethod
    def _grant(*allowed_paths) -> dict:
        return {"integration_grants": {"fileops": {"enabled": True, "allowed_paths": [str(p) for p in allowed_paths]}}}

    async def _read(self, path: str, link, *allowed_paths):
        from koda.services.tool_dispatcher import AgentToolCall, execute_tool

        with (
            patch("koda.services.tool_dispatcher.AGENT_RESOURCE_ACCESS_POLICY", self._grant(*allowed_paths)),
            patch("koda.services.execution_policy.AGENT_TOOL_POLICY", {"allowed_tool_ids": ["file_read"]}),
            patch("koda.services.execution_policy.FILEOPS_ENABLED", True),
            patch("koda.services.tool_dispatcher.FILEOPS_ENABLED", True),
        ):
            return await execute_tool(AgentToolCall("file_read", {"path": path}, ""), _make_ctx(str(link)))

    @pytest.mark.asyncio
    @pytest.mark.parametrize("path", ["{link}/src/main.py", "src/main.py", "src/../src/main.py"])
    async def test_paths_inside_a_symlinked_grant_root_are_granted(self, linked_work, path):
        result = await self._read(path.format(link=linked_work), linked_work, linked_work / "src")
        assert result.success, result.output
        assert "granted-source" in result.output

    @pytest.mark.asyncio
    @pytest.mark.parametrize("path", ["{link}/top.txt", "src/../top.txt"])
    async def test_paths_outside_a_symlinked_grant_root_are_still_refused(self, linked_work, path):
        result = await self._read(path.format(link=linked_work), linked_work, linked_work / "src")
        assert not result.success
        assert "outside the granted scope" in result.output
        assert "canary-top" not in result.output

    def test_the_contract_grant_check_canonicalises_entries(self, linked_work):
        from koda.agent_contract import evaluate_integration_grant

        real = linked_work.resolve()
        grant = self._grant(linked_work / "src")
        assert evaluate_integration_grant("file_read", {"path": str(real / "src" / "main.py")}, grant).allowed
        refused = evaluate_integration_grant("file_read", {"path": str(real / "top.txt")}, grant)
        assert not refused.allowed
        assert refused.reason == "path_not_granted"

    @pytest.mark.asyncio
    @pytest.mark.parametrize(("path", "granted"), [("src/main.py", True), ("top.txt", False)])
    async def test_a_home_relative_entry_is_expanded_then_canonicalised(
        self, linked_work, monkeypatch, tmp_path, path, granted
    ):
        """``~/link/src`` is ``<HOME>/link/src``, a grant root written through a symlink."""
        monkeypatch.setenv("HOME", str(tmp_path))
        result = await self._read(path, linked_work, "~/link/src")
        assert result.success == granted, result.output
        if not granted:
            assert "outside the granted scope" in result.output

    def test_a_relative_entry_is_not_resolved_against_the_process_cwd(self, linked_work):
        """The CWD is the parent of ``link``: resolving ``link/src`` there would widen the grant."""
        from koda.agent_contract import evaluate_integration_grant

        real = linked_work.resolve()
        grant = self._grant("link/src")
        decision = evaluate_integration_grant("file_read", {"path": str(real / "src" / "main.py")}, grant)
        assert not decision.allowed
        assert decision.reason == "path_not_granted"


class TestWorkDirUnderASensitiveRoot:
    """The Docker default work dir (HOME=/var/lib/koda/runtime/home) is under /var/lib, a SENSITIVE_DIRS root.

    The file tools must work there: the work dir and the paths inside it are allowed, a
    sensitive root that does not contain the work dir stays denied, and secret names stay
    blocked.
    """

    @pytest.fixture
    def docker_work(self, tmp_path, monkeypatch):
        root = tmp_path.resolve()
        sensitive = root / "var-lib"
        work = sensitive / "koda" / "runtime" / "home"
        (work / "src" / "pkg").mkdir(parents=True)
        (work / "src" / "main.py").write_text("TOKEN = 'top-level'\n")
        (work / "src" / "pkg" / "mod.py").write_text("TOKEN = 'nested'\n")
        (work / ".env").write_text("TOKEN=canary-secret\n")
        (root / "etc").mkdir()
        (root / "etc" / "passwd").write_text("TOKEN=canary-passwd\n")
        monkeypatch.setattr("koda.utils.workdir.SENSITIVE_DIRS", frozenset({str(sensitive), str(root / "etc")}))
        monkeypatch.setattr("koda.utils.workdir.DEFAULT_WORK_DIR", str(work))
        monkeypatch.chdir(root)
        return work

    async def _execute(self, tool: str, params: dict, work):
        from koda.services.tool_dispatcher import AgentToolCall, execute_tool

        fileops_enabled = {"integration_grants": {"fileops": {"enabled": True}}}
        with (
            patch("koda.services.tool_dispatcher.AGENT_RESOURCE_ACCESS_POLICY", fileops_enabled),
            patch("koda.services.execution_policy.AGENT_TOOL_POLICY", {"allowed_tool_ids": [tool]}),
            patch("koda.services.execution_policy.FILEOPS_ENABLED", True),
            patch("koda.services.tool_dispatcher.FILEOPS_ENABLED", True),
        ):
            return await execute_tool(AgentToolCall(tool, params, ""), _make_ctx(str(work)))

    @pytest.mark.asyncio
    @pytest.mark.parametrize("path", ["src/main.py", "{work}/src/main.py"])
    async def test_file_read_works_inside_the_work_dir(self, docker_work, path):
        result = await self._execute("file_read", {"path": path.format(work=docker_work)}, docker_work)
        assert result.success, result.output
        assert "top-level" in result.output

    @pytest.mark.asyncio
    async def test_file_write_and_list_work_inside_the_work_dir(self, docker_work):
        from koda.services.tool_dispatcher import _handle_file_write

        # file_write needs a human approval through execute_tool; the handler applies the path policy.
        with patch("koda.services.tool_dispatcher.FILEOPS_ENABLED", True):
            written = await _handle_file_write(
                {"path": "notes/todo.md", "content": "ship"}, _make_ctx(str(docker_work))
            )
        assert written.success, written.output
        assert (docker_work / "notes" / "todo.md").read_text() == "ship"
        listed = await self._execute("file_list", {}, docker_work)
        assert listed.success, listed.output
        assert "src" in listed.output

    @pytest.mark.asyncio
    async def test_file_grep_descends_into_subdirectories(self, docker_work):
        result = await self._execute("file_grep", {"pattern": "TOKEN"}, docker_work)
        assert result.success, result.output
        assert "src/main.py:1: TOKEN = 'top-level'" in result.output
        assert "src/pkg/mod.py:1: TOKEN = 'nested'" in result.output
        assert "canary" not in result.output

    @pytest.mark.asyncio
    async def test_secret_files_and_other_sensitive_roots_stay_refused(self, docker_work):
        secret = await self._execute("file_read", {"path": ".env"}, docker_work)
        assert not secret.success
        assert "blocked" in secret.output
        passwd = docker_work.parents[3] / "etc" / "passwd"
        outside = await self._execute("file_read", {"path": str(passwd)}, docker_work)
        assert not outside.success
        assert "canary" not in outside.output

    @pytest.mark.asyncio
    async def test_grep_still_prunes_a_sensitive_root_inside_the_work_dir(self, docker_work, monkeypatch):
        (docker_work / "etc").mkdir()
        (docker_work / "etc" / "shadow.txt").write_text("TOKEN=canary-inner\n")
        sensitive = docker_work.parents[2]
        monkeypatch.setattr("koda.utils.workdir.SENSITIVE_DIRS", frozenset({str(sensitive), str(docker_work / "etc")}))
        result = await self._execute("file_grep", {"pattern": "TOKEN"}, docker_work)
        assert result.success, result.output
        assert "src/pkg/mod.py" in result.output
        assert "canary-inner" not in result.output
        read = await self._execute("file_read", {"path": "etc/shadow.txt"}, docker_work)
        assert not read.success
        assert "sensitive system directory" in read.output
