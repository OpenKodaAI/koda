"""Tests for queue_manager helper functions."""

import asyncio
import re
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from telegram.error import TimedOut

from koda.config import DEFAULT_SYSTEM_PROMPT, IMAGE_TEMP_DIR, JIRA_ENABLED, VOICE_ACTIVE_PROMPT
from koda.knowledge.task_policy_defaults import default_execution_policy
from koda.knowledge.types import KnowledgeLayer
from koda.services.artifact_ingestion import (
    ArtifactDossier,
    ArtifactKind,
    ArtifactRef,
    ArtifactStatus,
    ExtractedArtifact,
)
from koda.services.jira_issue_context import IssueContextDossier
from koda.services.provider_runtime import ProviderCapabilities
from koda.services.queue_manager import (
    BudgetExceeded,
    QueryContext,
    QueueItem,
    RunResult,
    TaskInfo,
    _apply_policy_overrides,
    _compact_tool_label,
    _get_throttle_interval,
    _parse_queue_item,
    _post_process,
    _prepare_query_context,
    _process_queue,
    _resolve_provider_context,
    _run_streaming,
    _run_with_provider_fallback,
    _select_policy_runbook,
    _should_switch_provider,
    enqueue,
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
        assert _compact_tool_label("Bash", {"command": "npm test"}) == "Bash(npm test)"

    def test_bash_long(self):
        long_cmd = "npm run build -- --mode production --watch"
        label = _compact_tool_label("Bash", {"command": long_cmd})
        assert label.startswith("Bash(")
        assert label.endswith("...)")
        assert len(label) <= len("Bash(") + 30 + 1  # name + truncated + paren

    def test_grep(self):
        assert _compact_tool_label("Grep", {"pattern": "TODO"}) == "Grep(TODO)"

    def test_generic_with_input(self):
        label = _compact_tool_label("Edit", {"file_path": "/a/b/c.py", "old_string": "foo"})
        # Should use first string value
        assert label.startswith("Edit(")

    def test_no_input(self):
        assert _compact_tool_label("Read") == "Read"
        assert _compact_tool_label("Read", None) == "Read"
        assert _compact_tool_label("Read", {}) == "Read"


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
    async def test_prepare_query_context_builds_issue_dossier_and_blocks_writes_on_gaps(self):
        context = MagicMock()
        context.user_data = {
            "provider": "claude",
            "work_dir": "/tmp",
            "total_cost": 0.0,
            "auto_model": False,
            "manual_models_by_provider": {
                "claude": "claude-sonnet-4-6",
                "codex": "gpt-5.4-mini",
            },
            "provider_sessions": {},
        }
        item = QueueItem(chat_id=111, query_text="Analise o ticket SIM-410 e responda no Jira")
        image_path = "/tmp/jira_dossier_img.png"
        dossier = IssueContextDossier(
            issue={"key": "SIM-410", "fields": {"summary": "Checkout failure"}},
            comments=[],
            remote_links=[],
            dossier=ArtifactDossier(
                subject_id="SIM-410",
                subject_label="Jira issue SIM-410",
                summary="SIM-410 dossier",
                artifacts=[
                    ExtractedArtifact(
                        ref=ArtifactRef(
                            artifact_id="img-1",
                            kind=ArtifactKind.IMAGE,
                            label="screen.png",
                            source_type="jira_attachment",
                        ),
                        status=ArtifactStatus.COMPLETE,
                        summary="Image summary",
                        visual_paths=[image_path],
                    ),
                    ExtractedArtifact(
                        ref=ArtifactRef(
                            artifact_id="pdf-1",
                            kind=ArtifactKind.PDF,
                            label="spec.pdf",
                            source_type="jira_attachment",
                            critical_for_action=True,
                        ),
                        status=ArtifactStatus.UNRESOLVED,
                        summary="PDF could not be parsed",
                        critical_for_action=True,
                    ),
                ],
            ),
        )
        jira_service = MagicMock()
        jira_service.build_issue_dossier = AsyncMock(return_value=dossier)

        with (
            patch("koda.memory.config.MEMORY_ENABLED", False),
            patch("koda.knowledge.config.KNOWLEDGE_ENABLED", False),
            patch("koda.services.cache_config.CACHE_ENABLED", False),
            patch("koda.services.cache_config.SCRIPT_LIBRARY_ENABLED", False),
            patch("koda.services.queue_manager.JIRA_ENABLED", True),
            patch("koda.services.queue_manager.JIRA_DEEP_CONTEXT_ENABLED", True),
            patch("koda.services.queue_manager.get_provider_session_mapping", return_value=None),
            patch("koda.services.queue_manager.save_session"),
            patch("koda.services.queue_manager.resolve_provider_model", return_value="claude-sonnet-4-6"),
            patch("koda.services.atlassian_client.get_jira_service", return_value=jira_service),
        ):
            query_context = await _prepare_query_context(context, item, user_id=111)

        jira_service.build_issue_dossier.assert_awaited_once()
        assert query_context.permission_mode == "plan"
        assert query_context.effective_policy.approval_mode == "read_only"
        assert "artifact dossier incomplete; writes blocked" in query_context.warnings
        assert "<artifact_context>" in query_context.system_prompt
        assert "SIM-410 dossier" in query_context.system_prompt
        assert query_context.visual_paths == [image_path]

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
        voice_pos = prompt.index("## 🎙️ VOICE MODE ATIVO")
        assert voice_pos > user_pos

    def test_voice_prompt_constant_has_required_sections(self):
        assert "VOICE MODE ATIVO" in VOICE_ACTIVE_PROMPT
        assert "<voice_rules>" in VOICE_ACTIVE_PROMPT
        assert "Prosa corrida" in VOICE_ACTIVE_PROMPT
        assert "TTS" in VOICE_ACTIVE_PROMPT
        assert "URLs" in VOICE_ACTIVE_PROMPT
        assert "<voice_example>" in VOICE_ACTIVE_PROMPT


class TestSystemPromptAutonomousWork:
    def test_contains_autonomous_work_section(self):
        assert "<autonomous_work>" in DEFAULT_SYSTEM_PROMPT
        assert "Break the task into logical phases" in DEFAULT_SYSTEM_PROMPT
        assert "Run existing tests" in DEFAULT_SYSTEM_PROMPT

    def test_atlassian_prompt_is_provider_neutral(self):
        assert "visual analysis by Claude" not in DEFAULT_SYSTEM_PROMPT
        if JIRA_ENABLED:
            assert "visual analysis by the coding runtime" in DEFAULT_SYSTEM_PROMPT
            assert "comment_get" in DEFAULT_SYSTEM_PROMPT
            assert "comment_edit" in DEFAULT_SYSTEM_PROMPT
            assert "comment_delete" in DEFAULT_SYSTEM_PROMPT
            assert "comment_reply" in DEFAULT_SYSTEM_PROMPT
            assert "safe linked top-level comments" in DEFAULT_SYSTEM_PROMPT


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
        mock_update.effective_chat.id = 789
        raw = (mock_update, "hello world", ["/tmp/img.png"])
        item = _parse_queue_item(raw)
        assert item.chat_id == 789
        assert item.query_text == "hello world"
        assert item.image_paths == ["/tmp/img.png"]
        assert item.update is mock_update
        assert item.is_continuation is False

    def test_parse_normal_without_images(self):
        mock_update = MagicMock()
        mock_update.effective_chat.id = 100
        raw = (mock_update, "just text")
        item = _parse_queue_item(raw)
        assert item.chat_id == 100
        assert item.query_text == "just text"
        assert item.image_paths is None


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
        assert mock_log_query.call_args.kwargs["model"] == "gpt-5.4"

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
        from koda.services.queue_manager import (
            _cancelled_task_ids,
            _user_queues,
            cancel_queued_task,
        )

        _cancelled_task_ids.clear()
        queue = asyncio.Queue()
        user_id = 99999
        _user_queues[user_id] = queue

        # Enqueue three items with task_ids 1, 2, 3
        for tid in (1, 2, 3):
            await queue.put(("update", "query", "work_dir", tid))

        with patch("koda.services.metrics") as mock_metrics:
            mock_metrics.QUEUE_DEPTH.labels.return_value.set = MagicMock()
            result = await cancel_queued_task(2)

        assert result is True
        assert 2 in _cancelled_task_ids

        # All three items are still in the queue (sentinel approach)
        assert queue.qsize() == 3

        # Clean up
        _cancelled_task_ids.clear()
        _user_queues.pop(user_id, None)


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

        first_update = MagicMock()
        first_update.effective_chat.id = 654
        second_update = MagicMock()
        second_update.effective_chat.id = 654

        await queue.put((first_update, "primeira", None, None, 1))
        await queue.put((second_update, "segunda", None, None, 2))

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
