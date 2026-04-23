"""Tests for message handlers."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from koda.handlers.messages import handle_audio, handle_document, handle_message, handle_photo, handle_voice


class TestHandleMessage:
    @pytest.mark.asyncio
    async def test_unauthorized_user(self, unauthorized_update, mock_context):
        await handle_message(unauthorized_update, mock_context)
        unauthorized_update.message.reply_text.assert_called_with("Access denied.")

    @pytest.mark.asyncio
    async def test_empty_text(self, mock_update, mock_context):
        mock_update.message.text = None
        with patch("koda.handlers.messages.enqueue") as mock_enqueue:
            await handle_message(mock_update, mock_context)
            mock_enqueue.assert_not_called()

    @pytest.mark.asyncio
    async def test_rate_limited(self, mock_update, mock_context):
        with patch("koda.utils.command_helpers.acquire_rate_limit", return_value=False):
            await handle_message(mock_update, mock_context)
            call_text = mock_update.message.reply_text.call_args[0][0]
            assert "Rate limited" in call_text

    @pytest.mark.asyncio
    async def test_enqueues_message(self, mock_update, mock_context):
        with (
            patch("koda.utils.command_helpers.acquire_rate_limit", return_value=True),
            patch("koda.handlers.messages.enqueue") as mock_enqueue,
            patch("koda.handlers.messages.cleanup_previous_images"),
        ):
            await handle_message(mock_update, mock_context)
            mock_enqueue.assert_called_once()

    @pytest.mark.asyncio
    async def test_agent_local_settings_request_is_handled_without_enqueue(self, mock_update, mock_context):
        with (
            patch("koda.utils.command_helpers.acquire_rate_limit", return_value=True),
            patch(
                "koda.handlers.messages.maybe_apply_agent_local_settings_from_chat",
                return_value="Provider deste AGENT atualizado.",
            ),
            patch("koda.handlers.messages.enqueue") as mock_enqueue,
        ):
            await handle_message(mock_update, mock_context)
        mock_enqueue.assert_not_called()
        mock_update.message.reply_text.assert_called_once()


class TestHandlePhoto:
    @pytest.mark.asyncio
    async def test_unauthorized_user(self, unauthorized_update, mock_context):
        await handle_photo(unauthorized_update, mock_context)
        unauthorized_update.message.reply_text.assert_called_with("Access denied.")

    @pytest.mark.asyncio
    async def test_download_fails(self, mock_update, mock_context):
        with (
            patch("koda.utils.command_helpers.acquire_rate_limit", return_value=True),
            patch("koda.handlers.messages.download_photos", return_value=[]),
        ):
            await handle_photo(mock_update, mock_context)
            call_text = mock_update.message.reply_text.call_args[0][0]
            assert "Could not download" in call_text

    @pytest.mark.asyncio
    async def test_successful_photo_enqueues_artifact_bundle(self, mock_update, mock_context):
        mock_update.message.caption = "analise"
        with (
            patch("koda.utils.command_helpers.acquire_rate_limit", return_value=True),
            patch("koda.handlers.messages.download_photos", return_value=["/tmp/screen.png"]),
            patch("koda.handlers.messages.track_images"),
            patch("koda.handlers.messages.cleanup_previous_images"),
            patch("koda.handlers.messages.build_local_artifact_bundle", return_value="bundle") as mock_bundle,
            patch("koda.handlers.messages.enqueue") as mock_enqueue,
        ):
            await handle_photo(mock_update, mock_context)

        mock_bundle.assert_called_once_with(["/tmp/screen.png"], source="telegram_photo")
        assert mock_enqueue.call_args[0][4] == ["/tmp/screen.png"]
        assert mock_enqueue.call_args[0][5] == "bundle"


class TestHandleDocument:
    @pytest.mark.asyncio
    async def test_unsupported_document_type(self, mock_update, mock_context):
        mock_update.message.document = MagicMock(mime_type="application/octet-stream")
        with patch("koda.utils.command_helpers.acquire_rate_limit", return_value=True):
            await handle_document(mock_update, mock_context)
        call_text = mock_update.message.reply_text.call_args[0][0]
        assert "Unsupported document type" in call_text

    @pytest.mark.asyncio
    async def test_supported_document_enqueues_typed_artifact_bundle(self, mock_update, mock_context):
        mock_update.message.document = MagicMock(mime_type="application/pdf")
        mock_update.message.caption = "resuma"
        with (
            patch("koda.utils.command_helpers.acquire_rate_limit", return_value=True),
            patch("koda.handlers.messages.download_document", return_value=("/tmp/spec.pdf", "spec.pdf")),
            patch("koda.handlers.messages.track_images"),
            patch("koda.handlers.messages.cleanup_previous_images"),
            patch("koda.handlers.messages.build_local_artifact_bundle", return_value="bundle") as mock_bundle,
            patch("koda.handlers.messages.enqueue") as mock_enqueue,
        ):
            await handle_document(mock_update, mock_context)

        mock_bundle.assert_called_once_with(
            ["/tmp/spec.pdf"],
            source="telegram_document",
            mime_types={"/tmp/spec.pdf": "application/pdf"},
        )
        assert mock_enqueue.call_args[0][4] == ["/tmp/spec.pdf"]
        assert mock_enqueue.call_args[0][5] == "bundle"


class TestHandleVoice:
    @pytest.mark.asyncio
    async def test_unauthorized_user(self, unauthorized_update, mock_context):
        await handle_voice(unauthorized_update, mock_context)
        unauthorized_update.message.reply_text.assert_called_with("Access denied.")

    @pytest.mark.asyncio
    async def test_download_fails(self, mock_update, mock_context):
        with (
            patch("koda.utils.command_helpers.acquire_rate_limit", return_value=True),
            patch("koda.handlers.messages.download_voice", return_value=None),
        ):
            await handle_voice(mock_update, mock_context)
            call_text = mock_update.message.reply_text.call_args[0][0]
            assert "Could not download" in call_text

    @pytest.mark.asyncio
    async def test_transcription_fails(self, mock_update, mock_context):
        with (
            patch("koda.utils.command_helpers.acquire_rate_limit", return_value=True),
            patch("koda.handlers.messages.download_voice", return_value="/tmp/voice.ogg"),
            patch("koda.handlers.messages.transcribe_audio", return_value=None),
            patch("koda.handlers.messages.Path"),
        ):
            await handle_voice(mock_update, mock_context)
            call_text = mock_update.message.reply_text.call_args[0][0]
            assert "transcribe" in call_text.lower()

    @pytest.mark.asyncio
    async def test_successful_transcription_enqueues_text(self, mock_update, mock_context):
        mock_update.message.caption = None
        mock_context.user_data["transcription_provider"] = "codex"
        mock_context.user_data["transcription_model"] = "whisper-1"
        with (
            patch("koda.utils.command_helpers.acquire_rate_limit", return_value=True),
            patch("koda.handlers.messages.download_voice", return_value="/tmp/voice.ogg"),
            patch("koda.handlers.messages.transcribe_audio", return_value="Olá mundo") as mock_transcribe,
            patch("koda.handlers.messages.Path"),
            patch("koda.handlers.messages.enqueue") as mock_enqueue,
            patch("koda.handlers.messages.cleanup_previous_images"),
        ):
            await handle_voice(mock_update, mock_context)
            mock_transcribe.assert_awaited_once_with(
                "/tmp/voice.ogg",
                provider="codex",
                model="whisper-1",
            )
            mock_enqueue.assert_called_once()
            # Should enqueue as text only (no image_paths argument)
            args = mock_enqueue.call_args
            assert len(args[0]) == 4  # user_id, update, context, query_text
            assert "Olá mundo" in args[0][3]


class TestLinkAnalysisInterception:
    @pytest.mark.asyncio
    async def test_link_message_intercepted(self, mock_update, mock_context):
        """URL-only message should be intercepted, enqueue NOT called."""
        mock_update.message.text = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
        mock_meta = MagicMock()
        mock_meta.summary_text.return_value = "Preview text"

        with (
            patch("koda.utils.command_helpers.acquire_rate_limit", return_value=True),
            patch("koda.handlers.messages.cleanup_previous_images"),
            patch("koda.handlers.messages.LINK_ANALYSIS_ENABLED", True),
            patch(
                "koda.services.link_analyzer.fetch_link_metadata",
                new_callable=AsyncMock,
                return_value=mock_meta,
            ),
            patch("koda.services.link_analyzer.build_link_keyboard", return_value=MagicMock()),
            patch("koda.services.link_analyzer.meta_to_dict", return_value={}),
            patch("koda.handlers.messages.enqueue") as mock_enqueue,
        ):
            await handle_message(mock_update, mock_context)
            mock_enqueue.assert_not_called()
            mock_update.message.reply_text.assert_called_once()

    @pytest.mark.asyncio
    async def test_link_message_with_long_text_not_intercepted(self, mock_update, mock_context):
        """URL with long surrounding text should NOT be intercepted."""
        mock_update.message.text = (
            "preciso que você analise o conteúdo desse artigo e me diga se as conclusões são válidas "
            "https://example.com/article"
        )
        with (
            patch("koda.utils.command_helpers.acquire_rate_limit", return_value=True),
            patch("koda.handlers.messages.cleanup_previous_images"),
            patch("koda.handlers.messages.LINK_ANALYSIS_ENABLED", True),
            patch("koda.handlers.messages.enqueue") as mock_enqueue,
        ):
            await handle_message(mock_update, mock_context)
            mock_enqueue.assert_called_once()

    @pytest.mark.asyncio
    async def test_link_analysis_disabled(self, mock_update, mock_context):
        """When LINK_ANALYSIS_ENABLED is False, URL messages go to enqueue normally."""
        mock_update.message.text = "https://example.com"
        with (
            patch("koda.utils.command_helpers.acquire_rate_limit", return_value=True),
            patch("koda.handlers.messages.cleanup_previous_images"),
            patch("koda.handlers.messages.LINK_ANALYSIS_ENABLED", False),
            patch("koda.handlers.messages.enqueue") as mock_enqueue,
        ):
            await handle_message(mock_update, mock_context)
            mock_enqueue.assert_called_once()


class TestHandleAudio:
    @pytest.mark.asyncio
    async def test_unauthorized_user(self, unauthorized_update, mock_context):
        await handle_audio(unauthorized_update, mock_context)
        unauthorized_update.message.reply_text.assert_called_with("Access denied.")

    @pytest.mark.asyncio
    async def test_download_fails(self, mock_update, mock_context):
        with (
            patch("koda.utils.command_helpers.acquire_rate_limit", return_value=True),
            patch("koda.handlers.messages.download_audio", return_value=None),
        ):
            await handle_audio(mock_update, mock_context)
            call_text = mock_update.message.reply_text.call_args[0][0]
            assert "Could not download" in call_text

    @pytest.mark.asyncio
    async def test_successful_audio_with_caption(self, mock_update, mock_context):
        mock_update.message.caption = "Resumo disso"
        mock_context.user_data["transcription_provider"] = "codex"
        mock_context.user_data["transcription_model"] = "gpt-4o-transcribe"
        with (
            patch("koda.utils.command_helpers.acquire_rate_limit", return_value=True),
            patch("koda.handlers.messages.download_audio", return_value="/tmp/audio.mp3"),
            patch("koda.handlers.messages.transcribe_audio", return_value="Texto do áudio") as mock_transcribe,
            patch("koda.handlers.messages.Path"),
            patch("koda.handlers.messages.enqueue") as mock_enqueue,
            patch("koda.handlers.messages.cleanup_previous_images"),
        ):
            await handle_audio(mock_update, mock_context)
            mock_transcribe.assert_awaited_once_with(
                "/tmp/audio.mp3",
                provider="codex",
                model="gpt-4o-transcribe",
            )
            mock_enqueue.assert_called_once()
            query_text = mock_enqueue.call_args[0][3]
            assert "Texto do áudio" in query_text
            assert "Resumo disso" in query_text
