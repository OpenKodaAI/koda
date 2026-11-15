"""D-011 characterisation: agent tools that the policy allows, run outside an approval context.

The queue worker runs ``_run_agent_loop`` without setting the ``_execution_approved``
contextvar, which only ``with_approval`` and scheduled jobs set. ``shell_execute`` and the
``git_*`` tools refuse to run without it, and so does a write in supervised mode, even when
the execution policy allows the call. Each case drives the real agent loop and the real tool
handler with the central policy gate stubbed to allow (only the provider, the runtime kernel
and the git process are faked). Without an approval context the case is a strict xfail until
D-011 is fixed (M3-E3-T1); the same case inside the opt-in ``execution_approved`` fixture
passes, which pins the contextvar as the only reason it fails.
"""

from __future__ import annotations

from collections.abc import Callable
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from koda.agent_contract import resolve_action_envelope
from koda.services.execution_policy import PolicyEvaluation
from koda.services.queue_manager import QueryContext, QueueItem, RunResult, _run_agent_loop
from koda.services.tool_dispatcher import AgentToolResult
from koda.utils.approval import check_execution_approved

D011 = "D-011: the queue worker never sets the approval contextvar, so a policy-allowed call is refused"


def _allow(tool_id: str, params: dict | None = None, **_kwargs) -> PolicyEvaluation:
    envelope, _ = resolve_action_envelope(tool_id, params or {}, None)
    return PolicyEvaluation(decision="allow", reason_code="test_allow", reason="Allowed by policy.", envelope=envelope)


def _ctx(work_dir: str, agent_mode: str) -> QueryContext:
    return QueryContext(
        provider="claude",
        work_dir=work_dir,
        model="claude-sonnet-4-6",
        session_id="sess-1",
        provider_session_id=None,
        system_prompt="test prompt",
        agent_mode=agent_mode,
        permission_mode="bypassPermissions",
        max_turns=200,
    )


def _result(text: str) -> RunResult:
    return RunResult(
        provider="claude",
        model="claude-sonnet-4-6",
        result=text,
        session_id="sess-1",
        provider_session_id=None,
        cost_usd=0.01,
        error=False,
        stop_reason="end_turn",
        tool_uses=[],
        raw_output="",
    )


async def _run_tool(tool_call: str, work_dir: str, *, agent_mode: str = "autonomous") -> dict:
    """Run one agent-loop iteration whose call the policy allows; return that call's trace step."""
    context = MagicMock()
    context.user_data = {"work_dir": work_dir, "model": "claude-sonnet-4-6", "session_id": "sess-1"}
    context.bot = AsyncMock()
    context.bot.send_message.return_value = MagicMock(message_id=999)
    with (
        patch("koda.services.queue_manager.get_provider_session_mapping", return_value=None),
        patch("koda.services.queue_manager.save_provider_session_mapping"),
        patch(
            "koda.services.queue_manager._run_with_provider_fallback",
            new_callable=AsyncMock,
            return_value=_result("Done."),
        ),
        patch("koda.services.execution_policy.evaluate_execution_policy", side_effect=_allow),
        patch(
            "koda.utils.approval.request_agent_cmd_approval",
            new_callable=AsyncMock,
            side_effect=AssertionError("a policy-allowed call must not ask for approval"),
        ),
    ):
        result = await _run_agent_loop(
            _ctx(work_dir, agent_mode),
            QueueItem(chat_id=111, query_text="run it"),
            111,
            111,
            context,
            _result(tool_call),
        )
    [step] = result.tool_execution_trace
    return step


async def _shell_execute(work_dir: str) -> None:
    kernel = AsyncMock(return_value={"forwarded": True, "stdout": "hi\n", "stderr": "", "exit_code": 0})
    with (
        patch("koda.services.tool_dispatcher.SHELL_ENABLED", True),
        patch("koda.services.shell_runner.execute_in_runtime_kernel", kernel),
    ):
        step = await _run_tool('<agent_cmd tool="shell_execute">{"command": "echo hi"}</agent_cmd>', work_dir)
    assert (step["tool"], step["success"], step["output"]) == ("shell_execute", True, "Exit 0:\nhi")
    kernel.assert_awaited_once()


async def _git_status(work_dir: str) -> None:
    process = SimpleNamespace(returncode=0, communicate=AsyncMock(return_value=(b"nothing to commit\n", b"")))
    spawn = AsyncMock(return_value=process)
    with (
        patch("koda.services.tool_dispatcher.GIT_ENABLED", True),
        patch("koda.services.cli_runner.asyncio.create_subprocess_exec", spawn),
    ):
        step = await _run_tool('<agent_cmd tool="git_status">{}</agent_cmd>', work_dir)
    assert (step["tool"], step["success"], step["output"]) == ("git_status", True, "Exit 0:\nnothing to commit")
    assert spawn.await_args.args[:2] == ("git", "status")


async def _supervised_write(work_dir: str) -> None:
    handler = AsyncMock(return_value=AgentToolResult(tool="job_create", success=True, output="Job created."))
    with patch("koda.services.tool_dispatcher._TOOL_HANDLERS", {"job_create": handler}):
        step = await _run_tool(
            '<agent_cmd tool="job_create">{"expression": "0 3 * * *", "command": "echo hi"}</agent_cmd>',
            work_dir,
            agent_mode="supervised",
        )
    assert (step["tool"], step["success"], step["output"]) == ("job_create", True, "Job created.")
    handler.assert_awaited_once()


_CASES: dict[str, Callable] = {
    "shell_execute": _shell_execute,
    "git_status": _git_status,
    "supervised_write": _supervised_write,
}


@pytest.mark.xfail(strict=True, raises=AssertionError, reason=D011)
@pytest.mark.parametrize("case", sorted(_CASES))
async def test_policy_allowed_call_runs_without_approval_context(case: str, tmp_path) -> None:
    if check_execution_approved():
        pytest.fail("an approval context is set for every test, which hides D-011 (TD-041)")
    await _CASES[case](str(tmp_path))


@pytest.mark.parametrize("case", sorted(_CASES))
async def test_policy_allowed_call_runs_inside_approval_context(case: str, tmp_path, execution_approved) -> None:
    assert check_execution_approved() is True
    await _CASES[case](str(tmp_path))
