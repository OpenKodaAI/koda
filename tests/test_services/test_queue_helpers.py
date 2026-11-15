"""Tests for queue_manager helper functions."""

import asyncio
import contextlib
import re
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from telegram.error import TimedOut

from koda.config import DEFAULT_SYSTEM_PROMPT, IMAGE_TEMP_DIR, VOICE_ACTIVE_PROMPT
from koda.knowledge.task_policy_defaults import default_execution_policy
from koda.knowledge.types import KnowledgeLayer
from koda.services.provider_runtime import ProviderCapabilities
from koda.services.queue_manager import (
    BudgetExceeded,
    QueryContext,
    QueueItem,
    RunResult,
    TaskInfo,
    _agent_turn_input_audit_payload,
    _agent_turn_output_audit_payload,
    _apply_policy_overrides,
    _compact_tool_label,
    _control_plane_prompt_for_agent,
    _detect_audio_response_request,
    _get_throttle_interval,
    _grounding_gate_skip_reason,
    _maybe_enqueue_squad_coordinator_synthesis,
    _maybe_enqueue_squad_reply_synthesis,
    _maybe_enqueue_unblocked_squad_tasks,
    _native_tool_schemas_for_runtime,
    _parse_queue_item,
    _post_process,
    _prepare_query_context,
    _process_queue,
    _recover_provider_error_with_completed_output,
    _requires_kernel_terminal,
    _resolve_provider_context,
    _run_agent_loop,
    _run_fallback,
    _run_result_has_native_tool_calls,
    _run_streaming,
    _run_with_provider_fallback,
    _select_policy_runbook,
    _should_switch_provider,
    _squad_coordination_integrity_override,
    enqueue,
    enqueue_dashboard_chat_task,
    start_child_run_task,
)
from koda.utils.progress import _format_elapsed


class TestFormatElapsed:
    def test_seconds(self):
        assert _format_elapsed(0) == "0s"
        assert _format_elapsed(30) == "30s"
        assert _format_elapsed(59) == "59s"

    def test_minutes(self):
        assert _format_elapsed(60) == "1m"
        assert _format_elapsed(135) == "2m15s"
        assert _format_elapsed(3599) == "59m59s"

    def test_hours(self):
        assert _format_elapsed(3600) == "1h"
        assert _format_elapsed(3900) == "1h5m"
        assert _format_elapsed(7320) == "2h2m"


class TestCompactToolLabel:
    def test_read(self):
        assert _compact_tool_label("Read", {"file_path": "/workspace/main.py"}) == "Read(main.py)"

    def test_bash(self):
        assert _compact_tool_label("Bash", {"command": "npm test"}) == "Bash(execucao)"

    def test_bash_long(self):
        long_cmd = "npm run build -- --mode production --watch"
        label = _compact_tool_label("Bash", {"command": long_cmd})
        assert label == "Bash(execucao)"

    def test_grep(self):
        assert _compact_tool_label("Grep", {"pattern": "TODO"}) == "Grep(busca)"

    def test_generic_with_input(self):
        label = _compact_tool_label("Edit", {"file_path": "/a/b/c.py", "old_string": "foo"})
        # Should use first string value
        assert label.startswith("Edit(")

    def test_no_input(self):
        assert _compact_tool_label("Read") == "Read"
        assert _compact_tool_label("Read", None) == "Read"
        assert _compact_tool_label("Read", {}) == "Read"


def test_control_plane_prompt_for_agent_reads_documents_without_agent_spec_validation() -> None:
    manager = MagicMock()

    def _doc(_agent_id: str, kind: str) -> dict[str, str]:
        if kind == "identity_md":
            return {"content_md": "I am the Frontend specialist."}
        if kind == "instructions_md":
            return {"content_md": "Own React UI implementation."}
        return {"content_md": ""}

    manager.get_document.side_effect = _doc
    with patch("koda.control_plane.manager.get_control_plane_manager", return_value=manager):
        prompt = _control_plane_prompt_for_agent("FE")

    assert prompt is not None
    assert "Frontend specialist" in prompt
    assert "React UI implementation" in prompt
    assert not manager.method_calls or all(call[0] == "get_document" for call in manager.method_calls)


class TestRecoverProviderErrorWithCompletedOutput:
    def test_recovers_completed_artifact_response(self) -> None:
        run_result = RunResult(
            provider="codex",
            model="gpt-5.4-mini",
            result=(
                "Fechei em sequência, como você pediu: o planejador travou o briefing "
                "e o desenvolvedor já entregou a LP.\n\n"
                "**Artefato**\n"
                "- [fintech_landing_page.html](runtime_home/fintech_landing_page.html)\n\n"
                "**O que ficou pronto**\n"
                "- Landing page única, autocontida e responsiva."
            ),
            session_id="session-1",
            provider_session_id="provider-session-1",
            cost_usd=0.01,
            error=True,
            stop_reason="error",
            error_kind="provider_runtime",
        )

        assert _recover_provider_error_with_completed_output(run_result) is True
        assert run_result.error is False
        assert run_result.retryable is False
        assert run_result.error_kind == ""
        assert run_result.stop_reason == "completed_with_provider_warning"
        assert any("completed response" in warning for warning in run_result.warnings)

    def test_keeps_auth_failure_as_error(self) -> None:
        run_result = RunResult(
            provider="codex",
            model="gpt-5.4-mini",
            result="Codex authentication failed. Reauthenticate the Codex CLI and try again.",
            session_id="session-1",
            provider_session_id=None,
            cost_usd=0.0,
            error=True,
            stop_reason="error",
            error_kind="provider_auth",
        )

        assert _recover_provider_error_with_completed_output(run_result) is False
        assert run_result.error is True
        assert run_result.error_kind == "provider_auth"

    def test_keeps_retryable_text_as_error(self) -> None:
        run_result = RunResult(
            provider="codex",
            model="gpt-5.4-mini",
            result="Error: rate limit exceeded. Please retry later.",
            session_id="session-1",
            provider_session_id=None,
            cost_usd=0.0,
            error=True,
            stop_reason="error",
            error_kind="provider_runtime",
        )

        assert _recover_provider_error_with_completed_output(run_result) is False
        assert run_result.error is True


class TestPhase1NativeToolHelpers:
    def test_detects_native_openai_tool_calls(self):
        run_result = RunResult(
            provider="mistral",
            model="mistral-large-latest",
            result="",
            session_id="s",
            provider_session_id=None,
            cost_usd=0.0,
            error=False,
            stop_reason="tool_calls",
            tool_uses=[
                {
                    "source": "openai_compatible_tool_call",
                    "id": "call_1",
                    "name": "web_search",
                    "arguments": {"query": "koda"},
                }
            ],
        )

        assert _run_result_has_native_tool_calls(run_result) is True

    def test_runtime_native_schemas_come_from_tool_registry(self, monkeypatch):
        import koda.config as config_module

        monkeypatch.setattr(config_module, "FILEOPS_ENABLED", True)
        monkeypatch.setattr(config_module, "BROWSER_FEATURES_ENABLED", False)
        monkeypatch.setattr(config_module, "BROWSER_NETWORK_INTERCEPTION_ENABLED", False)
        monkeypatch.setattr(config_module, "BROWSER_SESSION_PERSISTENCE_ENABLED", False)
        monkeypatch.setattr(config_module, "SHELL_ENABLED", False)
        monkeypatch.setattr(config_module, "GIT_ENABLED", False)
        monkeypatch.setattr(config_module, "PLUGIN_SYSTEM_ENABLED", False)
        monkeypatch.setattr(config_module, "WORKFLOW_ENABLED", False)
        monkeypatch.setattr(config_module, "INTER_AGENT_ENABLED", False)
        monkeypatch.setattr(config_module, "SNAPSHOT_ENABLED", False)

        schemas = _native_tool_schemas_for_runtime()
        schema_by_name = {item["function"]["name"]: item for item in schemas}

        assert "web_search" in schema_by_name
        assert schema_by_name["web_search"]["function"]["parameters"]["required"] == ["query"]
        assert schema_by_name["file_write"]["function"]["parameters"]["required"] == ["path", "content"]

    def test_agent_turn_audit_payloads_redact_large_text_to_hashes(self):
        ctx = QueryContext(
            provider="mistral",
            work_dir="/tmp",
            model="mistral-large-latest",
            session_id="session-1",
            provider_session_id=None,
            system_prompt="secret prompt",
            agent_mode="autonomous",
            permission_mode="guarded",
            max_turns=1,
        )
        result = RunResult(
            provider="mistral",
            model="mistral-large-latest",
            result="done",
            session_id="session-1",
            provider_session_id=None,
            cost_usd=0.0,
            error=False,
            stop_reason="completed",
        )

        input_payload = _agent_turn_input_audit_payload(ctx)
        output_payload = _agent_turn_output_audit_payload(result)

        assert input_payload["contract_version"] == "agent_turn.v1"
        assert "compiled_prompt" not in input_payload
        assert input_payload["compiled_prompt_chars"] == len("secret prompt")
        assert output_payload["contract_version"] == "agent_turn.v1"
        assert "result" not in output_payload
        assert output_payload["result_chars"] == len("done")


class TestSquadCoordinationIntegrity:
    @pytest.mark.asyncio
    async def test_repairs_coordinator_delegation_claim_without_task_evidence(self) -> None:
        ctx = QueryContext(
            provider="codex",
            work_dir="/tmp",
            model="gpt-5.4-mini",
            session_id="canon-1",
            provider_session_id=None,
            system_prompt="system",
            agent_mode="autonomous",
            permission_mode="bypassPermissions",
            max_turns=5,
            executing_agent_id="PM",
            squad_thread_id="thread-1",
            parent_message_id="msg-1",
        )
        store = AsyncMock()
        store.get_thread = AsyncMock(return_value=MagicMock(coordinator_agent_id="PM"))
        store.thread_history = AsyncMock(return_value=[{"type": "agent_text", "metadata": {}}])
        store.post_thread_message = AsyncMock(return_value=99)
        with patch("koda.squads.get_squad_thread_store", return_value=store):
            override = await _squad_coordination_integrity_override(
                ctx,
                "Chamei o planejador e o desenvolvedor já entregou a LP.",
            )
        assert override is not None
        assert "sem um rastro real" in override
        store.post_thread_message.assert_awaited_once()
        assert store.post_thread_message.await_args.kwargs["metadata"]["event_type"] == (
            "coordination_integrity_violation"
        )

    @pytest.mark.asyncio
    async def test_allows_delegation_claim_with_task_request_evidence(self) -> None:
        ctx = QueryContext(
            provider="codex",
            work_dir="/tmp",
            model="gpt-5.4-mini",
            session_id="canon-1",
            provider_session_id=None,
            system_prompt="system",
            agent_mode="autonomous",
            permission_mode="bypassPermissions",
            max_turns=5,
            executing_agent_id="PM",
            squad_thread_id="thread-1",
            parent_message_id="msg-1",
        )
        store = AsyncMock()
        store.get_thread = AsyncMock(return_value=MagicMock(coordinator_agent_id="PM"))
        store.thread_history = AsyncMock(
            return_value=[{"type": "task_request", "metadata": {"parent_message_id": "msg-1"}}]
        )
        store.post_thread_message = AsyncMock(return_value=99)
        with patch("koda.squads.get_squad_thread_store", return_value=store):
            override = await _squad_coordination_integrity_override(
                ctx,
                "Chamei o planejador e o desenvolvedor já entregou a LP.",
            )
        assert override is None
        store.post_thread_message.assert_not_called()


def _squad_task_descriptor(
    task_id: str,
    *,
    agent_id: str,
    kind: str,
    status: str = "pending",
    depends_on: list[str] | None = None,
) -> object:
    from koda.squads.tasks import TaskDescriptor

    return TaskDescriptor(
        id=task_id,
        thread_id="thread-1",
        parent_task_id=None,
        depends_on=list(depends_on or []),
        assigned_agent_id=agent_id,
        assigner_agent_id="PM",
        kind=kind,
        title=f"{kind} task",
        description=f"Do {kind}",
        status=status,
        acceptance_criteria=["done"],
        deliverables_spec=["result"],
        delivered_artifact_ids=[],
        claim_token=None,
        claim_expires_at=None,
        delegation_depth=0,
        idempotency_key=None,
        cost_usd_so_far=Decimal(0),
        runtime_task_id=None,
        version=1,
        metadata={"coordination_parent_message_id": "msg-1"},
    )


class TestSquadTaskDependencyDispatch:
    @pytest.mark.asyncio
    async def test_enqueues_only_pending_tasks_whose_dependencies_are_done(self) -> None:
        ctx = QueryContext(
            provider="codex",
            work_dir="/tmp",
            model="gpt-5.4-mini",
            session_id="canon-1",
            provider_session_id=None,
            system_prompt="system",
            agent_mode="autonomous",
            permission_mode="bypassPermissions",
            max_turns=5,
            executing_agent_id="COPY",
            squad_thread_id="thread-1",
            squad_task_id="copy-task",
            parent_message_id="msg-1",
            telegram_message_thread_id=7,
        )
        app = MagicMock()
        bot_context = MagicMock(application=app, bot=MagicMock())
        thread = MagicMock(
            id="thread-1",
            squad_id="build",
            coordinator_agent_id="PM",
            owner_user_id=42,
            telegram_chat_id=-100,
            telegram_message_thread_id=7,
        )
        frontend = _squad_task_descriptor("frontend-task", agent_id="FE", kind="frontend", depends_on=["copy-task"])
        review = _squad_task_descriptor("review-task", agent_id="QA", kind="review", depends_on=["frontend-task"])
        claimed_frontend = _squad_task_descriptor(
            "frontend-task",
            agent_id="FE",
            kind="frontend",
            status="claimed",
            depends_on=["copy-task"],
        )
        copy_done = _squad_task_descriptor("copy-task", agent_id="COPY", kind="brief_copy", status="done")
        frontend_pending = _squad_task_descriptor(
            "frontend-task",
            agent_id="FE",
            kind="frontend",
            status="pending",
            depends_on=["copy-task"],
        )
        thread_store = AsyncMock()
        thread_store.get_thread = AsyncMock(return_value=thread)
        thread_store.post_thread_message = AsyncMock(return_value=88)
        task_store = AsyncMock()
        task_store.list_tasks = AsyncMock(return_value=[frontend, review])
        task_store.get_task = AsyncMock(side_effect=[copy_done, frontend_pending])
        task_store.claim_task = AsyncMock(return_value=claimed_frontend)
        enqueue = AsyncMock(return_value=123)

        with (
            patch("koda.squads.get_squad_thread_store", return_value=thread_store),
            patch("koda.squads.get_squad_task_store", return_value=task_store),
            patch("koda.services.queue_manager.enqueue_squad_agent_task", enqueue),
        ):
            dispatched = await _maybe_enqueue_unblocked_squad_tasks(
                user_id=42,
                context=bot_context,
                ctx=ctx,
            )

        assert dispatched == 1
        task_store.claim_task.assert_awaited_once_with(task_id="frontend-task", agent_id="FE", ttl_seconds=900)
        enqueue.assert_awaited_once()
        assert enqueue.await_args.kwargs["executing_agent_id"] == "FE"
        assert enqueue.await_args.kwargs["squad_task_id"] == "frontend-task"
        thread_store.post_thread_message.assert_awaited_once()


class TestSquadDeliverySynthesis:
    def _task_context(self) -> QueryContext:
        return QueryContext(
            provider="codex",
            work_dir="/tmp",
            model="gpt-5.4-mini",
            session_id="canon-1",
            provider_session_id=None,
            system_prompt="system",
            agent_mode="autonomous",
            permission_mode="bypassPermissions",
            max_turns=5,
            executing_agent_id="FE",
            squad_thread_id="thread-1",
            squad_task_id="frontend-task",
            parent_message_id="msg-1",
            telegram_message_thread_id=7,
        )

    @pytest.mark.asyncio
    async def test_coordinator_synthesis_waits_for_open_tasks(self) -> None:
        ctx = self._task_context()
        thread_store = AsyncMock()
        thread_store.get_thread = AsyncMock(
            return_value=MagicMock(
                squad_id="build",
                coordinator_agent_id="PM",
                owner_user_id=42,
                telegram_chat_id=None,
                telegram_message_thread_id=7,
            )
        )
        task_store = AsyncMock()
        task_store.list_tasks = AsyncMock(return_value=[_squad_task_descriptor("qa-task", agent_id="QA", kind="qa")])
        bus = MagicMock()
        bus.send = AsyncMock()

        with (
            patch("koda.squads.get_squad_thread_store", return_value=thread_store),
            patch("koda.squads.get_squad_task_store", return_value=task_store),
            patch("koda.agents.get_message_bus", return_value=bus),
            patch("koda.services.queue_manager.asyncio.sleep", new=AsyncMock()) as sleep,
        ):
            await _maybe_enqueue_squad_coordinator_synthesis(
                user_id=42,
                context=MagicMock(application=None),
                ctx=ctx,
                response_text="frontend done",
                squad_message_id="msg-2",
                artifact_ids=[],
            )

        bus.send.assert_not_awaited()
        assert sleep.await_count == 3

    @pytest.mark.asyncio
    async def test_coordinator_synthesis_rechecks_open_tasks_before_dispatch(self) -> None:
        ctx = self._task_context()
        thread_store = AsyncMock()
        thread_store.get_thread = AsyncMock(
            return_value=MagicMock(
                squad_id="build",
                coordinator_agent_id="PM",
                owner_user_id=42,
                telegram_chat_id=None,
                telegram_message_thread_id=7,
            )
        )
        thread_store.thread_history = AsyncMock(
            return_value=[
                {
                    "type": "task_result",
                    "from": "QA",
                    "content": "qa done",
                    "metadata": {"parent_message_id": "msg-1", "squad_task_id": "qa-task"},
                },
                {
                    "type": "task_result",
                    "from": "FE",
                    "content": "frontend done",
                    "metadata": {"parent_message_id": "msg-1", "squad_task_id": "frontend-task"},
                },
            ]
        )
        task_store = AsyncMock()
        task_store.list_tasks = AsyncMock(
            side_effect=[[_squad_task_descriptor("qa-task", agent_id="QA", kind="qa")], []]
        )
        bus = MagicMock()
        bus.send = AsyncMock()

        with (
            patch("koda.squads.get_squad_thread_store", return_value=thread_store),
            patch("koda.squads.get_squad_task_store", return_value=task_store),
            patch("koda.agents.get_message_bus", return_value=bus),
            patch("koda.services.queue_manager.asyncio.sleep", new=AsyncMock()) as sleep,
        ):
            await _maybe_enqueue_squad_coordinator_synthesis(
                user_id=42,
                context=MagicMock(application=None),
                ctx=ctx,
                response_text="frontend done",
                squad_message_id="msg-2",
                artifact_ids=[],
            )

        sleep.assert_awaited_once_with(0.5)
        bus.send.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_coordinator_synthesis_dispatches_after_all_tasks_close(self) -> None:
        ctx = self._task_context()
        thread_store = AsyncMock()
        thread_store.get_thread = AsyncMock(
            return_value=MagicMock(
                squad_id="build",
                coordinator_agent_id="PM",
                owner_user_id=42,
                telegram_chat_id=None,
                telegram_message_thread_id=7,
            )
        )
        thread_store.thread_history = AsyncMock(
            return_value=[
                {
                    "type": "task_result",
                    "from": "QA",
                    "content": "qa done",
                    "metadata": {"parent_message_id": "msg-1", "squad_task_id": "qa-task"},
                },
                {
                    "type": "task_result",
                    "from": "FE",
                    "content": "frontend done",
                    "metadata": {"parent_message_id": "msg-1", "squad_task_id": "frontend-task"},
                },
            ]
        )
        task_store = AsyncMock()
        task_store.list_tasks = AsyncMock(return_value=[])
        bus = MagicMock()
        bus.send = AsyncMock()

        with (
            patch("koda.squads.get_squad_thread_store", return_value=thread_store),
            patch("koda.squads.get_squad_task_store", return_value=task_store),
            patch("koda.agents.get_message_bus", return_value=bus),
        ):
            await _maybe_enqueue_squad_coordinator_synthesis(
                user_id=42,
                context=MagicMock(application=None),
                ctx=ctx,
                response_text="frontend done",
                squad_message_id="msg-2",
                artifact_ids=["artifact-1"],
            )

        bus.send.assert_awaited_once()
        payload = bus.send.await_args.kwargs
        assert payload["from_agent"] == "FE"
        assert payload["to_agent"] == "PM"
        assert "Todos os task_result abertos" in payload["content"]
        assert "QA / qa-task" in payload["content"]
        assert "FE / frontend-task" in payload["content"]
        assert "Não use apenas o último resultado" in payload["content"]
        assert "Preserve literalmente marcadores" in payload["content"]
        assert "Resultados confirmados:" in payload["content"]
        assert "- QA / qa-task: qa done" in payload["content"]
        assert "- FE / frontend-task: frontend done" in payload["content"]
        assert payload["metadata"]["kind"] == "task_result"
        assert payload["metadata"]["delivery_intent"] == "final_synthesis"
        assert payload["metadata"]["idempotency_key"] == "squad_synthesis:thread-1:msg-1:PM"
        assert payload["metadata"]["payload"]["artifact_ids"] == ["artifact-1"]

    @pytest.mark.asyncio
    async def test_coordinator_synthesis_counts_an_answered_reply_obligation_as_a_handoff_reply(self) -> None:
        ctx = self._task_context()
        thread_store = AsyncMock()
        thread_store.get_thread = AsyncMock(
            return_value=MagicMock(
                squad_id="build",
                coordinator_agent_id="PM",
                owner_user_id=42,
                telegram_chat_id=None,
                telegram_message_thread_id=7,
            )
        )
        handoff = {
            "schema_version": "handoff_event.v1",
            "handoff_id": "handoff-1",
            "status": "requested",
            "source_agent_id": "PM",
            "destination_agent_ids": ["FE", "QA"],
            "parent_message_id": "msg-1",
        }
        thread_store.thread_history = AsyncMock(
            return_value=[
                {
                    "type": "task_result",
                    "from": "FE",
                    "content": "frontend done",
                    "metadata": {"parent_message_id": "msg-1", "squad_task_id": "frontend-task"},
                },
                {"id": 2, "type": "system_event", "from": "PM", "content": "", "metadata": {"payload": handoff}},
                {
                    "id": 1,
                    "type": "user_input",
                    "from": "user:alice",
                    "content": "ship it",
                    "metadata": {},
                    # QA answered the user's message through a reply obligation instead of a task_result.
                    "reply_obligations": [{"id": 7, "status": "answered", "targetAgentId": "QA"}],
                },
            ]
        )
        task_store = AsyncMock()
        task_store.list_tasks = AsyncMock(return_value=[])
        bus = MagicMock()
        bus.send = AsyncMock()

        with (
            patch("koda.squads.get_squad_thread_store", return_value=thread_store),
            patch("koda.squads.get_squad_task_store", return_value=task_store),
            patch("koda.agents.get_message_bus", return_value=bus),
        ):
            await _maybe_enqueue_squad_coordinator_synthesis(
                user_id=42,
                context=MagicMock(application=None),
                ctx=ctx,
                response_text="frontend done",
                squad_message_id="msg-3",
                artifact_ids=[],
            )

        bus.send.assert_awaited_once()
        [handoff_post] = thread_store.post_thread_message.await_args_list
        assert handoff_post.kwargs["metadata"]["payload"]["handoff_id"] == "handoff-1"
        assert handoff_post.kwargs["metadata"]["payload"]["status"] == "returned"

    @pytest.mark.asyncio
    async def test_coordinator_synthesis_skips_existing_synthesis_request(self) -> None:
        ctx = self._task_context()
        thread_store = AsyncMock()
        thread_store.get_thread = AsyncMock(
            return_value=MagicMock(
                squad_id="build",
                coordinator_agent_id="PM",
                owner_user_id=42,
                telegram_chat_id=None,
                telegram_message_thread_id=7,
            )
        )
        thread_store.thread_history = AsyncMock(
            return_value=[
                {
                    "type": "task_result",
                    "from": "FE",
                    "content": "already queued",
                    "metadata": {"idempotency_key": "squad_synthesis:thread-1:msg-1:PM"},
                }
            ]
        )
        task_store = AsyncMock()
        task_store.list_tasks = AsyncMock(return_value=[])
        bus = MagicMock()
        bus.send = AsyncMock()

        with (
            patch("koda.squads.get_squad_thread_store", return_value=thread_store),
            patch("koda.squads.get_squad_task_store", return_value=task_store),
            patch("koda.agents.get_message_bus", return_value=bus),
        ):
            await _maybe_enqueue_squad_coordinator_synthesis(
                user_id=42,
                context=MagicMock(application=None),
                ctx=ctx,
                response_text="frontend done",
                squad_message_id="msg-2",
                artifact_ids=[],
            )

        bus.send.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_reply_synthesis_waits_for_open_reply_obligations(self) -> None:
        ctx = QueryContext(
            provider="codex",
            work_dir="/tmp",
            model="gpt-5.4-mini",
            session_id="canon-1",
            provider_session_id=None,
            system_prompt="system",
            agent_mode="autonomous",
            permission_mode="bypassPermissions",
            max_turns=5,
            executing_agent_id="FE",
            squad_thread_id="thread-1",
            delegation_request_id="reply:thread-1:10:FE",
            parent_message_id="msg-10",
        )
        thread_store = AsyncMock()
        thread_store.get_thread = AsyncMock(return_value=MagicMock(coordinator_agent_id="PM"))
        reply_service = AsyncMock()
        reply_service.list_obligations = AsyncMock(return_value=[MagicMock(status="open")])
        dispatch = AsyncMock()

        with (
            patch("koda.squads.get_squad_thread_store", return_value=thread_store),
            patch("koda.squads.get_thread_reply_service", return_value=reply_service),
            patch("koda.squads.dispatch_squad_turn", dispatch),
        ):
            await _maybe_enqueue_squad_reply_synthesis(
                user_id=42,
                context=MagicMock(application=None),
                ctx=ctx,
                response_text="reply done",
                squad_message_id="msg-11",
            )

        dispatch.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_reply_synthesis_dispatches_when_obligations_are_resolved(self) -> None:
        ctx = QueryContext(
            provider="codex",
            work_dir="/tmp",
            model="gpt-5.4-mini",
            session_id="canon-1",
            provider_session_id=None,
            system_prompt="system",
            agent_mode="autonomous",
            permission_mode="bypassPermissions",
            max_turns=5,
            executing_agent_id="FE",
            squad_thread_id="thread-1",
            delegation_request_id="reply:thread-1:10:FE",
            parent_message_id="msg-10",
        )
        thread_store = AsyncMock()
        thread_store.get_thread = AsyncMock(
            return_value=MagicMock(
                squad_id="build",
                coordinator_agent_id="PM",
                owner_user_id=42,
                telegram_chat_id=None,
                telegram_message_thread_id=7,
            )
        )
        thread_store.notify_event = AsyncMock()
        reply_service = AsyncMock()
        reply_service.list_obligations = AsyncMock(return_value=[])
        dispatch = AsyncMock(return_value=MagicMock(dispatched=True, to_dict=lambda: {"dispatched": True}))

        with (
            patch("koda.squads.get_squad_thread_store", return_value=thread_store),
            patch("koda.squads.get_thread_reply_service", return_value=reply_service),
            patch("koda.squads.dispatch_squad_turn", dispatch),
        ):
            await _maybe_enqueue_squad_reply_synthesis(
                user_id=42,
                context=MagicMock(application=None),
                ctx=ctx,
                response_text="reply done",
                squad_message_id="msg-11",
            )

        dispatch.assert_awaited_once()
        assert dispatch.await_args.kwargs["target_agent_id"] == "PM"
        assert dispatch.await_args.kwargs["parent_message_id"] == "msg-11"
        assert dispatch.await_args.kwargs["metadata"]["source"] == "reply_obligations_resolved"
        assert dispatch.await_args.kwargs["metadata"]["reply_kind"] == "synthesis_request"
        thread_store.notify_event.assert_awaited_once()


class TestAudioResponseIntent:
    def test_detects_portuguese_audio_request(self):
        assert _detect_audio_response_request("Pode me envie um audio com o resumo?")
        assert _detect_audio_response_request("responda por voz, por favor")

    def test_detects_english_audio_request(self):
        assert _detect_audio_response_request("send me a voice message with the answer")
        assert _detect_audio_response_request("reply by audio")

    def test_ignores_configuration_discussion(self):
        assert not _detect_audio_response_request("o modo de voz ainda nao funciona")


class TestGetThrottleInterval:
    def test_fast_at_start(self):
        assert _get_throttle_interval(5.0) == 1.5

    def test_medium_early(self):
        assert _get_throttle_interval(20.0) == 3.0

    def test_slow_mid(self):
        assert _get_throttle_interval(60.0) == 5.0

    def test_slowest_long(self):
        assert _get_throttle_interval(300.0) == 8.0


class TestMemoryConcurrentTimeout:
    """Test that memory timeout config exists and has a reasonable default."""

    def test_memory_recall_timeout_exists(self):
        from koda.memory.config import MEMORY_RECALL_TIMEOUT

        assert MEMORY_RECALL_TIMEOUT == 3.0

    def test_memory_recall_timeout_is_positive(self):
        from koda.memory.config import MEMORY_RECALL_TIMEOUT

        assert MEMORY_RECALL_TIMEOUT > 0

    @pytest.mark.asyncio
    async def test_prepare_query_context_cancels_timed_out_memory_task(self):
        context = MagicMock()
        context.user_data = {
            "provider": "codex",
            "work_dir": "/tmp",
            "total_cost": 0.0,
            "auto_model": False,
            "manual_models_by_provider": {
                "claude": "claude-sonnet-4-6",
                "codex": "gpt-5.4-mini",
            },
            "provider_sessions": {},
        }
        item = QueueItem(chat_id=111, query_text="hello")

        async def _slow_pre_query(*args, **kwargs):
            await asyncio.sleep(60)
            return ""

        memory_manager = MagicMock()
        memory_manager.pre_query = _slow_pre_query

        with (
            patch("koda.memory.config.MEMORY_ENABLED", True),
            patch("koda.memory.config.MEMORY_RECALL_TIMEOUT", 0.01),
            patch("koda.knowledge.config.KNOWLEDGE_ENABLED", False),
            patch("koda.services.cache_config.CACHE_ENABLED", False),
            patch("koda.services.cache_config.SCRIPT_LIBRARY_ENABLED", False),
            patch("koda.memory.get_memory_manager", return_value=memory_manager),
            patch("koda.services.queue_manager.get_provider_session_mapping", return_value=None),
            patch("koda.services.queue_manager.save_session"),
            patch("koda.services.queue_manager.resolve_provider_model", return_value="gpt-5.4-mini"),
            patch("koda.services.queue_manager._cancel_pending_task", new_callable=AsyncMock) as mock_cancel,
        ):
            query_context = await _prepare_query_context(context, item, user_id=111)

        assert "memory timeout" in query_context.warnings
        mock_cancel.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_prepare_query_context_appends_active_voice_state_from_policy(self):
        context = MagicMock()
        context.user_data = {
            "provider": "codex",
            "work_dir": "/tmp",
            "total_cost": 0.0,
            "auto_model": False,
            "manual_models_by_provider": {
                "claude": "claude-sonnet-4-6",
                "codex": "gpt-5.4-mini",
            },
            "provider_sessions": {},
            "audio_response": False,
            "tts_enabled": False,
            "voice_policy_active": True,
            "voice_policy_mode": "voice_active",
        }
        item = QueueItem(chat_id=111, query_text="hello")

        with (
            patch("koda.memory.config.MEMORY_ENABLED", False),
            patch("koda.knowledge.config.KNOWLEDGE_ENABLED", False),
            patch("koda.services.cache_config.CACHE_ENABLED", False),
            patch("koda.services.cache_config.SCRIPT_LIBRARY_ENABLED", False),
            patch("koda.services.queue_manager.get_provider_session_mapping", return_value=None),
            patch("koda.services.queue_manager.save_session"),
            patch("koda.services.queue_manager.resolve_provider_model", return_value="gpt-5.4-mini"),
        ):
            query_context = await _prepare_query_context(context, item, user_id=111)

        assert "Voice delivery is ACTIVE for this response" in query_context.system_prompt
        assert "continuous_voice_mode=active" in query_context.system_prompt
        assert "Do not say voice mode, TTS, or audio is disabled" in query_context.system_prompt


class TestRuntimeTerminalCutover:
    @pytest.mark.asyncio
    async def test_run_streaming_uses_kernel_stream_terminal_path_for_runtime_env(self):
        ctx = QueryContext(
            provider="codex",
            work_dir="/tmp",
            model="gpt-5.4-mini",
            session_id="canon-1",
            provider_session_id=None,
            system_prompt="system",
            agent_mode="autonomous",
            permission_mode="bypassPermissions",
            max_turns=5,
            runtime_env_id=7,
        )
        item = QueueItem(chat_id=111, query_text="hello")
        context = MagicMock()
        context.bot = AsyncMock()
        context.bot.send_message = AsyncMock()
        runtime = MagicMock()
        runtime.runtime_root = Path("/tmp/runtime")
        runtime.register_terminal = AsyncMock(return_value=17)
        runtime.cooperate_pause = AsyncMock()

        async def _fake_stream(*args, **kwargs):
            metadata = kwargs["metadata_collector"]
            metadata["stop_reason"] = "completed"
            yield "done"

        with (
            patch("koda.services.runtime.get_runtime_controller", return_value=runtime),
            patch("koda.services.queue_manager.RUNTIME_ENVIRONMENTS_ENABLED", True),
            patch("koda.services.queue_manager.run_llm_streaming", side_effect=_fake_stream),
            patch("koda.services.queue_manager._send_typing", new_callable=AsyncMock),
        ):
            result = await _run_streaming(ctx, item, 111, 111, context, task_id=7)

        assert result is not None
        assert result.runtime_terminal_id == 17
        assert result.runtime_terminal_path == "kernel-stream://stdout"
        runtime.register_terminal.assert_awaited_once()
        assert runtime.register_terminal.await_args.kwargs["path"] == "kernel-stream://stdout"
        assert runtime.register_terminal.await_args.kwargs["stream_path"] == "kernel-stream://stdout"

    @pytest.mark.parametrize(
        ("knowledge_enabled", "resolution", "reason"),
        [
            (False, None, "knowledge_disabled"),
            (True, SimpleNamespace(corpus_empty=True), "knowledge_corpus_empty"),
            (True, SimpleNamespace(corpus_empty=False), ""),
            # Knowledge on but no resolution (recall failed or timed out): the gate still judges.
            (True, None, ""),
        ],
    )
    def test_grounding_gate_is_skipped_without_knowledge_or_corpus(self, knowledge_enabled, resolution, reason):
        # M6-E1-T5 (F-MEM-28): with no knowledge to cite, the gate would send every write to review.
        with patch("koda.knowledge.config.KNOWLEDGE_ENABLED", knowledge_enabled):
            assert _grounding_gate_skip_reason(resolution) == reason

    @pytest.mark.parametrize(
        ("enabled", "runtime_env_id", "stop_reason", "required"),
        [
            (True, 7, "completed", True),
            (True, None, "completed", False),
            (True, 7, "cache_hit", False),
            (True, None, "cache_hit", False),
            (False, 7, "completed", False),
        ],
    )
    def test_kernel_terminal_is_required_only_for_a_provider_run_in_a_runtime_env(
        self, enabled, runtime_env_id, stop_reason, required
    ):
        # M6-E1-T8 (D-064): light tasks have no environment and cache hits run no provider.
        run_result = RunResult(
            provider="claude",
            model="claude-sonnet-4-6",
            result="done",
            session_id="canon-1",
            provider_session_id=None,
            cost_usd=0.0,
            error=False,
            stop_reason=stop_reason,
        )
        with patch("koda.services.queue_manager.RUNTIME_ENVIRONMENTS_ENABLED", enabled):
            assert _requires_kernel_terminal(runtime_env_id, run_result) is required

    @pytest.mark.asyncio
    @pytest.mark.parametrize("scenario", ["no_eligible_provider", "provider_unavailable"])
    async def test_error_result_that_ran_no_provider_skips_the_kernel_terminal_check(self, scenario):
        # D-297: with RUNTIME_ENVIRONMENTS_ENABLED a task with an environment whose provider never ran
        # failed with "runtime terminal output requires a kernel-backed terminal path", hiding the
        # provider error. Such an error result has no terminal, so the check does not apply to it.
        ctx = QueryContext(
            provider="claude",
            work_dir="/tmp",
            model="claude-sonnet-4-6",
            session_id="canon-1",
            provider_session_id=None,
            system_prompt="system",
            agent_mode="autonomous",
            permission_mode="bypassPermissions",
            max_turns=5,
            runtime_env_id=7,
            fallback_chain=[] if scenario == "no_eligible_provider" else ["claude"],
        )
        unavailable_ctx = QueryContext(
            provider="claude",
            work_dir="/tmp",
            model="claude-sonnet-4-6",
            session_id="canon-1",
            provider_session_id=None,
            system_prompt="system",
            agent_mode="autonomous",
            permission_mode="bypassPermissions",
            max_turns=5,
            runtime_env_id=7,
            warnings=["claude is not connected"],
            provider_available=False,
        )
        with (
            patch("koda.services.queue_manager.RUNTIME_ENVIRONMENTS_ENABLED", True),
            patch("koda.services.queue_manager.get_provider_fallback_chain", return_value=[]),
            patch("koda.services.queue_manager.get_provider_runtime_eligibility", return_value={}),
            patch("koda.services.queue_manager._resolve_provider_context", AsyncMock(return_value=unavailable_ctx)),
            patch("koda.services.queue_manager._run_streaming", AsyncMock()) as run_streaming,
            patch("koda.services.audit.emit_task_lifecycle"),
        ):
            result = await _run_with_provider_fallback(
                ctx, QueueItem(chat_id=111, query_text="hello"), 111, 111, MagicMock(), task_id=7
            )
            required = _requires_kernel_terminal(7, result)

        run_streaming.assert_not_awaited()
        assert result.error is True
        expected = (
            "No verified providers are eligible for runtime fallback."
            if scenario == "no_eligible_provider"
            else "claude is not connected"
        )
        assert result.result == expected
        assert required is False

    def test_error_result_from_a_provider_run_still_needs_a_kernel_terminal(self):
        # D-297: a provider that ran in a runtime environment registered its terminal, error or not.
        run_result = RunResult(
            provider="claude",
            model="claude-sonnet-4-6",
            result="provider failed",
            session_id="canon-1",
            provider_session_id=None,
            cost_usd=0.0,
            error=True,
            stop_reason="error",
            runtime_terminal_path="kernel-stream://stdout",
        )
        with patch("koda.services.queue_manager.RUNTIME_ENVIRONMENTS_ENABLED", True):
            assert _requires_kernel_terminal(7, run_result) is True

    @pytest.mark.asyncio
    async def test_recovered_provider_error_without_a_kernel_terminal_is_not_delivered(self, tmp_path):
        # D-297 review: the terminal check skips an error result without a terminal, but the recovery
        # step can turn an error with completed-looking output into a success. A result delivered as a
        # success must still carry a kernel-backed terminal (D-064), so the check runs after recovery.
        from koda.services import queue_manager as qm

        task_id = user_id = chat_id = 92970
        run_result = RunResult(
            provider="codex",
            model="gpt-5.4-mini",
            result=(
                "Fechei em sequência, como você pediu: o planejador travou o briefing "
                "e o desenvolvedor já entregou a LP.\n\n"
                "**Artefato**\n"
                "- [fintech_landing_page.html](runtime_home/fintech_landing_page.html)\n\n"
                "**O que ficou pronto**\n"
                "- Landing page única, autocontida e responsiva."
            ),
            session_id="canon-1",
            provider_session_id=None,
            cost_usd=0.0,
            error=True,
            stop_reason="error",
            error_kind="provider_runtime",
        )
        ctx = QueryContext(
            provider="codex",
            work_dir=str(tmp_path),
            model="gpt-5.4-mini",
            session_id="canon-1",
            provider_session_id=None,
            system_prompt="system",
            agent_mode="autonomous",
            permission_mode="bypassPermissions",
            max_turns=5,
        )
        raw_item = qm._build_user_message_raw_item(
            task_id=task_id,
            chat_id=chat_id,
            query_text="build the landing page",
            provider="codex",
            model="gpt-5.4-mini",
            work_dir=str(tmp_path),
            session_id="canon-1",
            update=None,
            image_paths=None,
            artifact_bundle=None,
        )
        raw_item["_runtime_preprovisioned"] = True
        runtime = MagicMock()
        runtime.runtime_root = str(tmp_path / "runtime")
        runtime.store.get_environment_by_task.return_value = {
            "id": 7,
            "workspace_path": str(tmp_path),
            "classification": "standard",
            "environment_kind": "dev_worktree",
        }
        for method in ("mark_phase", "register_terminal", "record_warning", "finalize_task", "heartbeat"):
            setattr(runtime, method, AsyncMock())
        context = MagicMock()
        context.user_data = {}
        context.bot.send_message = AsyncMock()
        task_info = TaskInfo(task_id=task_id, user_id=user_id, chat_id=chat_id, query_text="build the landing page")
        send_task_error = AsyncMock()

        with (
            patch("koda.services.runtime.get_runtime_controller", return_value=runtime),
            patch("koda.services.queue_manager.RUNTIME_ENVIRONMENTS_ENABLED", True),
            patch("koda.services.queue_manager.acquire_task_lease", return_value=True),
            patch("koda.services.queue_manager.extend_task_lease", return_value=True),
            patch("koda.services.queue_manager.release_task_lease"),
            patch("koda.services.queue_manager.update_task_with_lease", return_value=True),
            patch("koda.services.queue_manager._prepare_query_context", AsyncMock(return_value=ctx)),
            patch("koda.services.queue_manager._process_task_item", AsyncMock(return_value=run_result)),
            patch("koda.services.queue_manager._record_execution_episode", AsyncMock()),
            patch("koda.services.queue_manager._record_procedural_memory", AsyncMock()),
            patch("koda.services.queue_manager._finalize_scheduled_run", AsyncMock()),
            patch("koda.services.queue_manager._send_task_error", send_task_error),
            patch("koda.utils.command_helpers.init_user_data"),
            patch("koda.services.audit.emit"),
            patch("koda.services.audit.emit_task_lifecycle"),
            patch("koda.services.audit.emit_execution_trace"),
        ):
            await qm._execute_single_task(raw_item, user_id, context, task_id, task_info)

        phases = [call.kwargs["phase"] for call in runtime.mark_phase.await_args_list]
        assert "validating" not in phases
        runtime.register_terminal.assert_not_awaited()
        send_task_error.assert_awaited_once()
        assert send_task_error.await_args.args[1] == "runtime terminal output requires a kernel-backed terminal path"
        runtime.finalize_task.assert_awaited_once_with(
            task_id=task_id,
            success=False,
            error_message="runtime terminal output requires a kernel-backed terminal path",
        )

    @pytest.mark.asyncio
    @pytest.mark.parametrize("runtime_env_id", [7, None])
    async def test_run_fallback_registers_a_kernel_terminal_for_runtime_env(self, runtime_env_id):
        # M6-E1-T8 (D-064): the non-streaming fallback registers its terminal as streaming does, so a task
        # with a runtime environment passes the kernel terminal check; a task without one registers none.
        ctx = QueryContext(
            provider="codex",
            work_dir="/tmp",
            model="gpt-5.4-mini",
            session_id="canon-1",
            provider_session_id=None,
            system_prompt="system",
            agent_mode="autonomous",
            permission_mode="bypassPermissions",
            max_turns=5,
            runtime_env_id=runtime_env_id,
        )
        context = MagicMock()
        context.bot = AsyncMock()
        runtime = MagicMock()
        runtime.register_terminal = AsyncMock(return_value=17)
        run_llm = AsyncMock(return_value={"result": "done", "session_id": "prov-1", "_stop_reason": "completed"})

        with (
            patch("koda.services.runtime.get_runtime_controller", return_value=runtime),
            patch("koda.services.queue_manager.RUNTIME_ENVIRONMENTS_ENABLED", True),
            patch("koda.services.queue_manager.run_llm", new=run_llm),
        ):
            result = await _run_fallback(ctx, QueueItem(chat_id=111, query_text="hello"), 111, 111, context, task_id=7)

        assert result.result == "done"
        if runtime_env_id is None:
            runtime.register_terminal.assert_not_awaited()
            assert (result.runtime_terminal_id, result.runtime_terminal_path) == (None, None)
        else:
            runtime.register_terminal.assert_awaited_once()
            assert runtime.register_terminal.await_args.kwargs["path"] == "kernel-stream://stdout"
            assert runtime.register_terminal.await_args.kwargs["stream_path"] == "kernel-stream://stdout"
            assert (result.runtime_terminal_id, result.runtime_terminal_path) == (17, "kernel-stream://stdout")
            assert run_llm.await_args.kwargs["runtime_task_id"] == 7

    @pytest.mark.asyncio
    async def test_prepare_query_context_forces_safe_dry_run_mode(self):
        context = MagicMock()
        context.user_data = {
            "provider": "codex",
            "work_dir": "/tmp",
            "total_cost": 0.0,
            "auto_model": False,
            "manual_models_by_provider": {
                "claude": "claude-sonnet-4-6",
                "codex": "gpt-5.4-mini",
            },
            "provider_sessions": {"codex": "thread-1"},
            "session_id": "canon-1",
        }
        item = QueueItem(
            chat_id=111,
            query_text="validate",
            is_scheduled_run=True,
            scheduled_dry_run=True,
            scheduled_provider="codex",
            scheduled_work_dir="/tmp",
        )

        with (
            patch("koda.memory.config.MEMORY_ENABLED", False),
            patch("koda.knowledge.config.KNOWLEDGE_ENABLED", False),
            patch("koda.services.cache_config.CACHE_ENABLED", False),
            patch("koda.services.cache_config.SCRIPT_LIBRARY_ENABLED", False),
            patch(
                "koda.services.queue_manager.get_provider_session_mapping",
                return_value=("thread-1", "gpt-5.4-mini"),
            ),
            patch("koda.services.queue_manager.save_session"),
            patch("koda.services.queue_manager.resolve_provider_model", return_value="gpt-5.4-mini"),
        ):
            query_context = await _prepare_query_context(context, item, user_id=111)

        assert query_context.permission_mode == "plan"
        assert query_context.provider_session_id is None
        assert query_context.turn_mode == "new_turn"
        assert query_context.resume_requested is False
        assert "dry-run forced fresh provider turn" in query_context.warnings

    @pytest.mark.asyncio
    async def test_prepare_query_context_runs_a_child_under_its_parent_envelope(self):
        """M6-E2-T6: the child is judged by its parent's task kind, so rules keyed on it still bind."""
        context = MagicMock()
        context.user_data = {"provider": "claude", "work_dir": "/tmp", "total_cost": 0.0, "session_id": "canon-1"}
        capabilities = {"agent_id": "default", "allowed_tool_ids": ["file_list"], "task_kind": "deploy"}
        item = QueueItem(
            chat_id=111,
            query_text="list the files",
            is_child_run=True,
            child_run_id="childrun_x",
            parent_task_id=42,
            child_toolset="read_only",
            child_capabilities=capabilities,
        )

        with (
            patch("koda.memory.config.MEMORY_ENABLED", False),
            patch("koda.knowledge.config.KNOWLEDGE_ENABLED", False),
            patch("koda.services.cache_config.CACHE_ENABLED", False),
            patch("koda.services.cache_config.SCRIPT_LIBRARY_ENABLED", False),
            patch("koda.services.queue_manager.get_provider_session_mapping", return_value=None),
            patch("koda.services.queue_manager.save_session"),
        ):
            query_context = await _prepare_query_context(context, item, user_id=111)

        assert query_context.task_kind == "deploy"
        assert query_context.child_capabilities == capabilities
        assert query_context.effective_policy.approval_mode == "read_only"

    @staticmethod
    async def _started_child_raw_item(capabilities: dict, parent_user_data: dict | None = None) -> dict:
        """Run ``start_child_run_task`` with persistence stubbed and return the raw item it executes."""
        executed: dict = {}

        async def _execute(raw_item, _user_id, context, _task_id, _task_info):
            executed["raw_item"] = raw_item
            executed["user_data"] = context.user_data

        application = SimpleNamespace(
            user_data={111: {"provider": "claude", "total_cost": 0.0}}, bot=MagicMock(), bot_data={}
        )
        with (
            patch("koda.services.queue_manager.create_task", return_value=77),
            patch("koda.services.queue_manager._register_task"),
            patch("koda.services.queue_manager._persist_runtime_queue_item", AsyncMock()),
            patch("koda.services.queue_manager._update_runtime_queue_status"),
            patch("koda.services.queue_manager._execute_single_task", side_effect=_execute),
            patch("koda.services.audit.emit_task_lifecycle"),
        ):
            _task_id, task = await start_child_run_task(
                application=application,
                user_id=111,
                chat_id=111,
                query_text="child brief",
                parent_task_id=42,
                child_run_id="childrun_x",
                provider="claude",
                model=None,
                work_dir="/tmp",
                session_id="canon-1",
                child_context_prompt="child brief",
                context_policy={},
                toolset="read_only",
                capabilities=capabilities,
                **({"parent_user_data": parent_user_data} if parent_user_data is not None else {}),
            )
            await task
        return executed

    @pytest.mark.asyncio
    async def test_a_child_of_a_dry_run_parent_is_a_dry_run(self):
        """D-372: a child of a scheduled dry-run parent runs as a dry run and performs no write."""
        capabilities = {
            "agent_id": "default",
            "allowed_tool_ids": ["file_write", "job_list"],
            "task_kind": "general",
            "dry_run": True,
            "scheduled_job_id": 5,
            "scheduled_run_id": 9,
        }
        raw_item = (await self._started_child_raw_item(capabilities))["raw_item"]
        item = _parse_queue_item(raw_item)
        assert (item.scheduled_dry_run, item.scheduled_job_id, item.scheduled_run_id) == (True, 5, 9)
        assert item.is_scheduled_run is False  # the parent's scheduled run is finalized by the parent alone

        context = MagicMock()
        context.user_data = {"provider": "claude", "work_dir": "/tmp", "total_cost": 0.0, "session_id": "canon-1"}
        save_session = MagicMock()
        with (
            patch("koda.memory.config.MEMORY_ENABLED", False),
            patch("koda.knowledge.config.KNOWLEDGE_ENABLED", False),
            patch("koda.services.cache_config.CACHE_ENABLED", False),
            patch("koda.services.cache_config.SCRIPT_LIBRARY_ENABLED", False),
            patch("koda.services.queue_manager.get_provider_session_mapping", return_value=("thread-1", None)),
            patch("koda.services.queue_manager.save_session", save_session),
        ):
            query_context = await _prepare_query_context(context, item, user_id=111)

        assert query_context.dry_run is True
        assert query_context.provider_session_id is None
        assert "Scheduled Dry-Run Mode" in query_context.system_prompt
        save_session.assert_not_called()

        # The child's tools run in dry-run mode, and its write is never executed.
        from koda.services.tool_dispatcher import AgentToolResult

        seen_dry_run: list[bool] = []

        async def _job_list(_params, ctx):
            seen_dry_run.append(ctx.dry_run)
            return AgentToolResult(tool="job_list", success=True, output="No jobs.")

        handlers = {
            "job_list": AsyncMock(side_effect=_job_list),
            "file_write": AsyncMock(return_value=AgentToolResult(tool="file_write", success=True, output="ok")),
        }
        initial = RunResult(
            provider="claude",
            model="claude-sonnet-4-6",
            result=(
                '<agent_cmd tool="job_list">{}</agent_cmd>'
                '<agent_cmd tool="file_write">{"path": "out.txt", "content": "x"}</agent_cmd>'
            ),
            session_id="canon-1",
            provider_session_id=None,
            cost_usd=0.0,
            error=False,
            stop_reason="end_turn",
        )
        done = RunResult(
            provider="claude",
            model="claude-sonnet-4-6",
            result="done",
            session_id="canon-1",
            provider_session_id=None,
            cost_usd=0.0,
            error=False,
            stop_reason="end_turn",
        )
        loop_context = MagicMock()
        loop_context.user_data = dict(context.user_data)
        loop_context.bot = AsyncMock()
        with (
            patch("koda.services.queue_manager._run_with_provider_fallback", AsyncMock(return_value=done)),
            patch("koda.services.tool_dispatcher._TOOL_HANDLERS", handlers),
        ):
            await _run_agent_loop(query_context, item, 111, 111, loop_context, initial)

        assert seen_dry_run == [True]
        handlers["file_write"].assert_not_awaited()

    @pytest.mark.asyncio
    async def test_a_child_starts_from_its_parent_context_and_budget(self):
        """D-374: the child sees its parent's settings and spends against the parent's budget."""
        from koda.config import MAX_TOTAL_BUDGET_USD

        parent_user_data = {
            "provider": "claude",
            "work_dir": "/tmp",
            "session_id": "canon-1",
            "agent_mode": "supervised",
            "total_cost": MAX_TOTAL_BUDGET_USD,
        }
        executed = await self._started_child_raw_item(
            {"agent_id": "default", "allowed_tool_ids": ["job_list"], "task_kind": "general"},
            parent_user_data,
        )
        child_user_data = executed["user_data"]

        # Not application.user_data[111] (total 0.0, no agent_mode): the parent's own turn context.
        assert child_user_data["agent_mode"] == "supervised"
        assert child_user_data["total_cost"] == MAX_TOTAL_BUDGET_USD
        assert child_user_data is not parent_user_data  # the child's own keys stay in its copy

        with pytest.raises(BudgetExceeded):
            await _prepare_query_context(
                SimpleNamespace(user_data=child_user_data), _parse_queue_item(executed["raw_item"]), user_id=111
            )

    @pytest.mark.asyncio
    async def test_prepare_query_context_blocks_invalid_scheduled_workdir(self):
        context = MagicMock()
        context.user_data = {
            "provider": "claude",
            "work_dir": "/tmp",
            "total_cost": 0.0,
            "auto_model": False,
            "manual_models_by_provider": {"claude": "claude-sonnet-4-6"},
            "provider_sessions": {},
        }
        item = QueueItem(
            chat_id=111,
            query_text="run",
            is_scheduled_run=True,
            scheduled_work_dir="/etc",
        )

        with pytest.raises(ValueError, match="sensitive system directory"):
            await _prepare_query_context(context, item, user_id=111)

    @pytest.mark.asyncio
    async def test_prepare_query_context_does_not_invent_claude_provider_session_from_canonical_id(self):
        context = MagicMock()
        context.user_data = {
            "provider": "claude",
            "work_dir": "/tmp",
            "total_cost": 0.0,
            "auto_model": False,
            "manual_models_by_provider": {"claude": "claude-sonnet-4-6"},
            "provider_sessions": {},
            "session_id": "canon-1",
        }
        item = QueueItem(chat_id=111, query_text="continuar")

        with (
            patch("koda.memory.config.MEMORY_ENABLED", False),
            patch("koda.knowledge.config.KNOWLEDGE_ENABLED", False),
            patch("koda.services.cache_config.CACHE_ENABLED", False),
            patch("koda.services.cache_config.SCRIPT_LIBRARY_ENABLED", False),
            patch("koda.services.queue_manager.get_provider_session_mapping", return_value=None),
            patch("koda.services.queue_manager.save_session") as mock_save_session,
            patch("koda.services.queue_manager.resolve_provider_model", return_value="claude-sonnet-4-6"),
        ):
            query_context = await _prepare_query_context(context, item, user_id=111)

        assert query_context.provider_session_id is None
        assert query_context.turn_mode == "new_turn"
        assert query_context.resume_requested is False
        assert context.user_data["provider_sessions"] == {}
        assert mock_save_session.call_args.kwargs["provider_session_id"] is None

    @pytest.mark.asyncio
    async def test_prepare_query_context_blocks_prompt_budget_overflow(self):
        context = MagicMock()
        context.user_data = {
            "provider": "claude",
            "work_dir": "/tmp",
            "total_cost": 0.0,
            "auto_model": False,
            "manual_models_by_provider": {"claude": "claude-sonnet-4-6"},
            "provider_sessions": {},
        }
        item = QueueItem(chat_id=111, query_text="hello")

        fake_prompt_budget = MagicMock()
        fake_prompt_budget.compiled_prompt = ""
        fake_prompt_budget.to_dict.return_value = {
            "within_budget": False,
            "overflow_tokens": 321,
            "gate_reason": "compiled_overflow",
            "final_segment_order": ["immutable_base_policy", "tool_contracts"],
        }

        with (
            patch("koda.memory.config.MEMORY_ENABLED", False),
            patch("koda.knowledge.config.KNOWLEDGE_ENABLED", False),
            patch("koda.services.cache_config.CACHE_ENABLED", False),
            patch("koda.services.cache_config.SCRIPT_LIBRARY_ENABLED", False),
            patch("koda.services.queue_manager.get_provider_session_mapping", return_value=None),
            patch("koda.services.queue_manager.save_session"),
            patch("koda.services.queue_manager.resolve_provider_model", return_value="claude-sonnet-4-6"),
            patch("koda.services.queue_manager.PromptBudgetPlanner") as planner_cls,
        ):
            planner_cls.return_value.compile.return_value = fake_prompt_budget
            with pytest.raises(BudgetExceeded, match="Overflow=321 tokens"):
                await _prepare_query_context(context, item, user_id=111)


def _build_system_prompt(user_system_prompt: str | None, audio_response: bool, tts_enabled: bool) -> str:
    """Reproduce the system prompt composition logic from queue_manager."""
    if user_system_prompt:
        system_prompt = DEFAULT_SYSTEM_PROMPT + "\n\n## User Instructions\n" + user_system_prompt
    else:
        system_prompt = DEFAULT_SYSTEM_PROMPT

    if audio_response and tts_enabled:
        system_prompt += "\n\n" + VOICE_ACTIVE_PROMPT

    return system_prompt


class TestVoicePromptInjection:
    def test_voice_prompt_appended_when_active(self):
        prompt = _build_system_prompt(None, audio_response=True, tts_enabled=True)
        assert VOICE_ACTIVE_PROMPT in prompt

    def test_voice_prompt_not_appended_when_inactive(self):
        prompt = _build_system_prompt(None, audio_response=False, tts_enabled=True)
        assert VOICE_ACTIVE_PROMPT not in prompt

    def test_voice_prompt_not_appended_when_tts_disabled(self):
        prompt = _build_system_prompt(None, audio_response=True, tts_enabled=False)
        assert VOICE_ACTIVE_PROMPT not in prompt

    def test_voice_prompt_after_user_instructions(self):
        user_instr = "Always reply in English."
        prompt = _build_system_prompt(user_instr, audio_response=True, tts_enabled=True)
        user_pos = prompt.index("## User Instructions")
        # Use the section header which only appears in the appended VOICE_ACTIVE_PROMPT
        voice_pos = prompt.index("## 🎙️ VOICE MODE ACTIVE")
        assert voice_pos > user_pos

    def test_voice_prompt_constant_has_required_sections(self):
        assert "VOICE MODE ACTIVE" in VOICE_ACTIVE_PROMPT
        assert "<voice_rules>" in VOICE_ACTIVE_PROMPT
        assert "Flowing, continuous prose" in VOICE_ACTIVE_PROMPT
        assert "TTS" in VOICE_ACTIVE_PROMPT
        assert "URLs" in VOICE_ACTIVE_PROMPT
        assert "<voice_example>" in VOICE_ACTIVE_PROMPT
        assert "Do not say that voice mode, audio, or TTS is disabled" in VOICE_ACTIVE_PROMPT
        assert "Write in spoken English" not in VOICE_ACTIVE_PROMPT
        assert "user's language" in VOICE_ACTIVE_PROMPT

    def test_default_system_prompt_defers_voice_state_to_runtime_section(self):
        assert "If a voice-active section appears" in DEFAULT_SYSTEM_PROMPT
        assert "If the user asks for audio response but /voice is not active" not in DEFAULT_SYSTEM_PROMPT


class TestSystemPromptAutonomousWork:
    def test_contains_autonomous_work_section(self):
        assert "<autonomous_work>" in DEFAULT_SYSTEM_PROMPT
        assert "Break the task into logical phases" in DEFAULT_SYSTEM_PROMPT
        assert "Run existing tests" in DEFAULT_SYSTEM_PROMPT

    def test_default_prompt_has_no_native_atlassian_tooling(self):
        assert "visual analysis by Claude" not in DEFAULT_SYSTEM_PROMPT
        assert "`jira`" not in DEFAULT_SYSTEM_PROMPT
        assert "`confluence`" not in DEFAULT_SYSTEM_PROMPT


class TestParseQueueItem:
    def test_parse_continuation(self):
        item = _parse_queue_item({"_continuation": True, "chat_id": 123, "session_id": "sess-1"})
        assert isinstance(item, QueueItem)
        assert item.is_continuation is True
        assert item.chat_id == 123
        assert item.continuation_session_id == "sess-1"
        assert item.query_text == "Continue from where you left off."

    def test_parse_link_analysis(self):
        item = _parse_queue_item({"_link_analysis": True, "chat_id": 456, "query_text": "Analyze this"})
        assert item.is_link_analysis is True
        assert item.chat_id == 456
        assert item.query_text == "Analyze this"

    def test_parse_normal_with_images(self):
        mock_update = MagicMock()
        raw = {
            "_user_message": True,
            "chat_id": 789,
            "query_text": "hello world",
            "update": mock_update,
            "image_paths": ["/tmp/img.png"],
        }
        item = _parse_queue_item(raw)
        assert item.chat_id == 789
        assert item.query_text == "hello world"
        assert item.image_paths == ["/tmp/img.png"]
        assert item.update is mock_update
        assert item.is_continuation is False

    def test_parse_normal_without_images(self):
        raw = {"_user_message": True, "chat_id": 100, "query_text": "just text", "image_paths": []}
        item = _parse_queue_item(raw)
        assert item.chat_id == 100
        assert item.query_text == "just text"
        assert item.image_paths is None

    def test_parse_user_message_preserves_forced_audio_flag(self):
        item = _parse_queue_item(
            {
                "_user_message": True,
                "chat_id": 123,
                "query_text": "me envie um audio",
                "force_audio_response": True,
            }
        )

        assert item.force_audio_response is True

    def test_parse_dashboard_chat_preserves_forced_audio_flag(self):
        item = _parse_queue_item(
            {
                "_dashboard_chat": True,
                "chat_id": -123,
                "query_text": "me envie um audio",
                "force_audio_response": True,
            }
        )

        assert item.is_dashboard_chat is True
        assert item.force_audio_response is True

    @pytest.mark.asyncio
    async def test_enqueue_dashboard_chat_task_detects_explicit_audio_request(self):
        queued_items: list[dict[str, object]] = []

        class _Queue:
            async def put(self, item: dict[str, object]) -> None:
                queued_items.append(item)

        with (
            patch("koda.services.queue_manager.create_task", return_value=321),
            patch("koda.services.queue_manager.build_runtime_context", return_value=MagicMock()),
            patch("koda.services.queue_manager.get_queue", return_value=_Queue()),
            patch("koda.services.queue_manager._persist_runtime_queue_item", new_callable=AsyncMock),
            patch("koda.services.queue_manager._ensure_queue_worker", new_callable=AsyncMock),
            patch("koda.services.queue_manager._track_queued_task_id"),
            patch("koda.services.queue_manager._sync_user_queue_observability"),
            patch("koda.services.audit.emit_task_lifecycle"),
        ):
            task_id = await enqueue_dashboard_chat_task(
                application=MagicMock(),
                user_id=123,
                chat_id=-123,
                query_text="Pode me enviar um audio?",
                provider="claude",
                model="claude-sonnet-4-6",
                work_dir="/tmp",
                session_id="session-ui",
            )

        assert task_id == 321
        assert queued_items[0]["force_audio_response"] is True


class TestVideoFramePathDetection:
    """Test the regex-based frame path detection used in _run_agent_loop."""

    def _extract_paths(self, output: str) -> list[str]:
        """Reproduce the regex logic from _run_agent_loop."""
        return re.findall(
            rf"{re.escape(str(IMAGE_TEMP_DIR))}/\S+\.jpg",
            output,
        )

    def test_extracts_paths_from_summary(self):
        output = (
            f"## Video Analysis: bug.mp4 (PROJ-123)\n\n"
            f"Extracted 3 frames from 'bug.mp4' (duration: 15.0s, interval: 5s).\n\n"
            f"Frame files:\n"
            f"- {IMAGE_TEMP_DIR}/jira_frame_10001_001.jpg\n"
            f"- {IMAGE_TEMP_DIR}/jira_frame_10001_002.jpg\n"
            f"- {IMAGE_TEMP_DIR}/jira_frame_10001_003.jpg"
        )
        paths = self._extract_paths(output)
        assert len(paths) == 3
        assert all("jira_frame_10001" in p for p in paths)

    def test_no_match_without_image_temp_dir(self):
        output = "Extracted frames:\n- /other/path/frame.jpg"
        paths = self._extract_paths(output)
        assert paths == []

    def test_no_match_on_error_output(self):
        output = "Error: FFmpeg is not available. Cannot extract video frames."
        paths = self._extract_paths(output)
        assert paths == []

    def test_handles_single_frame(self):
        output = f"Frame files:\n- {IMAGE_TEMP_DIR}/jira_frame_99_001.jpg"
        paths = self._extract_paths(output)
        assert len(paths) == 1


class TestProviderFallback:
    def test_should_switch_provider_on_auth_error(self):
        run_result = RunResult(
            provider="claude",
            model="claude-opus-4-6",
            result="Claude authentication failed.",
            session_id="canon-1",
            provider_session_id=None,
            cost_usd=0.0,
            error=True,
            stop_reason="error",
            error_kind="provider_auth",
        )

        assert _should_switch_provider(run_result) is True

    @pytest.mark.asyncio
    async def test_run_streaming_continues_when_progress_message_times_out(self):
        ctx = QueryContext(
            provider="codex",
            work_dir="/tmp",
            model="gpt-5.4-mini",
            session_id="canon-1",
            provider_session_id=None,
            system_prompt="system",
            agent_mode="autonomous",
            permission_mode="bypassPermissions",
            max_turns=5,
        )
        item = QueueItem(chat_id=111, query_text="hello")
        context = MagicMock()
        context.bot = AsyncMock()
        context.bot.send_message = AsyncMock(side_effect=TimedOut("Timed out"))

        async def _fake_stream(*args, **kwargs):
            metadata = kwargs["metadata_collector"]
            metadata["stop_reason"] = "completed"
            yield "done"

        with (
            patch("koda.services.queue_manager.run_llm_streaming", side_effect=_fake_stream),
            patch("koda.services.queue_manager._send_typing", new_callable=AsyncMock),
        ):
            result = await _run_streaming(ctx, item, 111, 111, context, task_id=7)

        assert result is not None
        assert result.result == "done"
        assert result.provider == "codex"

    @pytest.mark.asyncio
    async def test_resolve_provider_context_preserves_effective_model_for_same_provider(self):
        ctx = QueryContext(
            provider="codex",
            work_dir="/tmp",
            model="gpt-5.4-mini",
            session_id="canon-1",
            provider_session_id="thread-1",
            system_prompt="system",
            agent_mode="autonomous",
            permission_mode="bypassPermissions",
            max_turns=5,
        )
        item = QueueItem(chat_id=111, query_text="resume")
        context = MagicMock()
        context.user_data = {
            "provider": "claude",
            "auto_model": False,
            "manual_models_by_provider": {
                "claude": "claude-sonnet-4-6",
                "codex": "gpt-5.4",
            },
            "provider_sessions": {"codex": "thread-1"},
        }

        with (
            patch(
                "koda.services.queue_manager.get_provider_session_mapping",
                return_value=None,
            ),
            patch(
                "koda.services.queue_manager.get_provider_capabilities",
                new=AsyncMock(
                    return_value=ProviderCapabilities(
                        provider="codex",
                        turn_mode="resume_turn",
                        status="ready",
                        can_execute=True,
                        supports_native_resume=True,
                    )
                ),
            ),
        ):
            resolved = await _resolve_provider_context(base_ctx=ctx, provider="codex", item=item, context=context)

        assert resolved.provider == "codex"
        assert resolved.model == "gpt-5.4-mini"
        assert resolved.provider_session_id == "thread-1"
        assert resolved.turn_mode == "resume_turn"

    @pytest.mark.asyncio
    async def test_resolve_provider_context_degrades_resume_when_capability_is_unavailable(self):
        ctx = QueryContext(
            provider="codex",
            work_dir="/tmp",
            model="gpt-5.4-mini",
            session_id="canon-1",
            provider_session_id="thread-1",
            system_prompt="system",
            agent_mode="autonomous",
            permission_mode="bypassPermissions",
            max_turns=5,
        )
        item = QueueItem(chat_id=111, query_text="resume")
        context = MagicMock()
        context.user_data = {
            "provider": "codex",
            "auto_model": False,
            "manual_models_by_provider": {"claude": "claude-sonnet-4-6", "codex": "gpt-5.4-mini"},
            "provider_sessions": {"codex": "thread-1"},
        }

        with (
            patch("koda.services.queue_manager.get_provider_session_mapping", return_value=None),
            patch(
                "koda.services.queue_manager.get_provider_capabilities",
                new=AsyncMock(
                    side_effect=[
                        ProviderCapabilities(
                            provider="codex",
                            turn_mode="resume_turn",
                            status="degraded",
                            can_execute=False,
                            supports_native_resume=False,
                            errors=["resume unavailable"],
                        ),
                        ProviderCapabilities(
                            provider="codex",
                            turn_mode="new_turn",
                            status="ready",
                            can_execute=True,
                            supports_native_resume=False,
                        ),
                    ]
                ),
            ),
        ):
            resolved = await _resolve_provider_context(base_ctx=ctx, provider="codex", item=item, context=context)

        assert resolved.provider_session_id is None
        assert resolved.turn_mode == "new_turn"
        assert resolved.resume_requested is True
        assert resolved.supports_native_resume is False
        assert any("resume degraded" in warning for warning in resolved.warnings)


class TestPolicySelection:
    def test_select_policy_runbook_prefers_semantic_hit(self):
        runbooks = [
            {"id": 1, "title": "Recent but irrelevant", "policy_overrides": {"min_read_evidence": 9}},
            {"id": 2, "title": "Relevant deploy runbook", "policy_overrides": {"min_read_evidence": 3}},
        ]
        resolution = MagicMock()
        resolution.hits = [
            MagicMock(
                entry=MagicMock(
                    layer=KnowledgeLayer.APPROVED_RUNBOOK,
                    source_path="approved_runbook:2",
                )
            )
        ]

        selected = _select_policy_runbook(runbooks, resolution)

        assert selected == runbooks[1]

    def test_apply_policy_overrides_ignores_invalid_config(self):
        base_policy = default_execution_policy("deploy")

        result = _apply_policy_overrides(
            base_policy,
            {"id": 7, "policy_overrides": {"approval_mode": "dangerously-open"}},
        )

        assert result == base_policy

    @pytest.mark.asyncio
    async def test_run_with_provider_fallback_switches_to_codex(self):
        ctx = QueryContext(
            provider="claude",
            work_dir="/tmp",
            model="claude-sonnet-4-6",
            session_id="canon-1",
            provider_session_id=None,
            system_prompt="system",
            agent_mode="autonomous",
            permission_mode="bypassPermissions",
            max_turns=5,
        )
        item = QueueItem(chat_id=111, query_text="hello")
        context = MagicMock()
        context.user_data = {
            "provider": "claude",
            "auto_model": False,
            "manual_models_by_provider": {
                "claude": "claude-sonnet-4-6",
                "codex": "gpt-5.4",
            },
            "provider_sessions": {},
        }

        claude_error = RunResult(
            provider="claude",
            model="claude-sonnet-4-6",
            result="temporarily unavailable",
            session_id="canon-1",
            provider_session_id=None,
            cost_usd=0.0,
            error=True,
            stop_reason="error",
        )
        codex_success = RunResult(
            provider="codex",
            model="gpt-5.4",
            result="done",
            session_id="canon-1",
            provider_session_id="thread-1",
            cost_usd=0.0,
            error=False,
            stop_reason="completed",
        )

        with (
            patch(
                "koda.services.queue_manager.get_provider_fallback_chain",
                return_value=["claude", "codex"],
            ),
            patch(
                "koda.services.queue_manager.build_bootstrap_prompt",
                return_value="bootstrapped",
            ),
            patch(
                "koda.services.queue_manager._run_streaming",
                new=AsyncMock(side_effect=[claude_error, codex_success]),
            ),
            patch(
                "koda.services.queue_manager.get_provider_capabilities",
                new=AsyncMock(
                    side_effect=[
                        ProviderCapabilities(
                            provider="claude",
                            turn_mode="new_turn",
                            status="ready",
                            can_execute=True,
                            supports_native_resume=True,
                        ),
                        ProviderCapabilities(
                            provider="codex",
                            turn_mode="new_turn",
                            status="ready",
                            can_execute=True,
                            supports_native_resume=False,
                        ),
                    ]
                ),
            ),
            patch(
                "koda.services.queue_manager.get_provider_session_mapping",
                return_value=None,
            ),
            patch(
                "koda.services.queue_manager._run_fallback",
                new=AsyncMock(),
            ),
            patch(
                "koda.services.queue_manager.save_provider_session_mapping",
            ) as mock_save_mapping,
        ):
            result = await _run_with_provider_fallback(ctx, item, 111, 111, context, task_id=7)

        assert result.provider == "codex"
        assert result.model == "gpt-5.4"
        assert result.result == "done"
        assert result.fallback_chain == ["claude", "codex"]
        mock_save_mapping.assert_called_once_with("canon-1", "codex", "thread-1", "gpt-5.4")

    @pytest.mark.asyncio
    async def test_run_with_provider_fallback_bootstraps_same_provider_after_resume_contract_error(self):
        ctx = QueryContext(
            provider="codex",
            work_dir="/tmp",
            model="gpt-5.4-mini",
            session_id="canon-1",
            provider_session_id="thread-1",
            system_prompt="system",
            agent_mode="autonomous",
            permission_mode="bypassPermissions",
            max_turns=5,
            turn_mode="resume_turn",
            resume_requested=True,
        )
        item = QueueItem(chat_id=111, query_text="lembra?")
        context = MagicMock()
        context.user_data = {
            "provider": "codex",
            "auto_model": False,
            "manual_models_by_provider": {"claude": "claude-sonnet-4-6", "codex": "gpt-5.4-mini"},
            "provider_sessions": {"codex": "thread-1"},
        }

        contract_error = RunResult(
            provider="codex",
            model="gpt-5.4-mini",
            result="error: unexpected argument '--cd' found",
            session_id="canon-1",
            provider_session_id="thread-1",
            cost_usd=0.0,
            error=True,
            stop_reason="error",
            turn_mode="resume_turn",
            error_kind="adapter_contract",
        )
        bootstrapped = RunResult(
            provider="codex",
            model="gpt-5.4-mini",
            result="Sim, lembro.",
            session_id="canon-1",
            provider_session_id="thread-2",
            cost_usd=0.0,
            error=False,
            stop_reason="completed",
            turn_mode="new_turn",
            supports_native_resume=False,
        )

        with (
            patch("koda.services.queue_manager.get_provider_fallback_chain", return_value=["codex", "claude"]),
            patch("koda.services.queue_manager.build_bootstrap_prompt", return_value="bootstrapped"),
            patch(
                "koda.services.queue_manager.get_provider_capabilities",
                new=AsyncMock(
                    return_value=ProviderCapabilities(
                        provider="codex",
                        turn_mode="resume_turn",
                        status="ready",
                        can_execute=True,
                        supports_native_resume=True,
                    )
                ),
            ),
            patch(
                "koda.services.queue_manager._run_streaming",
                new=AsyncMock(side_effect=[contract_error, bootstrapped]),
            ),
            patch("koda.services.queue_manager._run_fallback", new=AsyncMock()),
            patch("koda.services.queue_manager.get_provider_session_mapping", return_value=None),
            patch("koda.services.queue_manager.save_provider_session_mapping") as mock_save_mapping,
        ):
            result = await _run_with_provider_fallback(ctx, item, 111, 111, context, task_id=7)

        assert result.provider == "codex"
        assert result.result == "Sim, lembro."
        assert result.fallback_chain == ["codex"]
        assert any("resume degraded" in warning for warning in result.warnings)
        assert mock_save_mapping.call_args_list[-1].args == ("canon-1", "codex", "thread-2", "gpt-5.4-mini")

    @pytest.mark.asyncio
    async def test_run_with_provider_fallback_restarts_claude_after_invalid_session(self):
        ctx = QueryContext(
            provider="claude",
            work_dir="/tmp",
            model="claude-sonnet-4-6",
            session_id="canon-1",
            provider_session_id="bad-thread",
            system_prompt="system",
            agent_mode="autonomous",
            permission_mode="bypassPermissions",
            max_turns=5,
            turn_mode="resume_turn",
            resume_requested=True,
        )
        item = QueueItem(chat_id=111, query_text="retoma")
        context = MagicMock()
        context.user_data = {
            "provider": "claude",
            "auto_model": False,
            "manual_models_by_provider": {"claude": "claude-sonnet-4-6", "codex": "gpt-5.4-mini"},
            "provider_sessions": {"claude": "bad-thread"},
        }

        invalid_session = RunResult(
            provider="claude",
            model="claude-sonnet-4-6",
            result="Claude CLI error (exit 1):\nNo conversation found with session ID: bad-thread",
            session_id="canon-1",
            provider_session_id="bad-thread",
            cost_usd=0.0,
            error=True,
            stop_reason="error",
            turn_mode="resume_turn",
            error_kind="invalid_session",
        )
        bootstrapped = RunResult(
            provider="claude",
            model="claude-sonnet-4-6",
            result="Turno novo aberto.",
            session_id="canon-1",
            provider_session_id="fresh-thread",
            cost_usd=0.0,
            error=False,
            stop_reason="completed",
            turn_mode="new_turn",
            supports_native_resume=False,
        )

        with (
            patch("koda.services.queue_manager.get_provider_fallback_chain", return_value=["claude", "codex"]),
            patch("koda.services.queue_manager.build_bootstrap_prompt", return_value="bootstrapped"),
            patch(
                "koda.services.queue_manager.get_provider_capabilities",
                new=AsyncMock(
                    return_value=ProviderCapabilities(
                        provider="claude",
                        turn_mode="resume_turn",
                        status="ready",
                        can_execute=True,
                        supports_native_resume=True,
                    )
                ),
            ),
            patch(
                "koda.services.queue_manager._run_streaming",
                new=AsyncMock(side_effect=[invalid_session, bootstrapped]),
            ),
            patch("koda.services.queue_manager._run_fallback", new=AsyncMock()),
            patch("koda.services.queue_manager.get_provider_session_mapping", return_value=None),
            patch("koda.services.queue_manager.save_provider_session_mapping") as mock_save_mapping,
            patch("koda.services.queue_manager.delete_provider_session_mapping") as mock_delete_mapping,
        ):
            result = await _run_with_provider_fallback(ctx, item, 111, 111, context, task_id=7)

        assert result.provider == "claude"
        assert result.result == "Turno novo aberto."
        assert result.turn_mode == "new_turn"
        assert any("resume degraded" in warning for warning in result.warnings)
        mock_delete_mapping.assert_called_once_with("canon-1", "claude")
        assert context.user_data["provider_sessions"]["claude"] == "fresh-thread"
        assert mock_save_mapping.call_args_list[-1].args == ("canon-1", "claude", "fresh-thread", "claude-sonnet-4-6")

    @pytest.mark.asyncio
    async def test_run_with_provider_fallback_fails_closed_when_no_provider_is_eligible(self):
        ctx = QueryContext(
            provider="claude",
            work_dir="/tmp",
            model="claude-sonnet-4-6",
            session_id="canon-1",
            provider_session_id=None,
            system_prompt="system",
            agent_mode="autonomous",
            permission_mode="bypassPermissions",
            max_turns=5,
        )
        item = QueueItem(chat_id=111, query_text="hello")
        context = MagicMock()
        context.user_data = {"provider": "claude", "auto_model": False, "provider_sessions": {}}

        with (
            patch("koda.services.queue_manager.get_provider_fallback_chain", return_value=[]),
            patch(
                "koda.services.queue_manager.get_provider_runtime_eligibility",
                return_value={
                    "claude": {"eligible": False, "reason": "unverified"},
                    "codex": {"eligible": False, "reason": "disabled"},
                },
            ),
        ):
            result = await _run_with_provider_fallback(ctx, item, 111, 111, context, task_id=7)

        assert result.error is True
        assert result.error_kind == "provider_runtime"
        assert result.result == "No verified providers are eligible for runtime fallback."
        assert result.warnings == ["no eligible verified providers"]

    @pytest.mark.asyncio
    async def test_post_process_logs_actual_fallback_model(self):
        context = MagicMock()
        context.user_data = {
            "session_id": None,
            "provider_sessions": {},
            "total_cost": 0.0,
            "query_count": 0,
        }
        run_result = RunResult(
            provider="codex",
            model="gpt-5.4",
            result="done",
            session_id="canon-1",
            provider_session_id="thread-1",
            cost_usd=0.0,
            error=False,
            stop_reason="completed",
        )

        with (
            patch("koda.services.queue_manager.save_provider_session_mapping") as mock_save_mapping,
            patch("koda.services.queue_manager.save_session") as mock_save_session,
            patch("koda.services.queue_manager.log_query") as mock_log_query,
            patch("koda.services.queue_manager.save_user_cost"),
            patch("koda.memory.config.MEMORY_ENABLED", False),
        ):
            await _post_process(111, context, run_result, "hello", "/tmp", "claude-sonnet-4-6")

        mock_save_mapping.assert_called_once_with("canon-1", "codex", "thread-1", "gpt-5.4")
        mock_save_session.assert_called_once()
        assert mock_save_session.call_args.kwargs["model"] == "gpt-5.4"
        assert mock_save_session.call_args.args[1] == "canon-1"
        assert mock_log_query.call_args.kwargs["model"] == "gpt-5.4"
        assert mock_log_query.call_args.kwargs["session_id"] == "canon-1"
        assert mock_log_query.call_args.kwargs["provider_session_id"] == "thread-1"

    @pytest.mark.asyncio
    async def test_post_process_uses_final_response_and_skips_memory_when_needs_review(self):
        context = MagicMock()
        context.user_data = {
            "session_id": None,
            "provider_sessions": {},
            "total_cost": 0.0,
            "query_count": 0,
        }
        run_result = RunResult(
            provider="codex",
            model="gpt-5.4",
            result="unsafe success",
            session_id="canon-1",
            provider_session_id="thread-1",
            cost_usd=0.0,
            error=False,
            stop_reason="completed",
        )
        memory_manager = MagicMock()
        memory_manager.post_query = AsyncMock()

        with (
            patch("koda.services.queue_manager.save_provider_session_mapping"),
            patch("koda.services.queue_manager.save_session"),
            patch("koda.services.queue_manager.log_query") as mock_log_query,
            patch("koda.services.queue_manager.save_user_cost"),
            patch("koda.memory.config.MEMORY_ENABLED", True),
            patch("koda.memory.get_memory_manager", return_value=memory_manager),
        ):
            await _post_process(
                111,
                context,
                run_result,
                "hello",
                "/tmp",
                "claude-sonnet-4-6",
                final_status="needs_review",
                response_text_override="blocked for review",
            )

        assert mock_log_query.call_args.kwargs["response_text"] == "blocked for review"
        memory_manager.post_query.assert_not_called()


class TestCancelQueuedTask:
    @pytest.mark.asyncio
    async def test_cancel_queued_task_no_item_loss(self):
        """Cancelling a task does not lose other queued items."""
        import koda.services.metrics  # noqa: F401  (the patch target below must be imported)
        from koda.services.queue_manager import (
            _cancelled_task_ids,
            _track_queued_task_id,
            _user_queue_task_ids,
            _user_queues,
            cancel_queued_task,
        )

        _cancelled_task_ids.clear()
        queue = asyncio.Queue()
        user_id = 99999
        _user_queues[user_id] = queue

        # Enqueue three items with task_ids 1, 2, 3, tracked as the enqueue
        # helpers do.
        for tid in (1, 2, 3):
            await queue.put({"_task_id": tid, "chat_id": 1, "query_text": "query"})
            _track_queued_task_id(user_id, tid)

        try:
            with patch("koda.services.metrics") as mock_metrics:
                mock_metrics.QUEUE_DEPTH.labels.return_value.set = MagicMock()
                result = await cancel_queued_task(2)

            assert result is True
            assert 2 in _cancelled_task_ids
            # The cancelled task no longer counts as pending for the user.
            assert _user_queue_task_ids[user_id] == [1, 3]

            # All three items are still in the queue (sentinel approach)
            assert queue.qsize() == 3
        finally:
            _cancelled_task_ids.clear()
            _user_queue_task_ids.pop(user_id, None)
            _user_queues.pop(user_id, None)

    @pytest.mark.asyncio
    async def test_cancel_queued_task_returns_false_for_task_not_in_queue(self):
        """A task a worker already dequeued (running) is not reported as queued (D-009).

        Returning True here made the runtime controller skip
        ``cancel_active_task_execution`` and leaked the id in ``_cancelled_task_ids``.
        """
        from koda.services.queue_manager import (
            _cancelled_task_ids,
            _track_queued_task_id,
            _user_queue_task_ids,
            cancel_queued_task,
        )

        user_id = 99998
        _track_queued_task_id(user_id, 11)
        try:
            assert await cancel_queued_task(12) is False
            assert 12 not in _cancelled_task_ids
            assert _user_queue_task_ids[user_id] == [11]
        finally:
            _cancelled_task_ids.discard(11)
            _cancelled_task_ids.discard(12)
            _user_queue_task_ids.pop(user_id, None)


class TestCancelActiveTaskExecution:
    @pytest.mark.asyncio
    async def test_cancel_stops_the_streaming_run_and_removes_its_progress_message(self):
        """A cancelled streaming run kills its provider, propagates, and leaves no partial output (D-009)."""
        import signal
        import sys

        from koda.services.queue_manager import (
            _register_task,
            _unregister_task,
            active_processes,
            cancel_active_task_execution,
        )

        task_id = 7301
        ctx = QueryContext(
            provider="claude",
            work_dir="/tmp",
            model="claude-sonnet-4-6",
            session_id="canon-1",
            provider_session_id=None,
            system_prompt="system",
            agent_mode="autonomous",
            permission_mode="bypassPermissions",
            max_turns=5,
        )
        item = QueueItem(chat_id=111, query_text="hello")
        progress_message = MagicMock()
        progress_message.edit_text = AsyncMock()
        progress_message.delete = AsyncMock()
        context = MagicMock()
        context.bot.send_message = AsyncMock(return_value=progress_message)
        streaming = asyncio.Event()
        procs: list[asyncio.subprocess.Process] = []

        async def _fake_stream(**kwargs):
            proc = await asyncio.create_subprocess_exec(
                sys.executable,
                "-c",
                "import time; time.sleep(60)",
                start_new_session=True,
            )
            procs.append(proc)
            kwargs["process_holder"]["proc"] = proc
            kwargs["process_holder"]["event"].set()
            yield "partial output"
            streaming.set()
            await proc.wait()
            yield "output after the provider exited"

        task_info = TaskInfo(task_id=task_id, user_id=7300, chat_id=111, query_text="hello")
        _register_task(task_info)
        try:
            with (
                patch("koda.services.queue_manager.run_llm_streaming", new=_fake_stream),
                patch("koda.services.queue_manager._send_typing", new_callable=AsyncMock),
            ):
                run = asyncio.create_task(_run_streaming(ctx, item, 7300, 111, context, task_id=task_id))
                task_info.asyncio_task = run
                await asyncio.wait_for(streaming.wait(), timeout=10)
                for _ in range(100):
                    if task_id in active_processes:
                        break
                    await asyncio.sleep(0.01)
                assert active_processes[task_id] is procs[0]

                assert await cancel_active_task_execution(task_id, reason="Cancelled by /cancel command.") is True
                with pytest.raises(asyncio.CancelledError):
                    await asyncio.wait_for(run, timeout=10)

            await asyncio.wait_for(procs[0].wait(), timeout=10)
            assert procs[0].returncode == -signal.SIGTERM
            assert task_info.error_message == "Cancelled by /cancel command."
            progress_message.delete.assert_awaited_once()
            assert task_id not in active_processes
        finally:
            for proc in procs:
                if proc.returncode is None:
                    proc.kill()
                    await proc.wait()
            active_processes.pop(task_id, None)
            _unregister_task(task_info)

    @pytest.mark.asyncio
    async def test_provider_exit_during_kernel_termination_does_not_switch_provider(self):
        """D-222: a provider run that ends because a cancel is terminating it stops the task.

        The runtime kernel's termination yields. The first provider exits as soon as
        it is signalled and its runner reports a provider-switch error, all before the
        asyncio cancel lands. The next provider in the chain must not run, and the task
        must stop only after the termination returned.
        """
        from dataclasses import replace

        from koda.services.queue_manager import (
            _register_task,
            _unregister_task,
            active_processes,
            cancel_active_task_execution,
            get_task_info,
        )

        task_id = 7321
        order: list[str] = []
        attempts: list[str] = []
        provider_running = asyncio.Event()
        provider_signalled = asyncio.Event()
        ctx = QueryContext(
            provider="claude",
            work_dir="/tmp",
            model="claude-sonnet-4-6",
            session_id="canon-1",
            provider_session_id=None,
            system_prompt="system",
            agent_mode="autonomous",
            permission_mode="bypassPermissions",
            max_turns=5,
            fallback_chain=["claude", "codex"],
        )
        item = QueueItem(chat_id=111, query_text="hello")
        context = MagicMock()
        context.user_data = {}

        class _KernelProcess:
            kernel_managed = True

            async def terminate(self) -> None:
                marked = getattr(get_task_info(task_id), "cancel_requested", False)
                order.append(f"terminate:start cancel_requested={marked}")
                provider_signalled.set()
                await asyncio.sleep(0.05)
                order.append("terminate:done")

        async def _fake_run_streaming(attempt_ctx, _item, _user_id, _chat_id, _context, task_id=None):
            attempts.append(attempt_ctx.provider)
            active_processes[task_id] = _KernelProcess()
            provider_running.set()
            try:
                await provider_signalled.wait()
            finally:
                active_processes.pop(task_id, None)
            order.append("provider:exited")
            # What a runner reports for a provider killed mid-turn.
            return RunResult(
                provider=attempt_ctx.provider,
                model=attempt_ctx.model,
                result="CLI error (exit -15): connection reset",
                session_id="canon-1",
                provider_session_id=None,
                cost_usd=0.0,
                error=True,
                stop_reason="error",
                error_kind="provider_runtime",
                retryable=True,
            )

        async def _resolve_provider_context(*, base_ctx, provider, **_kwargs):
            return replace(base_ctx, provider=provider)

        async def _run() -> RunResult:
            try:
                return await _run_with_provider_fallback(ctx, item, 7320, 111, context, task_id=task_id)
            except asyncio.CancelledError:
                order.append("task:stopped")
                raise

        task_info = TaskInfo(task_id=task_id, user_id=7320, chat_id=111, query_text="hello")
        _register_task(task_info)
        try:
            with (
                patch("koda.services.queue_manager._run_streaming", new=_fake_run_streaming),
                patch("koda.services.queue_manager._run_fallback", new=AsyncMock()) as run_fallback,
                patch("koda.services.queue_manager._resolve_provider_context", new=_resolve_provider_context),
                patch("koda.services.queue_manager.build_bootstrap_prompt", return_value="bootstrapped"),
            ):
                run = asyncio.create_task(_run())
                task_info.asyncio_task = run
                await asyncio.wait_for(provider_running.wait(), timeout=10)

                assert await cancel_active_task_execution(task_id, reason="Cancelled by /cancel command.") is True
                with pytest.raises(asyncio.CancelledError):
                    await asyncio.wait_for(run, timeout=10)

            assert attempts == ["claude"]
            run_fallback.assert_not_awaited()
            assert order == [
                "terminate:start cancel_requested=True",
                "provider:exited",
                "terminate:done",
                "task:stopped",
            ]
            assert task_info.error_message == "Cancelled by /cancel command."
        finally:
            active_processes.pop(task_id, None)
            _unregister_task(task_info)

    @pytest.mark.asyncio
    async def test_provider_exit_in_non_streaming_fallback_during_kernel_termination_does_not_switch_provider(self):
        """D-222: a non-streaming fallback run that ends because a cancel is terminating it stops the task.

        The streaming run returns nothing on its own, before any cancel, so the
        non-streaming fallback starts a kernel-backed provider run. /cancel then
        terminates it: the provider exits as soon as it is signalled and its runner
        reports a retryable error while the kernel call is still terminating it, so the
        asyncio cancel has not landed yet. The next provider in the chain must not run,
        and the task must stop only after the termination returned.
        """
        from dataclasses import replace

        from koda.services.queue_manager import (
            _register_task,
            _unregister_task,
            active_processes,
            cancel_active_task_execution,
            get_task_info,
        )

        task_id = 7322
        order: list[str] = []
        runs: list[str] = []
        provider_running = asyncio.Event()
        provider_signalled = asyncio.Event()
        ctx = QueryContext(
            provider="claude",
            work_dir="/tmp",
            model="claude-sonnet-4-6",
            session_id="canon-1",
            provider_session_id=None,
            system_prompt="system",
            agent_mode="autonomous",
            permission_mode="bypassPermissions",
            max_turns=5,
            fallback_chain=["claude", "codex"],
        )
        item = QueueItem(chat_id=111, query_text="hello")
        context = MagicMock()
        context.user_data = {}

        class _KernelProcess:
            kernel_managed = True

            async def terminate(self) -> None:
                marked = getattr(get_task_info(task_id), "cancel_requested", False)
                order.append(f"terminate:start cancel_requested={marked}")
                provider_signalled.set()
                await asyncio.sleep(0.05)
                order.append("terminate:done")

        async def _fake_run_streaming(attempt_ctx, _item, _user_id, _chat_id, _context, task_id=None):
            # Streaming produced no result on its own; no cancel has been requested yet.
            runs.append(f"streaming:{attempt_ctx.provider}")
            return None

        async def _fake_run_fallback(attempt_ctx, _item, _user_id, _chat_id, _context, task_id=None):
            runs.append(f"fallback:{attempt_ctx.provider}")
            active_processes[task_id] = _KernelProcess()
            provider_running.set()
            try:
                await provider_signalled.wait()
            finally:
                active_processes.pop(task_id, None)
            order.append("provider:exited")
            # What a runner reports for a provider killed mid-turn.
            return RunResult(
                provider=attempt_ctx.provider,
                model=attempt_ctx.model,
                result="CLI error (exit -15): connection reset",
                session_id="canon-1",
                provider_session_id=None,
                cost_usd=0.0,
                error=True,
                stop_reason="error",
                error_kind="provider_runtime",
                retryable=True,
            )

        async def _resolve_provider_context(*, base_ctx, provider, **_kwargs):
            return replace(base_ctx, provider=provider)

        async def _run() -> RunResult:
            try:
                return await _run_with_provider_fallback(ctx, item, 7320, 111, context, task_id=task_id)
            except asyncio.CancelledError:
                order.append("task:stopped")
                raise

        task_info = TaskInfo(task_id=task_id, user_id=7320, chat_id=111, query_text="hello")
        _register_task(task_info)
        try:
            with (
                patch("koda.services.queue_manager._run_streaming", new=_fake_run_streaming),
                patch("koda.services.queue_manager._run_fallback", new=_fake_run_fallback),
                patch("koda.services.queue_manager._resolve_provider_context", new=_resolve_provider_context),
                patch("koda.services.queue_manager.build_bootstrap_prompt", return_value="bootstrapped"),
            ):
                run = asyncio.create_task(_run())
                task_info.asyncio_task = run
                await asyncio.wait_for(provider_running.wait(), timeout=10)

                assert await cancel_active_task_execution(task_id, reason="Cancelled by /cancel command.") is True
                with pytest.raises(asyncio.CancelledError):
                    await asyncio.wait_for(run, timeout=10)

            # The cancelled fallback run of claude was the last provider run: codex never started.
            assert runs == ["streaming:claude", "fallback:claude"]
            assert order == [
                "terminate:start cancel_requested=True",
                "provider:exited",
                "terminate:done",
                "task:stopped",
            ]
            assert task_info.error_message == "Cancelled by /cancel command."
        finally:
            active_processes.pop(task_id, None)
            _unregister_task(task_info)

    @pytest.mark.asyncio
    async def test_task_parked_on_a_cancel_stops_when_the_cancel_itself_is_cancelled(self):
        """D-222: a task waiting for a cancel's termination is released if that cancel is cancelled.

        The provider exits as soon as it is signalled, so the task parks in
        ``_stop_if_cancel_requested`` until the kernel termination returns. The caller of
        ``cancel_active_task_execution`` (a scheduler job or a child-run timeout path) is
        then cancelled while the kernel call is still terminating, so the asyncio cancel of
        the task is never sent. The task must still stop with ``CancelledError`` instead of
        waiting forever and holding the user's queue worker, and the next provider in the
        chain must not run.
        """
        from dataclasses import replace

        from koda.services.queue_manager import (
            _register_task,
            _unregister_task,
            active_processes,
            cancel_active_task_execution,
        )

        task_id = 7323
        order: list[str] = []
        attempts: list[str] = []
        provider_running = asyncio.Event()
        provider_signalled = asyncio.Event()
        provider_exited = asyncio.Event()
        ctx = QueryContext(
            provider="claude",
            work_dir="/tmp",
            model="claude-sonnet-4-6",
            session_id="canon-1",
            provider_session_id=None,
            system_prompt="system",
            agent_mode="autonomous",
            permission_mode="bypassPermissions",
            max_turns=5,
            fallback_chain=["claude", "codex"],
        )
        item = QueueItem(chat_id=111, query_text="hello")
        context = MagicMock()
        context.user_data = {}

        class _KernelProcess:
            kernel_managed = True

            async def terminate(self) -> None:
                order.append("terminate:start")
                provider_signalled.set()
                # The kernel's grace period and group reap; the canceller is cancelled meanwhile.
                await asyncio.sleep(5)
                order.append("terminate:done")

        async def _fake_run_streaming(attempt_ctx, _item, _user_id, _chat_id, _context, task_id=None):
            attempts.append(attempt_ctx.provider)
            active_processes[task_id] = _KernelProcess()
            provider_running.set()
            try:
                await provider_signalled.wait()
            finally:
                active_processes.pop(task_id, None)
            order.append("provider:exited")
            provider_exited.set()
            # What a runner reports for a provider killed mid-turn.
            return RunResult(
                provider=attempt_ctx.provider,
                model=attempt_ctx.model,
                result="CLI error (exit -15): connection reset",
                session_id="canon-1",
                provider_session_id=None,
                cost_usd=0.0,
                error=True,
                stop_reason="error",
                error_kind="provider_runtime",
                retryable=True,
            )

        async def _resolve_provider_context(*, base_ctx, provider, **_kwargs):
            return replace(base_ctx, provider=provider)

        async def _run() -> RunResult:
            try:
                return await _run_with_provider_fallback(ctx, item, 7320, 111, context, task_id=task_id)
            except asyncio.CancelledError:
                order.append("task:stopped")
                raise

        task_info = TaskInfo(task_id=task_id, user_id=7320, chat_id=111, query_text="hello")
        _register_task(task_info)
        run: asyncio.Task | None = None
        canceller: asyncio.Task | None = None
        try:
            with (
                patch("koda.services.queue_manager._run_streaming", new=_fake_run_streaming),
                patch("koda.services.queue_manager._run_fallback", new=AsyncMock()) as run_fallback,
                patch("koda.services.queue_manager._resolve_provider_context", new=_resolve_provider_context),
                patch("koda.services.queue_manager.build_bootstrap_prompt", return_value="bootstrapped"),
            ):
                run = asyncio.create_task(_run())
                task_info.asyncio_task = run
                await asyncio.wait_for(provider_running.wait(), timeout=10)

                canceller = asyncio.create_task(
                    cancel_active_task_execution(task_id, reason="Cancelled by /cancel command.")
                )
                # The provider exited and the task is now parked on the cancel, while the
                # kernel call is still terminating.
                await asyncio.wait_for(provider_exited.wait(), timeout=10)
                await asyncio.sleep(0)
                assert not run.done()
                assert order == ["terminate:start", "provider:exited"]

                canceller.cancel()
                with pytest.raises(asyncio.CancelledError):
                    await canceller

                done, _pending = await asyncio.wait({run}, timeout=2)
                assert run in done, "the task stayed parked on a cancel whose caller was cancelled"

            assert run.cancelled() is True
            assert attempts == ["claude"]
            run_fallback.assert_not_awaited()
            assert order == ["terminate:start", "provider:exited", "task:stopped"]
            assert task_info.error_message == "Cancelled by /cancel command."
        finally:
            for pending_task in (canceller, run):
                if pending_task is not None and not pending_task.done():
                    pending_task.cancel()
                    with contextlib.suppress(BaseException):
                        await pending_task
            active_processes.pop(task_id, None)
            _unregister_task(task_info)


class TestIsTaskActiveInProcess:
    def test_reports_queued_running_and_provider_tasks(self):
        from koda.services.queue_manager import (
            _register_task,
            _track_queued_task_id,
            _unregister_task,
            _untrack_queued_task_id,
            active_processes,
            is_task_active_in_process,
        )

        user_id = 7310
        task_info = TaskInfo(task_id=7312, user_id=user_id, chat_id=1, query_text="q")
        _track_queued_task_id(user_id, 7311)
        _register_task(task_info)
        active_processes[7313] = MagicMock()
        try:
            assert is_task_active_in_process(7311) is True
            assert is_task_active_in_process(7312) is True
            assert is_task_active_in_process(7313) is True
            assert is_task_active_in_process(7314) is False
        finally:
            _untrack_queued_task_id(user_id, 7311)
            _unregister_task(task_info)
            active_processes.pop(7313, None)


class TestQueueOrdering:
    @pytest.mark.asyncio
    async def test_enqueue_reports_fifo_feedback_when_user_already_has_task_running(self):
        from koda.services.queue_manager import _user_queues, _user_tasks

        user_id = 321
        update = MagicMock()
        update.effective_chat.id = 321
        update.message = AsyncMock()
        context = MagicMock()
        context.user_data = {
            "provider": "codex",
            "provider_sessions": {},
            "session_id": "canon-1",
        }
        _user_tasks[user_id] = {
            1: TaskInfo(task_id=1, user_id=user_id, chat_id=321, query_text="primeira"),
        }

        try:
            with (
                patch("koda.services.queue_manager.create_task", return_value=2),
                patch("koda.services.queue_manager.RUNTIME_ENVIRONMENTS_ENABLED", False),
                patch("koda.services.queue_manager._sync_user_queue_observability"),
                patch("koda.services.queue_manager._ensure_queue_worker", new_callable=AsyncMock),
            ):
                task_id = await enqueue(user_id, update, context, "segunda")

            assert task_id == 2
            update.message.reply_text.assert_awaited_once()
            feedback = update.message.reply_text.await_args.args[0]
            assert "queued it" in feedback.lower()
            assert "current task" in feedback.lower()
            assert "#2" in feedback
        finally:
            _user_tasks.pop(user_id, None)
            _user_queues.pop(user_id, None)

    @pytest.mark.asyncio
    async def test_process_queue_is_fifo_and_never_runs_same_user_tasks_in_parallel(self):
        from koda.services.queue_manager import _queue_workers, _unregister_task, _user_queues, _user_tasks

        user_id = 654
        context = MagicMock()
        context.user_data = {}
        queue = asyncio.Queue()
        _user_queues[user_id] = queue

        await queue.put({"_task_id": 1, "chat_id": 654, "query_text": "primeira"})
        await queue.put({"_task_id": 2, "chat_id": 654, "query_text": "segunda"})

        started: list[int] = []
        active = 0
        max_active = 0

        async def _fake_execute(raw_item, _user_id, _context, task_id, task_info):
            nonlocal active, max_active
            active += 1
            max_active = max(max_active, active)
            started.append(task_id)
            await asyncio.sleep(0)
            active -= 1
            _unregister_task(task_info)

        try:
            with (
                patch("koda.services.queue_manager._execute_single_task", side_effect=_fake_execute),
                patch("koda.services.queue_manager._sync_user_queue_observability"),
            ):
                await _process_queue(user_id, context)

            assert started == [1, 2]
            assert max_active == 1
            assert queue.qsize() == 0
        finally:
            _queue_workers.pop(user_id, None)
            _user_tasks.pop(user_id, None)
            _user_queues.pop(user_id, None)

    @pytest.mark.asyncio
    async def test_process_queue_keeps_running_after_a_task_is_cancelled(self):
        """Cancelling one running task must not kill the user's queue worker."""
        from koda.services.queue_manager import (
            _queue_workers,
            _unregister_task,
            _user_queues,
            _user_tasks,
            cancel_active_task_execution,
            get_task_info,
        )

        user_id = 655
        context = MagicMock()
        context.user_data = {}
        queue = asyncio.Queue()
        _user_queues[user_id] = queue
        await queue.put({"_task_id": 1, "chat_id": 655, "query_text": "longa"})
        await queue.put({"_task_id": 2, "chat_id": 655, "query_text": "seguinte"})

        first_started = asyncio.Event()
        finished: list[int] = []

        async def _fake_execute(raw_item, _user_id, _context, task_id, task_info):
            try:
                if task_id == 1:
                    first_started.set()
                    await asyncio.sleep(60)
                finished.append(task_id)
            finally:
                _unregister_task(task_info)

        try:
            with (
                patch("koda.services.queue_manager._execute_single_task", side_effect=_fake_execute),
                patch("koda.services.queue_manager._sync_user_queue_observability"),
            ):
                worker = asyncio.create_task(_process_queue(user_id, context))
                await asyncio.wait_for(first_started.wait(), timeout=5)
                assert await cancel_active_task_execution(1, reason="Cancelled by /cancel command.") is True
                await asyncio.wait_for(worker, timeout=5)

            assert finished == [2]
            assert queue.qsize() == 0
            assert get_task_info(1) is None
        finally:
            _queue_workers.pop(user_id, None)
            _user_tasks.pop(user_id, None)
            _user_queues.pop(user_id, None)

    @pytest.mark.asyncio
    async def test_process_queue_propagates_cancellation_of_the_worker_itself(self):
        """Shutdown cancels the worker; that cancellation must still propagate."""
        from koda.services.queue_manager import _queue_workers, _unregister_task, _user_queues, _user_tasks

        user_id = 656
        context = MagicMock()
        context.user_data = {}
        queue = asyncio.Queue()
        _user_queues[user_id] = queue
        await queue.put({"_task_id": 1, "chat_id": 656, "query_text": "longa"})
        await queue.put({"_task_id": 2, "chat_id": 656, "query_text": "seguinte"})

        first_started = asyncio.Event()
        started: list[int] = []

        async def _fake_execute(raw_item, _user_id, _context, task_id, task_info):
            started.append(task_id)
            try:
                first_started.set()
                await asyncio.sleep(60)
            finally:
                _unregister_task(task_info)

        try:
            with (
                patch("koda.services.queue_manager._execute_single_task", side_effect=_fake_execute),
                patch("koda.services.queue_manager._sync_user_queue_observability"),
            ):
                worker = asyncio.create_task(_process_queue(user_id, context))
                await asyncio.wait_for(first_started.wait(), timeout=5)
                worker.cancel()
                with pytest.raises(asyncio.CancelledError):
                    await asyncio.wait_for(worker, timeout=5)

            assert started == [1]
            assert queue.qsize() == 1
        finally:
            _queue_workers.pop(user_id, None)
            _user_tasks.pop(user_id, None)
            _user_queues.pop(user_id, None)


class TestRunFallbackProgressCleanup:
    """``_run_fallback`` cancels its progress indicator when the provider run ends.

    The indicator can end cancelled before its own handler runs: when it never got a step,
    or while it still sends the first "Processing..." message. That is the cleanup of this
    run, not a cancel of it, so the provider's result must still be returned. Only a cancel
    of the run itself propagates.
    """

    @staticmethod
    def _ctx() -> QueryContext:
        return QueryContext(
            provider="claude",
            work_dir="/tmp",
            model="claude-sonnet-4-6",
            session_id="canon-1",
            provider_session_id=None,
            system_prompt="system",
            agent_mode="autonomous",
            permission_mode="bypassPermissions",
            max_turns=5,
        )

    @staticmethod
    def _llm_result() -> dict:
        return {"result": "the answer", "session_id": "prov-1", "cost_usd": 0.01, "_stop_reason": "completed"}

    @pytest.mark.asyncio
    async def test_result_is_returned_when_the_provider_answers_before_the_indicator_starts(self):
        context = MagicMock()
        context.bot = AsyncMock()
        # Returns without yielding to the event loop, so the indicator never gets a step.
        run_llm = AsyncMock(return_value=self._llm_result())

        with patch("koda.services.queue_manager.run_llm", new=run_llm):
            result = await _run_fallback(self._ctx(), QueueItem(chat_id=111, query_text="hello"), 111, 111, context)

        run_llm.assert_awaited_once()
        assert result.result == "the answer"
        assert result.error is False
        context.bot.send_message.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_result_is_returned_when_the_provider_answers_while_the_first_message_is_sent(self):
        sending = asyncio.Event()

        async def _slow_send_message(**_kwargs):
            sending.set()
            await asyncio.sleep(60)

        context = MagicMock()
        context.bot = AsyncMock()
        context.bot.send_message = AsyncMock(side_effect=_slow_send_message)

        async def _run_llm(**_kwargs):
            await sending.wait()
            return self._llm_result()

        with patch("koda.services.queue_manager.run_llm", new=_run_llm):
            result = await asyncio.wait_for(
                _run_fallback(self._ctx(), QueueItem(chat_id=111, query_text="hello"), 111, 111, context),
                timeout=10,
            )

        assert result.result == "the answer"
        context.bot.send_message.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_progress_message_is_deleted_after_the_result(self):
        progress_msg = MagicMock()
        progress_msg.delete = AsyncMock()
        sent = asyncio.Event()

        async def _send_message(**_kwargs):
            sent.set()
            return progress_msg

        context = MagicMock()
        context.bot = AsyncMock()
        context.bot.send_message = AsyncMock(side_effect=_send_message)

        async def _run_llm(**_kwargs):
            await sent.wait()
            await asyncio.sleep(0)
            return self._llm_result()

        with patch("koda.services.queue_manager.run_llm", new=_run_llm):
            result = await _run_fallback(self._ctx(), QueueItem(chat_id=111, query_text="hello"), 111, 111, context)

        assert result.result == "the answer"
        progress_msg.delete.assert_awaited_once()

    @pytest.mark.parametrize("indicator_started", [False, True])
    @pytest.mark.asyncio
    async def test_cancelling_the_run_still_propagates(self, indicator_started: bool):
        sending = asyncio.Event()
        provider_running = asyncio.Event()

        async def _slow_send_message(**_kwargs):
            sending.set()
            await asyncio.sleep(60)

        context = MagicMock()
        context.bot = AsyncMock()
        context.bot.send_message = AsyncMock(side_effect=_slow_send_message)

        async def _run_llm(**_kwargs):
            provider_running.set()
            await asyncio.sleep(60)
            return self._llm_result()

        with patch("koda.services.queue_manager.run_llm", new=_run_llm):
            run = asyncio.create_task(
                _run_fallback(self._ctx(), QueueItem(chat_id=111, query_text="hello"), 111, 111, context)
            )
            await asyncio.wait_for(provider_running.wait(), timeout=10)
            if indicator_started:
                await asyncio.wait_for(sending.wait(), timeout=10)
            run.cancel()
            with pytest.raises(asyncio.CancelledError):
                await asyncio.wait_for(run, timeout=10)

        assert run.cancelled()

    @pytest.mark.asyncio
    async def test_cancelling_the_run_during_its_cleanup_still_propagates(self):
        """A /cancel that lands after the provider answered, while the finally block still deletes the
        progress message, must cancel the run. That CancelledError is the run's own, not the indicator's,
        so the cleanup handler re-raises it instead of returning the provider's result."""
        deleting = asyncio.Event()

        async def _slow_delete():
            deleting.set()
            await asyncio.sleep(60)

        progress_msg = MagicMock()
        progress_msg.delete = AsyncMock(side_effect=_slow_delete)
        sent = asyncio.Event()

        async def _send_message(**_kwargs):
            sent.set()
            return progress_msg

        context = MagicMock()
        context.bot = AsyncMock()
        context.bot.send_message = AsyncMock(side_effect=_send_message)

        async def _run_llm(**_kwargs):
            await sent.wait()
            await asyncio.sleep(0)
            return self._llm_result()

        with patch("koda.services.queue_manager.run_llm", new=_run_llm):
            run = asyncio.create_task(
                _run_fallback(self._ctx(), QueueItem(chat_id=111, query_text="hello"), 111, 111, context)
            )
            # The provider has answered; the finally block is awaiting progress_msg.delete().
            await asyncio.wait_for(deleting.wait(), timeout=10)
            run.cancel()
            with pytest.raises(asyncio.CancelledError):
                await asyncio.wait_for(run, timeout=10)

        assert run.cancelled()
        progress_msg.delete.assert_awaited_once()
