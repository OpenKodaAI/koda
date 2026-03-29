"""Tests for Codex CLI runner."""

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from koda.services.codex_runner import (
    _build_new_turn_cmd,
    _build_resume_turn_cmd,
    clear_codex_capability_cache,
    get_codex_capabilities,
    run_codex,
    run_codex_streaming,
)
from koda.services.provider_runtime import ProviderCapabilities


def _make_stream_proc(lines: list[str], stderr: bytes = b"") -> AsyncMock:
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


@pytest.fixture(autouse=True)
def _clear_capabilities():
    clear_codex_capability_cache()
    with patch(
        "koda.services.codex_runner._read_login_status",
        new=AsyncMock(return_value=(0, "Logged in using ChatGPT", "")),
    ):
        yield
    clear_codex_capability_cache()


def _ready_capability(turn_mode: str) -> ProviderCapabilities:
    return ProviderCapabilities(
        provider="codex",
        turn_mode=turn_mode,  # type: ignore[arg-type]
        status="ready",
        can_execute=True,
        supports_native_resume=turn_mode == "resume_turn",
    )


class TestCodexCommandBuilders:
    def test_build_new_turn_cmd_includes_cd_and_sandbox(self):
        with patch("koda.services.codex_runner.CODEX_SANDBOX", "danger-full-access"):
            cmd = _build_new_turn_cmd("gpt-5.4-mini", "/tmp/workdir", "system", None)

        assert cmd[:2] == ["codex", "exec"]
        assert "--cd" in cmd
        assert "/tmp/workdir" in cmd
        assert "--sandbox" in cmd
        assert "danger-full-access" in cmd
        assert cmd[-1] == "-"

    def test_build_resume_turn_cmd_omits_cd_and_uses_dangerous_flag(self):
        with patch("koda.services.codex_runner.CODEX_SANDBOX", "danger-full-access"):
            cmd = _build_resume_turn_cmd("gpt-5.4-mini", "thread-123", "system", None)

        assert cmd[:3] == ["codex", "exec", "resume"]
        assert "--cd" not in cmd
        assert "--sandbox" not in cmd
        assert "--dangerously-bypass-approvals-and-sandbox" in cmd
        assert cmd[-2:] == ["thread-123", "-"]

    def test_build_new_turn_cmd_uses_read_only_sandbox_for_dry_run(self):
        with patch("koda.services.codex_runner.CODEX_SANDBOX", "danger-full-access"):
            cmd = _build_new_turn_cmd("gpt-5.4-mini", "/tmp/workdir", "system", None, sandbox="read-only")

        assert "--sandbox" in cmd
        index = cmd.index("--sandbox")
        assert cmd[index + 1] == "read-only"


class TestCodexCapabilities:
    @pytest.mark.asyncio
    async def test_resume_degrades_when_configured_sandbox_is_not_supported(self):
        help_text = (
            "Usage: codex exec resume [OPTIONS] [SESSION_ID] [PROMPT]\n"
            "--json\n--model\n--dangerously-bypass-approvals-and-sandbox\n"
        )
        with (
            patch("koda.services.codex_runner._read_help_text", new=AsyncMock(return_value=(help_text, ""))),
            patch("koda.services.codex_runner.CODEX_SANDBOX", "workspace-write"),
        ):
            capabilities = await get_codex_capabilities("resume_turn")

        assert capabilities.status == "degraded"
        assert capabilities.can_execute is False
        assert capabilities.supports_native_resume is False

    @pytest.mark.asyncio
    async def test_new_turn_unavailable_when_login_status_fails(self):
        help_text = "Usage: codex exec [OPTIONS]\n--json\n--model\n--cd\n--sandbox\n"
        with (
            patch("koda.services.codex_runner._read_help_text", new=AsyncMock(return_value=(help_text, ""))),
            patch(
                "koda.services.codex_runner._read_login_status",
                new=AsyncMock(return_value=(1, "", "Not logged in")),
            ),
        ):
            capabilities = await get_codex_capabilities("new_turn")

        assert capabilities.status == "unavailable"
        assert capabilities.can_execute is False
        assert any("Codex authentication failed" in error for error in capabilities.errors)


class TestRunCodex:
    @pytest.mark.asyncio
    async def test_successful_run(self):
        stdout = "\n".join(
            [
                json.dumps({"type": "thread.started", "thread_id": "thread-123"}),
                json.dumps(
                    {
                        "type": "item.completed",
                        "item": {"id": "m1", "type": "agent_message", "text": "Hello from Codex"},
                    }
                ),
                json.dumps({"type": "turn.completed", "usage": {"input_tokens": 10, "output_tokens": 5}}),
            ]
        ).encode()
        mock_proc = AsyncMock()
        mock_proc.communicate = AsyncMock(return_value=(stdout, b""))
        mock_proc.returncode = 0

        with patch("koda.services.codex_runner.asyncio.create_subprocess_exec", return_value=mock_proc):
            result = await run_codex(
                query="hi",
                work_dir="/tmp",
                model="gpt-5.4",
                turn_mode="new_turn",
                capabilities=_ready_capability("new_turn"),
            )

        assert result["result"] == "Hello from Codex"
        assert result["session_id"] == "thread-123"
        assert result["error"] is False
        assert result["usage"] == {"input_tokens": 10, "output_tokens": 5}

    @pytest.mark.asyncio
    async def test_resume_run_uses_resume_command_without_cd(self):
        stdout = json.dumps({"type": "thread.started", "thread_id": "thread-123"}).encode()
        mock_proc = AsyncMock()
        mock_proc.communicate = AsyncMock(return_value=(stdout, b""))
        mock_proc.returncode = 0

        exec_path = "koda.services.codex_runner.asyncio.create_subprocess_exec"
        with patch(exec_path, return_value=mock_proc) as mock_exec:
            await run_codex(
                query="hi",
                work_dir="/tmp/workdir",
                model="gpt-5.4-mini",
                session_id="thread-123",
                turn_mode="resume_turn",
                capabilities=_ready_capability("resume_turn"),
            )

        argv = mock_exec.call_args[0]
        assert "resume" in argv
        assert "--cd" not in argv
        assert "--sandbox" not in argv
        assert "thread-123" in argv

    @pytest.mark.asyncio
    async def test_dry_run_uses_read_only_sandbox(self):
        stdout = json.dumps({"type": "thread.started", "thread_id": "thread-123"}).encode()
        mock_proc = AsyncMock()
        mock_proc.communicate = AsyncMock(return_value=(stdout, b""))
        mock_proc.returncode = 0

        exec_path = "koda.services.codex_runner.asyncio.create_subprocess_exec"
        with patch(exec_path, return_value=mock_proc) as mock_exec:
            await run_codex(
                query="hi",
                work_dir="/tmp/workdir",
                model="gpt-5.4-mini",
                turn_mode="new_turn",
                dry_run=True,
                capabilities=_ready_capability("new_turn"),
            )

        argv = mock_exec.call_args[0]
        assert "--sandbox" in argv
        index = argv.index("--sandbox")
        assert argv[index + 1] == "read-only"

    @pytest.mark.asyncio
    async def test_dry_run_resume_is_rejected_as_adapter_contract(self):
        result = await run_codex(
            query="hi",
            work_dir="/tmp/workdir",
            model="gpt-5.4-mini",
            session_id="thread-123",
            turn_mode="resume_turn",
            dry_run=True,
            capabilities=_ready_capability("resume_turn"),
        )

        assert result["error"] is True
        assert result["_error_kind"] == "adapter_contract"

    @pytest.mark.asyncio
    async def test_adapter_contract_error_is_not_retryable(self):
        mock_proc = AsyncMock()
        mock_proc.communicate = AsyncMock(
            return_value=(
                b"",
                b"error: unexpected argument '--cd' found\nUsage: codex exec resume --json <SESSION_ID> [PROMPT]",
            )
        )
        mock_proc.returncode = 2

        with patch("koda.services.codex_runner.asyncio.create_subprocess_exec", return_value=mock_proc):
            result = await run_codex(
                query="hi",
                work_dir="/tmp",
                model="gpt-5.4-mini",
                session_id="thread-123",
                turn_mode="resume_turn",
                capabilities=_ready_capability("resume_turn"),
            )

        assert result["error"] is True
        assert result["_error_kind"] == "adapter_contract"
        assert result["_retryable"] is False

    @pytest.mark.asyncio
    async def test_embedded_auth_message_is_treated_as_error(self):
        stdout = "\n".join(
            [
                json.dumps({"type": "thread.started", "thread_id": "thread-123"}),
                json.dumps(
                    {
                        "type": "item.completed",
                        "item": {
                            "id": "m1",
                            "type": "agent_message",
                            "text": (
                                'Failed to authenticate. API Error: 401 {"type":"error","error":'
                                '{"type":"authentication_error"}}'
                            ),
                        },
                    }
                ),
                json.dumps({"type": "turn.completed", "usage": {"input_tokens": 10, "output_tokens": 5}}),
            ]
        ).encode()
        mock_proc = AsyncMock()
        mock_proc.communicate = AsyncMock(return_value=(stdout, b""))
        mock_proc.returncode = 0

        with patch("koda.services.codex_runner.asyncio.create_subprocess_exec", return_value=mock_proc):
            result = await run_codex(
                query="hi",
                work_dir="/tmp",
                model="gpt-5.4",
                turn_mode="new_turn",
                capabilities=_ready_capability("new_turn"),
            )

        assert result["error"] is True
        assert result["_error_kind"] == "provider_auth"
        assert "Codex authentication failed" in result["result"]


class TestRunCodexStreaming:
    @pytest.mark.asyncio
    async def test_streaming_agent_message(self):
        lines = [
            json.dumps({"type": "thread.started", "thread_id": "thread-123"}),
            json.dumps(
                {
                    "type": "item.updated",
                    "item": {"id": "m1", "type": "agent_message", "text": "Hello"},
                }
            ),
            json.dumps({"type": "turn.completed", "usage": {"input_tokens": 10, "output_tokens": 5}}),
        ]
        mock_proc = _make_stream_proc(lines)
        metadata_collector: dict = {}

        with patch("koda.services.codex_runner.asyncio.create_subprocess_exec", return_value=mock_proc):
            chunks = []
            async for chunk in run_codex_streaming(
                query="hi",
                work_dir="/tmp",
                model="gpt-5.4",
                metadata_collector=metadata_collector,
                turn_mode="new_turn",
                capabilities=_ready_capability("new_turn"),
            ):
                chunks.append(chunk)

        assert chunks == ["Hello"]
        assert metadata_collector["session_id"] == "thread-123"
        assert metadata_collector["usage"] == {"input_tokens": 10, "output_tokens": 5}


class TestConcurrentAuthProbes:
    @pytest.mark.asyncio
    async def test_concurrent_auth_probes_serialized(self):
        """Concurrent auth status calls should not spawn redundant probes."""
        import koda.services.codex_runner as cr

        cr._AUTH_CAPABILITY_CACHE = None  # Force cache miss

        call_count = 0

        async def counting_read():
            nonlocal call_count
            call_count += 1
            await asyncio.sleep(0.05)  # Simulate I/O
            return 0, "logged in", ""

        with patch.object(cr, "_read_login_status", side_effect=counting_read):
            results = await asyncio.gather(
                cr._get_codex_auth_status(),
                cr._get_codex_auth_status(),
                cr._get_codex_auth_status(),
            )

        # With double-checked locking, only 1 probe should run
        assert call_count == 1
        for authenticated, _method, _msg in results:
            assert authenticated is True
