"""Security tests for setdir path restriction."""

import os
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
        context.user_data = {"work_dir": "/tmp"}
        return update, context

    @pytest.mark.asyncio
    @pytest.mark.parametrize("path", ["/etc", "/root", "/proc", "/sys", "/dev", "/boot", "/var/run", "/var/lib"])
    async def test_sensitive_dir_blocked(self, setup, path):
        update, context = setup
        context.args = [path]

        with patch("os.path.isdir", return_value=True):
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

        with patch("os.path.isdir", return_value=True):
            from koda.handlers.commands import cmd_setdir

            await cmd_setdir(update, context)

        call_args = update.message.reply_text.call_args
        assert "Access denied" in call_args[0][0]

    @pytest.mark.asyncio
    async def test_normal_dir_allowed(self, setup, tmp_path):
        update, context = setup
        projects = tmp_path / "workspace" / "projects"
        projects.mkdir(parents=True)
        context.args = [str(projects)]

        from koda.handlers.commands import cmd_setdir

        await cmd_setdir(update, context)

        assert context.user_data["work_dir"] == str(projects.resolve())

    @pytest.mark.asyncio
    async def test_symlink_to_sensitive_dir_blocked(self, setup, tmp_path):
        """Symlinks resolving to sensitive dirs should be blocked."""
        update, context = setup
        link = tmp_path / "link-to-etc"
        link.symlink_to("/etc")
        context.args = [str(link)]

        with patch("os.path.isdir", return_value=True):
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

        with patch("koda.handlers.callbacks.auth_check", return_value=True):
            from koda.handlers.callbacks import callback_setdir

            await callback_setdir(update, context)

        update.callback_query.edit_message_text.assert_called_once()
        call_args = update.callback_query.edit_message_text.call_args
        assert "Access denied" in call_args[0][0]


def _setdir_update_and_context():
    update = MagicMock()
    update.effective_user = MagicMock()
    update.effective_user.id = 111
    update.message = AsyncMock()
    update.message.reply_text = AsyncMock()
    update.callback_query = MagicMock()
    update.callback_query.answer = AsyncMock()
    update.callback_query.edit_message_text = AsyncMock()
    context = MagicMock()
    context.user_data = {"work_dir": "/tmp"}
    return update, context


_VAR_RUN_IS_RUN = os.path.realpath("/var/run") == "/run" and os.path.isdir("/run")


class TestSetdirUsesTheSharedWorkDirCheck:
    """/setdir and its buttons refuse what agent_set_workdir and the file tools refuse.

    A sensitive directory is matched in its resolved form too: /var/run is /run on most
    Linux hosts, so /setdir must not accept /run as a work dir.
    """

    @pytest.fixture
    def aliased_sensitive_dir(self, tmp_path, monkeypatch):
        real = tmp_path / "real-run"
        (real / "app").mkdir(parents=True)
        alias = tmp_path / "var-run"
        alias.symlink_to(real)
        monkeypatch.setattr("koda.utils.workdir.SENSITIVE_DIRS", frozenset({str(alias)}))
        return real / "app"

    @pytest.mark.asyncio
    async def test_cmd_setdir_refuses_resolved_form_of_sensitive_dir(self, aliased_sensitive_dir):
        from koda.handlers.commands import cmd_setdir
        from koda.utils.workdir import validate_work_dir

        update, context = _setdir_update_and_context()
        context.args = [str(aliased_sensitive_dir)]
        with patch("koda.handlers.commands.auth_check", return_value=True):
            await cmd_setdir(update, context)

        assert validate_work_dir(str(aliased_sensitive_dir)).blocked
        assert "Access denied" in update.message.reply_text.call_args[0][0]
        assert context.user_data["work_dir"] == "/tmp"

    @pytest.mark.asyncio
    async def test_callback_setdir_refuses_resolved_form_of_sensitive_dir(self, aliased_sensitive_dir):
        from koda.handlers.callbacks import callback_setdir

        update, context = _setdir_update_and_context()
        update.callback_query.data = f"setdir:{aliased_sensitive_dir}"
        with patch("koda.handlers.callbacks.auth_check", return_value=True):
            await callback_setdir(update, context)

        assert "Access denied" in update.callback_query.edit_message_text.call_args[0][0]
        assert context.user_data["work_dir"] == "/tmp"

    @pytest.mark.asyncio
    @pytest.mark.skipif(not _VAR_RUN_IS_RUN, reason="needs a host where /var/run resolves to /run")
    async def test_cmd_setdir_refuses_run_on_hosts_where_var_run_is_run(self):
        from koda.handlers.commands import cmd_setdir

        update, context = _setdir_update_and_context()
        context.args = ["/run"]
        with patch("koda.handlers.commands.auth_check", return_value=True):
            await cmd_setdir(update, context)

        assert "Access denied" in update.message.reply_text.call_args[0][0]
        assert context.user_data["work_dir"] == "/tmp"

    @pytest.mark.asyncio
    @pytest.mark.skipif(not _VAR_RUN_IS_RUN, reason="needs a host where /var/run resolves to /run")
    async def test_callback_setdir_refuses_run_on_hosts_where_var_run_is_run(self):
        from koda.handlers.callbacks import callback_setdir

        update, context = _setdir_update_and_context()
        update.callback_query.data = "setdir:/run"
        with patch("koda.handlers.callbacks.auth_check", return_value=True):
            await callback_setdir(update, context)

        assert "Access denied" in update.callback_query.edit_message_text.call_args[0][0]
        assert context.user_data["work_dir"] == "/tmp"

    @pytest.mark.asyncio
    async def test_callback_setdir_stores_the_resolved_directory(self, tmp_path):
        from koda.handlers.callbacks import callback_setdir

        real = tmp_path / "project"
        real.mkdir()
        link = tmp_path / "project-link"
        link.symlink_to(real)
        update, context = _setdir_update_and_context()
        update.callback_query.data = f"setdir:{link}"
        with patch("koda.handlers.callbacks.auth_check", return_value=True):
            await callback_setdir(update, context)

        assert context.user_data["work_dir"] == str(real.resolve())
        assert "Working directory set" in update.callback_query.edit_message_text.call_args[0][0]

    @pytest.mark.asyncio
    async def test_callback_setdir_with_empty_path_does_not_fall_back_to_default(self):
        from koda.handlers.callbacks import callback_setdir

        update, context = _setdir_update_and_context()
        update.callback_query.data = "setdir:"
        with patch("koda.handlers.callbacks.auth_check", return_value=True):
            await callback_setdir(update, context)

        assert "Directory not found" in update.callback_query.edit_message_text.call_args[0][0]
        assert context.user_data["work_dir"] == "/tmp"
