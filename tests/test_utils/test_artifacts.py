"""Tests for koda.utils.artifacts."""

import os
from unittest.mock import AsyncMock

import pytest

from koda.utils.artifacts import (
    _is_valid_image,
    extract_created_files,
    send_created_files,
)

# -- extract_created_files ---------------------------------------------------


def test_extract_write_and_write_file():
    tool_uses = [
        {"name": "Write", "input": {"file_path": "/tmp/a.py"}},
        {"name": "write_file", "input": {"file_path": "/tmp/b.txt"}},
    ]
    assert extract_created_files(tool_uses) == ["/tmp/a.py", "/tmp/b.txt"]


def test_extract_edit_paths():
    tool_uses = [
        {"name": "Edit", "input": {"file_path": "/tmp/c.html"}},
        {"name": "edit_file", "input": {"file_path": "/tmp/d.css"}},
    ]
    assert extract_created_files(tool_uses) == ["/tmp/c.html", "/tmp/d.css"]


def test_extract_ignores_non_file_tools():
    tool_uses = [
        {"name": "Read", "input": {"file_path": "/tmp/x.py"}},
        {"name": "Bash", "input": {"command": "ls"}},
        {"name": "Grep", "input": {"pattern": "foo"}},
        {"name": "Write", "input": {"file_path": "/tmp/y.py"}},
    ]
    assert extract_created_files(tool_uses) == ["/tmp/y.py"]


def test_extract_deduplicates():
    tool_uses = [
        {"name": "Write", "input": {"file_path": "/tmp/dup.py"}},
        {"name": "Write", "input": {"file_path": "/tmp/dup.py"}},
    ]
    assert extract_created_files(tool_uses) == ["/tmp/dup.py"]


def test_extract_empty():
    assert extract_created_files([]) == []


def test_extract_missing_file_path():
    tool_uses = [
        {"name": "Write", "input": {}},
        {"name": "Write"},
    ]
    assert extract_created_files(tool_uses) == []


def test_extract_native_command_created_docx_from_output(tmp_path):
    doc = tmp_path / "animais_silvestres_teste.docx"
    doc.write_bytes(b"docx")
    native_items = [
        {
            "type": "command_execution",
            "command": "python - <<'PY'\nout = 'animais_silvestres_teste.docx'\nPY",
            "output": "animais_silvestres_teste.docx\n",
        }
    ]

    assert extract_created_files([], native_items, work_dir=str(tmp_path)) == [str(doc.resolve())]


def test_extract_native_command_ignores_artifact_outside_work_dir(tmp_path):
    outside = tmp_path.parent / "outside.pdf"
    outside.write_bytes(b"pdf")
    native_items = [{"type": "command_execution", "output": str(outside)}]

    assert extract_created_files([], native_items, work_dir=str(tmp_path)) == []


def test_extract_native_file_change_resolves_relative_path(tmp_path):
    native_items = [{"type": "file_change", "kind": "add", "path": "relatorio.pdf"}]

    assert extract_created_files([], native_items, work_dir=str(tmp_path)) == [str(tmp_path / "relatorio.pdf")]


def test_extract_agent_shell_created_artifact_from_trace_output(tmp_path):
    sheet = tmp_path / "planilha.xlsx"
    sheet.write_bytes(b"xlsx")
    trace = [
        {
            "tool": "shell_execute",
            "success": True,
            "output": "Created planilha.xlsx",
            "metadata": {"category": "shell"},
        }
    ]

    assert extract_created_files([], [], trace, work_dir=str(tmp_path)) == [str(sheet.resolve())]


def test_extract_agent_file_write_from_trace_params(tmp_path):
    doc = tmp_path / "resumo.docx"
    doc.write_bytes(b"docx")
    trace = [
        {
            "tool": "file_write",
            "success": True,
            "params": {"path": "resumo.docx"},
            "output": "Written 4 bytes to resumo.docx",
            "metadata": {"write": True},
        }
    ]

    assert extract_created_files([], [], trace, work_dir=str(tmp_path)) == [str(doc.resolve())]


def test_extract_trace_ignores_read_output_artifact_name(tmp_path):
    doc = tmp_path / "entrada.docx"
    doc.write_bytes(b"docx")
    trace = [
        {
            "tool": "file_read",
            "success": True,
            "output": "entrada.docx",
            "metadata": {"write": False},
        }
    ]

    assert extract_created_files([], [], trace, work_dir=str(tmp_path)) == []


def test_extract_tool_use_shell_output_without_command_leak(tmp_path):
    pdf = tmp_path / "relatorio.pdf"
    pdf.write_bytes(b"pdf")
    tool_uses = [
        {
            "name": "Bash",
            "input": {"command": "python generate.py --secret sk-test"},
            "output": "relatorio.pdf",
        }
    ]

    assert extract_created_files(tool_uses, work_dir=str(tmp_path)) == [str(pdf.resolve())]


def test_extract_tool_use_shell_does_not_attach_command_only_path(tmp_path):
    existing = tmp_path / "entrada.pdf"
    existing.write_bytes(b"pdf")
    tool_uses = [
        {
            "name": "Bash",
            "input": {"command": "python process.py entrada.pdf"},
        }
    ]

    assert extract_created_files(tool_uses, work_dir=str(tmp_path)) == []


# -- send_created_files -------------------------------------------------------


@pytest.mark.asyncio
async def test_send_image(mock_update, mock_context, tmp_path):
    img = tmp_path / "photo.png"
    img.write_bytes(b"\x89PNG" + b"\x00" * 100)
    sent = await send_created_files([str(img)], 111, mock_context, mock_update)
    assert sent == 1
    mock_update.message.reply_photo.assert_awaited_once()


@pytest.mark.asyncio
async def test_send_video(mock_update, mock_context, tmp_path):
    vid = tmp_path / "clip.mp4"
    vid.write_bytes(b"\x00\x00")
    sent = await send_created_files([str(vid)], 111, mock_context, mock_update)
    assert sent == 1
    mock_update.message.reply_video.assert_awaited_once()


@pytest.mark.asyncio
async def test_send_document(mock_update, mock_context, tmp_path):
    doc = tmp_path / "data.csv"
    doc.write_text("a,b,c")
    sent = await send_created_files([str(doc)], 111, mock_context, mock_update)
    assert sent == 1
    mock_update.message.reply_document.assert_awaited_once()


@pytest.mark.asyncio
async def test_send_gif_as_animation(mock_update, mock_context, tmp_path):
    gif = tmp_path / "anim.gif"
    gif.write_bytes(b"GIF89a" + b"\x00" * 100)
    sent = await send_created_files([str(gif)], 111, mock_context, mock_update)
    assert sent == 1
    mock_update.message.reply_animation.assert_awaited_once()


@pytest.mark.asyncio
async def test_send_audio(mock_update, mock_context, tmp_path):
    audio = tmp_path / "track.mp3"
    audio.write_bytes(b"\xff\xfb\x90" + b"\x00" * 100)
    sent = await send_created_files([str(audio)], 111, mock_context, mock_update)
    assert sent == 1
    mock_update.message.reply_audio.assert_awaited_once()


@pytest.mark.asyncio
async def test_send_voice(mock_update, mock_context, tmp_path):
    voice = tmp_path / "memo.ogg"
    voice.write_bytes(b"OggS" + b"\x00" * 100)
    sent = await send_created_files([str(voice)], 111, mock_context, mock_update)
    assert sent == 1
    mock_update.message.reply_voice.assert_awaited_once()


@pytest.mark.asyncio
async def test_large_photo_sent_as_document(mock_update, mock_context, tmp_path, monkeypatch):
    """Photo >10MB should be sent as document, not photo."""
    img = tmp_path / "huge.png"
    img.write_bytes(b"\x89PNG" + b"\x00" * 100)
    monkeypatch.setattr(os.path, "getsize", lambda _: 11 * 1024 * 1024)
    sent = await send_created_files([str(img)], 111, mock_context, mock_update)
    assert sent == 1
    mock_update.message.reply_photo.assert_not_awaited()
    mock_update.message.reply_document.assert_awaited_once()


@pytest.mark.asyncio
async def test_invalid_image_fallback_document(mock_update, mock_context, tmp_path):
    """A .png file with HTML content (not a real image) should be sent as document."""
    fake_img = tmp_path / "report.png"
    fake_img.write_text("<html><body>Not an image</body></html>")
    sent = await send_created_files([str(fake_img)], 111, mock_context, mock_update)
    assert sent == 1
    mock_update.message.reply_photo.assert_not_awaited()
    mock_update.message.reply_document.assert_awaited_once()


@pytest.mark.asyncio
async def test_photo_api_error_fallback_document(mock_update, mock_context, tmp_path):
    """If reply_photo raises, fallback to reply_document."""
    img = tmp_path / "tricky.png"
    img.write_bytes(b"\x89PNG" + b"\x00" * 100)
    mock_update.message.reply_photo = AsyncMock(side_effect=Exception("Telegram API error"))
    sent = await send_created_files([str(img)], 111, mock_context, mock_update)
    assert sent == 1
    mock_update.message.reply_document.assert_awaited_once()


@pytest.mark.asyncio
async def test_animation_api_error_fallback_document(mock_update, mock_context, tmp_path):
    """If reply_animation raises, fallback to reply_document."""
    gif = tmp_path / "broken.gif"
    gif.write_bytes(b"GIF89a" + b"\x00" * 100)
    mock_update.message.reply_animation = AsyncMock(side_effect=Exception("Telegram API error"))
    sent = await send_created_files([str(gif)], 111, mock_context, mock_update)
    assert sent == 1
    mock_update.message.reply_document.assert_awaited_once()


@pytest.mark.asyncio
async def test_video_api_error_fallback_document(mock_update, mock_context, tmp_path):
    vid = tmp_path / "broken.mp4"
    vid.write_bytes(b"\x00\x00\x00\x18ftypmp42" + b"\x00" * 100)
    mock_update.message.reply_video = AsyncMock(side_effect=Exception("Telegram API error"))
    sent = await send_created_files([str(vid)], 111, mock_context, mock_update)
    assert sent == 1
    mock_update.message.reply_document.assert_awaited_once()


@pytest.mark.asyncio
async def test_audio_api_error_fallback_document(mock_update, mock_context, tmp_path):
    audio = tmp_path / "broken.mp3"
    audio.write_bytes(b"\xff\xfb\x90" + b"\x00" * 100)
    mock_update.message.reply_audio = AsyncMock(side_effect=Exception("Telegram API error"))
    sent = await send_created_files([str(audio)], 111, mock_context, mock_update)
    assert sent == 1
    mock_update.message.reply_document.assert_awaited_once()


@pytest.mark.asyncio
async def test_voice_api_error_fallback_document(mock_update, mock_context, tmp_path):
    voice = tmp_path / "broken.ogg"
    voice.write_bytes(b"OggS" + b"\x00" * 100)
    mock_update.message.reply_voice = AsyncMock(side_effect=Exception("Telegram API error"))
    sent = await send_created_files([str(voice)], 111, mock_context, mock_update)
    assert sent == 1
    mock_update.message.reply_document.assert_awaited_once()


@pytest.mark.asyncio
async def test_caption_includes_size(mock_update, mock_context, tmp_path):
    doc = tmp_path / "readme.txt"
    doc.write_text("hello world")
    sent = await send_created_files([str(doc)], 111, mock_context, mock_update)
    assert sent == 1
    call_kwargs = mock_update.message.reply_document.call_args
    caption = call_kwargs.kwargs.get("caption", "") or call_kwargs[1].get("caption", "")
    assert "readme.txt" in caption
    # Size should be present (e.g. "11B" or similar)
    assert "B" in caption or "KB" in caption or "MB" in caption


@pytest.mark.asyncio
async def test_skip_missing(mock_update, mock_context):
    sent = await send_created_files(["/nonexistent/file.txt"], 111, mock_context, mock_update)
    assert sent == 0


@pytest.mark.asyncio
async def test_skip_large(mock_update, mock_context, tmp_path, monkeypatch):
    big = tmp_path / "big.bin"
    big.write_bytes(b"x")
    # Pretend the file is over 50 MB
    monkeypatch.setattr(os.path, "getsize", lambda _: 60 * 1024 * 1024)
    sent = await send_created_files([str(big)], 111, mock_context, mock_update)
    assert sent == 0


@pytest.mark.asyncio
async def test_fallback_context_agent(mock_context, tmp_path):
    """When update is None, uses context.bot methods."""
    doc = tmp_path / "out.json"
    doc.write_text("{}")
    sent = await send_created_files([str(doc)], 111, mock_context, None)
    assert sent == 1
    mock_context.bot.send_document.assert_awaited_once()


# -- _is_valid_image ----------------------------------------------------------


def test_valid_png(tmp_path):
    img = tmp_path / "test.png"
    img.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 100)
    assert _is_valid_image(str(img)) is True


def test_valid_jpg(tmp_path):
    img = tmp_path / "test.jpg"
    img.write_bytes(b"\xff\xd8\xff\xe0" + b"\x00" * 100)
    assert _is_valid_image(str(img)) is True


def test_valid_bmp(tmp_path):
    img = tmp_path / "test.bmp"
    img.write_bytes(b"BM" + b"\x00" * 100)
    assert _is_valid_image(str(img)) is True


def test_valid_webp(tmp_path):
    img = tmp_path / "test.webp"
    img.write_bytes(b"RIFF\x00\x00\x00\x00WEBP" + b"\x00" * 100)
    assert _is_valid_image(str(img)) is True


def test_riff_non_webp_is_invalid(tmp_path):
    """A RIFF file that is NOT WebP (e.g. WAV) should not pass image validation."""
    img = tmp_path / "audio.webp"
    img.write_bytes(b"RIFF\x00\x00\x00\x00WAVE" + b"\x00" * 100)
    assert _is_valid_image(str(img)) is False


def test_invalid_image_html(tmp_path):
    img = tmp_path / "fake.png"
    img.write_text("<html>not an image</html>")
    assert _is_valid_image(str(img)) is False
