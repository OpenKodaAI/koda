"""Tests for the agent loop in queue_manager."""

import asyncio
import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from koda.knowledge.task_policy_defaults import default_execution_policy
from koda.services.queue_manager import (
    QueryContext,
    QueueItem,
    RunResult,
    _run_agent_loop,
    _send_response,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_ctx(**overrides) -> QueryContext:
    defaults = dict(
        provider="claude",
        work_dir="/tmp",
        model="claude-sonnet-4-6",
        session_id="sess-1",
        provider_session_id=None,
        system_prompt="test prompt",
        agent_mode="autonomous",
        permission_mode="bypassPermissions",
        max_turns=200,
    )
    defaults.update(overrides)
    return QueryContext(**defaults)


def _make_item(**overrides) -> QueueItem:
    defaults = dict(chat_id=111, query_text="test query")
    defaults.update(overrides)
    return QueueItem(**defaults)


def _make_result(**overrides) -> RunResult:
    defaults = dict(
        provider="claude",
        model="claude-sonnet-4-6",
        result="",
        session_id="sess-1",
        provider_session_id=None,
        cost_usd=0.01,
        error=False,
        stop_reason="end_turn",
        tool_uses=[],
        raw_output="",
    )
    defaults.update(overrides)
    return RunResult(**defaults)


def _make_context():
    context = MagicMock()
    context.user_data = {
        "work_dir": "/tmp",
        "model": "claude-sonnet-4-6",
        "session_id": "sess-1",
        "total_cost": 0.0,
        "query_count": 5,
    }
    context.bot = AsyncMock()
    context.bot.send_message = AsyncMock()
    context.bot.delete_message = AsyncMock()
    # Make send_message return a mock with message_id
    msg_mock = MagicMock()
    msg_mock.message_id = 999
    context.bot.send_message.return_value = msg_mock
    return context


def _resolved_agent_cmd_approval(decision: str = "approved_scope"):
    async def _request(*_args, **kwargs):
        from koda.utils.approval import _PENDING_AGENT_CMD_OPS

        op_id = f"op-{decision}"
        request = list(kwargs.get("requests") or [])[0]
        envelope = request["envelope"]
        approval_scope = request.get("approval_scope")
        grant_kind = "approve_scope" if decision == "approved_scope" else "approve_once"
        max_uses = int(getattr(approval_scope, "max_uses", 1) if grant_kind == "approve_scope" else 1)
        grant = {
            "grant_id": f"grant-{decision}",
            "user_id": 111,
            "agent_id": str(kwargs.get("agent_id") or "default"),
            "session_id": str(kwargs.get("session_id") or "sess-1"),
            "chat_id": int(kwargs.get("chat_id") or 111),
            "kind": grant_kind,
            "remaining_uses": max_uses,
            "max_uses": max_uses,
            "exact_fingerprint": f"{envelope.resource_scope_fingerprint}:{envelope.params_fingerprint}",
            "scope_fingerprint": envelope.resource_scope_fingerprint,
        }
        event = asyncio.Event()
        event.set()
        _PENDING_AGENT_CMD_OPS[op_id] = {
            "user_id": 111,
            "timestamp": time.time(),
            "event": event,
            "decision": decision,
            "description": "approved in test",
            "agent_id": str(kwargs.get("agent_id") or "default"),
            "requests": list(kwargs.get("requests") or []),
            "grants": [grant],
            "preview_text": str(kwargs.get("preview_text") or ""),
        }
        return op_id

    return _request


SCHEDULER_WRITE_POLICY = {
    "integration_grants": {
        "scheduler": {
            "allow_actions": ["job_*", "cron_*"],
        }
    }
}

SCHEDULER_EXECUTION_POLICY = {
    "version": 1,
    "rules": [
        {
            "id": "allow-cron-add",
            "decision": "allow",
            "selectors": {"tool_id": ["cron_add"]},
        },
        {
            "id": "allow-job-create",
            "decision": "allow",
            "selectors": {"tool_id": ["job_create"]},
        },
    ],
}


@pytest.fixture(autouse=True)
def _mock_provider_session_store():
    with (
        patch("koda.services.queue_manager.get_provider_session_mapping", return_value=None),
        patch("koda.services.queue_manager.save_provider_session_mapping"),
    ):
        yield


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestAgentLoop:
    @pytest.mark.asyncio
    async def test_no_agent_commands_passes_through(self):
        """If no <agent_cmd> tags, result passes through unchanged."""
        ctx = _make_ctx()
        item = _make_item()
        context = _make_context()
        initial = _make_result(result="Just a normal response.")

        result = await _run_agent_loop(ctx, item, 111, 111, context, initial)
        assert result.result == "Just a normal response."
        assert result.cost_usd == 0.01

    @pytest.mark.asyncio
    async def test_one_iteration(self):
        """Parse → execute → resume → final response."""
        ctx = _make_ctx()
        item = _make_item()
        context = _make_context()

        initial = _make_result(
            result='Let me check. <agent_cmd tool="cron_list">{}</agent_cmd>',
        )

        # Mock the provider resume call.
        resume_result = _make_result(
            result="You have no cron jobs.",
            cost_usd=0.02,
            session_id="sess-2",
        )

        with (
            patch(
                "koda.services.queue_manager._run_with_provider_fallback",
                new_callable=AsyncMock,
                return_value=resume_result,
            ),
            patch("koda.services.tool_dispatcher._handle_cron_list", new_callable=AsyncMock) as mock_handler,
        ):
            from koda.services.tool_dispatcher import AgentToolResult

            mock_handler.return_value = AgentToolResult(
                tool="cron_list",
                success=True,
                output="No cron jobs found.",
            )
            with patch("koda.services.tool_dispatcher._TOOL_HANDLERS", {"cron_list": mock_handler}):
                result = await _run_agent_loop(ctx, item, 111, 111, context, initial)

        assert result.result == "You have no cron jobs."
        assert result.cost_usd == pytest.approx(0.03)  # 0.01 + 0.02

    @pytest.mark.asyncio
    async def test_max_iterations(self):
        """Stops after MAX_AGENT_TOOL_ITERATIONS."""
        ctx = _make_ctx()
        item = _make_item()
        context = _make_context()

        # Each iteration returns a result with agent_cmd tags (different params to avoid cycle detection)
        call_count = 0

        async def _mock_streaming(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            return _make_result(
                result=f'<agent_cmd tool="web_search">{{"query": "iter {call_count}"}}</agent_cmd>',
                cost_usd=0.01,
                session_id="sess-1",
            )

        initial = _make_result(
            result='<agent_cmd tool="web_search">{"query": "iter 0"}</agent_cmd>',
        )

        with (
            patch("koda.services.queue_manager._run_with_provider_fallback", side_effect=_mock_streaming),
            patch("koda.services.tool_dispatcher._handle_web_search", new_callable=AsyncMock) as mock_search,
            patch("koda.services.queue_manager.MAX_AGENT_TOOL_ITERATIONS", 3),
        ):
            from koda.services.tool_dispatcher import AgentToolResult

            mock_search.return_value = AgentToolResult(
                tool="web_search",
                success=True,
                output="results",
            )
            with patch("koda.services.tool_dispatcher._TOOL_HANDLERS", {"web_search": mock_search}):
                await _run_agent_loop(ctx, item, 111, 111, context, initial)

        # Should have called streaming 3 times (max iterations)
        assert call_count == 3

    @pytest.mark.asyncio
    async def test_cycle_detection(self):
        """Stops when the same tool calls are repeated."""
        ctx = _make_ctx()
        item = _make_item()
        context = _make_context()

        # Resume always returns the same agent_cmd
        async def _mock_streaming(*args, **kwargs):
            return _make_result(
                result='<agent_cmd tool="cron_list">{}</agent_cmd>',
                cost_usd=0.01,
                session_id="sess-1",
            )

        initial = _make_result(
            result='<agent_cmd tool="cron_list">{}</agent_cmd>',
        )

        with (
            patch("koda.services.queue_manager._run_with_provider_fallback", side_effect=_mock_streaming),
            patch("koda.services.tool_dispatcher._handle_cron_list", new_callable=AsyncMock) as mock_handler,
        ):
            from koda.services.tool_dispatcher import AgentToolResult

            mock_handler.return_value = AgentToolResult(
                tool="cron_list",
                success=True,
                output="No jobs.",
            )
            with patch("koda.services.tool_dispatcher._TOOL_HANDLERS", {"cron_list": mock_handler}):
                result = await _run_agent_loop(ctx, item, 111, 111, context, initial)

        # Should stop after 2 iterations (first execution + cycle detected on second)
        # The result should be clean text (tags stripped)
        assert "<agent_cmd" not in result.result

    @pytest.mark.asyncio
    async def test_streaming_failure_returns_clean_text(self):
        """If resume streaming fails, return the clean text."""
        ctx = _make_ctx()
        item = _make_item()
        context = _make_context()

        initial = _make_result(
            result='Before <agent_cmd tool="cron_list">{}</agent_cmd> After',
        )

        with (
            patch(
                "koda.services.queue_manager._run_with_provider_fallback",
                new_callable=AsyncMock,
                return_value=None,
            ),
            patch("koda.services.tool_dispatcher._handle_cron_list", new_callable=AsyncMock) as mock_handler,
        ):
            from koda.services.tool_dispatcher import AgentToolResult

            mock_handler.return_value = AgentToolResult(
                tool="cron_list",
                success=True,
                output="No jobs.",
            )
            with patch("koda.services.tool_dispatcher._TOOL_HANDLERS", {"cron_list": mock_handler}):
                result = await _run_agent_loop(ctx, item, 111, 111, context, initial)

        assert "<agent_cmd" not in result.result
        assert "Before" in result.result
        assert "After" in result.result

    @pytest.mark.asyncio
    async def test_cost_accumulated(self):
        """Costs are properly accumulated across iterations."""
        ctx = _make_ctx()
        item = _make_item()
        context = _make_context()

        initial = _make_result(
            result='<agent_cmd tool="agent_get_status">{}</agent_cmd>',
            cost_usd=0.05,
        )

        resume_result = _make_result(
            result="Status: all good.",
            cost_usd=0.03,
            session_id="sess-2",
        )

        with (
            patch(
                "koda.services.queue_manager._run_with_provider_fallback",
                new_callable=AsyncMock,
                return_value=resume_result,
            ),
            patch("koda.services.tool_dispatcher._handle_get_status", new_callable=AsyncMock) as mock_handler,
        ):
            from koda.services.tool_dispatcher import AgentToolResult

            mock_handler.return_value = AgentToolResult(
                tool="agent_get_status",
                success=True,
                output="status info",
            )
            with patch("koda.services.tool_dispatcher._TOOL_HANDLERS", {"agent_get_status": mock_handler}):
                result = await _run_agent_loop(ctx, item, 111, 111, context, initial)

        assert result.cost_usd == pytest.approx(0.08)  # 0.05 + 0.03

    @pytest.mark.asyncio
    async def test_status_messages_cleaned_up(self):
        """Status messages sent during execution are deleted afterward."""
        ctx = _make_ctx()
        item = _make_item()
        context = _make_context()

        initial = _make_result(
            result='<agent_cmd tool="agent_get_status">{}</agent_cmd>',
        )

        resume_result = _make_result(result="Done.", cost_usd=0.01)

        with (
            patch(
                "koda.services.queue_manager._run_with_provider_fallback",
                new_callable=AsyncMock,
                return_value=resume_result,
            ),
            patch("koda.services.tool_dispatcher._handle_get_status", new_callable=AsyncMock) as mock_handler,
        ):
            from koda.services.tool_dispatcher import AgentToolResult

            mock_handler.return_value = AgentToolResult(
                tool="agent_get_status",
                success=True,
                output="info",
            )
            with patch("koda.services.tool_dispatcher._TOOL_HANDLERS", {"agent_get_status": mock_handler}):
                await _run_agent_loop(ctx, item, 111, 111, context, initial)

        # Verify status message was sent and then deleted
        context.bot.send_message.assert_called()
        context.bot.delete_message.assert_called()

    @pytest.mark.asyncio
    async def test_write_without_action_plan_is_blocked(self):
        ctx = _make_ctx(knowledge_hits=[{"source_label": "README.md", "freshness": "fresh"}])
        item = _make_item()
        context = _make_context()
        initial = _make_result(
            result='<agent_cmd tool="cron_add">{"expression": "0 3 * * *", "command": "echo hi"}</agent_cmd>',
        )
        resume_result = _make_result(result="Need more evidence before writing.", cost_usd=0.01)

        with patch(
            "koda.services.queue_manager._run_with_provider_fallback",
            new_callable=AsyncMock,
            return_value=resume_result,
        ):
            result = await _run_agent_loop(ctx, item, 111, 111, context, initial)

        assert result.result == "Need more evidence before writing."
        assert ctx.confidence_reports[-1]["blocked"] is True

    @pytest.mark.asyncio
    async def test_write_with_action_plan_and_evidence_executes(self):
        ctx = _make_ctx(knowledge_hits=[{"source_label": "README.md", "freshness": "fresh"}])
        item = _make_item()
        context = _make_context()
        initial = _make_result(
            result=(
                "<action_plan>"
                "<summary>Add the cron job</summary>"
                "<assumptions>User wants a daily backup</assumptions>"
                "<evidence>I listed current cron jobs first</evidence>"
                "<sources>README.md</sources>"
                "<risk>Wrong schedule would create noisy automation</risk>"
                "<success>The cron job is listed after creation</success>"
                "</action_plan>"
                '<agent_cmd tool="cron_list">{}</agent_cmd>'
                '<agent_cmd tool="cron_add">{"expression": "0 3 * * *", "command": "echo hi"}</agent_cmd>'
            ),
        )
        resume_result = _make_result(result="Cron created.", cost_usd=0.01)

        with (
            patch(
                "koda.services.queue_manager._run_with_provider_fallback",
                new_callable=AsyncMock,
                return_value=resume_result,
            ),
            patch("koda.services.execution_policy.AGENT_EXECUTION_POLICY", SCHEDULER_EXECUTION_POLICY),
            patch("koda.services.queue_manager.AGENT_RESOURCE_ACCESS_POLICY", SCHEDULER_WRITE_POLICY),
            patch("koda.services.execution_policy.AGENT_RESOURCE_ACCESS_POLICY", SCHEDULER_WRITE_POLICY),
            patch("koda.services.tool_dispatcher.AGENT_RESOURCE_ACCESS_POLICY", SCHEDULER_WRITE_POLICY),
            patch(
                "koda.utils.approval.request_agent_cmd_approval",
                new_callable=AsyncMock,
                side_effect=_resolved_agent_cmd_approval("approved_scope"),
            ),
            patch("koda.services.tool_dispatcher._handle_cron_list", new_callable=AsyncMock) as mock_list,
            patch("koda.services.tool_dispatcher._handle_cron_add", new_callable=AsyncMock) as mock_add,
        ):
            from koda.services.tool_dispatcher import AgentToolResult

            mock_list.return_value = AgentToolResult(tool="cron_list", success=True, output="No cron jobs found.")
            mock_add.return_value = AgentToolResult(tool="cron_add", success=True, output="Cron created.")
            with patch(
                "koda.services.tool_dispatcher._TOOL_HANDLERS",
                {"cron_list": mock_list, "cron_add": mock_add},
            ):
                result = await _run_agent_loop(ctx, item, 111, 111, context, initial)

        assert result.result == "Cron created."
        assert mock_add.await_count == 1
        assert ctx.confidence_reports[-1]["blocked"] is False

    @pytest.mark.asyncio
    async def test_browser_navigation_runs_before_screenshot_in_same_iteration(self):
        ctx = _make_ctx()
        item = _make_item()
        context = _make_context()
        initial = _make_result(
            result=(
                '<agent_cmd tool="browser_navigate">{"url": "https://example.com"}</agent_cmd>'
                '<agent_cmd tool="browser_screenshot">{}</agent_cmd>'
            ),
        )
        resume_result = _make_result(result="Browser validation complete.", cost_usd=0.01)
        call_order: list[str] = []

        async def _navigate(*args, **kwargs):
            call_order.append("navigate")
            from koda.services.tool_dispatcher import AgentToolResult

            return AgentToolResult(tool="browser_navigate", success=True, output="Navigated to Example")

        async def _screenshot(*args, **kwargs):
            call_order.append("screenshot")
            from koda.services.tool_dispatcher import AgentToolResult

            return AgentToolResult(tool="browser_screenshot", success=True, output="/tmp/runtime-browser.png")

        with (
            patch(
                "koda.services.queue_manager._run_with_provider_fallback",
                new_callable=AsyncMock,
                return_value=resume_result,
            ),
            patch(
                "koda.services.tool_dispatcher._TOOL_HANDLERS",
                {"browser_navigate": _navigate, "browser_screenshot": _screenshot},
            ),
        ):
            result = await _run_agent_loop(ctx, item, 111, 111, context, initial)

        assert result.result == "Browser validation complete."
        assert call_order == ["navigate", "screenshot"]
        assert [step["tool"] for step in result.tool_execution_trace[:2]] == ["browser_navigate", "browser_screenshot"]

    @pytest.mark.asyncio
    async def test_blocked_write_skips_following_reads_in_same_iteration(self):
        ctx = _make_ctx(knowledge_hits=[{"source_label": "README.md", "freshness": "fresh"}])
        item = _make_item()
        context = _make_context()
        initial = _make_result(
            result=(
                '<agent_cmd tool="cron_add">{"expression": "0 3 * * *", "command": "echo hi"}</agent_cmd>'
                '<agent_cmd tool="browser_screenshot">{}</agent_cmd>'
            ),
        )
        resume_result = _make_result(result="Write blocked.", cost_usd=0.01)
        mock_screenshot = AsyncMock()

        with (
            patch(
                "koda.services.queue_manager._run_with_provider_fallback",
                new_callable=AsyncMock,
                return_value=resume_result,
            ),
            patch("koda.services.tool_dispatcher._handle_browser_screenshot", mock_screenshot),
            patch(
                "koda.services.tool_dispatcher._TOOL_HANDLERS",
                {
                    "cron_add": AsyncMock(),
                    "browser_screenshot": mock_screenshot,
                },
            ),
        ):
            result = await _run_agent_loop(ctx, item, 111, 111, context, initial)

        assert result.result == "Write blocked."
        mock_screenshot.assert_not_awaited()
        assert any(
            step["tool"] == "browser_screenshot"
            and "Skipped because a previous write step was blocked or denied." in step["output"]
            for step in result.tool_execution_trace
        )

    @pytest.mark.asyncio
    async def test_scheduled_job_create_with_action_plan_and_evidence_executes(self):
        ctx = _make_ctx(knowledge_hits=[{"source_label": "README.md", "freshness": "fresh"}])
        item = _make_item()
        context = _make_context()
        initial = _make_result(
            result=(
                "<action_plan>"
                "<summary>Create the recurring job</summary>"
                "<assumptions>User wants a recurring status check</assumptions>"
                "<evidence>I reviewed the scheduler guidance first</evidence>"
                "<sources>README.md</sources>"
                "<risk>Wrong cadence would create noisy automation</risk>"
                "<success>The job is created and validated safely</success>"
                "</action_plan>"
                '<agent_cmd tool="job_list">{}</agent_cmd>'
                '<agent_cmd tool="job_create">{"job_type": "agent_query", "trigger_type": "interval", '
                '"schedule_expr": "3600", "query": "Check deploy status"}'
                "</agent_cmd>"
            ),
        )
        resume_result = _make_result(result="Job created.", cost_usd=0.01)

        with (
            patch(
                "koda.services.queue_manager._run_with_provider_fallback",
                new_callable=AsyncMock,
                return_value=resume_result,
            ),
            patch("koda.services.execution_policy.AGENT_EXECUTION_POLICY", SCHEDULER_EXECUTION_POLICY),
            patch("koda.services.queue_manager.AGENT_RESOURCE_ACCESS_POLICY", SCHEDULER_WRITE_POLICY),
            patch("koda.services.execution_policy.AGENT_RESOURCE_ACCESS_POLICY", SCHEDULER_WRITE_POLICY),
            patch("koda.services.tool_dispatcher.AGENT_RESOURCE_ACCESS_POLICY", SCHEDULER_WRITE_POLICY),
            patch(
                "koda.utils.approval.request_agent_cmd_approval",
                new_callable=AsyncMock,
                side_effect=_resolved_agent_cmd_approval("approved_scope"),
            ),
            patch("koda.services.tool_dispatcher._handle_job_list", new_callable=AsyncMock) as mock_list,
            patch("koda.services.tool_dispatcher._handle_job_create", new_callable=AsyncMock) as mock_create,
        ):
            from koda.services.tool_dispatcher import AgentToolResult

            mock_list.return_value = AgentToolResult(tool="job_list", success=True, output="No jobs found.")
            mock_create.return_value = AgentToolResult(tool="job_create", success=True, output="Job created.")
            with patch(
                "koda.services.tool_dispatcher._TOOL_HANDLERS",
                {"job_list": mock_list, "job_create": mock_create},
            ):
                result = await _run_agent_loop(ctx, item, 111, 111, context, initial)

        assert result.result == "Job created."
        assert mock_list.await_count == 1
        assert mock_create.await_count == 1
        assert ctx.confidence_reports[-1]["blocked"] is False

    @pytest.mark.asyncio
    async def test_write_with_native_read_evidence_executes(self):
        ctx = _make_ctx(knowledge_hits=[{"source_label": "README.md", "freshness": "fresh"}])
        item = _make_item()
        context = _make_context()
        initial = _make_result(
            result=(
                "<action_plan>"
                "<summary>Add the cron job</summary>"
                "<assumptions>User wants a daily backup</assumptions>"
                "<evidence>I inspected the project docs first</evidence>"
                "<sources>README.md</sources>"
                "<risk>Wrong schedule would create noisy automation</risk>"
                "<success>The cron job is listed after creation</success>"
                "</action_plan>"
                '<agent_cmd tool="cron_add">{"expression": "0 3 * * *", "command": "echo hi"}</agent_cmd>'
            ),
            tool_uses=[{"name": "Read", "input": {"file_path": "/tmp/README.md"}}],
        )
        resume_result = _make_result(result="Cron created.", cost_usd=0.01)

        with (
            patch(
                "koda.services.queue_manager._run_with_provider_fallback",
                new_callable=AsyncMock,
                return_value=resume_result,
            ),
            patch("koda.services.execution_policy.AGENT_EXECUTION_POLICY", SCHEDULER_EXECUTION_POLICY),
            patch("koda.services.queue_manager.AGENT_RESOURCE_ACCESS_POLICY", SCHEDULER_WRITE_POLICY),
            patch("koda.services.execution_policy.AGENT_RESOURCE_ACCESS_POLICY", SCHEDULER_WRITE_POLICY),
            patch("koda.services.tool_dispatcher.AGENT_RESOURCE_ACCESS_POLICY", SCHEDULER_WRITE_POLICY),
            patch(
                "koda.utils.approval.request_agent_cmd_approval",
                new_callable=AsyncMock,
                side_effect=_resolved_agent_cmd_approval("approved_scope"),
            ),
            patch("koda.services.tool_dispatcher._handle_cron_add", new_callable=AsyncMock) as mock_add,
        ):
            from koda.services.tool_dispatcher import AgentToolResult

            mock_add.return_value = AgentToolResult(tool="cron_add", success=True, output="Cron created.")
            with patch(
                "koda.services.tool_dispatcher._TOOL_HANDLERS",
                {"cron_add": mock_add},
            ):
                result = await _run_agent_loop(ctx, item, 111, 111, context, initial)

        assert result.result == "Cron created."
        assert mock_add.await_count == 1
        assert ctx.confidence_reports[-1]["read_evidence_count"] == 1
        assert ctx.confidence_reports[-1]["blocked"] is False

    @pytest.mark.asyncio
    async def test_code_change_requires_post_write_verification_before_finalize(self):
        ctx = _make_ctx(
            task_kind="code_change",
            knowledge_hits=[
                {"source_label": "agent_a.toml", "layer": "canonical_policy", "freshness": "fresh"},
                {"source_label": "README.md", "layer": "workspace_doc", "freshness": "fresh"},
            ],
        )
        item = _make_item(query_text="Implement the code change safely")
        context = _make_context()
        initial = _make_result(
            result=(
                "<action_plan>"
                "<summary>Apply the code change</summary>"
                "<assumptions>The requested change is correct</assumptions>"
                "<evidence>I inspected the file first</evidence>"
                "<sources>README.md</sources>"
                "<risk>Could break the workflow</risk>"
                "<verification>Read the resulting file and run checks</verification>"
                "<success>The resulting state is validated</success>"
                "</action_plan>"
                '<agent_cmd tool="cron_add">{"expression": "0 3 * * *", "command": "echo hi"}</agent_cmd>'
            ),
            tool_uses=[
                {"name": "Read", "input": {"file_path": "/tmp/README.md"}},
                {"name": "Grep", "input": {"pattern": "cron", "path": "/tmp/README.md"}},
            ],
        )
        resume_after_write = _make_result(result="Write complete.", cost_usd=0.01)
        verification_turn = _make_result(result='<agent_cmd tool="cron_list">{}</agent_cmd>', cost_usd=0.01)
        final_verified = _make_result(result="Verified and complete.", cost_usd=0.01)

        with (
            patch(
                "koda.services.queue_manager._run_with_provider_fallback",
                new_callable=AsyncMock,
                side_effect=[resume_after_write, verification_turn, final_verified],
            ),
            patch("koda.services.execution_policy.AGENT_EXECUTION_POLICY", SCHEDULER_EXECUTION_POLICY),
            patch("koda.services.queue_manager.AGENT_RESOURCE_ACCESS_POLICY", SCHEDULER_WRITE_POLICY),
            patch("koda.services.execution_policy.AGENT_RESOURCE_ACCESS_POLICY", SCHEDULER_WRITE_POLICY),
            patch("koda.services.tool_dispatcher.AGENT_RESOURCE_ACCESS_POLICY", SCHEDULER_WRITE_POLICY),
            patch("koda.services.tool_dispatcher._handle_cron_add", new_callable=AsyncMock) as mock_add,
            patch("koda.services.tool_dispatcher._handle_cron_list", new_callable=AsyncMock) as mock_list,
        ):
            from koda.services.tool_dispatcher import AgentToolResult

            mock_add.return_value = AgentToolResult(tool="cron_add", success=True, output="Cron created.")
            mock_list.return_value = AgentToolResult(tool="cron_list", success=True, output="Cron exists.")
            with patch(
                "koda.services.tool_dispatcher._TOOL_HANDLERS",
                {"cron_add": mock_add, "cron_list": mock_list},
            ):
                result = await _run_agent_loop(ctx, item, 111, 111, context, initial)

        assert result.result == "Verified and complete."
        assert mock_add.await_count == 1
        assert mock_list.await_count == 1
        assert ctx.verified_before_finalize is True

    @pytest.mark.asyncio
    async def test_guarded_policy_auto_executes_without_manual_approval(self):
        ctx = _make_ctx(
            task_kind="code_change",
            knowledge_hits=[
                {"source_label": "agent_a.toml", "layer": "canonical_policy", "freshness": "fresh"},
                {"source_label": "README.md", "layer": "workspace_doc", "freshness": "fresh"},
            ],
        )
        item = _make_item(query_text="Implement a safe code change")
        context = _make_context()
        initial = _make_result(
            result=(
                "<action_plan>"
                "<summary>Apply the code change</summary>"
                "<assumptions>The requested change is correct</assumptions>"
                "<evidence>I inspected the file and docs first</evidence>"
                "<sources>README.md</sources>"
                "<risk>Could break the workflow</risk>"
                "<verification>Read the resulting file and run checks</verification>"
                "<success>The resulting state is validated</success>"
                "</action_plan>"
                '<agent_cmd tool="cron_add">{"expression": "0 3 * * *", "command": "echo hi"}</agent_cmd>'
            ),
            tool_uses=[
                {"name": "Read", "input": {"file_path": "/tmp/README.md"}},
                {"name": "Grep", "input": {"pattern": "cron", "path": "/tmp/README.md"}},
            ],
        )
        resume_result = _make_result(result="Change applied.", cost_usd=0.01)

        with (
            patch(
                "koda.services.queue_manager._run_with_provider_fallback",
                new_callable=AsyncMock,
                return_value=resume_result,
            ),
            patch("koda.services.execution_policy.AGENT_EXECUTION_POLICY", SCHEDULER_EXECUTION_POLICY),
            patch("koda.services.queue_manager.AGENT_RESOURCE_ACCESS_POLICY", SCHEDULER_WRITE_POLICY),
            patch("koda.services.execution_policy.AGENT_RESOURCE_ACCESS_POLICY", SCHEDULER_WRITE_POLICY),
            patch("koda.services.tool_dispatcher.AGENT_RESOURCE_ACCESS_POLICY", SCHEDULER_WRITE_POLICY),
            patch("koda.services.tool_dispatcher._handle_cron_add", new_callable=AsyncMock) as mock_add,
            patch(
                "koda.utils.approval.request_agent_cmd_approval",
                new_callable=AsyncMock,
                side_effect=AssertionError("guarded write should not request approval"),
            ),
        ):
            from koda.services.tool_dispatcher import AgentToolResult

            mock_add.return_value = AgentToolResult(tool="cron_add", success=True, output="Cron created.")
            with patch("koda.services.tool_dispatcher._TOOL_HANDLERS", {"cron_add": mock_add}):
                result = await _run_agent_loop(ctx, item, 111, 111, context, initial)

        assert result.result == "Change applied."
        assert mock_add.await_count == 1
        assert ctx.confidence_reports[-1]["requires_human_approval"] is False

    @pytest.mark.asyncio
    async def test_send_response_includes_operational_footer_for_writes(self):
        ctx = _make_ctx(
            task_kind="code_change",
            effective_policy=default_execution_policy("code_change"),
            knowledge_hits=[
                {
                    "source_label": "agent_a.toml",
                    "layer": "canonical_policy",
                    "freshness": "fresh",
                    "updated_at": "2026-03-18",
                },
                {
                    "source_label": "workspace:README.md",
                    "layer": "workspace_doc",
                    "freshness": "fresh",
                    "updated_at": "2026-03-18",
                },
            ],
            verified_before_finalize=True,
        )
        context = _make_context()
        run_result = _make_result(
            result="Change applied successfully.",
            tool_execution_trace=[{"metadata": {"write": True}, "success": True}],
            fallback_chain=["claude", "codex"],
        )

        await _send_response(
            111,
            None,
            context,
            run_result,
            "/tmp",
            "autonomous",
            elapsed=6.0,
            model="claude-sonnet-4-6",
            task_id=77,
            ctx=ctx,
        )

        sent_text = context.bot.send_message.call_args.kwargs["text"]
        assert "Sources: agent_a.toml (2026-03-18), workspace:README.md (2026-03-18)" in sent_text
        assert "Verification: verified" in sent_text
        assert "Tier: t2 | Mode: guarded" in sent_text
        assert "Flow: guarded, provider-fallback" in sent_text

    @pytest.mark.asyncio
    async def test_send_response_uses_agent_local_audio_defaults_for_tts(self):
        ctx = _make_ctx()
        context = _make_context()
        context.user_data.update(
            {
                "audio_response": True,
                "tts_voice": "pm_alex",
                "tts_voice_language": "pt-br",
                "audio_provider": "kokoro",
                "audio_model": "kokoro-v1",
            }
        )
        run_result = _make_result(result="Resposta curta.")

        with (
            patch("koda.services.queue_manager.TTS_ENABLED", True),
            patch("koda.utils.tts.is_mostly_code", return_value=False),
            patch("koda.utils.tts.strip_for_tts", return_value="Resposta curta"),
            patch("koda.utils.tts.synthesize_speech", new_callable=AsyncMock, return_value=None) as mock_tts,
        ):
            await _send_response(
                111,
                None,
                context,
                run_result,
                "/tmp",
                "autonomous",
                elapsed=1.0,
                model="claude-sonnet-4-6",
                task_id=77,
                ctx=ctx,
            )

        mock_tts.assert_awaited_once_with(
            "Resposta curta",
            "pm_alex",
            1.0,
            provider="kokoro",
            model="kokoro-v1",
            language="pt-br",
        )
