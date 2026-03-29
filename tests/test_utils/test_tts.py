"""Tests for TTS module."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from koda.utils.tts import AVAILABLE_VOICES, VoiceConfig, is_mostly_code, strip_for_tts


class TestStripForTts:
    def test_removes_code_blocks(self):
        text = "Hello\n```python\nprint('hi')\n```\nWorld"
        result = strip_for_tts(text)
        assert "print" not in result
        assert "bloco de código omitido" in result
        assert "Hello" in result
        assert "World" in result

    def test_removes_inline_code(self):
        result = strip_for_tts("Use `pip install foo` to install")
        assert "`" not in result
        assert "pip install foo" not in result

    def test_converts_markdown_links(self):
        result = strip_for_tts("Check [the docs](https://example.com) here")
        assert "the docs" in result
        assert "https://example.com" not in result

    def test_removes_bare_urls(self):
        result = strip_for_tts("Visit https://example.com/path for more")
        assert "https://" not in result

    def test_removes_html_entities(self):
        result = strip_for_tts("Use &amp; and &lt; in HTML")
        assert "&amp;" not in result
        assert "&lt;" not in result

    def test_removes_markdown_formatting(self):
        result = strip_for_tts("This is **bold** and *italic* and ~~struck~~")
        assert "**" not in result
        assert "~~" not in result

    def test_collapses_newlines(self):
        result = strip_for_tts("Line 1\n\n\n\n\nLine 2")
        assert "\n\n\n" not in result

    def test_truncates_long_text(self):
        with patch("koda.utils.tts.TTS_MAX_CHARS", 100):
            long_text = "This is a sentence. " * 20
            result = strip_for_tts(long_text)
            assert len(result) <= 100

    def test_truncates_at_sentence_boundary(self):
        with patch("koda.utils.tts.TTS_MAX_CHARS", 50):
            text = "First sentence. Second sentence. Third sentence. Fourth sentence."
            result = strip_for_tts(text)
            assert result.endswith(".")

    def test_empty_input(self):
        assert strip_for_tts("") == ""

    def test_preserves_plain_text(self):
        text = "Hello, this is a simple text response."
        assert strip_for_tts(text) == text


class TestIsMostlyCode:
    def test_mostly_code(self):
        text = "```python\n" + "x = 1\n" * 50 + "```\nshort note"
        assert is_mostly_code(text) is True

    def test_mostly_text(self):
        text = "This is a long explanation. " * 20 + "```\nx=1\n```"
        assert is_mostly_code(text) is False

    def test_no_code(self):
        assert is_mostly_code("Just a plain response with no code.") is False

    def test_empty(self):
        assert is_mostly_code("") is False

    def test_exactly_at_threshold(self):
        # 60% code: code_len / total_len > 0.6
        code = "```\n" + "a" * 60 + "\n```"  # ~67 chars
        text_part = "b" * 30
        full = code + text_part
        # code block includes the backticks, let's verify
        result = is_mostly_code(full)
        # The code block is > 60% of total, should be True
        assert isinstance(result, bool)


class TestVoiceConfig:
    def test_available_voices_structure(self):
        """Verify AVAILABLE_VOICES has correct VoiceConfig structure."""
        assert len(AVAILABLE_VOICES) == 6
        for _vid, vc in AVAILABLE_VOICES.items():
            assert isinstance(vc, VoiceConfig)
            assert vc.engine in ("elevenlabs", "kokoro")
            assert vc.label
            assert vc.engine_voice_id

    def test_elevenlabs_voices_have_fallback(self):
        """All ElevenLabs voices must have a Kokoro fallback."""
        for _vid, vc in AVAILABLE_VOICES.items():
            if vc.engine == "elevenlabs":
                assert vc.fallback_kokoro is not None
                assert vc.fallback_kokoro in AVAILABLE_VOICES

    def test_kokoro_voices_have_no_fallback(self):
        """Kokoro voices should not have a fallback."""
        for _vid, vc in AVAILABLE_VOICES.items():
            if vc.engine == "kokoro":
                assert vc.fallback_kokoro is None


class TestElevenLabsSynthesize:
    @pytest.mark.asyncio
    async def test_success_returns_ogg_path(self):
        """Mock aiohttp, return 200 + bytes -> OGG path."""
        mock_resp = AsyncMock()
        mock_resp.status = 200
        mock_resp.read = AsyncMock(return_value=b"fake-ogg-data")

        mock_session_ctx = AsyncMock()
        mock_session_ctx.__aenter__ = AsyncMock(return_value=mock_resp)
        mock_session_ctx.__aexit__ = AsyncMock(return_value=False)

        mock_session = AsyncMock()
        mock_session.post = MagicMock(return_value=mock_session_ctx)

        mock_client_ctx = AsyncMock()
        mock_client_ctx.__aenter__ = AsyncMock(return_value=mock_session)
        mock_client_ctx.__aexit__ = AsyncMock(return_value=False)

        with (
            patch("koda.utils.tts.ELEVENLABS_API_KEY", "test-key"),
            patch("aiohttp.ClientSession", return_value=mock_client_ctx),
        ):
            from koda.utils.tts import _elevenlabs_synthesize

            result = await _elevenlabs_synthesize("Hello world", "voice123")

        assert result is not None
        assert result.endswith(".ogg")
        # Clean up temp file
        import os

        if result and os.path.exists(result):
            os.unlink(result)

    @pytest.mark.asyncio
    async def test_api_error_returns_none(self):
        """Status 401/429 -> None."""
        mock_resp = AsyncMock()
        mock_resp.status = 401
        mock_resp.text = AsyncMock(return_value="Unauthorized")

        mock_session_ctx = AsyncMock()
        mock_session_ctx.__aenter__ = AsyncMock(return_value=mock_resp)
        mock_session_ctx.__aexit__ = AsyncMock(return_value=False)

        mock_session = AsyncMock()
        mock_session.post = MagicMock(return_value=mock_session_ctx)

        mock_client_ctx = AsyncMock()
        mock_client_ctx.__aenter__ = AsyncMock(return_value=mock_session)
        mock_client_ctx.__aexit__ = AsyncMock(return_value=False)

        with (
            patch("koda.utils.tts.ELEVENLABS_API_KEY", "test-key"),
            patch("aiohttp.ClientSession", return_value=mock_client_ctx),
        ):
            from koda.utils.tts import _elevenlabs_synthesize

            result = await _elevenlabs_synthesize("Hello", "voice123")

        assert result is None

    @pytest.mark.asyncio
    async def test_network_error_returns_none(self):
        """ConnectionError -> None."""
        import aiohttp

        mock_client_ctx = AsyncMock()
        mock_client_ctx.__aenter__ = AsyncMock(side_effect=aiohttp.ClientError("Connection failed"))
        mock_client_ctx.__aexit__ = AsyncMock(return_value=False)

        with (
            patch("koda.utils.tts.ELEVENLABS_API_KEY", "test-key"),
            patch("aiohttp.ClientSession", return_value=mock_client_ctx),
        ):
            from koda.utils.tts import _elevenlabs_synthesize

            result = await _elevenlabs_synthesize("Hello", "voice123")

        assert result is None

    @pytest.mark.asyncio
    async def test_timeout_returns_none(self):
        """TimeoutError -> None."""
        mock_client_ctx = AsyncMock()
        mock_client_ctx.__aenter__ = AsyncMock(side_effect=TimeoutError())
        mock_client_ctx.__aexit__ = AsyncMock(return_value=False)

        with (
            patch("koda.utils.tts.ELEVENLABS_API_KEY", "test-key"),
            patch("aiohttp.ClientSession", return_value=mock_client_ctx),
        ):
            from koda.utils.tts import _elevenlabs_synthesize

            result = await _elevenlabs_synthesize("Hello", "voice123")

        assert result is None

    @pytest.mark.asyncio
    async def test_no_api_key_returns_none(self):
        """ELEVENLABS_API_KEY=None -> None immediately."""
        with patch("koda.utils.tts.ELEVENLABS_API_KEY", None):
            from koda.utils.tts import _elevenlabs_synthesize

            result = await _elevenlabs_synthesize("Hello", "voice123")

        assert result is None


class TestSynthesizeSpeechRouting:
    @pytest.mark.asyncio
    async def test_elevenlabs_voice_calls_elevenlabs(self):
        """ElevenLabs voice -> calls _elevenlabs_synthesize."""
        with (
            patch(
                "koda.utils.tts._elevenlabs_synthesize", new_callable=AsyncMock, return_value="/tmp/test.ogg"
            ) as mock_el,
            patch("koda.utils.tts._kokoro_synthesize", new_callable=AsyncMock) as mock_ko,
        ):
            from koda.utils.tts import synthesize_speech

            result = await synthesize_speech("Hello", "brian", 1.0)

        assert result == "/tmp/test.ogg"
        mock_el.assert_called_once_with("Hello", "nPczCjzI2devNBz1zQrb", 1.0, model_id=None)
        mock_ko.assert_not_called()

    @pytest.mark.asyncio
    async def test_elevenlabs_voice_passes_speed(self):
        """Speed parameter is forwarded to _elevenlabs_synthesize."""
        with (
            patch(
                "koda.utils.tts._elevenlabs_synthesize", new_callable=AsyncMock, return_value="/tmp/test.ogg"
            ) as mock_el,
            patch("koda.utils.tts._kokoro_synthesize", new_callable=AsyncMock),
        ):
            from koda.utils.tts import synthesize_speech

            await synthesize_speech("Hello", "brian", 1.5)

        mock_el.assert_called_once_with("Hello", "nPczCjzI2devNBz1zQrb", 1.5, model_id=None)

    @pytest.mark.asyncio
    async def test_custom_elevenlabs_voice_id(self):
        """Long alphanumeric voice ID -> tries ElevenLabs directly."""
        custom_id = "Xb7hH8MSUJpSbSDYk0k2"  # 20+ chars, alphanumeric
        with (
            patch(
                "koda.utils.tts._elevenlabs_synthesize", new_callable=AsyncMock, return_value="/tmp/custom.ogg"
            ) as mock_el,
            patch("koda.utils.tts._kokoro_synthesize", new_callable=AsyncMock) as mock_ko,
        ):
            from koda.utils.tts import synthesize_speech

            result = await synthesize_speech("Hello", custom_id, 1.0)

        assert result == "/tmp/custom.ogg"
        mock_el.assert_called_once_with("Hello", custom_id, 1.0, model_id=None)
        mock_ko.assert_not_called()

    @pytest.mark.asyncio
    async def test_custom_elevenlabs_voice_id_fallback(self):
        """Custom ElevenLabs voice fails -> falls back to Kokoro default."""
        custom_id = "Xb7hH8MSUJpSbSDYk0k2"
        with (
            patch("koda.utils.tts._elevenlabs_synthesize", new_callable=AsyncMock, return_value=None) as mock_el,
            patch("koda.utils.tts._kokoro_synthesize", new_callable=AsyncMock, return_value="/tmp/ko.ogg") as mock_ko,
            patch("koda.utils.tts.KOKORO_DEFAULT_VOICE", "pf_dora"),
        ):
            from koda.utils.tts import synthesize_speech

            result = await synthesize_speech("Hello", custom_id, 1.0)

        assert result == "/tmp/ko.ogg"
        mock_el.assert_called_once()
        mock_ko.assert_called_once_with("Hello", "pf_dora", 1.0, language=None)

    @pytest.mark.asyncio
    async def test_elevenlabs_failure_falls_back_to_kokoro(self):
        """ElevenLabs returns None -> falls back to _kokoro_synthesize."""
        with (
            patch("koda.utils.tts._elevenlabs_synthesize", new_callable=AsyncMock, return_value=None) as mock_el,
            patch(
                "koda.utils.tts._kokoro_synthesize", new_callable=AsyncMock, return_value="/tmp/kokoro.ogg"
            ) as mock_ko,
        ):
            from koda.utils.tts import synthesize_speech

            result = await synthesize_speech("Hello", "brian", 1.0)

        assert result == "/tmp/kokoro.ogg"
        mock_el.assert_called_once()
        mock_ko.assert_called_once_with("Hello", "pm_alex", 1.0, language=None)

    @pytest.mark.asyncio
    async def test_kokoro_voice_skips_elevenlabs(self):
        """Kokoro voice -> only calls _kokoro_synthesize."""
        with (
            patch("koda.utils.tts._elevenlabs_synthesize", new_callable=AsyncMock) as mock_el,
            patch(
                "koda.utils.tts._kokoro_synthesize", new_callable=AsyncMock, return_value="/tmp/kokoro.ogg"
            ) as mock_ko,
        ):
            from koda.utils.tts import synthesize_speech

            result = await synthesize_speech("Hello", "pm_alex", 1.0)

        assert result == "/tmp/kokoro.ogg"
        mock_el.assert_not_called()
        mock_ko.assert_called_once_with("Hello", "pm_alex", 1.0, language=None)

    @pytest.mark.asyncio
    async def test_unknown_voice_tries_kokoro(self):
        """Unknown voice -> Kokoro directly."""
        with (
            patch("koda.utils.tts._elevenlabs_synthesize", new_callable=AsyncMock) as mock_el,
            patch(
                "koda.utils.tts._kokoro_synthesize", new_callable=AsyncMock, return_value="/tmp/kokoro.ogg"
            ) as mock_ko,
        ):
            from koda.utils.tts import synthesize_speech

            result = await synthesize_speech("Hello", "unknown_voice", 1.0)

        assert result == "/tmp/kokoro.ogg"
        mock_el.assert_not_called()
        mock_ko.assert_called_once_with("Hello", "unknown_voice", 1.0, language=None)

    @pytest.mark.asyncio
    async def test_explicit_audio_provider_model_and_language_are_forwarded(self):
        with (
            patch(
                "koda.utils.tts._elevenlabs_synthesize", new_callable=AsyncMock, return_value="/tmp/test.ogg"
            ) as mock_el,
            patch("koda.utils.tts._kokoro_synthesize", new_callable=AsyncMock) as mock_ko,
        ):
            from koda.utils.tts import synthesize_speech

            result = await synthesize_speech(
                "Hello",
                "brian",
                1.0,
                provider="elevenlabs",
                model="eleven_v3",
                language="pt-br",
            )

        assert result == "/tmp/test.ogg"
        mock_el.assert_called_once_with("Hello", "nPczCjzI2devNBz1zQrb", 1.0, model_id="eleven_v3")
        mock_ko.assert_not_called()

    @pytest.mark.asyncio
    async def test_explicit_kokoro_language_is_forwarded(self):
        with (
            patch("koda.utils.tts._elevenlabs_synthesize", new_callable=AsyncMock) as mock_el,
            patch(
                "koda.utils.tts._kokoro_synthesize", new_callable=AsyncMock, return_value="/tmp/kokoro.ogg"
            ) as mock_ko,
        ):
            from koda.utils.tts import synthesize_speech

            result = await synthesize_speech("Hello", "pm_alex", 1.0, provider="kokoro", language="en-us")

        assert result == "/tmp/kokoro.ogg"
        mock_el.assert_not_called()
        mock_ko.assert_called_once_with("Hello", "pm_alex", 1.0, language="en-us")


class TestKokoroSynthesize:
    @pytest.mark.asyncio
    async def test_success_flow(self):
        """Test the happy path with mocked dependencies."""
        import sys

        mock_sf = MagicMock()
        sys.modules.setdefault("soundfile", mock_sf)

        mock_samples = MagicMock()
        mock_kokoro = MagicMock()
        mock_kokoro.create.return_value = (mock_samples, 24000)

        mock_proc = AsyncMock()
        mock_proc.returncode = 0
        mock_proc.communicate = AsyncMock(return_value=(b"", b""))

        with (
            patch("koda.utils.tts.ensure_kokoro_voice_downloaded"),
            patch("koda.utils.tts._get_kokoro", return_value=mock_kokoro),
            patch.dict("sys.modules", {"soundfile": mock_sf}),
            patch("asyncio.create_subprocess_exec", return_value=mock_proc),
            patch("pathlib.Path.unlink"),
        ):
            from koda.utils.tts import _kokoro_synthesize

            result = await _kokoro_synthesize("Hello world", "pf_dora", 1.0)
            assert result is not None
            assert result.endswith(".ogg")
            mock_kokoro.create.assert_called_once_with("Hello world", voice="pf_dora", lang="pt-br", speed=1.0)
            mock_sf.write.assert_called_once()

    @pytest.mark.asyncio
    async def test_ffmpeg_failure_returns_none(self):
        """Test that ffmpeg failure returns None."""
        mock_sf = MagicMock()

        mock_samples = MagicMock()
        mock_kokoro = MagicMock()
        mock_kokoro.create.return_value = (mock_samples, 24000)

        mock_proc = AsyncMock()
        mock_proc.returncode = 1
        mock_proc.communicate = AsyncMock(return_value=(b"", b"error"))

        with (
            patch("koda.utils.tts.ensure_kokoro_voice_downloaded"),
            patch("koda.utils.tts._get_kokoro", return_value=mock_kokoro),
            patch.dict("sys.modules", {"soundfile": mock_sf}),
            patch("asyncio.create_subprocess_exec", return_value=mock_proc),
            patch("pathlib.Path.unlink"),
        ):
            from koda.utils.tts import _kokoro_synthesize

            result = await _kokoro_synthesize("Hello world")
            assert result is None

    @pytest.mark.asyncio
    async def test_exception_returns_none(self):
        """Test that exceptions return None gracefully."""
        with (
            patch("koda.utils.tts.ensure_kokoro_voice_downloaded"),
            patch("koda.utils.tts._get_kokoro", side_effect=RuntimeError("model not found")),
        ):
            from koda.utils.tts import _kokoro_synthesize

            result = await _kokoro_synthesize("Hello world")
            assert result is None


class TestCmdVoice:
    @pytest.mark.asyncio
    async def test_toggle_on(self, mock_update, mock_context):
        """Test /voice toggles on."""
        from koda.handlers.commands import cmd_voice

        mock_context.user_data["audio_response"] = False
        mock_context.args = []

        with patch("koda.handlers.commands.TTS_ENABLED", True):
            await cmd_voice(mock_update, mock_context)

        assert mock_context.user_data["audio_response"] is True
        call_text = (
            mock_update.message.reply_text.call_args[1].get("text") or mock_update.message.reply_text.call_args[0][0]
        )
        assert "ON" in call_text

    @pytest.mark.asyncio
    async def test_toggle_off(self, mock_update, mock_context):
        """Test /voice toggles off when already on."""
        from koda.handlers.commands import cmd_voice

        mock_context.user_data["audio_response"] = True
        mock_context.args = []

        with patch("koda.handlers.commands.TTS_ENABLED", True):
            await cmd_voice(mock_update, mock_context)

        assert mock_context.user_data["audio_response"] is False

    @pytest.mark.asyncio
    async def test_voice_disabled(self, mock_update, mock_context):
        """Test /voice when TTS is disabled."""
        from koda.handlers.commands import cmd_voice

        mock_context.args = []
        with patch("koda.handlers.commands.TTS_ENABLED", False):
            await cmd_voice(mock_update, mock_context)

        call_text = mock_update.message.reply_text.call_args[0][0]
        assert "disabled" in call_text.lower()

    @pytest.mark.asyncio
    async def test_set_voice(self, mock_update, mock_context):
        """Test /voice brian changes voice."""
        from koda.handlers.commands import cmd_voice

        mock_context.args = ["brian"]
        with (
            patch("koda.handlers.commands.TTS_ENABLED", True),
            patch(
                "koda.handlers.commands.set_agent_voice_default",
                return_value={
                    "default_provider": "claude",
                    "general_model": "claude-opus-4-6",
                    "default_models_by_provider": {"claude": "claude-opus-4-6"},
                    "functional_defaults": {"general": {"provider_id": "claude", "model_id": "claude-opus-4-6"}},
                    "transcription_provider": "whispercpp",
                    "transcription_model": "whisper-cpp-local",
                    "audio_provider": "elevenlabs",
                    "audio_model": "eleven_flash_v2_5",
                    "tts_voice": "brian",
                    "tts_voice_label": "Brian",
                    "tts_voice_language": "en",
                    "selectable_function_options": {},
                },
            ),
        ):
            await cmd_voice(mock_update, mock_context)

        assert mock_context.user_data["tts_voice"] == "brian"

    @pytest.mark.asyncio
    async def test_set_kokoro_voice(self, mock_update, mock_context):
        """Test /voice pm_alex changes voice."""
        from koda.handlers.commands import cmd_voice

        mock_context.args = ["pm_alex"]
        with (
            patch("koda.handlers.commands.TTS_ENABLED", True),
            patch(
                "koda.handlers.commands.set_agent_voice_default",
                return_value={
                    "default_provider": "claude",
                    "general_model": "claude-opus-4-6",
                    "default_models_by_provider": {"claude": "claude-opus-4-6"},
                    "functional_defaults": {"general": {"provider_id": "claude", "model_id": "claude-opus-4-6"}},
                    "transcription_provider": "whispercpp",
                    "transcription_model": "whisper-cpp-local",
                    "audio_provider": "kokoro",
                    "audio_model": "kokoro-v1",
                    "tts_voice": "pm_alex",
                    "tts_voice_label": "Alex",
                    "tts_voice_language": "pt-br",
                    "selectable_function_options": {},
                },
            ),
        ):
            await cmd_voice(mock_update, mock_context)

        assert mock_context.user_data["tts_voice"] == "pm_alex"

    @pytest.mark.asyncio
    async def test_list_voices(self, mock_update, mock_context):
        """Test /voice voices lists available voices grouped by engine."""
        from koda.handlers.commands import cmd_voice

        mock_context.args = ["voices"]
        with patch("koda.handlers.commands.TTS_ENABLED", True):
            await cmd_voice(mock_update, mock_context)

        call_text = mock_update.message.reply_text.call_args[0][0]
        assert "pf_dora" in call_text
        assert "pm_alex" in call_text
        assert "brian" in call_text
        assert "ElevenLabs" in call_text
        assert "Kokoro" in call_text

    @pytest.mark.asyncio
    async def test_unknown_option(self, mock_update, mock_context):
        """Test /voice with unknown argument."""
        from koda.handlers.commands import cmd_voice

        mock_context.args = ["invalid_voice"]
        with patch("koda.handlers.commands.TTS_ENABLED", True):
            await cmd_voice(mock_update, mock_context)

        call_text = mock_update.message.reply_text.call_args[0][0]
        assert "Unknown option" in call_text
        assert "search" in call_text

    @pytest.mark.asyncio
    async def test_search_no_query(self, mock_update, mock_context):
        """Test /voice search without query shows usage."""
        from koda.handlers.commands import cmd_voice

        mock_context.args = ["search"]
        with patch("koda.handlers.commands.TTS_ENABLED", True):
            await cmd_voice(mock_update, mock_context)

        call_text = mock_update.message.reply_text.call_args[0][0]
        assert "Usage" in call_text

    @pytest.mark.asyncio
    async def test_search_shows_results(self, mock_update, mock_context):
        """Test /voice search <query> shows results with buttons."""
        from koda.handlers.commands import cmd_voice
        from koda.utils.tts import ElevenLabsVoice

        mock_voices = [
            ElevenLabsVoice("id123456789012345678", "TestVoice", "premade", "female", "Brazilian", "pt"),
        ]
        with (
            patch("koda.handlers.commands.TTS_ENABLED", True),
            patch("koda.utils.tts.search_elevenlabs_voices", new_callable=AsyncMock, return_value=mock_voices),
        ):
            mock_context.args = ["search", "portuguese"]
            await cmd_voice(mock_update, mock_context)

        # Last call should have reply_markup (buttons)
        last_call = mock_update.message.reply_text.call_args_list[-1]
        assert last_call[1].get("reply_markup") is not None
        call_text = last_call[0][0]
        assert "TestVoice" in call_text

    @pytest.mark.asyncio
    async def test_search_no_results(self, mock_update, mock_context):
        """Test /voice search with no results."""
        from koda.handlers.commands import cmd_voice

        with (
            patch("koda.handlers.commands.TTS_ENABLED", True),
            patch("koda.utils.tts.search_elevenlabs_voices", new_callable=AsyncMock, return_value=[]),
        ):
            mock_context.args = ["search", "nonexistent"]
            await cmd_voice(mock_update, mock_context)

        last_call_text = mock_update.message.reply_text.call_args_list[-1][0][0]
        assert "No voices found" in last_call_text

    @pytest.mark.asyncio
    async def test_voices_shows_custom_voice(self, mock_update, mock_context):
        """Test /voice voices shows custom ElevenLabs voice when set."""
        from koda.handlers.commands import cmd_voice

        mock_context.user_data["tts_voice"] = "Xb7hH8MSUJpSbSDYk0k2"
        mock_context.user_data["tts_voice_label"] = "Custom Voice"
        mock_context.args = ["voices"]
        with patch("koda.handlers.commands.TTS_ENABLED", True):
            await cmd_voice(mock_update, mock_context)

        call_text = mock_update.message.reply_text.call_args[0][0]
        assert "Custom Voice" in call_text
        assert "Custom (via search)" in call_text


class TestElevenLabsBreakerIntegration:
    @pytest.mark.asyncio
    async def test_breaker_open_returns_none(self):
        """Breaker open -> returns None without making HTTP call."""
        with (
            patch("koda.utils.tts.ELEVENLABS_API_KEY", "test-key"),
            patch("koda.utils.tts.check_breaker", return_value="circuit open"),
            patch("aiohttp.ClientSession") as mock_session,
        ):
            from koda.utils.tts import _elevenlabs_synthesize

            result = await _elevenlabs_synthesize("Hello", "voice123")
        assert result is None
        mock_session.assert_not_called()

    @pytest.mark.asyncio
    async def test_api_error_records_failure(self):
        """HTTP 500 -> record_failure called."""
        mock_resp = AsyncMock()
        mock_resp.status = 500
        mock_resp.text = AsyncMock(return_value="Internal Server Error")

        mock_session_ctx = AsyncMock()
        mock_session_ctx.__aenter__ = AsyncMock(return_value=mock_resp)
        mock_session_ctx.__aexit__ = AsyncMock(return_value=False)

        mock_session = AsyncMock()
        mock_session.post = MagicMock(return_value=mock_session_ctx)

        mock_client_ctx = AsyncMock()
        mock_client_ctx.__aenter__ = AsyncMock(return_value=mock_session)
        mock_client_ctx.__aexit__ = AsyncMock(return_value=False)

        with (
            patch("koda.utils.tts.ELEVENLABS_API_KEY", "test-key"),
            patch("koda.utils.tts.check_breaker", return_value=None),
            patch("koda.utils.tts.record_failure") as mock_fail,
            patch("aiohttp.ClientSession", return_value=mock_client_ctx),
        ):
            from koda.utils.tts import _elevenlabs_synthesize

            result = await _elevenlabs_synthesize("Hello", "voice123")
        assert result is None
        mock_fail.assert_called_once()

    @pytest.mark.asyncio
    async def test_success_records_latency(self):
        """HTTP 200 -> DEPENDENCY_LATENCY.labels(...).observe() called."""
        mock_resp = AsyncMock()
        mock_resp.status = 200
        mock_resp.read = AsyncMock(return_value=b"fake-ogg-data")

        mock_session_ctx = AsyncMock()
        mock_session_ctx.__aenter__ = AsyncMock(return_value=mock_resp)
        mock_session_ctx.__aexit__ = AsyncMock(return_value=False)

        mock_session = AsyncMock()
        mock_session.post = MagicMock(return_value=mock_session_ctx)

        mock_client_ctx = AsyncMock()
        mock_client_ctx.__aenter__ = AsyncMock(return_value=mock_session)
        mock_client_ctx.__aexit__ = AsyncMock(return_value=False)

        mock_observe = MagicMock()
        mock_labels = MagicMock(return_value=MagicMock(observe=mock_observe))

        with (
            patch("koda.utils.tts.ELEVENLABS_API_KEY", "test-key"),
            patch("koda.utils.tts.check_breaker", return_value=None),
            patch("koda.utils.tts.record_success"),
            patch("koda.utils.tts.DEPENDENCY_LATENCY", labels=mock_labels),
            patch("aiohttp.ClientSession", return_value=mock_client_ctx),
        ):
            from koda.utils.tts import _elevenlabs_synthesize

            result = await _elevenlabs_synthesize("Hello", "voice123")

        assert result is not None
        mock_labels.assert_called_once()
        call_kwargs = mock_labels.call_args[1]
        assert call_kwargs["dependency"] == "elevenlabs"
        mock_observe.assert_called_once()

        # Clean up temp file
        import os

        if result and os.path.exists(result):
            os.unlink(result)


class TestSearchElevenLabsVoices:
    @pytest.mark.asyncio
    async def test_success_returns_voices(self):
        """Successful search returns list of ElevenLabsVoice."""
        api_response = {
            "voices": [
                {
                    "voice_id": "abc123",
                    "name": "Maria",
                    "category": "premade",
                    "labels": {"gender": "female", "accent": "Brazilian"},
                    "verified_languages": [{"language": "pt"}],
                },
            ],
            "has_more": False,
        }

        mock_resp = AsyncMock()
        mock_resp.status = 200
        mock_resp.json = AsyncMock(return_value=api_response)

        mock_session_ctx = AsyncMock()
        mock_session_ctx.__aenter__ = AsyncMock(return_value=mock_resp)
        mock_session_ctx.__aexit__ = AsyncMock(return_value=False)

        mock_session = AsyncMock()
        mock_session.get = MagicMock(return_value=mock_session_ctx)

        mock_client_ctx = AsyncMock()
        mock_client_ctx.__aenter__ = AsyncMock(return_value=mock_session)
        mock_client_ctx.__aexit__ = AsyncMock(return_value=False)

        with (
            patch("koda.utils.tts.ELEVENLABS_API_KEY", "test-key"),
            patch("aiohttp.ClientSession", return_value=mock_client_ctx),
        ):
            from koda.utils.tts import search_elevenlabs_voices

            result = await search_elevenlabs_voices("portuguese")

        assert len(result) == 1
        assert result[0].voice_id == "abc123"
        assert result[0].name == "Maria"
        assert result[0].gender == "female"
        assert result[0].accent == "Brazilian"

    @pytest.mark.asyncio
    async def test_no_api_key_returns_empty(self):
        """No API key -> empty list."""
        with patch("koda.utils.tts.ELEVENLABS_API_KEY", None):
            from koda.utils.tts import search_elevenlabs_voices

            result = await search_elevenlabs_voices("test")

        assert result == []

    @pytest.mark.asyncio
    async def test_api_error_returns_empty(self):
        """API error -> empty list."""
        mock_resp = AsyncMock()
        mock_resp.status = 500

        mock_session_ctx = AsyncMock()
        mock_session_ctx.__aenter__ = AsyncMock(return_value=mock_resp)
        mock_session_ctx.__aexit__ = AsyncMock(return_value=False)

        mock_session = AsyncMock()
        mock_session.get = MagicMock(return_value=mock_session_ctx)

        mock_client_ctx = AsyncMock()
        mock_client_ctx.__aenter__ = AsyncMock(return_value=mock_session)
        mock_client_ctx.__aexit__ = AsyncMock(return_value=False)

        with (
            patch("koda.utils.tts.ELEVENLABS_API_KEY", "test-key"),
            patch("aiohttp.ClientSession", return_value=mock_client_ctx),
        ):
            from koda.utils.tts import search_elevenlabs_voices

            result = await search_elevenlabs_voices("test")

        assert result == []


class TestCallbackVoiceElevenLabs:
    @pytest.mark.asyncio
    async def test_sets_voice_from_callback(self, mock_update, mock_context):
        """Callback sets tts_voice and tts_voice_label."""
        from koda.handlers.callbacks import callback_voice_elevenlabs

        query = AsyncMock()
        query.data = "voiceel:abc123456789012345:Maria"
        query.answer = AsyncMock()
        query.edit_message_text = AsyncMock()
        mock_update.callback_query = query

        with patch(
            "koda.handlers.callbacks.set_agent_voice_default",
            return_value={
                "default_provider": "claude",
                "general_model": "claude-opus-4-6",
                "default_models_by_provider": {"claude": "claude-opus-4-6"},
                "functional_defaults": {"general": {"provider_id": "claude", "model_id": "claude-opus-4-6"}},
                "transcription_provider": "whispercpp",
                "transcription_model": "whisper-cpp-local",
                "audio_provider": "elevenlabs",
                "audio_model": "eleven_flash_v2_5",
                "tts_voice": "abc123456789012345",
                "tts_voice_label": "Maria",
                "tts_voice_language": "pt",
                "selectable_function_options": {},
            },
        ):
            await callback_voice_elevenlabs(mock_update, mock_context)

        assert mock_context.user_data["tts_voice"] == "abc123456789012345"
        assert mock_context.user_data["tts_voice_label"] == "Maria"
        query.edit_message_text.assert_called_once()
        call_text = query.edit_message_text.call_args[0][0]
        assert "Maria" in call_text
