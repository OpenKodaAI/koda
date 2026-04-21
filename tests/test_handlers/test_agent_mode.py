"""Tests for agent mode (autonomous/supervised) feature."""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from koda.handlers.callbacks import callback_mode, callback_supervised
from koda.handlers.commands import cmd_mode
from koda.services.provider_runtime import ProviderCapabilities
from koda.utils.command_helpers import init_user_data


class TestCmdMode:
    @pytest.mark.asyncio
    async def test_no_args_shows_keyboard(self, mock_update, mock_context):
        mock_context.args = []
        init_user_data(mock_context.user_data)
        await cmd_mode(mock_update, mock_context)
        call_kwargs = mock_update.message.reply_text.call_args
        assert "reply_markup" in call_kwargs.kwargs or call_kwargs[1].get("reply_markup")
        call_text = call_kwargs[0][0]
        assert "autonomous" in call_text

    @pytest.mark.asyncio
    async def test_set_autonomous(self, mock_update, mock_context):
        mock_context.args = ["autonomous"]
        init_user_data(mock_context.user_data)
        await cmd_mode(mock_update, mock_context)
        assert mock_context.user_data["agent_mode"] == "autonomous"

    @pytest.mark.asyncio
    async def test_set_supervised(self, mock_update, mock_context):
        mock_context.args = ["supervised"]
        init_user_data(mock_context.user_data)
        await cmd_mode(mock_update, mock_context)
        assert mock_context.user_data["agent_mode"] == "supervised"

    @pytest.mark.asyncio
    async def test_invalid_mode(self, mock_update, mock_context):
        mock_context.args = ["turbo"]
        init_user_data(mock_context.user_data)
        await cmd_mode(mock_update, mock_context)
        call_text = mock_update.message.reply_text.call_args[0][0]
        assert "Unknown mode" in call_text


class TestCallbackMode:
    @pytest.mark.asyncio
    async def test_sets_mode(self, mock_update, mock_context):
        query = AsyncMock()
        query.data = "mode:supervised"
        query.answer = AsyncMock()
        query.edit_message_text = AsyncMock()
        mock_update.callback_query = query
        init_user_data(mock_context.user_data)
        await callback_mode(mock_update, mock_context)
        assert mock_context.user_data["agent_mode"] == "supervised"
        query.edit_message_text.assert_called_once()

    @pytest.mark.asyncio
    async def test_ignores_invalid_mode(self, mock_update, mock_context):
        query = AsyncMock()
        query.data = "mode:invalid"
        query.answer = AsyncMock()
        query.edit_message_text = AsyncMock()
        mock_update.callback_query = query
        init_user_data(mock_context.user_data)
        await callback_mode(mock_update, mock_context)
        # Should remain at default
        assert mock_context.user_data["agent_mode"] == "autonomous"
        query.edit_message_text.assert_not_called()


class TestCallbackSupervised:
    @pytest.mark.asyncio
    async def test_continue_enqueues(self, mock_update, mock_context):
        query = AsyncMock()
        query.data = "supervised:continue"
        query.answer = AsyncMock()
        query.edit_message_text = AsyncMock()
        query.message = MagicMock()
        query.message.text = "Some response"
        mock_update.callback_query = query
        mock_update.effective_user.id = 111
        mock_update.effective_chat.id = 111
        init_user_data(mock_context.user_data)
        mock_context.user_data["_supervised_session_id"] = "test-session-123"

        with patch("koda.services.queue_manager.enqueue_continuation", new_callable=AsyncMock) as mock_enqueue:
            await callback_supervised(mock_update, mock_context)
            mock_enqueue.assert_called_once_with(111, 111, mock_context)

    @pytest.mark.asyncio
    async def test_stop_edits_message(self, mock_update, mock_context):
        query = AsyncMock()
        query.data = "supervised:stop"
        query.answer = AsyncMock()
        query.edit_message_text = AsyncMock()
        query.message = MagicMock()
        query.message.text = "Some response"
        mock_update.callback_query = query
        init_user_data(mock_context.user_data)

        await callback_supervised(mock_update, mock_context)
        call_text = query.edit_message_text.call_args[0][0]
        assert "[Stopped]" in call_text


class TestStreamingMetadataCollector:
    @pytest.mark.asyncio
    async def test_metadata_collector_captures_tool_uses(self):
        """Test that metadata_collector is populated during streaming."""
        # Simulate stream events
        events = [
            json.dumps(
                {
                    "type": "assistant",
                    "message": {
                        "content": [
                            {"type": "tool_use", "name": "Read", "input": {"file_path": "/a.py"}},
                            {"type": "text", "text": "Reading file..."},
                        ]
                    },
                }
            ),
            json.dumps(
                {
                    "type": "result",
                    "result": "Done",
                    "session_id": "sess-abc",
                    "total_cost_usd": 0.05,
                    "stop_reason": "max_turns",
                }
            ),
        ]
        stream_data = "\n".join(events) + "\n"

        mock_proc = AsyncMock()
        mock_proc.stdin = AsyncMock()
        mock_proc.stdin.write = MagicMock()
        mock_proc.stdin.drain = AsyncMock()
        mock_proc.stdin.close = MagicMock()
        mock_proc.stdin.wait_closed = AsyncMock()
        mock_proc.returncode = 0
        mock_proc.stderr = AsyncMock()
        mock_proc.wait = AsyncMock()

        # Simulate readline
        lines = [line.encode() + b"\n" for line in stream_data.strip().split("\n")]
        lines.append(b"")  # EOF
        mock_proc.stdout = AsyncMock()
        mock_proc.stdout.readline = AsyncMock(side_effect=lines)

        metadata_collector: dict = {}

        ready = ProviderCapabilities(
            provider="claude",
            turn_mode="new_turn",
            status="ready",
            can_execute=True,
            supports_native_resume=True,
            checked_via="auth_status",
        )

        with (
            patch("koda.services.claude_runner._probe_claude_auth_status", new=AsyncMock(return_value=ready)),
            patch("koda.services.claude_runner.asyncio.create_subprocess_exec", return_value=mock_proc),
        ):
            from koda.services.claude_runner import run_claude_streaming

            chunks = []
            async for chunk in run_claude_streaming(
                query="test",
                work_dir="/tmp",
                model="claude-sonnet-4-6",
                metadata_collector=metadata_collector,
            ):
                chunks.append(chunk)

        assert "Reading file..." in chunks
        assert len(metadata_collector.get("tool_uses", [])) == 1
        assert metadata_collector["tool_uses"][0]["name"] == "Read"
        assert metadata_collector["session_id"] == "sess-abc"
        assert metadata_collector["cost_usd"] == 0.05
        assert metadata_collector["stop_reason"] == "max_turns"

    @pytest.mark.asyncio
    async def test_tool_only_streaming_no_fallback_to_nonstreaming(self):
        """When streaming emits only tool_use (no text), metadata with stop_reason
        should prevent fallback to non-streaming, avoiding raw JSON in output."""
        # Simulate stream events: only tool_use, no text content
        events = [
            json.dumps(
                {
                    "type": "assistant",
                    "message": {
                        "content": [
                            {"type": "tool_use", "name": "Bash", "input": {"command": "glab mr list"}},
                        ]
                    },
                }
            ),
            json.dumps(
                {
                    "type": "result",
                    "result": "",
                    "session_id": "sess-tool-only",
                    "total_cost_usd": 0.03,
                    "stop_reason": "max_turns",
                }
            ),
        ]
        stream_data = "\n".join(events) + "\n"

        mock_proc = AsyncMock()
        mock_proc.stdin = AsyncMock()
        mock_proc.stdin.write = MagicMock()
        mock_proc.stdin.drain = AsyncMock()
        mock_proc.stdin.close = MagicMock()
        mock_proc.stdin.wait_closed = AsyncMock()
        mock_proc.returncode = 0
        mock_proc.stderr = AsyncMock()
        mock_proc.wait = AsyncMock()

        lines = [line.encode() + b"\n" for line in stream_data.strip().split("\n")]
        lines.append(b"")  # EOF
        mock_proc.stdout = AsyncMock()
        mock_proc.stdout.readline = AsyncMock(side_effect=lines)

        metadata_collector: dict = {}

        ready = ProviderCapabilities(
            provider="claude",
            turn_mode="new_turn",
            status="ready",
            can_execute=True,
            supports_native_resume=True,
            checked_via="auth_status",
        )

        with (
            patch("koda.services.claude_runner._probe_claude_auth_status", new=AsyncMock(return_value=ready)),
            patch("koda.services.claude_runner.asyncio.create_subprocess_exec", return_value=mock_proc),
        ):
            from koda.services.claude_runner import run_claude_streaming

            chunks = []
            async for chunk in run_claude_streaming(
                query="list merge requests",
                work_dir="/tmp",
                model="claude-sonnet-4-6",
                metadata_collector=metadata_collector,
            ):
                chunks.append(chunk)

        # No text chunks emitted (tool-only)
        assert chunks == []
        # But metadata IS populated
        assert metadata_collector["session_id"] == "sess-tool-only"
        assert metadata_collector["stop_reason"] == "max_turns"
        assert len(metadata_collector.get("tool_uses", [])) == 1

        # Simulate what queue_manager builds from this result
        full_response = "".join(chunks)
        result = {
            "result": full_response,
            "session_id": metadata_collector.get("session_id"),
            "cost_usd": metadata_collector.get("cost_usd", 0.0),
            "_stop_reason": metadata_collector.get("stop_reason", ""),
            "_tool_uses": metadata_collector.get("tool_uses", []),
        }

        # The fix: fallback condition should NOT trigger because _stop_reason is set
        should_fallback = result is None or (not result.get("result") and not result.get("_stop_reason"))
        assert not should_fallback, "Should NOT fallback to non-streaming when metadata has stop_reason"

        # Tool summary should be used as the response
        from koda.utils.tool_parser import summarize_tool_uses

        tool_summary = summarize_tool_uses(result["_tool_uses"])
        assert tool_summary  # non-empty
        assert "Bash" in tool_summary

        # Build final response like queue_manager does
        response = result["result"]
        if not response and tool_summary:
            response = tool_summary
        elif tool_summary:
            response = f"{tool_summary}\n\n{response}"

        # Response should be tool summary, NOT raw JSON
        assert "Bash" in response
        assert "{" not in response.split("Used:")[0]  # no JSON before tool summary
