"""Tests for callback handlers."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from koda.handlers.callbacks import callback_feedback, callback_link_analysis, callback_provider


@pytest.fixture
def mock_callback_update():
    """Create a mock Update with callback_query for link analysis."""
    update = MagicMock()
    update.effective_user = MagicMock()
    update.effective_user.id = 111
    update.effective_chat = MagicMock()
    update.effective_chat.id = 111
    update.callback_query = AsyncMock()
    update.callback_query.answer = AsyncMock()
    update.callback_query.edit_message_text = AsyncMock()
    update.callback_query.message = MagicMock()
    update.callback_query.message.text = "Preview text"
    return update


class TestCallbackLinkAnalysis:
    @pytest.mark.asyncio
    async def test_callback_link_analysis_summary(self, mock_callback_update, mock_context):
        """Clicking summary should call enqueue_link_analysis."""
        mock_callback_update.callback_query.data = "link:summary:a1b2c3d4e5"
        meta_dict = {
            "url": "https://example.com",
            "link_type": "article",
            "title": "Test",
            "description": "",
            "site_name": "",
            "thumbnail_url": "",
            "youtube_id": None,
            "duration": "",
            "has_transcript": False,
        }
        mock_context.user_data["_link_meta"] = {"a1b2c3d4e5": meta_dict}

        with patch("koda.services.queue_manager.enqueue_link_analysis", new_callable=AsyncMock) as mock_enqueue:
            await callback_link_analysis(mock_callback_update, mock_context)
            mock_enqueue.assert_called_once()
            # Verify prompt contains the URL
            prompt = mock_enqueue.call_args[0][3]
            assert "https://example.com" in prompt

    @pytest.mark.asyncio
    async def test_callback_link_analysis_thumbnail(self, mock_callback_update, mock_context):
        """YouTube thumbnail should send photo directly without provider execution."""
        mock_callback_update.callback_query.data = "link:thumbnail:a1b2c3d4e5"
        meta_dict = {
            "url": "https://youtube.com/watch?v=abc12345678",
            "link_type": "video",
            "title": "Test Video",
            "description": "",
            "site_name": "YouTube",
            "thumbnail_url": "",
            "youtube_id": "abc12345678",
            "duration": "",
            "has_transcript": False,
        }
        mock_context.user_data["_link_meta"] = {"a1b2c3d4e5": meta_dict}

        with patch("koda.services.queue_manager.enqueue_link_analysis", new_callable=AsyncMock) as mock_enqueue:
            await callback_link_analysis(mock_callback_update, mock_context)
            mock_enqueue.assert_not_called()
            mock_context.bot.send_photo.assert_called_once()
            photo_url = mock_context.bot.send_photo.call_args[1]["photo"]
            assert "abc12345678" in photo_url

    @pytest.mark.asyncio
    async def test_callback_link_analysis_expired_metadata(self, mock_callback_update, mock_context):
        """When metadata is not found, should show error message."""
        mock_callback_update.callback_query.data = "link:summary:nonexistent"
        mock_context.user_data["_link_meta"] = {}

        await callback_link_analysis(mock_callback_update, mock_context)
        mock_callback_update.callback_query.edit_message_text.assert_called_once()
        call_text = mock_callback_update.callback_query.edit_message_text.call_args[0][0]
        assert "expirados" in call_text.lower()

    @pytest.mark.asyncio
    async def test_callback_link_analysis_transcript_direct(self, mock_callback_update, mock_context):
        """Transcript should send text directly without provider execution."""
        mock_callback_update.callback_query.data = "link:transcript:a1b2c3d4e5"
        meta_dict = {
            "url": "https://youtube.com/watch?v=abc12345678",
            "link_type": "video",
            "title": "Test Video",
            "description": "",
            "site_name": "YouTube",
            "thumbnail_url": "",
            "youtube_id": "abc12345678",
            "duration": "",
            "has_transcript": True,
        }
        mock_context.user_data["_link_meta"] = {"a1b2c3d4e5": meta_dict}

        with (
            patch(
                "koda.services.link_analyzer.fetch_youtube_transcript",
                new_callable=AsyncMock,
                return_value="[00:00] Hello world\n[00:05] This is a test",
            ),
            patch(
                "koda.services.queue_manager.enqueue_link_analysis",
                new_callable=AsyncMock,
            ) as mock_enqueue,
        ):
            await callback_link_analysis(mock_callback_update, mock_context)
            # Should NOT go through provider execution
            mock_enqueue.assert_not_called()
            # Should send message directly
            mock_context.bot.send_message.assert_called()
            sent_text = mock_context.bot.send_message.call_args[1]["text"]
            assert "Transcrição" in sent_text
            assert "Hello world" in sent_text

    @pytest.mark.asyncio
    async def test_callback_link_analysis_transcript_unavailable(self, mock_callback_update, mock_context):
        """Transcript unavailable should show error without calling provider execution."""
        mock_callback_update.callback_query.data = "link:transcript:a1b2c3d4e5"
        meta_dict = {
            "url": "https://youtube.com/watch?v=abc12345678",
            "link_type": "video",
            "title": "Test Video",
            "description": "",
            "site_name": "YouTube",
            "thumbnail_url": "",
            "youtube_id": "abc12345678",
            "duration": "",
            "has_transcript": False,
        }
        mock_context.user_data["_link_meta"] = {"a1b2c3d4e5": meta_dict}

        with (
            patch(
                "koda.services.link_analyzer.fetch_youtube_transcript",
                new_callable=AsyncMock,
                return_value=None,
            ),
            patch(
                "koda.services.queue_manager.enqueue_link_analysis",
                new_callable=AsyncMock,
            ) as mock_enqueue,
        ):
            await callback_link_analysis(mock_callback_update, mock_context)
            mock_enqueue.assert_not_called()
            mock_context.bot.send_message.assert_called_once()
            sent_text = mock_context.bot.send_message.call_args[1]["text"]
            assert "não foi possível" in sent_text.lower()


class TestCallbackProvider:
    @pytest.mark.asyncio
    async def test_callback_provider_sets_provider(self, mock_callback_update, mock_context):
        mock_callback_update.callback_query.data = "provider:codex"
        with patch(
            "koda.handlers.callbacks.set_agent_general_provider",
            return_value={
                "default_provider": "codex",
                "general_model": "gpt-5.4",
                "default_models_by_provider": {"codex": "gpt-5.4"},
                "functional_defaults": {"general": {"provider_id": "codex", "model_id": "gpt-5.4"}},
                "transcription_provider": "whispercpp",
                "transcription_model": "whisper-cpp-local",
                "audio_provider": "kokoro",
                "audio_model": "kokoro-v1",
                "tts_voice": "pf_dora",
                "tts_voice_label": "Dora",
                "tts_voice_language": "pt-br",
                "selectable_function_options": {
                    "general": [
                        {
                            "provider_id": "codex",
                            "model_id": "gpt-5.4",
                            "provider_title": "Codex",
                            "title": "gpt-5.4",
                        }
                    ]
                },
            },
        ):
            await callback_provider(mock_callback_update, mock_context)
        assert mock_context.user_data["provider"] == "codex"
        assert mock_context.user_data["model"].startswith("gpt-")


class TestCallbackFeedback:
    @pytest.mark.asyncio
    async def test_risky_feedback_creates_pending_risk_candidate(self, mock_callback_update, mock_context):
        mock_callback_update.callback_query.data = "feedback:risky:77"
        with (
            patch(
                "koda.handlers.callbacks.get_latest_execution_episode",
                return_value={
                    "id": 12,
                    "task_kind": "deploy",
                    "project_key": "workspace",
                    "environment": "prod",
                    "team": "agent_a",
                    "status": "completed",
                    "verified_before_finalize": True,
                    "confidence_score": 0.91,
                    "source_refs": [{"source_label": "agent_a.toml", "layer": "canonical_policy"}],
                    "plan": {"summary": "Deploy safely"},
                },
            ),
            patch("koda.handlers.callbacks.get_correction_event", return_value=None),
            patch("koda.handlers.callbacks.record_correction_event", return_value=9),
            patch("koda.handlers.callbacks.update_execution_reliability_stats") as mock_stats,
            patch("koda.handlers.callbacks.upsert_knowledge_candidate") as mock_candidate,
            patch("koda.handlers.callbacks.record_utility_event") as mock_utility,
            patch("koda.services.metrics.HUMAN_CORRECTION_EVENTS"),
        ):
            await callback_feedback(mock_callback_update, mock_context)

        mock_stats.assert_called_once()
        assert mock_stats.call_args.kwargs["count_execution"] is False
        assert mock_candidate.call_args.kwargs["candidate_type"] == "risk_pattern"
        assert mock_candidate.call_args.kwargs["force_pending"] is True
        mock_utility.assert_called_once_with("AGENT_A", "noise")
        mock_callback_update.callback_query.answer.assert_called()

    @pytest.mark.asyncio
    async def test_invalid_payload_is_rejected(self, mock_callback_update, mock_context):
        mock_callback_update.callback_query.data = "feedback:broken"

        await callback_feedback(mock_callback_update, mock_context)

        mock_callback_update.callback_query.answer.assert_any_call("Invalid feedback payload.", show_alert=True)

    @pytest.mark.asyncio
    async def test_invalid_task_id_is_rejected(self, mock_callback_update, mock_context):
        mock_callback_update.callback_query.data = "feedback:risky:not-a-number"

        await callback_feedback(mock_callback_update, mock_context)

        mock_callback_update.callback_query.answer.assert_any_call("Invalid task id.", show_alert=True)

    @pytest.mark.asyncio
    async def test_missing_execution_episode_is_rejected(self, mock_callback_update, mock_context):
        mock_callback_update.callback_query.data = "feedback:risky:77"
        with patch("koda.handlers.callbacks.get_latest_execution_episode", return_value=None):
            await callback_feedback(mock_callback_update, mock_context)

        mock_callback_update.callback_query.answer.assert_any_call(
            "No execution episode found for this task.",
            show_alert=True,
        )

    @pytest.mark.asyncio
    async def test_duplicate_feedback_is_idempotent(self, mock_callback_update, mock_context):
        mock_callback_update.callback_query.data = "feedback:approved:77"
        with (
            patch(
                "koda.handlers.callbacks.get_latest_execution_episode",
                return_value={
                    "id": 12,
                    "task_kind": "deploy",
                    "project_key": "workspace",
                    "environment": "prod",
                    "team": "agent_a",
                    "status": "completed",
                    "verified_before_finalize": True,
                    "confidence_score": 0.91,
                    "source_refs": [{"source_label": "agent_a.toml", "layer": "canonical_policy"}],
                    "plan": {"summary": "Deploy safely", "verification": ["Run smoke tests"]},
                    "stale_sources_present": False,
                    "ungrounded_operationally": False,
                    "answer_gate_status": "approved",
                    "post_write_review_required": False,
                },
            ),
            patch("koda.handlers.callbacks.get_correction_event", return_value={"id": 33}),
            patch("koda.handlers.callbacks.record_correction_event") as mock_record,
            patch("koda.handlers.callbacks.upsert_knowledge_candidate") as mock_candidate,
            patch("koda.services.metrics.HUMAN_CORRECTION_EVENTS"),
        ):
            await callback_feedback(mock_callback_update, mock_context)

        mock_record.assert_not_called()
        mock_candidate.assert_not_called()
        mock_callback_update.callback_query.answer.assert_any_call(
            "Feedback already recorded for this execution.",
            show_alert=True,
        )

    @pytest.mark.asyncio
    async def test_promote_feedback_creates_success_candidate_and_marks_useful(
        self,
        mock_callback_update,
        mock_context,
    ):
        mock_callback_update.callback_query.data = "feedback:promote:77"
        with (
            patch(
                "koda.handlers.callbacks.get_latest_execution_episode",
                return_value={
                    "id": 12,
                    "task_kind": "deploy",
                    "project_key": "workspace",
                    "environment": "prod",
                    "team": "agent_a",
                    "status": "completed",
                    "verified_before_finalize": True,
                    "confidence_score": 0.91,
                    "source_refs": [{"source_label": "agent_a.toml", "layer": "canonical_policy"}],
                    "plan": {
                        "summary": "Deploy safely",
                        "verification": ["Run smoke tests"],
                        "steps": ["Apply deployment manifests", "Verify rollout"],
                        "rollback": "Rollback deployment if smoke tests fail.",
                    },
                    "stale_sources_present": False,
                    "ungrounded_operationally": False,
                    "answer_gate_status": "approved",
                    "post_write_review_required": False,
                },
            ),
            patch("koda.handlers.callbacks.get_correction_event", return_value=None),
            patch("koda.handlers.callbacks.record_correction_event", return_value=9),
            patch("koda.handlers.callbacks.update_execution_reliability_stats") as mock_stats,
            patch("koda.handlers.callbacks.upsert_knowledge_candidate") as mock_candidate,
            patch("koda.handlers.callbacks.record_utility_event") as mock_utility,
            patch("koda.services.metrics.HUMAN_CORRECTION_EVENTS"),
        ):
            await callback_feedback(mock_callback_update, mock_context)

        assert mock_candidate.call_args.kwargs["candidate_type"] == "success_pattern"
        mock_stats.assert_called_once()
        mock_utility.assert_called_once_with("AGENT_A", "useful")

    @pytest.mark.asyncio
    async def test_corrected_feedback_marks_memory_as_misleading(self, mock_callback_update, mock_context):
        mock_callback_update.callback_query.data = "feedback:corrected:77"
        with (
            patch(
                "koda.handlers.callbacks.get_latest_execution_episode",
                return_value={
                    "id": 12,
                    "task_kind": "deploy",
                    "project_key": "workspace",
                    "environment": "prod",
                    "team": "agent_a",
                    "status": "completed",
                    "verified_before_finalize": False,
                    "confidence_score": 0.91,
                    "source_refs": [],
                    "plan": {"summary": "Deploy safely"},
                },
            ),
            patch("koda.handlers.callbacks.get_correction_event", return_value=None),
            patch("koda.handlers.callbacks.record_correction_event", return_value=9),
            patch("koda.handlers.callbacks.update_execution_reliability_stats"),
            patch("koda.handlers.callbacks.upsert_knowledge_candidate"),
            patch("koda.handlers.callbacks.record_utility_event") as mock_utility,
            patch("koda.services.metrics.HUMAN_CORRECTION_EVENTS"),
        ):
            await callback_feedback(mock_callback_update, mock_context)

        mock_utility.assert_called_once_with("AGENT_A", "misleading")

    @pytest.mark.asyncio
    async def test_promote_feedback_is_blocked_when_gates_fail(self, mock_callback_update, mock_context):
        mock_callback_update.callback_query.data = "feedback:promote:77"
        with (
            patch(
                "koda.handlers.callbacks.get_latest_execution_episode",
                return_value={
                    "id": 12,
                    "task_kind": "deploy",
                    "project_key": "workspace",
                    "environment": "prod",
                    "team": "agent_a",
                    "status": "completed",
                    "verified_before_finalize": True,
                    "confidence_score": 0.91,
                    "source_refs": [],
                    "plan": {"summary": "Deploy safely", "verification": ["Run smoke tests"]},
                    "stale_sources_present": True,
                    "ungrounded_operationally": True,
                    "answer_gate_status": "needs_review",
                    "post_write_review_required": True,
                },
            ),
            patch("koda.handlers.callbacks.get_correction_event", return_value=None),
            patch("koda.handlers.callbacks.record_correction_event", return_value=9),
            patch("koda.handlers.callbacks.update_execution_reliability_stats") as mock_stats,
            patch("koda.handlers.callbacks.upsert_knowledge_candidate") as mock_candidate,
            patch("koda.handlers.callbacks.record_utility_event") as mock_utility,
            patch("koda.services.metrics.HUMAN_CORRECTION_EVENTS"),
        ):
            await callback_feedback(mock_callback_update, mock_context)

        mock_candidate.assert_not_called()
        mock_stats.assert_called_once()
        mock_utility.assert_called_once_with("AGENT_A", "noise")
        mock_callback_update.callback_query.answer.assert_any_call(
            "Promotion blocked: missing minimum gates for reusable routine creation.",
            show_alert=True,
        )

    @pytest.mark.asyncio
    async def test_approved_feedback_reinforces_success_candidate(self, mock_callback_update, mock_context):
        mock_callback_update.callback_query.data = "feedback:approved:77"
        with (
            patch(
                "koda.handlers.callbacks.get_latest_execution_episode",
                return_value={
                    "id": 12,
                    "task_kind": "deploy",
                    "project_key": "workspace",
                    "environment": "prod",
                    "team": "agent_a",
                    "status": "completed",
                    "verified_before_finalize": True,
                    "confidence_score": 0.91,
                    "source_refs": [{"source_label": "agent_a.toml", "layer": "canonical_policy"}],
                    "plan": {
                        "summary": "Deploy safely",
                        "verification": ["Run smoke tests"],
                        "steps": ["Apply deployment manifests", "Verify rollout"],
                        "rollback": "Rollback deployment if smoke tests fail.",
                    },
                    "stale_sources_present": False,
                    "ungrounded_operationally": False,
                    "answer_gate_status": "approved",
                    "post_write_review_required": False,
                },
            ),
            patch("koda.handlers.callbacks.get_correction_event", return_value=None),
            patch("koda.handlers.callbacks.record_correction_event", return_value=9),
            patch("koda.handlers.callbacks.update_execution_reliability_stats") as mock_stats,
            patch("koda.handlers.callbacks.upsert_knowledge_candidate") as mock_candidate,
            patch("koda.handlers.callbacks.record_utility_event") as mock_utility,
            patch("koda.services.metrics.HUMAN_CORRECTION_EVENTS"),
        ):
            await callback_feedback(mock_callback_update, mock_context)

        assert mock_candidate.call_args.kwargs["candidate_type"] == "success_pattern"
        mock_stats.assert_called_once()
        mock_utility.assert_called_once_with("AGENT_A", "useful")
        mock_callback_update.callback_query.answer.assert_any_call(
            "Feedback registrado como aprovado. Abri um candidato de rotina positiva para revisão.",
            show_alert=True,
        )
