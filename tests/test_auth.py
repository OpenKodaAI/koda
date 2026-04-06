"""Tests for authentication."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import koda.auth as auth_module
from koda.auth import auth_check, is_admin, reject_unauthorized


@pytest.fixture(autouse=True)
def _allowed_user_ids() -> None:
    auth_module.ALLOWED_USER_IDS = {111}
    auth_module.ADMIN_USER_IDS = {111}


class TestAuthCheck:
    def test_allowed_user(self):
        update = MagicMock()
        update.effective_user = MagicMock()
        update.effective_user.id = 111
        assert auth_check(update) is True

    def test_denied_user(self):
        update = MagicMock()
        update.effective_user = MagicMock()
        update.effective_user.id = 999999
        assert auth_check(update) is False

    def test_no_user(self):
        update = MagicMock()
        update.effective_user = None
        assert auth_check(update) is False

    def test_whitespace_user_id_still_checks_int(self):
        """User IDs are integers; whitespace in token is irrelevant to auth_check."""
        update = MagicMock()
        update.effective_user = MagicMock()
        update.effective_user.id = 111
        assert auth_check(update) is True

    def test_empty_allowed_set_denies_everyone(self):
        auth_module.ALLOWED_USER_IDS = set()
        update = MagicMock()
        update.effective_user = MagicMock()
        update.effective_user.id = 111
        assert auth_check(update) is False


class TestRejectUnauthorized:
    @pytest.mark.asyncio
    async def test_message_reply(self):
        update = MagicMock()
        update.message = AsyncMock()
        update.message.reply_text = AsyncMock()
        update.callback_query = None

        await reject_unauthorized(update)
        update.message.reply_text.assert_called_with("Access denied.")

    @pytest.mark.asyncio
    async def test_callback_query_reply(self):
        update = MagicMock()
        update.message = None
        update.callback_query = AsyncMock()
        update.callback_query.answer = AsyncMock()

        await reject_unauthorized(update)
        update.callback_query.answer.assert_called_with("Access denied.", show_alert=True)

    @pytest.mark.asyncio
    async def test_no_message_no_callback(self):
        """When neither message nor callback_query exists, should not raise."""
        update = MagicMock()
        update.effective_user = MagicMock()
        update.effective_user.id = 999
        update.message = None
        update.callback_query = None

        # Should complete without error
        await reject_unauthorized(update)

    @pytest.mark.asyncio
    async def test_no_effective_user(self):
        """When effective_user is None, user_id passed to audit is None."""
        update = MagicMock()
        update.effective_user = None
        update.message = AsyncMock()
        update.message.reply_text = AsyncMock()
        update.callback_query = None

        with patch("koda.services.audit.emit_security") as mock_emit:
            await reject_unauthorized(update)
            mock_emit.assert_called_once()
            call_kwargs = mock_emit.call_args
            assert call_kwargs[1]["user_id"] is None


class TestAuthFailureAuditEvent:
    """reject_unauthorized must emit a security audit event."""

    @pytest.mark.asyncio
    async def test_audit_event_emitted_on_rejection(self):
        update = MagicMock()
        update.effective_user = MagicMock()
        update.effective_user.id = 999999
        update.message = AsyncMock()
        update.message.reply_text = AsyncMock()
        update.callback_query = None

        with patch("koda.services.audit.emit_security") as mock_emit:
            await reject_unauthorized(update)
            mock_emit.assert_called_once_with("security.auth_failure", user_id=999999)

    @pytest.mark.asyncio
    async def test_audit_event_type_is_auth_failure(self):
        update = MagicMock()
        update.effective_user = MagicMock()
        update.effective_user.id = 42
        update.message = AsyncMock()
        update.message.reply_text = AsyncMock()
        update.callback_query = None

        with patch("koda.services.audit.emit_security") as mock_emit:
            await reject_unauthorized(update)
            event_type = mock_emit.call_args[0][0]
            assert event_type == "security.auth_failure"

    @pytest.mark.asyncio
    async def test_audit_event_includes_user_id(self):
        update = MagicMock()
        update.effective_user = MagicMock()
        update.effective_user.id = 777
        update.message = AsyncMock()
        update.message.reply_text = AsyncMock()
        update.callback_query = None

        with patch("koda.services.audit.emit_security") as mock_emit:
            await reject_unauthorized(update)
            assert mock_emit.call_args[1]["user_id"] == 777


class TestIsAdmin:
    def test_admin_user(self):
        assert is_admin(111) is True

    def test_non_admin_user(self):
        assert is_admin(999) is False

    def test_separate_admin_set(self):
        """When ADMIN_USER_IDS is a strict subset, non-admin allowed users are not admins."""
        auth_module.ALLOWED_USER_IDS = {111, 222}
        auth_module.ADMIN_USER_IDS = {111}
        assert is_admin(111) is True
        assert is_admin(222) is False

    def test_defaults_to_allowed_user_ids(self):
        """When ADMIN_USER_IDS mirrors ALLOWED_USER_IDS, every allowed user is admin."""
        auth_module.ALLOWED_USER_IDS = {111, 222}
        auth_module.ADMIN_USER_IDS = {111, 222}
        assert is_admin(111) is True
        assert is_admin(222) is True
        assert is_admin(333) is False
