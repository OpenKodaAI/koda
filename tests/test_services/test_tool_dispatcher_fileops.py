"""Tests for filesystem tool handlers."""

import os
from unittest.mock import AsyncMock, patch

import pytest

from koda.services.tool_dispatcher import (
    ToolContext,
    _resolve_file_path,
)


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
