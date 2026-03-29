"""Tests for Claude CLI runner."""

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from koda.services.claude_runner import (
    clear_claude_capability_cache,
    get_claude_capabilities,
    run_claude,
    run_claude_streaming,
)
from koda.services.provider_runtime import ProviderCapabilities


@pytest.fixture(autouse=True)
def _mock_claude_auth_probe():
    clear_claude_capability_cache()
    ready = ProviderCapabilities(
        provider="claude",
        turn_mode="new_turn",
        status="ready",
        can_execute=True,
        supports_native_resume=True,
        checked_via="auth_status",
    )
    with patch("koda.services.claude_runner._probe_claude_auth_status", new=AsyncMock(return_value=ready)):
        yield
    clear_claude_capability_cache()


@pytest.fixture(autouse=True)
def _isolate_claude_breaker():
    with (
        patch("koda.services.resilience.check_breaker", return_value=None),
        patch("koda.services.resilience.record_failure"),
        patch("koda.services.resilience.record_success"),
    ):
        yield


class TestRunClaude:
    @pytest.mark.asyncio
    async def test_successful_run(self):
        mock_result = {
            "result": "Hello! I can help with that.",
            "session_id": "sess-123",
            "total_cost_usd": 0.01,
        }
        mock_proc = AsyncMock()
        mock_proc.communicate = AsyncMock(return_value=(json.dumps(mock_result).encode(), b""))
        mock_proc.returncode = 0

        with patch("koda.services.claude_runner.asyncio.create_subprocess_exec", return_value=mock_proc):
            result = await run_claude(
                query="Hello",
                work_dir="/tmp",
                model="claude-sonnet-4-6",
            )

        assert result["result"] == "Hello! I can help with that."
        assert result["session_id"] == "sess-123"
        assert result["cost_usd"] == 0.01
        assert result["error"] is False

    @pytest.mark.asyncio
    async def test_timeout(self):
        mock_proc = AsyncMock()
        mock_proc.communicate = AsyncMock(side_effect=TimeoutError())
        mock_proc.kill = AsyncMock()
        mock_proc.wait = AsyncMock()

        with patch("koda.services.claude_runner.asyncio.create_subprocess_exec", return_value=mock_proc):
            result = await run_claude(
                query="Complex query",
                work_dir="/tmp",
                model="claude-sonnet-4-6",
            )

        assert result["error"] is True
        assert "Timeout" in result["result"]

    @pytest.mark.asyncio
    async def test_cli_error_non_retryable(self):
        mock_proc = AsyncMock()
        mock_proc.communicate = AsyncMock(return_value=(b"", b"Some fatal error"))
        mock_proc.returncode = 1

        with patch("koda.services.claude_runner.asyncio.create_subprocess_exec", return_value=mock_proc):
            result = await run_claude(
                query="test",
                work_dir="/tmp",
                model="claude-sonnet-4-6",
            )

        assert result["error"] is True
        assert "fatal error" in result["result"]

    @pytest.mark.asyncio
    async def test_cli_error_invalid_session_is_classified(self):
        mock_proc = AsyncMock()
        mock_proc.communicate = AsyncMock(
            return_value=(b"", b"No conversation found with session ID: 8d991867-e598-4420-b562-44d59df0fc75")
        )
        mock_proc.returncode = 1

        with patch("koda.services.claude_runner.asyncio.create_subprocess_exec", return_value=mock_proc):
            result = await run_claude(
                query="test",
                work_dir="/tmp",
                model="claude-sonnet-4-6",
                session_id="8d991867-e598-4420-b562-44d59df0fc75",
            )

        assert result["error"] is True
        assert result["_error_kind"] == "invalid_session"
        assert result["_retryable"] is False

    @pytest.mark.asyncio
    async def test_process_holder_gets_populated(self):
        mock_result = {"result": "ok", "session_id": None, "total_cost_usd": 0}
        mock_proc = AsyncMock()
        mock_proc.communicate = AsyncMock(return_value=(json.dumps(mock_result).encode(), b""))
        mock_proc.returncode = 0

        holder = {}
        with patch("koda.services.claude_runner.asyncio.create_subprocess_exec", return_value=mock_proc):
            await run_claude(
                query="test",
                work_dir="/tmp",
                model="claude-sonnet-4-6",
                process_holder=holder,
            )

        assert holder["proc"] is mock_proc

    @pytest.mark.asyncio
    async def test_json_multiline_parsing(self):
        """Test parsing when stdout has multiple JSON lines."""
        line1 = json.dumps({"partial": True})
        line2 = json.dumps({"result": "Final answer", "session_id": "s1", "total_cost_usd": 0.05})
        stdout = f"{line1}\n{line2}".encode()

        mock_proc = AsyncMock()
        mock_proc.communicate = AsyncMock(return_value=(stdout, b""))
        mock_proc.returncode = 0

        with patch("koda.services.claude_runner.asyncio.create_subprocess_exec", return_value=mock_proc):
            result = await run_claude(
                query="test",
                work_dir="/tmp",
                model="claude-sonnet-4-6",
            )

        assert result["result"] == "Final answer"

    @pytest.mark.asyncio
    async def test_session_resume(self):
        mock_result = {"result": "Resumed", "session_id": "sess-123", "total_cost_usd": 0}
        mock_proc = AsyncMock()
        mock_proc.communicate = AsyncMock(return_value=(json.dumps(mock_result).encode(), b""))
        mock_proc.returncode = 0

        exec_path = "koda.services.claude_runner.asyncio.create_subprocess_exec"
        with patch(exec_path, return_value=mock_proc) as mock_exec:
            await run_claude(
                query="test",
                work_dir="/tmp",
                model="claude-sonnet-4-6",
                session_id="sess-123",
            )

        call_args = mock_exec.call_args[0]
        assert "--resume" in call_args
        assert "sess-123" in call_args

    @pytest.mark.asyncio
    async def test_dry_run_forces_plan_permission_mode(self):
        mock_result = {"result": "Planned", "session_id": "sess-123", "total_cost_usd": 0}
        mock_proc = AsyncMock()
        mock_proc.communicate = AsyncMock(return_value=(json.dumps(mock_result).encode(), b""))
        mock_proc.returncode = 0

        exec_path = "koda.services.claude_runner.asyncio.create_subprocess_exec"
        with patch(exec_path, return_value=mock_proc) as mock_exec:
            await run_claude(
                query="test",
                work_dir="/tmp",
                model="claude-sonnet-4-6",
                permission_mode="bypassPermissions",
                dry_run=True,
            )

        call_args = mock_exec.call_args[0]
        assert "--permission-mode" in call_args
        index = call_args.index("--permission-mode")
        assert call_args[index + 1] == "plan"

    @pytest.mark.asyncio
    async def test_empty_result_returns_generic_message_not_raw_json(self):
        """When JSON result and response are both empty, return generic message, not raw JSON."""
        # Simulate CLI output where result/response are empty (tool-only execution)
        mock_data = {
            "result": "",
            "response": "",
            "session_id": "sess-456",
            "total_cost_usd": 0.02,
            "stop_reason": "max_turns",
        }
        mock_proc = AsyncMock()
        mock_proc.communicate = AsyncMock(return_value=(json.dumps(mock_data).encode(), b""))
        mock_proc.returncode = 0

        with patch("koda.services.claude_runner.asyncio.create_subprocess_exec", return_value=mock_proc):
            result = await run_claude(
                query="list MRs",
                work_dir="/tmp",
                model="claude-sonnet-4-6",
            )

        # Should NOT contain raw JSON
        assert "{" not in result["result"]
        assert "Task completed" in result["result"]
        assert result["session_id"] == "sess-456"
        assert result["_stop_reason"] == "max_turns"

    @pytest.mark.asyncio
    async def test_embedded_auth_result_is_treated_as_error(self):
        mock_data = {
            "result": (
                'Failed to authenticate. API Error: 401 {"type":"error","error":{"type":"authentication_error",'
                '"message":"Invalid authentication credentials"}}'
            ),
            "session_id": "sess-456",
            "total_cost_usd": 0.0,
            "stop_reason": "stop_sequence",
        }
        mock_proc = AsyncMock()
        mock_proc.communicate = AsyncMock(return_value=(json.dumps(mock_data).encode(), b""))
        mock_proc.returncode = 0

        with patch("koda.services.claude_runner.asyncio.create_subprocess_exec", return_value=mock_proc):
            result = await run_claude(
                query="test",
                work_dir="/tmp",
                model="claude-opus-4-6",
            )

        assert result["error"] is True
        assert result["_error_kind"] == "provider_auth"
        assert "Claude authentication failed" in result["result"]

    @pytest.mark.asyncio
    async def test_process_holder_event_set(self):
        """Event on process_holder is set when process starts."""
        mock_result = {"result": "ok", "session_id": None, "total_cost_usd": 0}
        mock_proc = AsyncMock()
        mock_proc.communicate = AsyncMock(return_value=(json.dumps(mock_result).encode(), b""))
        mock_proc.returncode = 0

        event = asyncio.Event()
        holder = {"event": event}
        with patch("koda.services.claude_runner.asyncio.create_subprocess_exec", return_value=mock_proc):
            await run_claude(
                query="test",
                work_dir="/tmp",
                model="claude-sonnet-4-6",
                process_holder=holder,
            )

        assert event.is_set()


def _make_stream_proc(lines: list[str], stderr: bytes = b"") -> AsyncMock:
    """Create a mock process that yields lines from stdout."""
    mock_proc = AsyncMock()

    line_iter = iter(lines)

    async def _readline() -> bytes:
        try:
            return (next(line_iter) + "\n").encode()
        except StopIteration:
            return b""

    mock_stdout = MagicMock()
    mock_stdout.readline = _readline

    mock_stdin = MagicMock()
    mock_stdin.write = MagicMock()
    mock_stdin.drain = AsyncMock()
    mock_stdin.close = MagicMock()
    mock_stdin.wait_closed = AsyncMock()

    mock_stderr = MagicMock()
    mock_stderr.read = AsyncMock(return_value=stderr)

    mock_proc.stdout = mock_stdout
    mock_proc.stdin = mock_stdin
    mock_proc.stderr = mock_stderr
    mock_proc.wait = AsyncMock()
    mock_proc.kill = AsyncMock()
    mock_proc.returncode = 0

    return mock_proc


class TestRunClaudeStreaming:
    @pytest.mark.asyncio
    async def test_assistant_event_yields_text(self):
        """CLI assistant events with message.content text blocks yield text."""
        lines = [
            json.dumps({"type": "system", "subtype": "init", "session_id": "s1"}),
            json.dumps(
                {
                    "type": "assistant",
                    "message": {"content": [{"type": "text", "text": "Hello!"}]},
                    "session_id": "s1",
                }
            ),
            json.dumps({"type": "result", "result": "Hello!", "session_id": "s1"}),
        ]
        mock_proc = _make_stream_proc(lines)

        with patch("koda.services.claude_runner.asyncio.create_subprocess_exec", return_value=mock_proc):
            chunks = []
            async for chunk in run_claude_streaming(query="test", work_dir="/tmp", model="claude-sonnet-4-6"):
                chunks.append(chunk)

        # Text from assistant event; result event skipped (not duplicated)
        assert chunks == ["Hello!"]

    @pytest.mark.asyncio
    async def test_assistant_skips_thinking_blocks(self):
        """Thinking blocks in assistant events are not yielded."""
        lines = [
            json.dumps(
                {
                    "type": "assistant",
                    "message": {"content": [{"type": "thinking", "thinking": "hmm"}]},
                }
            ),
            json.dumps(
                {
                    "type": "assistant",
                    "message": {"content": [{"type": "text", "text": "Answer"}]},
                }
            ),
            json.dumps({"type": "result", "result": "Answer"}),
        ]
        mock_proc = _make_stream_proc(lines)

        with patch("koda.services.claude_runner.asyncio.create_subprocess_exec", return_value=mock_proc):
            chunks = []
            async for chunk in run_claude_streaming(query="test", work_dir="/tmp", model="claude-sonnet-4-6"):
                chunks.append(chunk)

        assert chunks == ["Answer"]

    @pytest.mark.asyncio
    async def test_content_block_delta_compatibility(self):
        """content_block_delta events still work (raw API compatibility)."""
        lines = [
            json.dumps({"type": "content_block_delta", "delta": {"type": "text_delta", "text": "Hi"}}),
            json.dumps({"type": "result", "result": "Hi"}),
        ]
        mock_proc = _make_stream_proc(lines)

        with patch("koda.services.claude_runner.asyncio.create_subprocess_exec", return_value=mock_proc):
            chunks = []
            async for chunk in run_claude_streaming(query="test", work_dir="/tmp", model="claude-sonnet-4-6"):
                chunks.append(chunk)

        assert chunks == ["Hi"]

    @pytest.mark.asyncio
    async def test_result_event_yields_when_no_text(self):
        """If no assistant text events, the result event yields text as fallback."""
        lines = [
            json.dumps({"type": "result", "result": "Final answer"}),
        ]
        mock_proc = _make_stream_proc(lines)

        with patch("koda.services.claude_runner.asyncio.create_subprocess_exec", return_value=mock_proc):
            chunks = []
            async for chunk in run_claude_streaming(query="test", work_dir="/tmp", model="claude-sonnet-4-6"):
                chunks.append(chunk)

        assert chunks == ["Final answer"]

    @pytest.mark.asyncio
    async def test_result_event_auth_error_sets_metadata_without_yielding(self):
        lines = [
            json.dumps(
                {
                    "type": "result",
                    "result": (
                        "Failed to authenticate. API Error: 401 "
                        '{"type":"error","error":{"type":"authentication_error"}}'
                    ),
                    "session_id": "s1",
                }
            ),
        ]
        mock_proc = _make_stream_proc(lines)
        metadata_collector: dict = {}

        with patch("koda.services.claude_runner.asyncio.create_subprocess_exec", return_value=mock_proc):
            chunks = []
            async for chunk in run_claude_streaming(
                query="test",
                work_dir="/tmp",
                model="claude-sonnet-4-6",
                metadata_collector=metadata_collector,
            ):
                chunks.append(chunk)

        assert chunks == []
        assert metadata_collector["error"] is True
        assert metadata_collector["error_kind"] == "provider_auth"
        assert "Claude authentication failed" in metadata_collector["error_message"]

    @pytest.mark.asyncio
    async def test_result_event_invalid_session_sets_metadata_without_yielding(self):
        lines = [
            json.dumps(
                {
                    "type": "result",
                    "result": "No conversation found with session ID: 8d991867-e598-4420-b562-44d59df0fc75",
                    "session_id": "s1",
                }
            ),
        ]
        mock_proc = _make_stream_proc(lines)
        metadata_collector: dict = {}

        with patch("koda.services.claude_runner.asyncio.create_subprocess_exec", return_value=mock_proc):
            chunks = []
            async for chunk in run_claude_streaming(
                query="test",
                work_dir="/tmp",
                model="claude-sonnet-4-6",
                metadata_collector=metadata_collector,
            ):
                chunks.append(chunk)

        assert chunks == []
        assert metadata_collector["error"] is True
        assert metadata_collector["error_kind"] == "invalid_session"
        assert metadata_collector["retryable"] is False


class TestClaudeCapabilities:
    @pytest.mark.asyncio
    async def test_capabilities_become_unavailable_when_auth_probe_fails(self):
        clear_claude_capability_cache()
        unavailable = ProviderCapabilities(
            provider="claude",
            turn_mode="new_turn",
            status="unavailable",
            can_execute=False,
            supports_native_resume=False,
            errors=["Claude authentication failed."],
            checked_via="auth_status",
        )
        with patch(
            "koda.services.claude_runner._probe_claude_auth_status",
            new=AsyncMock(return_value=unavailable),
        ):
            capabilities = await get_claude_capabilities("new_turn")

        assert capabilities.can_execute is False
        assert capabilities.status == "unavailable"

    @pytest.mark.asyncio
    async def test_result_not_duplicated_after_assistant_text(self):
        """Result event is skipped when assistant events already yielded text."""
        lines = [
            json.dumps(
                {
                    "type": "assistant",
                    "message": {"content": [{"type": "text", "text": "Response"}]},
                }
            ),
            json.dumps({"type": "result", "result": "Response"}),
        ]
        mock_proc = _make_stream_proc(lines)

        with patch("koda.services.claude_runner.asyncio.create_subprocess_exec", return_value=mock_proc):
            chunks = []
            async for chunk in run_claude_streaming(query="test", work_dir="/tmp", model="claude-sonnet-4-6"):
                chunks.append(chunk)

        assert chunks == ["Response"]

    @pytest.mark.asyncio
    async def test_process_holder_event_set(self):
        """Event on process_holder is set when streaming process starts."""
        lines = [json.dumps({"type": "result", "result": "ok"})]
        mock_proc = _make_stream_proc(lines)
        event = asyncio.Event()
        holder = {"event": event}

        with patch("koda.services.claude_runner.asyncio.create_subprocess_exec", return_value=mock_proc):
            async for _ in run_claude_streaming(
                query="test",
                work_dir="/tmp",
                model="claude-sonnet-4-6",
                process_holder=holder,
            ):
                pass

        assert event.is_set()
        assert holder["proc"] is mock_proc

    @pytest.mark.asyncio
    async def test_empty_stream_logs_stderr(self):
        """When streaming yields nothing, stderr is logged."""
        lines: list[str] = []
        mock_proc = _make_stream_proc(lines, stderr=b"some error output")

        with patch("koda.services.claude_runner.asyncio.create_subprocess_exec", return_value=mock_proc):
            chunks = []
            async for chunk in run_claude_streaming(
                query="test",
                work_dir="/tmp",
                model="claude-sonnet-4-6",
            ):
                chunks.append(chunk)

        assert chunks == []
        mock_proc.stderr.read.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_first_chunk_timeout(self):
        """Stream ends cleanly when no content arrives within first_chunk_timeout."""
        # Simulate a line that hangs by raising TimeoutError on readline
        mock_proc = AsyncMock()
        mock_stdout = MagicMock()
        mock_stdout.readline = AsyncMock(side_effect=TimeoutError())
        mock_stdin = MagicMock()
        mock_stdin.write = MagicMock()
        mock_stdin.drain = AsyncMock()
        mock_stdin.close = MagicMock()
        mock_stdin.wait_closed = AsyncMock()
        mock_stderr = MagicMock()
        mock_stderr.read = AsyncMock(return_value=b"")
        mock_proc.stdout = mock_stdout
        mock_proc.stdin = mock_stdin
        mock_proc.stderr = mock_stderr
        mock_proc.wait = AsyncMock()
        mock_proc.kill = MagicMock()
        mock_proc.returncode = None

        with patch("koda.services.claude_runner.asyncio.create_subprocess_exec", return_value=mock_proc):
            chunks = []
            async for chunk in run_claude_streaming(
                query="test",
                work_dir="/tmp",
                model="claude-sonnet-4-6",
                first_chunk_timeout=0.1,
            ):
                chunks.append(chunk)

        assert chunks == []
        mock_proc.kill.assert_called_once()

    @pytest.mark.asyncio
    async def test_system_and_rate_limit_events_ignored(self):
        """Non-content events (system, rate_limit) are silently ignored."""
        lines = [
            json.dumps({"type": "system", "subtype": "init", "session_id": "s1"}),
            json.dumps({"type": "rate_limit_event", "rate_limit_info": {}}),
            json.dumps(
                {
                    "type": "assistant",
                    "message": {"content": [{"type": "text", "text": "Ok"}]},
                }
            ),
            json.dumps({"type": "result", "result": "Ok"}),
        ]
        mock_proc = _make_stream_proc(lines)

        with patch("koda.services.claude_runner.asyncio.create_subprocess_exec", return_value=mock_proc):
            chunks = []
            async for chunk in run_claude_streaming(
                query="test",
                work_dir="/tmp",
                model="claude-sonnet-4-6",
            ):
                chunks.append(chunk)

        assert chunks == ["Ok"]
