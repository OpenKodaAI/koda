"""Tests for filesystem tool handlers."""

import os
from unittest.mock import AsyncMock, patch

import pytest

from koda.services.tool_dispatcher import (
    ToolContext,
    _validate_file_path,
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


class TestValidateFilePath:
    def test_empty_path(self):
        assert _validate_file_path("", "/tmp/work") is not None

    def test_path_within_workdir(self, tmp_path):
        assert _validate_file_path(str(tmp_path / "foo.txt"), str(tmp_path)) is None

    def test_path_outside_workdir(self, tmp_path):
        err = _validate_file_path("/etc/passwd", str(tmp_path))
        assert err is not None
        assert "outside" in err or "not allowed" in err

    def test_blocked_extension(self, tmp_path):
        err = _validate_file_path(str(tmp_path / "secrets.env"), str(tmp_path))
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
