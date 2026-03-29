"""Tests for authentication."""

from unittest.mock import AsyncMock, MagicMock

import pytest

import koda.auth as auth_module
from koda.auth import auth_check, reject_unauthorized


@pytest.fixture(autouse=True)
def _allowed_user_ids() -> None:
    auth_module.ALLOWED_USER_IDS = {111}


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
