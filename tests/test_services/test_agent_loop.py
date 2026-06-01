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
    _build_voice_active_prompt,
    _compose_response_text,
    _extract_spoken_response_block,
    _prepare_delivery_outcome,
    _prepare_spoken_response_for_tts,
    _run_agent_loop,
    _send_response,
    _voice_continuous_mode_active,
)

# Helpers


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


def test_compose_response_does_not_prefix_native_shell_trace():
    run_result = _make_result(
        result="Criei o arquivo animais_silvestres_teste.docx.",
        native_items=[
            {
                "type": "command_execution",
                "command": "python - <<'PY'\nout = 'animais_silvestres_teste.docx'\nPY",
            }
        ],
    )

    response, tool_summary = _compose_response_text(run_result, elapsed=18.0)

    assert response == "Criei o arquivo animais_silvestres_teste.docx."
    assert "python" not in response
    assert "Tools:" not in response
    assert "etapa" in tool_summary


def test_compose_response_replaces_empty_task_fallback_with_native_artifact_summary():
    run_result = _make_result(
        result="Task completed (no text output).",
        native_items=[
            {
                "type": "file_change",
                "kind": "add",
                "path": "/tmp/render.png",
            }
        ],
    )

    response, tool_summary = _compose_response_text(run_result, elapsed=18.0)

    assert response == tool_summary
    assert "Task completed" not in response
    assert "Arquivos: render.png" in response


def test_compose_response_strips_leading_provider_tool_transcript():
    run_result = _make_result(
        result=(
            "Tools: shell(/bin/bash -lc 'pwd && ls -la'), shell(/bin/bash -lc \"python - <<'PY'\n"
            "from docx import Document\n"
            "out = 'animais_silvestres_teste.docx'\n"
            "print(out)\n"
            'PY")\n\n'
            "Vou criar um .docx simples e anexar aqui.\n\n"
            "Criei o arquivo animais_silvestres_teste.docx."
        )
    )

    response, _tool_summary = _compose_response_text(run_result, elapsed=18.0)

    assert response.startswith("Vou criar")
    assert "Tools:" not in response
    assert "/bin/bash" not in response
    assert "from docx" not in response


def test_extract_spoken_response_block_removes_visible_tag():
    visible, spoken = _extract_spoken_response_block(
        "<spoken_response>Resumo falado curto.</spoken_response>\n\nDetalhes completos em texto."
    )

    assert spoken == "Resumo falado curto."
    assert visible == "Detalhes completos em texto."
    assert "spoken_response" not in visible


def test_prepare_spoken_response_uses_policy_limit_and_keeps_text_details():
    response = (
        "Primeira frase importante. Segunda frase com contexto. Terceira frase com detalhe. "
        + "Mais detalhes operacionais. " * 80
    )

    spoken, send_text = _prepare_spoken_response_for_tts(
        response,
        user_data={
            "tts_voice_language": "pt-br",
            "voice_policy": {"max_spoken_chars": 280},
        },
    )

    assert len(spoken) <= 280
    assert "Deixei os detalhes completos em texto" in spoken
    assert send_text is True


def test_prepare_spoken_response_summarizes_code_and_mentions_artifact(tmp_path):
    doc = tmp_path / "relatorio.docx"
    doc.write_bytes(b"docx")
    response = "Segue o codigo:\n```\n" + "print('x')\n" * 200 + "```\nArquivo relatorio.docx criado."

    spoken, send_text = _prepare_spoken_response_for_tts(
        response,
        created_artifacts=[str(doc)],
        user_data={"tts_voice_language": "pt-br"},
    )

    assert "codigo ou detalhes tecnicos" in spoken
    assert "relatorio.docx" not in spoken
    assert "documento" in spoken
    assert "print" not in spoken
    assert send_text is True


def test_prepare_spoken_response_humanizes_artifact_only_image_voice(tmp_path):
    image = tmp_path / "ig_voice.png"
    image.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 100)

    spoken, send_text = _prepare_spoken_response_for_tts(
        "Pronto, gerei e anexei: ig_voice.png.",
        created_artifacts=[str(image)],
        artifact_summary_response=True,
        query_text="Gere uma imagem no estilo anime antigo.",
        user_data={"tts_voice_language": "pt-br"},
    )

    assert "ig_voice.png" not in spoken
    assert "imagem" in spoken
    assert "anime antigo" in spoken
    assert "Telegram" in spoken
    assert send_text is False


def test_prepare_spoken_response_replaces_filename_with_natural_artifact_reference(tmp_path):
    image = tmp_path / "render_final.png"
    image.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 100)

    spoken, send_text = _prepare_spoken_response_for_tts(
        "Criei o arquivo render_final.png e anexei aqui.",
        created_artifacts=[str(image)],
        user_data={"tts_voice_language": "pt-br"},
    )

    assert "render_final.png" not in spoken
    assert "arquivo a imagem" not in spoken
    assert "Criei a imagem" in spoken
    assert send_text is False


def test_build_voice_prompt_uses_agent_policy_without_forcing_english():
    prompt = _build_voice_active_prompt(
        {
            "audio_response": True,
            "tts_voice_language": "pt-br",
            "voice_policy_active": True,
            "voice_policy": {
                "max_spoken_chars": 360,
                "spoken_style": "objetivo e acolhedor",
                "detail_level": "resumo curto",
            },
        }
    )

    assert "max_spoken_chars=360" in prompt
    assert "spoken_style=objetivo e acolhedor" in prompt
    assert "detail_level=resumo curto" in prompt
    assert "Voice delivery is ACTIVE for this response" in prompt
    assert "continuous_voice_mode=active" in prompt
    assert "turn_audio_request=false" in prompt
    assert "Do not say voice mode, TTS, or audio is disabled" in prompt
    assert "Write in spoken English" not in prompt


def test_build_voice_prompt_marks_one_turn_audio_as_active_even_when_continuous_mode_is_off():
    prompt = _build_voice_active_prompt(
        {
            "audio_response": False,
            "tts_enabled": False,
            "tts_voice_language": "pt-br",
        },
        force_audio_response=True,
    )

    assert "Voice delivery is ACTIVE for this response" in prompt
    assert "continuous_voice_mode=inactive" in prompt
    assert "turn_audio_request=true" in prompt
    assert "Do not tell the user to use /voice to enable audio in this response" in prompt


def test_voice_continuous_mode_active_uses_policy_even_when_audio_response_is_missing():
    assert _voice_continuous_mode_active({"audio_response": False, "voice_policy_active": True}) is True
    assert _voice_continuous_mode_active({"audio_response": False, "voice_policy_mode": "voice_active"}) is True
    assert _voice_continuous_mode_active({"audio_response": False, "tts_enabled": True}) is False


@pytest.mark.asyncio
async def test_send_response_warns_when_claimed_artifact_is_missing(tmp_path):
    context = _make_context()
    run_result = _make_result(
        result="Criei o arquivo relatorio.docx.",
        native_items=[
            {
                "type": "command_execution",
                "command": "python gerar.py",
                "output": "relatorio.docx",
            }
        ],
    )

    with patch("koda.services.queue_manager._ARTIFACT_DISCOVERY_POLL_SECONDS", 0.0):
        await _send_response(
            111,
            None,
            context,
            run_result,
            str(tmp_path),
            "autonomous",
            elapsed=6.0,
            model="gpt-5.4-mini",
        )

    sent_text = context.bot.send_message.call_args.kwargs["text"]
    assert "Nao encontrei esse arquivo" in sent_text
    assert "artifact not found" in run_result.warnings


@pytest.mark.asyncio
async def test_send_response_attaches_artifact_from_agent_tool_trace(tmp_path):
    context = _make_context()
    doc = tmp_path / "relatorio.docx"
    doc.write_bytes(b"docx")
    run_result = _make_result(
        result="Criei o arquivo relatorio.docx.",
        tool_execution_trace=[
            {
                "tool": "shell_execute",
                "success": True,
                "output": "relatorio.docx",
                "metadata": {"category": "shell"},
            }
        ],
    )

    await _send_response(
        111,
        None,
        context,
        run_result,
        str(tmp_path),
        "autonomous",
        elapsed=6.0,
        model="gpt-5.4-mini",
    )

    context.bot.send_document.assert_awaited_once()
    assert "artifact not found" not in run_result.warnings


@pytest.mark.asyncio
async def test_send_response_attaches_recent_work_dir_artifacts_by_supported_type(tmp_path):
    context = _make_context()
    payloads = {
        "relatorio.pdf": b"%PDF-1.4\n",
        "pacote.zip": b"PK\x03\x04",
        "animacao.gif": b"GIF89a" + b"\x00" * 100,
        "clip.mp4": b"\x00\x00\x00\x18ftypmp42" + b"\x00" * 100,
        "track.mp3": b"\xff\xfb\x90" + b"\x00" * 100,
        "memo.ogg": b"OggS" + b"\x00" * 100,
    }
    for filename, payload in payloads.items():
        (tmp_path / filename).write_bytes(payload)
    run_result = _make_result(result="Pronto, gerei os anexos.")

    await _send_response(
        111,
        None,
        context,
        run_result,
        str(tmp_path),
        "autonomous",
        elapsed=6.0,
        model="gpt-5.4-mini",
    )

    assert context.bot.send_document.await_count == 2
    context.bot.send_animation.assert_awaited_once()
    context.bot.send_video.assert_awaited_once()
    context.bot.send_audio.assert_awaited_once()
    context.bot.send_voice.assert_awaited_once()


@pytest.mark.asyncio
async def test_send_response_persists_and_sends_provider_native_artifact_in_voice_mode(tmp_path):
    context = _make_context()
    context.user_data.update(
        {
            "voice_policy_active": True,
            "tts_enabled": True,
            "tts_voice_language": "pt-br",
        }
    )
    image = tmp_path / "render.png"
    image.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 100)
    run_result = _make_result(
        provider="codex",
        model="gpt-5.4-mini",
        result="Task completed (no text output).",
        native_items=[
            {
                "type": "file_change",
                "kind": "add",
                "path": str(image),
                "source_type": "provider_event",
                "metadata": {"provider_event_type": "image_generation_end"},
            }
        ],
    )
    runtime = MagicMock()
    runtime.store.list_artifacts.return_value = []
    runtime.add_artifact = AsyncMock(return_value=77)
    runtime.events.publish = AsyncMock()

    with (
        patch("koda.services.runtime.get_runtime_controller", return_value=runtime),
        patch("koda.services.queue_manager.tts_enabled_for_session", return_value=True),
        patch("koda.utils.tts.synthesize_speech", new=AsyncMock(return_value=None)),
    ):
        await _send_response(
            111,
            None,
            context,
            run_result,
            str(tmp_path),
            "autonomous",
            elapsed=6.0,
            model="gpt-5.4-mini",
            task_id=42,
            query_text="Gere uma imagem no estilo anime antigo.",
        )

    runtime.add_artifact.assert_awaited_once()
    artifact_kwargs = runtime.add_artifact.await_args.kwargs
    assert artifact_kwargs["task_id"] == 42
    assert artifact_kwargs["artifact_kind"] == "image"
    assert artifact_kwargs["label"] == "render.png"
    assert artifact_kwargs["path"] == str(image)
    assert artifact_kwargs["metadata"]["provider"] == "codex"
    runtime.events.publish.assert_awaited_once()
    event_kwargs = runtime.events.publish.await_args.kwargs
    assert event_kwargs["event_type"] == "artifact_ready"
    assert event_kwargs["payload"]["artifact"]["download_url"] == "/api/runtime/artifacts/77/download"
    context.bot.send_photo.assert_awaited_once()


@pytest.mark.asyncio
async def test_voice_mode_speaks_artifact_summary_and_sends_artifact(tmp_path):
    context = _make_context()
    context.user_data.update(
        {
            "voice_policy_active": True,
            "tts_enabled": True,
            "tts_voice_language": "pt-br",
        }
    )
    image = tmp_path / "ig_voice.png"
    image.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 100)
    voice = tmp_path.parent / f"{tmp_path.name}-voice.ogg"
    voice.write_bytes(b"OggS" + b"\x00" * 100)
    run_result = _make_result(
        provider="codex",
        model="gpt-5.4-mini",
        result="Text completed (no text output).",
        native_items=[
            {
                "type": "file_change",
                "kind": "add",
                "path": str(image),
                "source_type": "provider_event",
            }
        ],
    )
    runtime = MagicMock()
    runtime.store.list_artifacts.return_value = []
    runtime.add_artifact = AsyncMock(return_value=78)
    runtime.events.publish = AsyncMock()
    synthesize = AsyncMock(return_value=str(voice))

    with (
        patch("koda.services.runtime.get_runtime_controller", return_value=runtime),
        patch("koda.services.queue_manager.tts_enabled_for_session", return_value=True),
        patch("koda.utils.tts.synthesize_speech", new=synthesize),
    ):
        await _send_response(
            111,
            None,
            context,
            run_result,
            str(tmp_path),
            "autonomous",
            elapsed=6.0,
            model="gpt-5.4-mini",
            task_id=42,
            query_text="Gere uma imagem no estilo anime antigo.",
        )

    context.bot.send_photo.assert_awaited_once()
    context.bot.send_voice.assert_awaited_once()
    spoken_text = synthesize.await_args.args[0]
    assert "Task completed" not in spoken_text
    assert "Text completed" not in spoken_text
    assert "ig_voice.png" not in spoken_text
    assert "imagem" in spoken_text
    assert "anime antigo" in spoken_text
    assert not voice.exists()


@pytest.mark.asyncio
async def test_voice_mode_without_text_or_artifact_never_speaks_raw_fallback(tmp_path):
    context = _make_context()
    context.user_data.update(
        {
            "voice_policy_active": True,
            "tts_enabled": True,
            "tts_voice_language": "pt-br",
        }
    )
    voice = tmp_path.parent / f"{tmp_path.name}-voice.ogg"
    voice.write_bytes(b"OggS" + b"\x00" * 100)
    run_result = _make_result(result="Text completed (no text output).")
    synthesize = AsyncMock(return_value=str(voice))

    with (
        patch("koda.services.queue_manager.tts_enabled_for_session", return_value=True),
        patch("koda.utils.tts.synthesize_speech", new=synthesize),
    ):
        await _send_response(
            111,
            None,
            context,
            run_result,
            str(tmp_path),
            "autonomous",
            elapsed=6.0,
            model="gpt-5.4-mini",
        )

    context.bot.send_voice.assert_awaited_once()
    spoken_text = synthesize.await_args.args[0]
    assert "Task completed" not in spoken_text
    assert "Text completed" not in spoken_text
    assert "sem texto" in spoken_text


@pytest.mark.asyncio
async def test_send_response_reports_discovered_artifact_delivery_failure(tmp_path):
    context = _make_context()
    image = tmp_path / "render.png"
    image.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 100)
    context.bot.send_photo.side_effect = Exception("photo failed")
    context.bot.send_document.side_effect = Exception("document failed")
    run_result = _make_result(
        result="Task completed (no text output).",
        native_items=[{"type": "file_change", "kind": "add", "path": str(image)}],
    )

    await _send_response(
        111,
        None,
        context,
        run_result,
        str(tmp_path),
        "autonomous",
        elapsed=6.0,
        model="gpt-5.4-mini",
    )

    sent_text = context.bot.send_message.await_args.kwargs["text"]
    assert "nao consegui anexa-los" in sent_text
    assert "Task completed" not in sent_text
    assert "artifact delivery failed" in run_result.warnings


@pytest.mark.asyncio
async def test_send_response_finds_codex_generated_image_when_native_event_is_missing(tmp_path):
    context = _make_context()
    provider_session_id = "thread-123"
    image_dir = tmp_path / ".codex" / "generated_images" / provider_session_id
    image_dir.mkdir(parents=True)
    image = image_dir / "ig_missing_event.png"
    image.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 100)
    run_result = _make_result(
        provider="codex",
        model="gpt-5.4-mini",
        result="Task completed (no text output).",
        provider_session_id=provider_session_id,
        native_items=[],
    )
    runtime = MagicMock()
    runtime.store.list_artifacts.return_value = []
    runtime.add_artifact = AsyncMock(return_value=88)
    runtime.events.publish = AsyncMock()

    with patch("koda.services.runtime.get_runtime_controller", return_value=runtime):
        await _send_response(
            111,
            None,
            context,
            run_result,
            str(tmp_path),
            "autonomous",
            elapsed=6.0,
            model="gpt-5.4-mini",
            task_id=43,
        )

    runtime.add_artifact.assert_awaited_once()
    assert runtime.add_artifact.await_args.kwargs["path"] == str(image.resolve())
    context.bot.send_photo.assert_awaited_once()
    sent_text = context.bot.send_message.await_args.kwargs["text"]
    assert "Task completed" not in sent_text
    assert "ig_missing_event.png" in sent_text


@pytest.mark.asyncio
async def test_prepare_delivery_outcome_summarizes_and_persists_no_text_artifact(tmp_path):
    provider_session_id = "thread-delivery"
    image_dir = tmp_path / ".codex" / "generated_images" / provider_session_id
    image_dir.mkdir(parents=True)
    image = image_dir / "ig_delivery.png"
    image.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 100)
    run_result = _make_result(
        provider="codex",
        model="gpt-5.4-mini",
        result="Task completed (no text output).",
        provider_session_id=provider_session_id,
    )
    runtime = MagicMock()
    runtime.store.list_artifacts.return_value = []
    runtime.add_artifact = AsyncMock(return_value=91)
    runtime.events.publish = AsyncMock()

    with (
        patch("koda.services.queue_manager._ARTIFACT_DISCOVERY_POLL_SECONDS", 0.0),
        patch("koda.services.runtime.get_runtime_controller", return_value=runtime),
    ):
        outcome = await _prepare_delivery_outcome(
            run_result,
            str(tmp_path),
            elapsed=6.0,
            task_id=46,
        )

    assert outcome.response == "Pronto, gerei e anexei: ig_delivery.png."
    assert outcome.artifact_summary_applied is True
    assert outcome.created_artifacts == [str(image.resolve())]
    runtime.add_artifact.assert_awaited_once()
    assert runtime.add_artifact.await_args.kwargs["path"] == str(image.resolve())


@pytest.mark.asyncio
async def test_prepare_delivery_outcome_keeps_clear_fallback_without_text_or_artifacts(tmp_path):
    run_result = _make_result(result="Task completed (no text output).")

    with patch("koda.services.queue_manager._discover_created_artifacts", new=AsyncMock(return_value=[])):
        outcome = await _prepare_delivery_outcome(
            run_result,
            str(tmp_path),
            elapsed=6.0,
            task_id=47,
        )

    assert outcome.response == "A execucao terminou sem texto e sem artefatos localizaveis."
    assert outcome.created_artifacts == []
    assert outcome.artifact_summary_applied is False


@pytest.mark.asyncio
async def test_send_response_finds_codex_generated_video_when_native_event_is_missing(tmp_path):
    context = _make_context()
    provider_session_id = "thread-456"
    video_dir = tmp_path / ".codex" / "generated_videos" / provider_session_id
    video_dir.mkdir(parents=True)
    video = video_dir / "movie_missing_event.mp4"
    video.write_bytes(b"\x00\x00\x00\x18ftypmp42" + b"\x00" * 100)
    run_result = _make_result(
        provider="codex",
        model="gpt-5.4-mini",
        result="Task completed (no text output).",
        provider_session_id=provider_session_id,
        native_items=[],
    )
    runtime = MagicMock()
    runtime.store.list_artifacts.return_value = []
    runtime.add_artifact = AsyncMock(return_value=89)
    runtime.events.publish = AsyncMock()

    with patch("koda.services.runtime.get_runtime_controller", return_value=runtime):
        await _send_response(
            111,
            None,
            context,
            run_result,
            str(tmp_path),
            "autonomous",
            elapsed=6.0,
            model="gpt-5.4-mini",
            task_id=44,
        )

    runtime.add_artifact.assert_awaited_once()
    assert runtime.add_artifact.await_args.kwargs["artifact_kind"] == "video"
    assert runtime.add_artifact.await_args.kwargs["path"] == str(video.resolve())
    context.bot.send_video.assert_awaited_once()


@pytest.mark.asyncio
async def test_send_response_finds_codex_generated_image_in_hyphenated_nested_dir(tmp_path):
    context = _make_context()
    provider_session_id = "thread-nested"
    image_dir = tmp_path / ".codex" / "generated-images" / provider_session_id / "outputs"
    image_dir.mkdir(parents=True)
    image = image_dir / "ig_nested.png"
    image.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 100)
    run_result = _make_result(
        provider="codex",
        model="gpt-5.4-mini",
        result="Task completed (no text output).",
        provider_session_id=provider_session_id,
        native_items=[],
    )
    runtime = MagicMock()
    runtime.store.list_artifacts.return_value = []
    runtime.add_artifact = AsyncMock(return_value=90)
    runtime.events.publish = AsyncMock()

    with patch("koda.services.runtime.get_runtime_controller", return_value=runtime):
        await _send_response(
            111,
            None,
            context,
            run_result,
            str(tmp_path),
            "autonomous",
            elapsed=6.0,
            model="gpt-5.4-mini",
            task_id=45,
        )

    runtime.add_artifact.assert_awaited_once()
    assert runtime.add_artifact.await_args.kwargs["path"] == str(image.resolve())
    context.bot.send_photo.assert_awaited_once()


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
            "selectors": {"tool_id": ["job_create"]},
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


# Tests


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
            result='Let me check. <agent_cmd tool="job_list">{}</agent_cmd>',
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
            patch("koda.services.tool_dispatcher._handle_job_list", new_callable=AsyncMock) as mock_handler,
        ):
            from koda.services.tool_dispatcher import AgentToolResult

            mock_handler.return_value = AgentToolResult(
                tool="job_list",
                success=True,
                output="No jobs found.",
            )
            with patch("koda.services.tool_dispatcher._TOOL_HANDLERS", {"job_list": mock_handler}):
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
                result='<agent_cmd tool="job_list">{}</agent_cmd>',
                cost_usd=0.01,
                session_id="sess-1",
            )

        initial = _make_result(
            result='<agent_cmd tool="job_list">{}</agent_cmd>',
        )

        with (
            patch("koda.services.queue_manager._run_with_provider_fallback", side_effect=_mock_streaming),
            patch("koda.services.tool_dispatcher._handle_job_list", new_callable=AsyncMock) as mock_handler,
        ):
            from koda.services.tool_dispatcher import AgentToolResult

            mock_handler.return_value = AgentToolResult(
                tool="job_list",
                success=True,
                output="No jobs.",
            )
            with patch("koda.services.tool_dispatcher._TOOL_HANDLERS", {"job_list": mock_handler}):
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
            result='Before <agent_cmd tool="job_list">{}</agent_cmd> After',
        )

        with (
            patch(
                "koda.services.queue_manager._run_with_provider_fallback",
                new_callable=AsyncMock,
                return_value=None,
            ),
            patch("koda.services.tool_dispatcher._handle_job_list", new_callable=AsyncMock) as mock_handler,
        ):
            from koda.services.tool_dispatcher import AgentToolResult

            mock_handler.return_value = AgentToolResult(
                tool="job_list",
                success=True,
                output="No jobs.",
            )
            with patch("koda.services.tool_dispatcher._TOOL_HANDLERS", {"job_list": mock_handler}):
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
            result='<agent_cmd tool="job_create">{"expression": "0 3 * * *", "command": "echo hi"}</agent_cmd>',
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
                '<agent_cmd tool="job_list">{}</agent_cmd>'
                '<agent_cmd tool="job_create">{"expression": "0 3 * * *", "command": "echo hi"}</agent_cmd>'
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
            patch("koda.services.tool_dispatcher._handle_job_create", new_callable=AsyncMock) as mock_add,
        ):
            from koda.services.tool_dispatcher import AgentToolResult

            mock_list.return_value = AgentToolResult(tool="job_list", success=True, output="No jobs found.")
            mock_add.return_value = AgentToolResult(tool="job_create", success=True, output="Job created.")
            with patch(
                "koda.services.tool_dispatcher._TOOL_HANDLERS",
                {"job_list": mock_list, "job_create": mock_add},
            ):
                result = await _run_agent_loop(ctx, item, 111, 111, context, initial)

        assert result.result == "Job created."
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
                '<agent_cmd tool="job_create">{"expression": "0 3 * * *", "command": "echo hi"}</agent_cmd>'
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
                    "job_create": AsyncMock(),
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
                '<agent_cmd tool="job_create">{"expression": "0 3 * * *", "command": "echo hi"}</agent_cmd>'
            ),
            tool_uses=[{"name": "Read", "input": {"file_path": "/tmp/README.md"}}],
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
            patch("koda.services.tool_dispatcher._handle_job_create", new_callable=AsyncMock) as mock_add,
        ):
            from koda.services.tool_dispatcher import AgentToolResult

            mock_add.return_value = AgentToolResult(tool="job_create", success=True, output="Job created.")
            with patch(
                "koda.services.tool_dispatcher._TOOL_HANDLERS",
                {"job_create": mock_add},
            ):
                result = await _run_agent_loop(ctx, item, 111, 111, context, initial)

        assert result.result == "Job created."
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
                '<agent_cmd tool="job_create">{"expression": "0 3 * * *", "command": "echo hi"}</agent_cmd>'
            ),
            tool_uses=[
                {"name": "Read", "input": {"file_path": "/tmp/README.md"}},
                {"name": "Grep", "input": {"pattern": "cron", "path": "/tmp/README.md"}},
            ],
        )
        resume_after_write = _make_result(result="Write complete.", cost_usd=0.01)
        verification_turn = _make_result(result='<agent_cmd tool="job_list">{}</agent_cmd>', cost_usd=0.01)
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
            patch("koda.services.tool_dispatcher._handle_job_create", new_callable=AsyncMock) as mock_add,
            patch("koda.services.tool_dispatcher._handle_job_list", new_callable=AsyncMock) as mock_list,
        ):
            from koda.services.tool_dispatcher import AgentToolResult

            mock_add.return_value = AgentToolResult(tool="job_create", success=True, output="Job created.")
            mock_list.return_value = AgentToolResult(tool="job_list", success=True, output="Cron exists.")
            with patch(
                "koda.services.tool_dispatcher._TOOL_HANDLERS",
                {"job_create": mock_add, "job_list": mock_list},
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
                '<agent_cmd tool="job_create">{"expression": "0 3 * * *", "command": "echo hi"}</agent_cmd>'
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
            patch("koda.services.tool_dispatcher._handle_job_create", new_callable=AsyncMock) as mock_add,
            patch(
                "koda.utils.approval.request_agent_cmd_approval",
                new_callable=AsyncMock,
                side_effect=AssertionError("guarded write should not request approval"),
            ),
        ):
            from koda.services.tool_dispatcher import AgentToolResult

            mock_add.return_value = AgentToolResult(tool="job_create", success=True, output="Job created.")
            with patch("koda.services.tool_dispatcher._TOOL_HANDLERS", {"job_create": mock_add}):
                result = await _run_agent_loop(ctx, item, 111, 111, context, initial)

        assert result.result == "Change applied."
        assert mock_add.await_count == 1
        assert ctx.confidence_reports[-1]["requires_human_approval"] is False

    @pytest.mark.asyncio
    async def test_send_response_includes_operational_footer_for_writes(self, tmp_path):
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
            str(tmp_path),
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
    async def test_send_response_uses_agent_local_audio_defaults_for_tts(self, tmp_path):
        ctx = _make_ctx()
        context = _make_context()
        context.user_data.update(
            {
                "audio_response": True,
                "tts_voice": "pm_alex",
                "tts_voice_language": "pt-br",
                "audio_provider": "kokoro",
                "audio_model": "kokoro-v1",
                "tts_enabled": True,
            }
        )
        run_result = _make_result(result="Resposta curta.")

        with (
            patch("koda.utils.command_helpers.TTS_ENABLED", False),
            patch("koda.utils.tts.is_mostly_code", return_value=False),
            patch("koda.utils.tts.strip_for_tts", return_value="Resposta curta"),
            patch("koda.utils.tts.synthesize_speech", new_callable=AsyncMock, return_value=None) as mock_tts,
        ):
            await _send_response(
                111,
                None,
                context,
                run_result,
                str(tmp_path),
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

    @pytest.mark.asyncio
    async def test_send_response_force_audio_request_bypasses_disabled_session_flag(self, tmp_path):
        ctx = _make_ctx(force_audio_response=True)
        context = _make_context()
        context.user_data.update(
            {
                "audio_response": False,
                "tts_voice": "pm_alex",
                "tts_voice_language": "pt-br",
                "audio_provider": "kokoro",
                "audio_model": "kokoro-v1",
                "tts_enabled": False,
            }
        )
        run_result = _make_result(result="Resumo curto para este turno.")

        with (
            patch("koda.utils.command_helpers.TTS_ENABLED", False),
            patch("koda.utils.tts.is_mostly_code", return_value=False),
            patch("koda.utils.tts.strip_for_tts", return_value="Resumo curto para este turno."),
            patch("koda.utils.tts.synthesize_speech", new_callable=AsyncMock, return_value=None) as mock_tts,
        ):
            await _send_response(
                111,
                None,
                context,
                run_result,
                str(tmp_path),
                "autonomous",
                elapsed=1.0,
                model="claude-sonnet-4-6",
                task_id=77,
                ctx=ctx,
            )

        mock_tts.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_send_response_uses_voice_policy_active_when_audio_response_flag_is_stale(self, tmp_path):
        ctx = _make_ctx()
        context = _make_context()
        context.user_data.update(
            {
                "audio_response": False,
                "voice_policy_active": True,
                "voice_policy_mode": "voice_active",
                "tts_voice": "pm_alex",
                "tts_voice_language": "pt-br",
                "audio_provider": "kokoro",
                "audio_model": "kokoro-v1",
                "tts_enabled": False,
            }
        )
        run_result = _make_result(result="Resposta curta com voz ativa.")

        with (
            patch("koda.utils.command_helpers.TTS_ENABLED", False),
            patch("koda.utils.tts.is_mostly_code", return_value=False),
            patch("koda.utils.tts.strip_for_tts", return_value="Resposta curta com voz ativa."),
            patch("koda.utils.tts.synthesize_speech", new_callable=AsyncMock, return_value=None) as mock_tts,
        ):
            await _send_response(
                111,
                None,
                context,
                run_result,
                str(tmp_path),
                "autonomous",
                elapsed=1.0,
                model="claude-sonnet-4-6",
                task_id=77,
                ctx=ctx,
            )

        mock_tts.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_send_response_explains_elevenlabs_paid_plan_voice_failure(self, tmp_path):
        ctx = _make_ctx()
        context = _make_context()
        context.user_data.update(
            {
                "audio_response": True,
                "tts_voice": "WSBwiRQRmi2mEG7BfKwS",
                "tts_voice_language": "pt-br",
                "audio_provider": "elevenlabs",
                "audio_model": "eleven_multilingual_v2",
                "tts_enabled": True,
            }
        )
        run_result = _make_result(result="Resposta curta.")

        with (
            patch("koda.utils.tts.is_mostly_code", return_value=False),
            patch("koda.utils.tts.strip_for_tts", return_value="Resposta curta"),
            patch("koda.utils.tts.synthesize_speech", new_callable=AsyncMock, return_value=None),
            patch(
                "koda.utils.tts.get_last_tts_error",
                return_value={
                    "provider": "elevenlabs",
                    "status": 402,
                    "code": "paid_plan_required",
                    "message": "Free users cannot use library voices via the API.",
                },
            ),
        ):
            await _send_response(
                111,
                None,
                context,
                run_result,
                str(tmp_path),
                "autonomous",
                elapsed=1.0,
                model="claude-sonnet-4-6",
                task_id=77,
                ctx=ctx,
            )

        sent_text = context.bot.send_message.call_args.kwargs["text"]
        assert "voz selecionada exige plano pago" in sent_text
        assert "Escolha uma voz premade" in sent_text

    @pytest.mark.asyncio
    async def test_send_response_uses_spoken_block_for_audio_and_sends_text_details(self, tmp_path):
        ctx = _make_ctx()
        context = _make_context()
        context.user_data.update(
            {
                "audio_response": True,
                "tts_voice": "pm_alex",
                "tts_voice_language": "pt-br",
                "audio_provider": "kokoro",
                "audio_model": "kokoro-v1",
                "tts_enabled": True,
            }
        )
        ogg = tmp_path.parent / f"{tmp_path.name}-voice.ogg"
        ogg.write_bytes(b"OggS" + b"\x00" * 16)
        run_result = _make_result(
            result=(
                "<spoken_response>Resumo falado curto.</spoken_response>\n\n"
                "Detalhes completos em texto com tabela:\n\n| A | B |\n| - | - |\n| 1 | 2 |"
            )
        )

        with patch("koda.utils.tts.synthesize_speech", new_callable=AsyncMock, return_value=str(ogg)) as mock_tts:
            await _send_response(
                111,
                None,
                context,
                run_result,
                str(tmp_path),
                "autonomous",
                elapsed=1.0,
                model="claude-sonnet-4-6",
                task_id=77,
                ctx=ctx,
            )

        mock_tts.assert_awaited_once()
        assert mock_tts.call_args.args[0] == "Resumo falado curto."
        context.bot.send_voice.assert_awaited_once()
        sent_text = context.bot.send_message.call_args.kwargs["text"]
        assert "Detalhes completos em texto" in sent_text
        assert "spoken_response" not in sent_text

    @pytest.mark.asyncio
    async def test_send_response_persists_tts_audio_as_runtime_artifact(self, tmp_path):
        ctx = _make_ctx()
        context = _make_context()
        context.user_data.update(
            {
                "audio_response": True,
                "tts_voice": "pm_alex",
                "tts_voice_language": "pt-br",
                "audio_provider": "kokoro",
                "audio_model": "kokoro-v1",
                "tts_enabled": True,
            }
        )
        ogg = tmp_path / "temporary-voice.ogg"
        ogg.write_bytes(b"OggS" + b"\x00" * 16)
        runtime = MagicMock()
        persisted_path = tmp_path / "runtime" / "tasks" / "77" / "artifacts" / "voice-response-77.ogg"
        runtime.persist_generated_artifact_file = AsyncMock(
            return_value={
                "id": 88,
                "label": "voice-response-77.ogg",
                "path": str(persisted_path),
                "mime_type": "audio/ogg",
                "size_bytes": 20,
            }
        )
        runtime.events.publish = AsyncMock()
        run_result = _make_result(
            result="Resposta curta.",
            session_id="sess-voice",
            provider_session_id="thread-voice",
        )

        with (
            patch("koda.utils.tts.synthesize_speech", new_callable=AsyncMock, return_value=str(ogg)),
            patch("koda.services.runtime.get_runtime_controller", return_value=runtime),
        ):
            await _send_response(
                111,
                None,
                context,
                run_result,
                str(tmp_path),
                "autonomous",
                elapsed=1.0,
                model="claude-sonnet-4-6",
                task_id=77,
                ctx=ctx,
            )

        runtime.persist_generated_artifact_file.assert_awaited_once()
        persist_kwargs = runtime.persist_generated_artifact_file.await_args.kwargs
        assert persist_kwargs["source_path"] == str(ogg)
        assert persist_kwargs["artifact_kind"] == "audio"
        assert persist_kwargs["metadata"]["source_type"] == "voice_response"
        assert persist_kwargs["metadata"]["provider"] == "kokoro"
        assert persist_kwargs["metadata"]["model"] == "kokoro-v1"
        assert persist_kwargs["metadata"]["voice"] == "pm_alex"
        assert persist_kwargs["metadata"]["session_id"] == "sess-voice"
        assert persist_kwargs["metadata"]["provider_session_id"] == "thread-voice"
        runtime.events.publish.assert_awaited_once()
        event_payload = runtime.events.publish.await_args.kwargs["payload"]
        assert event_payload["artifact"]["id"] == "88"
        assert event_payload["artifact"]["kind"] == "audio"
        assert event_payload["artifact"]["source_execution_id"] == "77"
        assert not ogg.exists()

    @pytest.mark.asyncio
    async def test_send_response_speaks_code_summary_and_keeps_code_as_text(self, tmp_path):
        ctx = _make_ctx()
        context = _make_context()
        context.user_data.update(
            {
                "audio_response": True,
                "tts_voice": "pm_alex",
                "tts_voice_language": "pt-br",
                "audio_provider": "kokoro",
                "audio_model": "kokoro-v1",
                "tts_enabled": True,
            }
        )
        ogg = tmp_path.parent / f"{tmp_path.name}-voice.ogg"
        ogg.write_bytes(b"OggS" + b"\x00" * 16)
        run_result = _make_result(result="Aqui esta:\n```\n" + "print('x')\n" * 200 + "```")

        with patch("koda.utils.tts.synthesize_speech", new_callable=AsyncMock, return_value=str(ogg)) as mock_tts:
            await _send_response(
                111,
                None,
                context,
                run_result,
                str(tmp_path),
                "autonomous",
                elapsed=1.0,
                model="claude-sonnet-4-6",
                task_id=77,
                ctx=ctx,
            )

        spoken_text = mock_tts.call_args.args[0]
        assert "codigo ou detalhes tecnicos" in spoken_text
        assert "print" not in spoken_text
        context.bot.send_voice.assert_awaited_once()
        context.bot.send_document.assert_awaited()
