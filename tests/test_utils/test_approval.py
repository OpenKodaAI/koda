"""Tests for the approval system (classifier + decorator)."""

import asyncio
import time
from unittest.mock import AsyncMock, MagicMock

import pytest

from koda.utils.approval import (
    _PENDING_AGENT_CMD_OPS,
    _PENDING_OPS,
    APPROVAL_TIMEOUT,
    _execution_approved,
    cleanup_agent_cmd_op,
    dispatch_approved_operation,
    get_agent_cmd_decision,
    is_write_operation,
    request_agent_cmd_approval,
    reset_approval_state,
    resolve_agent_cmd_approval,
    with_approval,
)


@pytest.fixture(autouse=True)
def _reset_contextvar():
    """Reset the contextvar to False for approval-specific tests."""
    token = _execution_approved.set(False)
    yield
    _execution_approved.reset(token)


# ---------------------------------------------------------------------------
# TestIsWriteOperation — classifier tests
# ---------------------------------------------------------------------------


class TestIsWriteOperation:
    """Test the READ/WRITE classifier for various commands."""

    # Always WRITE
    def test_rm_is_write(self):
        assert is_write_operation("rm", "test.txt") is True

    def test_write_is_write(self):
        assert is_write_operation("write", "file.txt content") is True

    def test_edit_is_write(self):
        assert is_write_operation("edit", "file.txt more") is True

    def test_mkdir_is_write(self):
        assert is_write_operation("mkdir", "newdir") is True

    # Always READ
    def test_cat_is_read(self):
        assert is_write_operation("cat", "file.txt") is False

    def test_search_is_read(self):
        assert is_write_operation("search", "query") is False

    def test_fetch_is_read(self):
        assert is_write_operation("fetch", "https://example.com") is False

    def test_curl_is_read(self):
        assert is_write_operation("curl", "https://example.com") is False

    def test_browse_is_read(self):
        assert is_write_operation("browse", "https://example.com") is False

    def test_screenshot_is_read(self):
        assert is_write_operation("screenshot", "") is False

    # Shell
    def test_shell_ls_is_read(self):
        assert is_write_operation("shell", "ls -la") is False

    def test_shell_cat_is_read(self):
        assert is_write_operation("shell", "cat /etc/hosts") is False

    def test_shell_rm_is_write(self):
        assert is_write_operation("shell", "rm foo") is True

    def test_shell_empty_is_write(self):
        assert is_write_operation("shell", "") is True

    def test_shell_sed_is_write(self):
        assert is_write_operation("shell", "sed -i 's/foo/bar/g' file.txt") is True

    def test_shell_awk_is_write(self):
        assert is_write_operation("shell", "awk '{print}' file.txt") is True

    def test_shell_tee_is_write(self):
        assert is_write_operation("shell", "tee output.txt") is True

    # Git
    def test_git_status_is_read(self):
        assert is_write_operation("git", "status") is False

    def test_git_log_is_read(self):
        assert is_write_operation("git", "log --oneline") is False

    def test_git_diff_is_read(self):
        assert is_write_operation("git", "diff HEAD") is False

    def test_git_push_is_write(self):
        assert is_write_operation("git", "push origin main") is True

    def test_git_commit_is_write(self):
        assert is_write_operation("git", "commit -m 'msg'") is True

    def test_git_merge_is_write(self):
        assert is_write_operation("git", "merge feature") is True

    def test_git_config_is_write(self):
        assert is_write_operation("git", "config user.name 'Evil'") is True

    def test_git_branch_is_write(self):
        assert is_write_operation("git", "branch -d feature") is True

    def test_git_stash_is_write(self):
        assert is_write_operation("git", "stash") is True

    def test_git_tag_is_write(self):
        assert is_write_operation("git", "tag v1.0") is True

    # GitHub CLI
    def test_gh_pr_list_is_read(self):
        assert is_write_operation("gh", "pr list") is False

    def test_gh_pr_create_is_write(self):
        assert is_write_operation("gh", "pr create") is True

    def test_gh_issue_list_is_read(self):
        assert is_write_operation("gh", "issue list") is False

    def test_gh_api_is_write(self):
        assert is_write_operation("gh", "api --method POST /repos/owner/repo") is True

    # Docker
    def test_docker_ps_is_read(self):
        assert is_write_operation("docker", "ps") is False

    def test_docker_images_is_read(self):
        assert is_write_operation("docker", "images") is False

    def test_docker_rm_is_write(self):
        assert is_write_operation("docker", "rm container_id") is True

    def test_docker_run_is_write(self):
        assert is_write_operation("docker", "run hello-world") is True

    # Google Workspace
    def test_gws_list_is_read(self):
        assert is_write_operation("gws", "gmail users.messages.list") is False

    def test_gws_send_is_write(self):
        assert is_write_operation("gws", "gmail users.messages.send") is True

    def test_gmail_list_is_read(self):
        assert is_write_operation("gmail", "users.messages.list") is False

    # Atlassian
    def test_jira_search_is_read(self):
        assert is_write_operation("jira", "issues search") is False

    def test_jira_get_is_read(self):
        assert is_write_operation("jira", "issues get --key PROJ-1") is False

    def test_jira_comment_get_is_read(self):
        assert is_write_operation("jira", "issues comment_get --key PROJ-1 --comment-id 100") is False

    def test_jira_create_is_write(self):
        assert is_write_operation("jira", "issues create --project PROJ") is True

    def test_jira_comment_reply_is_write(self):
        assert is_write_operation("jira", "issues comment_reply --key PROJ-1 --comment-id 100 --body hi") is True

    def test_jira_comment_edit_is_write(self):
        assert is_write_operation("jira", "issues comment_edit --key PROJ-1 --comment-id 100 --body hi") is True

    def test_jira_comment_delete_is_write(self):
        assert is_write_operation("jira", "issues comment_delete --key PROJ-1 --comment-id 100") is True

    def test_confluence_get_is_read(self):
        assert is_write_operation("confluence", "pages get --id 123") is False

    # Package managers
    def test_pip_list_is_read(self):
        assert is_write_operation("pip", "list") is False

    def test_pip_install_is_write(self):
        assert is_write_operation("pip", "install requests") is True

    def test_npm_list_is_read(self):
        assert is_write_operation("npm", "list") is False

    def test_npm_install_is_write(self):
        assert is_write_operation("npm", "install lodash") is True

    # HTTP
    def test_http_get_is_read(self):
        assert is_write_operation("http", "GET https://example.com") is False

    def test_http_post_is_write(self):
        assert is_write_operation("http", "POST https://example.com") is True

    def test_http_head_is_read(self):
        assert is_write_operation("http", "HEAD https://example.com") is False

    # Cron
    def test_cron_list_is_read(self):
        assert is_write_operation("cron", "list") is False

    def test_cron_add_is_write(self):
        assert is_write_operation("cron", 'add "*/5 * * * *" echo hi') is True

    # Browser mutations
    def test_click_is_write(self):
        assert is_write_operation("click", "#btn") is True

    def test_type_is_write(self):
        assert is_write_operation("type", "#input hello") is True

    def test_js_is_write(self):
        assert is_write_operation("js", "document.title") is True

    # Unknown command → default True
    def test_unknown_command_is_write(self):
        assert is_write_operation("unknown_cmd", "anything") is True


# ---------------------------------------------------------------------------
# TestWithApprovalDecorator
# ---------------------------------------------------------------------------


class TestWithApprovalDecorator:
    """Test the @with_approval decorator behavior."""

    def _make_update_context(self, args=None):
        update = MagicMock()
        update.effective_user = MagicMock()
        update.effective_user.id = 111
        update.message = AsyncMock()
        update.message.reply_text = AsyncMock()

        context = MagicMock()
        context.user_data = {"_approve_all": False}
        context.args = args or []

        return update, context

    @pytest.mark.asyncio
    async def test_read_operation_passes_through(self):
        """READ operations should execute immediately without approval."""
        call_log = []

        async def handler(update, context):
            call_log.append((update, context))

        decorated = with_approval("cat")(handler)
        update, context = self._make_update_context(["file.txt"])

        await decorated(update, context)

        assert len(call_log) == 1
        update.message.reply_text.assert_not_called()

    @pytest.mark.asyncio
    async def test_read_sets_contextvar(self):
        """READ operations should have contextvar True during execution."""
        recorded_value = None

        async def handler(update, context):
            nonlocal recorded_value
            recorded_value = _execution_approved.get()

        decorated = with_approval("cat")(handler)
        update, context = self._make_update_context(["file.txt"])

        await decorated(update, context)

        assert recorded_value is True
        assert _execution_approved.get() is False

    @pytest.mark.asyncio
    async def test_write_without_approval_shows_keyboard(self):
        """WRITE operations without approval should show the keyboard."""
        call_log = []

        async def handler(update, context):
            call_log.append(True)

        decorated = with_approval("rm")(handler)
        update, context = self._make_update_context(["test.txt"])

        _PENDING_OPS.clear()
        result = await decorated(update, context)

        assert result is None
        assert len(call_log) == 0
        update.message.reply_text.assert_called_once()
        call_kwargs = update.message.reply_text.call_args
        assert call_kwargs.kwargs.get("reply_markup") is not None
        _PENDING_OPS.clear()

    @pytest.mark.asyncio
    async def test_write_with_approve_all_passes_through(self):
        """WRITE operations with _approve_all should execute directly."""
        call_log = []

        async def handler(update, context):
            call_log.append(True)

        decorated = with_approval("rm")(handler)
        update, context = self._make_update_context(["test.txt"])
        context.user_data["_approve_all"] = True

        await decorated(update, context)

        assert len(call_log) == 1

    @pytest.mark.asyncio
    async def test_write_with_approved_flag_passes_through(self):
        """WRITE operations with _approved flag should execute and reset the flag."""
        call_log = []

        async def handler(update, context):
            call_log.append(True)

        decorated = with_approval("rm")(handler)
        update, context = self._make_update_context(["test.txt"])
        context.user_data["_approved"] = True

        await decorated(update, context)

        assert len(call_log) == 1
        assert context.user_data["_approved"] is False

    @pytest.mark.asyncio
    async def test_contextvar_reset_after_write(self):
        """ContextVar should be False after WRITE execution completes."""
        recorded_value = None

        async def handler(update, context):
            nonlocal recorded_value
            recorded_value = _execution_approved.get()

        decorated = with_approval("rm")(handler)
        update, context = self._make_update_context(["test.txt"])
        context.user_data["_approve_all"] = True

        await decorated(update, context)

        assert recorded_value is True
        assert _execution_approved.get() is False

    @pytest.mark.asyncio
    async def test_pending_op_stored(self):
        """Pending operation should be stored when approval is needed."""

        async def handler(update, context):
            pass

        decorated = with_approval("rm")(handler)
        update, context = self._make_update_context(["test.txt"])

        _PENDING_OPS.clear()
        await decorated(update, context)

        assert len(_PENDING_OPS) == 1
        op = next(iter(_PENDING_OPS.values()))
        assert op["cmd_name"] == "rm"
        assert op["args"] == "test.txt"
        _PENDING_OPS.clear()


# ---------------------------------------------------------------------------
# TestDispatchApprovedOperation
# ---------------------------------------------------------------------------


class TestDispatchApprovedOperation:
    """Test dispatching approved operations."""

    @pytest.mark.asyncio
    async def test_dispatch_executes_handler(self):
        handler = AsyncMock()
        update = MagicMock()
        context = MagicMock()
        context.user_data = {}

        op_id = "test_op_1"
        _PENDING_OPS[op_id] = {
            "handler": handler,
            "update": update,
            "context": context,
            "args": "test.txt",
            "cmd_name": "rm",
            "timestamp": time.time(),
        }

        await dispatch_approved_operation(op_id)

        handler.assert_called_once_with(update, context)
        assert op_id not in _PENDING_OPS

    @pytest.mark.asyncio
    async def test_dispatch_invalid_op_id(self):
        """Dispatching an invalid op_id should do nothing."""
        _PENDING_OPS.clear()
        await dispatch_approved_operation("nonexistent")
        # No exception raised

    @pytest.mark.asyncio
    async def test_dispatch_resets_contextvar(self):
        recorded = None

        async def handler(update, context):
            nonlocal recorded
            recorded = _execution_approved.get()

        update = MagicMock()
        context = MagicMock()
        context.user_data = {}

        op_id = "test_op_2"
        _PENDING_OPS[op_id] = {
            "handler": handler,
            "update": update,
            "context": context,
            "args": "",
            "cmd_name": "rm",
            "timestamp": time.time(),
        }

        await dispatch_approved_operation(op_id)

        assert recorded is True
        assert _execution_approved.get() is False


# ---------------------------------------------------------------------------
# TestResetApprovalState
# ---------------------------------------------------------------------------


class TestResetApprovalState:
    def test_reset_clears_all_keys(self):
        user_data = {
            "_approve_all": True,
            "_approved": True,
            "_pending_op_id": "some_id",
            "_approve_all_agent_tools": True,
            "work_dir": "/tmp",
        }
        reset_approval_state(user_data)
        assert "_approve_all" not in user_data
        assert "_approved" not in user_data
        assert "_pending_op_id" not in user_data
        assert "_approve_all_agent_tools" not in user_data
        assert user_data["work_dir"] == "/tmp"

    def test_reset_no_keys_present(self):
        user_data = {"work_dir": "/tmp"}
        reset_approval_state(user_data)  # Should not raise
        assert user_data == {"work_dir": "/tmp"}


# ---------------------------------------------------------------------------
# TestOpIdEntropy
# ---------------------------------------------------------------------------


class TestOpIdEntropy:
    """Test that op_id uses sufficient entropy."""

    @pytest.mark.asyncio
    async def test_op_id_has_high_entropy(self):
        """op_id should use secrets.token_urlsafe(16) = 128 bits."""
        from koda.utils.approval import _show_approval_keyboard

        update = MagicMock()
        update.effective_user = MagicMock()
        update.effective_user.id = 111
        update.message = AsyncMock()
        update.message.reply_text = AsyncMock()

        context = MagicMock()
        context.user_data = {}

        _PENDING_OPS.clear()
        await _show_approval_keyboard(update, context, "rm", "test.txt", AsyncMock())

        assert len(_PENDING_OPS) == 1
        op_id = next(iter(_PENDING_OPS.keys()))
        # op_id format: {timestamp}_{user_id}_{token_urlsafe(16)}
        parts = op_id.split("_", 2)
        assert len(parts) == 3
        token_part = parts[2]
        # token_urlsafe(16) produces ~22 chars (base64url encoding of 16 bytes)
        assert len(token_part) >= 20, f"Token too short ({len(token_part)} chars): {token_part}"
        _PENDING_OPS.clear()

    @pytest.mark.asyncio
    async def test_op_ids_are_unique(self):
        """Two consecutive op_ids should differ."""
        from koda.utils.approval import _show_approval_keyboard

        update = MagicMock()
        update.effective_user = MagicMock()
        update.effective_user.id = 111
        update.message = AsyncMock()
        update.message.reply_text = AsyncMock()

        context = MagicMock()
        context.user_data = {}

        _PENDING_OPS.clear()
        await _show_approval_keyboard(update, context, "rm", "a.txt", AsyncMock())
        await _show_approval_keyboard(update, context, "rm", "b.txt", AsyncMock())

        op_ids = list(_PENDING_OPS.keys())
        assert len(op_ids) == 2
        assert op_ids[0] != op_ids[1]
        _PENDING_OPS.clear()


# ---------------------------------------------------------------------------
# TestPendingOpsLimit
# ---------------------------------------------------------------------------


class TestPendingOpsLimit:
    """Test per-user pending operations limit."""

    def test_max_constant_exists(self):
        from koda.utils.approval import MAX_PENDING_OPS_PER_USER

        assert MAX_PENDING_OPS_PER_USER == 10

    @pytest.mark.asyncio
    async def test_exceeds_limit_blocked(self):
        """Exceeding MAX_PENDING_OPS_PER_USER should block new operations."""
        from koda.utils.approval import MAX_PENDING_OPS_PER_USER, _show_approval_keyboard

        update = MagicMock()
        update.effective_user = MagicMock()
        update.effective_user.id = 111
        update.message = AsyncMock()
        update.message.reply_text = AsyncMock()

        context = MagicMock()
        context.user_data = {}

        _PENDING_OPS.clear()
        # Fill up to the limit
        for i in range(MAX_PENDING_OPS_PER_USER):
            _PENDING_OPS[f"op_{i}"] = {
                "user_id": 111,
                "timestamp": time.time(),
                "cmd_name": "rm",
                "args": f"file_{i}",
            }

        # Next one should be blocked
        await _show_approval_keyboard(update, context, "rm", "overflow.txt", AsyncMock())

        update.message.reply_text.assert_called_once()
        call_text = update.message.reply_text.call_args[0][0]
        assert "Too many" in call_text
        # Should not have added a new op
        assert len(_PENDING_OPS) == MAX_PENDING_OPS_PER_USER
        _PENDING_OPS.clear()

    @pytest.mark.asyncio
    async def test_different_user_not_blocked(self):
        """A different user's pending ops shouldn't count against you."""
        from koda.utils.approval import MAX_PENDING_OPS_PER_USER, _show_approval_keyboard

        _PENDING_OPS.clear()
        # Fill with user 222's ops
        for i in range(MAX_PENDING_OPS_PER_USER):
            _PENDING_OPS[f"op_{i}"] = {
                "user_id": 222,
                "timestamp": time.time(),
                "cmd_name": "rm",
                "args": f"file_{i}",
            }

        update = MagicMock()
        update.effective_user = MagicMock()
        update.effective_user.id = 111  # different user
        update.message = AsyncMock()
        update.message.reply_text = AsyncMock()

        context = MagicMock()
        context.user_data = {}

        await _show_approval_keyboard(update, context, "rm", "test.txt", AsyncMock())

        # User 111 should succeed (their count is 0)
        assert len(_PENDING_OPS) == MAX_PENDING_OPS_PER_USER + 1
        _PENDING_OPS.clear()


# ---------------------------------------------------------------------------
# TestEnvPrintenvClassification
# ---------------------------------------------------------------------------


class TestEnvPrintenvClassification:
    """Test that env/printenv are now classified as WRITE (not READ)."""

    def test_env_is_write(self):
        assert is_write_operation("shell", "env") is True

    def test_printenv_is_write(self):
        assert is_write_operation("shell", "printenv AGENT_TOKEN") is True

    def test_set_is_write(self):
        assert is_write_operation("shell", "set") is True


# ---------------------------------------------------------------------------
# TestAgentCmdApproval — agent-cmd approval infrastructure
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _clear_agent_cmd_ops():
    """Clear agent-cmd pending ops before and after each test."""
    _PENDING_AGENT_CMD_OPS.clear()
    yield
    _PENDING_AGENT_CMD_OPS.clear()


class TestAgentCmdApproval:
    """Test the agent-cmd approval infrastructure for agent loop tool calls."""

    @pytest.mark.asyncio
    async def test_request_returns_op_id(self):
        telegram_bot = AsyncMock()
        telegram_bot.send_message = AsyncMock()
        op_id = await request_agent_cmd_approval(telegram_bot, chat_id=111, user_id=222, description="jira transition")
        assert isinstance(op_id, str)
        assert len(op_id) > 0
        assert op_id in _PENDING_AGENT_CMD_OPS
        telegram_bot.send_message.assert_called_once()

    @pytest.mark.asyncio
    async def test_resolve_sets_event(self):
        telegram_bot = AsyncMock()
        telegram_bot.send_message = AsyncMock()
        op_id = await request_agent_cmd_approval(telegram_bot, chat_id=111, user_id=222, description="test")
        op = _PENDING_AGENT_CMD_OPS[op_id]
        assert not op["event"].is_set()

        resolve_agent_cmd_approval(op_id, "approved")

        assert op["event"].is_set()
        assert op["decision"] == "approved"

    @pytest.mark.asyncio
    async def test_get_decision_after_resolve(self):
        telegram_bot = AsyncMock()
        telegram_bot.send_message = AsyncMock()
        op_id = await request_agent_cmd_approval(telegram_bot, chat_id=111, user_id=222, description="test")

        resolve_agent_cmd_approval(op_id, "denied")

        assert get_agent_cmd_decision(op_id) == "denied"

    @pytest.mark.asyncio
    async def test_get_decision_nonexistent(self):
        assert get_agent_cmd_decision("nonexistent") is None

    @pytest.mark.asyncio
    async def test_cleanup_removes_op(self):
        telegram_bot = AsyncMock()
        telegram_bot.send_message = AsyncMock()
        op_id = await request_agent_cmd_approval(telegram_bot, chat_id=111, user_id=222, description="test")
        assert op_id in _PENDING_AGENT_CMD_OPS

        cleanup_agent_cmd_op(op_id)

        assert op_id not in _PENDING_AGENT_CMD_OPS

    @pytest.mark.asyncio
    async def test_cleanup_stale_ops(self):
        import asyncio as _asyncio

        from koda.utils.approval import _cleanup_stale_agent_cmd_ops

        event = _asyncio.Event()
        _PENDING_AGENT_CMD_OPS["stale_op"] = {
            "user_id": 111,
            "timestamp": time.time() - APPROVAL_TIMEOUT - 10,
            "event": event,
            "decision": None,
            "description": "test",
        }

        _cleanup_stale_agent_cmd_ops()

        assert "stale_op" not in _PENDING_AGENT_CMD_OPS
        assert event.is_set()  # Event should be signaled with timeout

    @pytest.mark.asyncio
    async def test_op_id_fits_callback_data(self):
        """Op ID + prefix must fit within Telegram's 64-byte callback_data limit."""
        telegram_bot = AsyncMock()
        telegram_bot.send_message = AsyncMock()
        op_id = await request_agent_cmd_approval(telegram_bot, chat_id=111, user_id=222, description="test")

        # Longest prefix: "acmd:all:" = 9 chars
        callback_data = f"acmd:all:{op_id}"
        assert len(callback_data.encode("utf-8")) <= 64


# ---------------------------------------------------------------------------
# TestPeriodicCleanup — background approval cleanup
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_periodic_cleanup_removes_stale_ops():
    """Background approval cleanup removes expired pending ops."""
    from koda.utils.approval import (
        _PENDING_AGENT_CMD_OPS,
        _PENDING_OPS,
        APPROVAL_TIMEOUT,
        _cleanup_stale_agent_cmd_ops,
        _cleanup_stale_ops,
    )

    # Add a stale op
    _PENDING_OPS["stale_test"] = {
        "user_id": 1,
        "timestamp": time.time() - APPROVAL_TIMEOUT - 10,
    }
    _PENDING_AGENT_CMD_OPS["stale_agent_test"] = {
        "user_id": 1,
        "timestamp": time.time() - APPROVAL_TIMEOUT - 10,
        "event": asyncio.Event(),
        "decision": None,
    }

    _cleanup_stale_ops()
    _cleanup_stale_agent_cmd_ops()

    assert "stale_test" not in _PENDING_OPS
    assert "stale_agent_test" not in _PENDING_AGENT_CMD_OPS
