"""Tests for audio utilities."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from koda.utils.audio import (
    _PREPROCESS_FILTER,
    _transcribe_openai_audio,
    build_audio_prompt,
    convert_and_preprocess,
    convert_to_wav,
    is_ffmpeg_available,
    transcribe_audio,
)


def _mock_process(*, returncode: int = 0, stdout: bytes = b"", stderr: bytes = b"") -> MagicMock:
    proc = MagicMock()
    proc.returncode = returncode
    proc.communicate = AsyncMock(return_value=(stdout, stderr))
    proc.kill = MagicMock()
    proc.wait = AsyncMock(return_value=None)
    return proc


class TestBuildAudioPrompt:
    def test_with_caption(self):
        prompt = build_audio_prompt("Olá, tudo bem?", "What does this say?")
        assert "Olá, tudo bem?" in prompt
        assert "What does this say?" in prompt
        assert "Transcrição do áudio" in prompt

    def test_without_caption(self):
        prompt = build_audio_prompt("Olá, tudo bem?")
        assert "Olá, tudo bem?" in prompt
        assert "Responda ao conteúdo" in prompt


class TestIsFfmpegAvailable:
    def test_returns_bool(self):
        result = is_ffmpeg_available()
        assert isinstance(result, bool)


class TestConvertToWav:
    @pytest.mark.asyncio
    async def test_wav_returns_same_path(self):
        result = await convert_to_wav("/tmp/test.wav")
        assert result == "/tmp/test.wav"

    @pytest.mark.asyncio
    async def test_wav_uppercase_returns_same_path(self):
        result = await convert_to_wav("/tmp/test.WAV")
        assert result == "/tmp/test.WAV"

    @pytest.mark.asyncio
    async def test_non_wav_without_ffmpeg(self):
        with patch("koda.utils.audio.is_ffmpeg_available", return_value=False):
            result = await convert_to_wav("/tmp/test.ogg")
            assert result is None

    @pytest.mark.asyncio
    async def test_non_wav_delegates_to_ffmpeg(self):
        with (
            patch("koda.utils.audio.is_ffmpeg_available", return_value=True),
            patch("koda.utils.audio.convert_ogg_to_wav", return_value="/tmp/test.wav") as mock_convert,
        ):
            result = await convert_to_wav("/tmp/test.mp3")
            assert result == "/tmp/test.wav"
            mock_convert.assert_awaited_once_with("/tmp/test.mp3")


class TestTranscribeAudio:
    @pytest.mark.asyncio
    async def test_disabled(self):
        with (
            patch("koda.utils.audio.WHISPER_ENABLED", False),
            patch("koda.utils.audio._runtime_transcription_defaults", return_value=("", "", "")),
        ):
            result = await transcribe_audio("/tmp/test.wav")
            assert result is None

    @pytest.mark.asyncio
    async def test_binary_not_found(self):
        with (
            patch("koda.utils.audio.WHISPER_ENABLED", True),
            patch("koda.utils.audio.shutil.which", return_value=None),
        ):
            result = await transcribe_audio("/tmp/test.wav")
            assert result is None

    @pytest.mark.asyncio
    async def test_model_not_found(self):
        with (
            patch("koda.utils.audio.WHISPER_ENABLED", True),
            patch("koda.utils.audio.shutil.which", return_value="/usr/bin/whisper-cli"),
            patch("koda.utils.audio.Path.exists", return_value=False),
        ):
            result = await transcribe_audio("/tmp/test.wav")
            assert result is None

    @pytest.mark.asyncio
    async def test_successful_transcription(self):
        mock_proc = _mock_process(stdout=b"Texto transcrito", stderr=b"")

        with (
            patch("koda.utils.audio.WHISPER_ENABLED", True),
            patch("koda.utils.audio.shutil.which", return_value="/usr/bin/whisper-cli"),
            patch("koda.utils.audio.Path.exists", return_value=True),
            patch("koda.utils.audio.convert_to_wav", return_value="/tmp/test.wav"),
            patch("asyncio.create_subprocess_exec", return_value=mock_proc),
            patch("koda.utils.audio.Path.unlink"),
        ):
            result = await transcribe_audio("/tmp/test.wav")
            assert result == "Texto transcrito"
            mock_proc.communicate.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_transcription_nonzero_exit(self):
        mock_proc = _mock_process(returncode=1, stdout=b"", stderr=b"error")

        with (
            patch("koda.utils.audio.WHISPER_ENABLED", True),
            patch("koda.utils.audio.shutil.which", return_value="/usr/bin/whisper-cli"),
            patch("koda.utils.audio.Path.exists", return_value=True),
            patch("koda.utils.audio.convert_to_wav", return_value="/tmp/test.wav"),
            patch("asyncio.create_subprocess_exec", return_value=mock_proc),
            patch("koda.utils.audio.Path.unlink"),
        ):
            result = await transcribe_audio("/tmp/test.wav")
            assert result is None

    @pytest.mark.asyncio
    async def test_transcription_uses_openai_when_codex_is_selected(self):
        with (
            patch("koda.utils.audio.WHISPER_ENABLED", True),
            patch("koda.utils.audio.TRANSCRIPTION_PROVIDER", "codex"),
            patch("koda.utils.audio.TRANSCRIPTION_MODEL", "whisper-1"),
            patch("koda.utils.audio._transcribe_openai_audio", return_value="Texto OpenAI") as mock_openai,
            patch("koda.utils.audio._transcribe_with_whisper_cpp") as mock_local,
        ):
            result = await transcribe_audio("/tmp/test.wav")
            assert result == "Texto OpenAI"
            mock_openai.assert_awaited_once_with("/tmp/test.wav", "whisper-1", language="pt")
            mock_local.assert_not_called()

    @pytest.mark.asyncio
    async def test_transcription_falls_back_to_whispercpp_when_openai_fails(self):
        with (
            patch("koda.utils.audio.WHISPER_ENABLED", True),
            patch("koda.utils.audio.TRANSCRIPTION_PROVIDER", "codex"),
            patch("koda.utils.audio.TRANSCRIPTION_MODEL", "whisper-1"),
            patch("koda.utils.audio._transcribe_openai_audio", return_value=None) as mock_openai,
            patch(
                "koda.utils.audio._transcribe_with_whisper_cpp",
                return_value="Texto local",
            ) as mock_local,
        ):
            result = await transcribe_audio("/tmp/test.wav")
            assert result == "Texto local"
            mock_openai.assert_awaited_once_with("/tmp/test.wav", "whisper-1", language="pt")
            mock_local.assert_awaited_once_with("/tmp/test.wav", language="pt")

    @pytest.mark.asyncio
    async def test_transcription_honors_runtime_overrides(self):
        with (
            patch("koda.utils.audio.WHISPER_ENABLED", True),
            patch("koda.utils.audio.TRANSCRIPTION_PROVIDER", "whispercpp"),
            patch("koda.utils.audio.TRANSCRIPTION_MODEL", "whisper-cpp-local"),
            patch("koda.utils.audio._transcribe_openai_audio", return_value="Texto OpenAI") as mock_openai,
            patch("koda.utils.audio._transcribe_with_whisper_cpp") as mock_local,
        ):
            result = await transcribe_audio(
                "/tmp/test.wav",
                provider="codex",
                model="gpt-4o-transcribe",
                language="en",
            )

        assert result == "Texto OpenAI"
        mock_openai.assert_awaited_once_with("/tmp/test.wav", "gpt-4o-transcribe", language="en")
        mock_local.assert_not_called()

    @pytest.mark.asyncio
    async def test_transcription_uses_elevenlabs_when_selected(self):
        with (
            patch("koda.utils.audio.WHISPER_ENABLED", True),
            patch("koda.utils.audio.TRANSCRIPTION_PROVIDER", "elevenlabs"),
            patch("koda.utils.audio.TRANSCRIPTION_MODEL", "scribe_v2"),
            patch(
                "koda.utils.audio._transcribe_elevenlabs_audio",
                return_value="Texto ElevenLabs",
            ) as mock_elevenlabs,
            patch("koda.utils.audio._transcribe_with_whisper_cpp") as mock_local,
        ):
            result = await transcribe_audio("/tmp/test.wav")

        assert result == "Texto ElevenLabs"
        mock_elevenlabs.assert_awaited_once_with("/tmp/test.wav", "scribe_v2", language="pt")
        mock_local.assert_not_called()

    @pytest.mark.asyncio
    async def test_transcription_falls_back_to_whispercpp_when_elevenlabs_fails(self):
        with (
            patch("koda.utils.audio.WHISPER_ENABLED", True),
            patch("koda.utils.audio.TRANSCRIPTION_PROVIDER", "elevenlabs"),
            patch("koda.utils.audio.TRANSCRIPTION_MODEL", "scribe_v2"),
            patch("koda.utils.audio._transcribe_elevenlabs_audio", return_value=None) as mock_elevenlabs,
            patch(
                "koda.utils.audio._transcribe_with_whisper_cpp",
                return_value="Texto local",
            ) as mock_local,
        ):
            result = await transcribe_audio("/tmp/test.wav")

        assert result == "Texto local"
        mock_elevenlabs.assert_awaited_once_with("/tmp/test.wav", "scribe_v2", language="pt")
        mock_local.assert_awaited_once_with("/tmp/test.wav", language="pt")

    @pytest.mark.asyncio
    async def test_transcription_uses_agent_runtime_defaults_when_explicit_args_are_missing(self):
        with (
            patch("koda.utils.audio.WHISPER_ENABLED", False),
            patch(
                "koda.utils.audio._runtime_transcription_defaults",
                return_value=("codex", "gpt-4o-transcribe", "en"),
            ),
            patch("koda.utils.audio._transcribe_openai_audio", return_value="Texto OpenAI") as mock_openai,
            patch("koda.utils.audio._transcribe_with_whisper_cpp") as mock_local,
        ):
            result = await transcribe_audio("/tmp/test.wav")

        assert result == "Texto OpenAI"
        mock_openai.assert_awaited_once_with("/tmp/test.wav", "gpt-4o-transcribe", language="en")
        mock_local.assert_not_called()

    @pytest.mark.asyncio
    async def test_openai_transcription_returns_none_without_api_key(self):
        with patch.dict("os.environ", {}, clear=True):
            result = await _transcribe_openai_audio("/tmp/test.wav", "whisper-1")
            assert result is None


class TestConvertAndPreprocess:
    @pytest.mark.asyncio
    async def test_successful_preprocessing(self):
        mock_proc = _mock_process(stdout=b"", stderr=b"")

        mock_stat = MagicMock()
        mock_stat.st_size = 32000  # Well above minimum

        with (
            patch("asyncio.create_subprocess_exec", return_value=mock_proc) as mock_exec,
            patch("koda.utils.audio.Path.exists", return_value=True),
            patch("koda.utils.audio.Path.stat", return_value=mock_stat),
        ):
            result = await convert_and_preprocess("/tmp/voice.ogg")
            assert result == "/tmp/voice.wav"
            # Verify filter chain is in the ffmpeg args
            call_args = mock_exec.call_args[0]
            assert "-af" in call_args
            af_idx = call_args.index("-af")
            assert call_args[af_idx + 1] == _PREPROCESS_FILTER
            # Verify output format
            assert "-ar" in call_args
            assert "16000" in call_args
            assert "-ac" in call_args
            assert "1" in call_args

    @pytest.mark.asyncio
    async def test_preprocessing_fallback_on_failure(self):
        mock_proc = _mock_process(returncode=1, stdout=b"", stderr=b"filter error")

        with (
            patch("asyncio.create_subprocess_exec", return_value=mock_proc),
            patch(
                "koda.utils.audio.convert_ogg_to_wav",
                return_value="/tmp/voice.wav",
            ) as mock_fallback,
        ):
            result = await convert_and_preprocess("/tmp/voice.ogg")
            assert result == "/tmp/voice.wav"
            mock_fallback.assert_awaited_once_with("/tmp/voice.ogg")

    @pytest.mark.asyncio
    async def test_preprocessing_fallback_on_timeout(self):
        mock_proc = _mock_process()
        mock_proc.communicate.side_effect = TimeoutError

        async def _raise_timeout(awaitable, timeout):
            if hasattr(awaitable, "close"):
                awaitable.close()
            raise TimeoutError

        with (
            patch("asyncio.create_subprocess_exec", return_value=mock_proc),
            patch("asyncio.wait_for", side_effect=_raise_timeout),
            patch(
                "koda.utils.audio.convert_ogg_to_wav",
                return_value="/tmp/voice.wav",
            ) as mock_fallback,
        ):
            result = await convert_and_preprocess("/tmp/voice.ogg")
            assert result == "/tmp/voice.wav"
            mock_fallback.assert_awaited_once_with("/tmp/voice.ogg")

    @pytest.mark.asyncio
    async def test_preprocessing_output_too_short(self):
        mock_proc = _mock_process(stdout=b"", stderr=b"")

        mock_stat = MagicMock()
        mock_stat.st_size = 100  # Below _MIN_OUTPUT_BYTES

        with (
            patch("asyncio.create_subprocess_exec", return_value=mock_proc),
            patch("koda.utils.audio.Path.exists", return_value=True),
            patch("koda.utils.audio.Path.stat", return_value=mock_stat),
            patch("koda.utils.audio.Path.unlink"),
        ):
            result = await convert_and_preprocess("/tmp/voice.ogg")
            assert result is None


class TestPreprocessDispatch:
    @pytest.mark.asyncio
    async def test_preprocess_flag_dispatches_correctly(self):
        with (
            patch("koda.utils.audio.is_ffmpeg_available", return_value=True),
            patch("koda.utils.audio.AUDIO_PREPROCESS", True),
            patch(
                "koda.utils.audio.convert_and_preprocess",
                return_value="/tmp/test.wav",
            ) as mock_preprocess,
        ):
            result = await convert_to_wav("/tmp/test.ogg", preprocess=True)
            assert result == "/tmp/test.wav"
            mock_preprocess.assert_awaited_once_with("/tmp/test.ogg")

    @pytest.mark.asyncio
    async def test_preprocess_disabled_via_config(self):
        with (
            patch("koda.utils.audio.is_ffmpeg_available", return_value=True),
            patch("koda.utils.audio.AUDIO_PREPROCESS", False),
            patch(
                "koda.utils.audio.convert_ogg_to_wav",
                return_value="/tmp/test.wav",
            ) as mock_simple,
        ):
            result = await convert_to_wav("/tmp/test.ogg", preprocess=True)
            assert result == "/tmp/test.wav"
            mock_simple.assert_awaited_once_with("/tmp/test.ogg")

    @pytest.mark.asyncio
    async def test_transcribe_calls_convert_with_preprocess(self):
        mock_proc = _mock_process(stdout=b"Hello world", stderr=b"")

        with (
            patch("koda.utils.audio.WHISPER_ENABLED", True),
            patch("koda.utils.audio.shutil.which", return_value="/usr/bin/whisper-cli"),
            patch("koda.utils.audio.Path.exists", return_value=True),
            patch(
                "koda.utils.audio.convert_to_wav",
                return_value="/tmp/test.wav",
            ) as mock_convert,
            patch("asyncio.create_subprocess_exec", return_value=mock_proc),
            patch("koda.utils.audio.Path.unlink"),
        ):
            result = await transcribe_audio("/tmp/test.ogg")
            assert result == "Hello world"
            mock_convert.assert_awaited_once_with("/tmp/test.ogg", preprocess=True)
