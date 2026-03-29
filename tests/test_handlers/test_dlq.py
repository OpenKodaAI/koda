"""Tests for /dlq command handler."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


@pytest.fixture
def mock_update():
    update = MagicMock()
    update.effective_user = MagicMock()
    update.effective_user.id = 111
    update.message = AsyncMock()
    update.message.reply_text = AsyncMock()
    return update


@pytest.fixture
def mock_context():
    context = MagicMock()
    context.args = []
    context.bot = AsyncMock()
    context.user_data = {}
    return context


class TestCmdDlq:
    @pytest.mark.asyncio
    async def test_dlq_list_empty(self, mock_update, mock_context):
        with (
            patch("koda.handlers.commands.auth_check", return_value=True),
            patch("koda.handlers.commands.dlq_list", return_value=[]),
        ):
            from koda.handlers.commands import cmd_dlq

            await cmd_dlq(mock_update, mock_context)
            mock_update.message.reply_text.assert_called_once_with("Dead letter queue is empty.")

    @pytest.mark.asyncio
    async def test_dlq_list_with_entries(self, mock_update, mock_context):
        entries = [
            (1, 10, 111, 111, "test query", "some error", 3, "2026-01-01T00:00:00", 1),
        ]
        with (
            patch("koda.handlers.commands.auth_check", return_value=True),
            patch("koda.handlers.commands.dlq_list", return_value=entries),
        ):
            from koda.handlers.commands import cmd_dlq

            await cmd_dlq(mock_update, mock_context)
            call_text = mock_update.message.reply_text.call_args[0][0]
            assert "Dead Letter Queue" in call_text
            assert "#1" in call_text
            assert "task #10" in call_text

    @pytest.mark.asyncio
    async def test_dlq_inspect(self, mock_update, mock_context):
        mock_context.args = ["inspect", "1"]
        entry_dict = {
            "id": 1,
            "task_id": 10,
            "user_id": 111,
            "chat_id": 111,
            "agent_id": "test",
            "pod_name": "pod-1",
            "query_text": "test query",
            "model": "sonnet",
            "error_message": "timeout",
            "error_class": "RetryableError",
            "attempt_count": 3,
            "original_created_at": "2026-01-01",
            "failed_at": "2026-01-01T01:00:00",
            "retry_eligible": 1,
            "retried_at": None,
            "metadata_json": "{}",
        }
        with (
            patch("koda.handlers.commands.auth_check", return_value=True),
            patch("koda.handlers.commands.dlq_get_dict", return_value=entry_dict),
        ):
            from koda.handlers.commands import cmd_dlq

            await cmd_dlq(mock_update, mock_context)
            call_text = mock_update.message.reply_text.call_args[0][0]
            assert "DLQ #1" in call_text
            assert "Task: #10" in call_text
            assert "sonnet" in call_text

    @pytest.mark.asyncio
    async def test_dlq_inspect_not_found(self, mock_update, mock_context):
        mock_context.args = ["inspect", "999"]
        with (
            patch("koda.handlers.commands.auth_check", return_value=True),
            patch("koda.handlers.commands.dlq_get_dict", return_value=None),
        ):
            from koda.handlers.commands import cmd_dlq

            await cmd_dlq(mock_update, mock_context)
            mock_update.message.reply_text.assert_called_once_with("DLQ entry #999 not found.")

    @pytest.mark.asyncio
    async def test_dlq_retry(self, mock_update, mock_context):
        mock_context.args = ["retry", "1"]
        entry_dict = {
            "id": 1,
            "task_id": 10,
            "user_id": 111,
            "chat_id": 111,
            "agent_id": "test",
            "pod_name": "pod-1",
            "query_text": "test query",
            "model": "sonnet",
            "error_message": "timeout",
            "error_class": "RetryableError",
            "attempt_count": 3,
            "original_created_at": "2026-01-01",
            "failed_at": "2026-01-01T01:00:00",
            "retry_eligible": 1,
            "retried_at": None,
            "metadata_json": "{}",
        }
        mock_queue = AsyncMock()
        with (
            patch("koda.handlers.commands.auth_check", return_value=True),
            patch("koda.handlers.commands.dlq_get_dict", return_value=entry_dict),
            patch("koda.handlers.commands.dlq_mark_retried", return_value=True),
            patch("koda.services.queue_manager.get_queue", return_value=mock_queue),
            patch("koda.services.queue_manager._get_worker_lock", return_value=asyncio.Lock()),
            patch("koda.services.queue_manager._queue_workers", {}),
        ):
            from koda.handlers.commands import cmd_dlq

            await cmd_dlq(mock_update, mock_context)
            call_text = mock_update.message.reply_text.call_args[0][0]
            assert "re-queued" in call_text

    @pytest.mark.asyncio
    async def test_dlq_retry_not_eligible(self, mock_update, mock_context):
        mock_context.args = ["retry", "1"]
        entry_dict = {
            "id": 1,
            "task_id": 10,
            "user_id": 111,
            "chat_id": 111,
            "agent_id": "test",
            "pod_name": "pod-1",
            "query_text": "test query",
            "model": "sonnet",
            "error_message": "timeout",
            "error_class": "RetryableError",
            "attempt_count": 3,
            "original_created_at": "2026-01-01",
            "failed_at": "2026-01-01T01:00:00",
            "retry_eligible": 0,
            "retried_at": None,
            "metadata_json": "{}",
        }
        with (
            patch("koda.handlers.commands.auth_check", return_value=True),
            patch("koda.handlers.commands.dlq_get_dict", return_value=entry_dict),
        ):
            from koda.handlers.commands import cmd_dlq

            await cmd_dlq(mock_update, mock_context)
            mock_update.message.reply_text.assert_called_once_with("DLQ #1 is not eligible for retry.")
