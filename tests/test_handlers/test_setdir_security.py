"""Security tests for setdir path restriction."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from koda.config import SENSITIVE_DIRS


class TestSensitiveDirs:
    """Test that SENSITIVE_DIRS contains expected paths."""

    def test_contains_critical_paths(self):
        for path in ["/etc", "/root", "/proc", "/sys", "/dev", "/boot"]:
            assert path in SENSITIVE_DIRS

    def test_contains_var_paths(self):
        assert "/var/run" in SENSITIVE_DIRS
        assert "/var/lib" in SENSITIVE_DIRS


class TestCmdSetdirSecurity:
    """Test cmd_setdir blocks sensitive directories."""

    @pytest.fixture
    def setup(self):
        update = MagicMock()
        update.effective_user = MagicMock()
        update.effective_user.id = 111
        update.message = AsyncMock()
        update.message.reply_text = AsyncMock()

        context = MagicMock()
        context.user_data = {"work_dir": "/tmp", "_approve_all": True}
        return update, context

    @pytest.mark.asyncio
    @pytest.mark.parametrize("path", ["/etc", "/root", "/proc", "/sys", "/dev", "/boot", "/var/run", "/var/lib"])
    async def test_sensitive_dir_blocked(self, setup, path):
        update, context = setup
        context.args = [path]

        with patch("os.path.isdir", return_value=True), patch("os.path.realpath", return_value=path):
            from koda.handlers.commands import cmd_setdir

            await cmd_setdir(update, context)

        update.message.reply_text.assert_called_once()
        call_args = update.message.reply_text.call_args
        assert "Access denied" in call_args[0][0]

    @pytest.mark.asyncio
    async def test_sensitive_subdir_blocked(self, setup):
        """Subdirectories of sensitive paths should also be blocked."""
        update, context = setup
        context.args = ["/etc/ssh"]

        with patch("os.path.isdir", return_value=True), patch("os.path.realpath", return_value="/etc/ssh"):
            from koda.handlers.commands import cmd_setdir

            await cmd_setdir(update, context)

        call_args = update.message.reply_text.call_args
        assert "Access denied" in call_args[0][0]

    @pytest.mark.asyncio
    async def test_normal_dir_allowed(self, setup):
        update, context = setup
        context.args = ["/workspace/projects"]

        with (
            patch("os.path.isdir", return_value=True),
            patch("os.path.realpath", return_value="/workspace/projects"),
            patch("os.path.expanduser", return_value="/workspace/projects"),
        ):
            from koda.handlers.commands import cmd_setdir

            await cmd_setdir(update, context)

        assert context.user_data["work_dir"] == "/workspace/projects"

    @pytest.mark.asyncio
    async def test_symlink_to_sensitive_dir_blocked(self, setup):
        """Symlinks resolving to sensitive dirs should be blocked."""
        update, context = setup
        context.args = ["/tmp/link-to-etc"]

        with (
            patch("os.path.isdir", return_value=True),
            patch("os.path.realpath", return_value="/etc"),
            patch("os.path.expanduser", return_value="/tmp/link-to-etc"),
        ):
            from koda.handlers.commands import cmd_setdir

            await cmd_setdir(update, context)

        call_args = update.message.reply_text.call_args
        assert "Access denied" in call_args[0][0]


class TestCallbackSetdirSecurity:
    """Test callback_setdir blocks sensitive directories."""

    @pytest.mark.asyncio
    async def test_sensitive_dir_blocked(self):
        update = MagicMock()
        update.callback_query = MagicMock()
        update.callback_query.answer = AsyncMock()
        update.callback_query.data = "setdir:/etc"
        update.callback_query.edit_message_text = AsyncMock()
        update.effective_user = MagicMock()
        update.effective_user.id = 111

        context = MagicMock()
        context.user_data = {"work_dir": "/tmp"}

        with (
            patch("os.path.realpath", return_value="/etc"),
            patch("koda.handlers.callbacks.auth_check", return_value=True),
        ):
            from koda.handlers.callbacks import callback_setdir

            await callback_setdir(update, context)

        update.callback_query.edit_message_text.assert_called_once()
        call_args = update.callback_query.edit_message_text.call_args
        assert "Access denied" in call_args[0][0]
