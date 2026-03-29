"""Tests for the approval callback handler."""

import time
from unittest.mock import AsyncMock, MagicMock

import pytest

from koda.utils.approval import _PENDING_AGENT_CMD_OPS, _PENDING_OPS, APPROVAL_TIMEOUT


@pytest.fixture(autouse=True)
def clear_pending_ops():
    """Clear pending operations before each test."""
    _PENDING_OPS.clear()
    _PENDING_AGENT_CMD_OPS.clear()
    yield
    _PENDING_OPS.clear()
    _PENDING_AGENT_CMD_OPS.clear()


def _make_callback_update(data: str, user_id: int = 111):
    """Create a mock Update with a callback_query."""
    update = MagicMock()
    update.effective_user = MagicMock()
    update.effective_user.id = user_id

    query = AsyncMock()
    query.data = data
    query.answer = AsyncMock()
    query.edit_message_text = AsyncMock()
    query.message = MagicMock()
    query.message.text = "test"
    update.callback_query = query
    update.message = None

    return update


def _make_context(user_data=None):
    context = MagicMock()
    context.user_data = user_data or {}
    context.args = []
    context.bot = AsyncMock()
    return context


def _add_pending_op(op_id, handler=None, timestamp=None):
    """Helper to add a pending operation."""
    _PENDING_OPS[op_id] = {
        "handler": handler or AsyncMock(),
        "update": MagicMock(),
        "context": _make_context(),
        "args": "test.txt",
        "cmd_name": "rm",
        "timestamp": timestamp or time.time(),
    }


class TestCallbackApproval:
    """Test the callback_approval handler."""

    @pytest.mark.asyncio
    async def test_approve_one_executes_handler(self):
        from koda.handlers.callbacks import callback_approval

        handler = AsyncMock()
        op_id = "12345_111"
        pending_context = _make_context()
        _PENDING_OPS[op_id] = {
            "handler": handler,
            "update": MagicMock(),
            "context": pending_context,
            "args": "test.txt",
            "cmd_name": "rm",
            "timestamp": time.time(),
        }

        update = _make_callback_update(f"approve:one:{op_id}")
        context = _make_context()

        await callback_approval(update, context)

        handler.assert_called_once()
        assert op_id not in _PENDING_OPS

    @pytest.mark.asyncio
    async def test_approve_all_sets_flag_and_executes(self):
        from koda.handlers.callbacks import callback_approval

        handler = AsyncMock()
        op_id = "12345_111"
        pending_context = _make_context()
        _PENDING_OPS[op_id] = {
            "handler": handler,
            "update": MagicMock(),
            "context": pending_context,
            "args": "test.txt",
            "cmd_name": "rm",
            "timestamp": time.time(),
        }

        update = _make_callback_update(f"approve:all:{op_id}")
        context = _make_context()

        await callback_approval(update, context)

        handler.assert_called_once()
        assert context.user_data.get("_approve_all") is True

    @pytest.mark.asyncio
    async def test_deny_does_not_execute(self):
        from koda.handlers.callbacks import callback_approval

        handler = AsyncMock()
        op_id = "12345_111"
        _add_pending_op(op_id, handler=handler)

        update = _make_callback_update(f"approve:deny:{op_id}")
        context = _make_context()

        await callback_approval(update, context)

        handler.assert_not_called()
        assert op_id not in _PENDING_OPS
        # Check "Negado" message
        update.callback_query.edit_message_text.assert_called()
        msg = update.callback_query.edit_message_text.call_args[0][0]
        assert "Negado" in msg

    @pytest.mark.asyncio
    async def test_expired_op_shows_timeout(self):
        from koda.handlers.callbacks import callback_approval

        handler = AsyncMock()
        op_id = "12345_111"
        _add_pending_op(op_id, handler=handler, timestamp=time.time() - APPROVAL_TIMEOUT - 10)

        update = _make_callback_update(f"approve:one:{op_id}")
        context = _make_context()

        await callback_approval(update, context)

        handler.assert_not_called()
        msg = update.callback_query.edit_message_text.call_args[0][0]
        assert "expirada" in msg.lower()

    @pytest.mark.asyncio
    async def test_invalid_op_id(self):
        from koda.handlers.callbacks import callback_approval

        update = _make_callback_update("approve:one:nonexistent_op")
        context = _make_context()

        await callback_approval(update, context)

        msg = update.callback_query.edit_message_text.call_args[0][0]
        assert "expirada" in msg.lower() or "invalida" in msg.lower()

    @pytest.mark.asyncio
    async def test_unauthorized_user_rejected(self):
        from koda.handlers.callbacks import callback_approval

        op_id = "12345_111"
        _add_pending_op(op_id)

        # User 999999 is not in ALLOWED_USER_IDS
        update = _make_callback_update(f"approve:one:{op_id}", user_id=999999)
        context = _make_context()

        await callback_approval(update, context)

        # Handler should NOT have been called
        assert op_id in _PENDING_OPS  # Op still pending

    @pytest.mark.asyncio
    async def test_malformed_data_ignored(self):
        from koda.handlers.callbacks import callback_approval

        update = _make_callback_update("approve:badformat")
        context = _make_context()

        # Should not raise
        await callback_approval(update, context)


# ---------------------------------------------------------------------------
# Agent-cmd approval callback tests
# ---------------------------------------------------------------------------


def _add_agent_cmd_op(op_id, user_id=111, timestamp=None):
    """Helper to add a pending agent-cmd operation."""
    import asyncio

    event = asyncio.Event()
    _PENDING_AGENT_CMD_OPS[op_id] = {
        "user_id": user_id,
        "timestamp": timestamp or time.time(),
        "event": event,
        "decision": None,
        "description": "jira transition",
    }
    return event


class TestCallbackAgentCmdApproval:
    """Test the callback_agent_cmd_approval handler."""

    @pytest.mark.asyncio
    async def test_approve_sets_decision(self):
        from koda.handlers.callbacks import callback_agent_cmd_approval

        op_id = "test_acmd_1"
        event = _add_agent_cmd_op(op_id)

        update = _make_callback_update(f"acmd:ok:{op_id}")
        context = _make_context()

        await callback_agent_cmd_approval(update, context)

        assert event.is_set()
        assert _PENDING_AGENT_CMD_OPS[op_id]["decision"] == "approved"
        update.callback_query.edit_message_text.assert_called()
        msg = update.callback_query.edit_message_text.call_args[0][0]
        assert "Aprovado" in msg

    @pytest.mark.asyncio
    async def test_approve_all_sets_flag_and_decision(self):
        from koda.handlers.callbacks import callback_agent_cmd_approval

        op_id = "test_acmd_2"
        event = _add_agent_cmd_op(op_id)

        update = _make_callback_update(f"acmd:all:{op_id}")
        context = _make_context()

        await callback_agent_cmd_approval(update, context)

        assert event.is_set()
        assert _PENDING_AGENT_CMD_OPS[op_id]["decision"] == "approved_all"
        assert context.user_data.get("_approve_all_agent_tools") is True
        msg = update.callback_query.edit_message_text.call_args[0][0]
        assert "todos" in msg.lower()

    @pytest.mark.asyncio
    async def test_deny_sets_decision(self):
        from koda.handlers.callbacks import callback_agent_cmd_approval

        op_id = "test_acmd_3"
        event = _add_agent_cmd_op(op_id)

        update = _make_callback_update(f"acmd:no:{op_id}")
        context = _make_context()

        await callback_agent_cmd_approval(update, context)

        assert event.is_set()
        assert _PENDING_AGENT_CMD_OPS[op_id]["decision"] == "denied"
        msg = update.callback_query.edit_message_text.call_args[0][0]
        assert "Negado" in msg

    @pytest.mark.asyncio
    async def test_expired_op_shows_timeout(self):
        from koda.handlers.callbacks import callback_agent_cmd_approval

        op_id = "test_acmd_4"
        _add_agent_cmd_op(op_id, timestamp=time.time() - APPROVAL_TIMEOUT - 10)

        update = _make_callback_update(f"acmd:ok:{op_id}")
        context = _make_context()

        await callback_agent_cmd_approval(update, context)

        msg = update.callback_query.edit_message_text.call_args[0][0]
        assert "expirada" in msg.lower()

    @pytest.mark.asyncio
    async def test_invalid_op_id(self):
        from koda.handlers.callbacks import callback_agent_cmd_approval

        update = _make_callback_update("acmd:ok:nonexistent")
        context = _make_context()

        await callback_agent_cmd_approval(update, context)

        msg = update.callback_query.edit_message_text.call_args[0][0]
        assert "expirada" in msg.lower() or "invalida" in msg.lower()

    @pytest.mark.asyncio
    async def test_wrong_user_rejected(self):
        from koda.handlers.callbacks import callback_agent_cmd_approval

        op_id = "test_acmd_5"
        event = _add_agent_cmd_op(op_id, user_id=111)

        # Different user (999) tries to approve
        update = _make_callback_update(f"acmd:ok:{op_id}", user_id=999)
        context = _make_context()

        await callback_agent_cmd_approval(update, context)

        # Event should NOT be set — wrong user was rejected
        assert not event.is_set()
        assert _PENDING_AGENT_CMD_OPS[op_id]["decision"] is None

    @pytest.mark.asyncio
    async def test_malformed_data_ignored(self):
        from koda.handlers.callbacks import callback_agent_cmd_approval

        update = _make_callback_update("acmd:badformat")
        context = _make_context()

        # Should not raise
        await callback_agent_cmd_approval(update, context)
