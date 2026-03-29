"""Audio conversion and transcription utilities for voice notes."""

import asyncio
import inspect
import os
import shutil
from pathlib import Path
from typing import Any, cast

from telegram import Update

from koda.config import (
    AUDIO_PREPROCESS,
    ELEVENLABS_API_KEY,
    ELEVENLABS_TIMEOUT,
    IMAGE_TEMP_DIR,
    TRANSCRIPTION_MODEL,
    TRANSCRIPTION_PROVIDER,
    WHISPER_BIN,
    WHISPER_ENABLED,
    WHISPER_LANGUAGE,
    WHISPER_MODEL,
    WHISPER_TIMEOUT,
)
from koda.logging_config import get_logger
from koda.utils.command_helpers import require_message, require_user_id

log = get_logger(__name__)


def _runtime_transcription_defaults() -> tuple[str, str, str]:
    """Return agent-local transcription defaults when the runtime is namespaced."""
    try:
        from koda.services.agent_settings import get_agent_runtime_settings

        settings = get_agent_runtime_settings()
    except Exception:
        return "", "", ""
    if not settings:
        return "", "", ""
    provider = str(settings.get("transcription_provider") or "").strip().lower()
    model = str(settings.get("transcription_model") or "").strip()
    language = str(settings.get("transcription_language") or "").strip().lower()
    return provider, model, language


def _normalize_elevenlabs_language_code(language: str) -> str:
    normalized = str(language or "").strip().lower()
    if not normalized:
        return ""
    direct = {
        "eng",
        "por",
        "spa",
        "fra",
        "ita",
        "deu",
        "jpn",
        "hin",
        "cmn",
    }
    if normalized in direct:
        return normalized
    aliases = {
        "en": "eng",
        "en-us": "eng",
        "en-gb": "eng",
        "pt": "por",
        "pt-br": "por",
        "pt-pt": "por",
        "es": "spa",
        "es-es": "spa",
        "fr": "fra",
        "fr-fr": "fra",
        "it": "ita",
        "it-it": "ita",
        "de": "deu",
        "de-de": "deu",
        "ja": "jpn",
        "ja-jp": "jpn",
        "hi": "hin",
        "hi-in": "hin",
        "zh": "cmn",
        "zh-cn": "cmn",
    }
    return aliases.get(normalized, "")


async def _kill_process(proc: asyncio.subprocess.Process) -> None:
    kill = cast(Any, proc.kill)
    result = kill()
    if inspect.isawaitable(result):
        await result


def is_ffmpeg_available() -> bool:
    """Check if ffmpeg is available on the system."""
    return shutil.which("ffmpeg") is not None


async def convert_ogg_to_wav(ogg_path: str) -> str | None:
    """Convert an OGG file to WAV using ffmpeg.

    Returns the WAV file path, or None on failure.
    """
    wav_path = str(Path(ogg_path).with_suffix(".wav"))

    try:
        proc = await asyncio.create_subprocess_exec(
            "ffmpeg",
            "-i",
            ogg_path,
            "-y",
            wav_path,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        _, stderr = await asyncio.wait_for(proc.communicate(), timeout=30)
        if proc.returncode != 0:
            log.error("ffmpeg_conversion_failed", stderr=stderr.decode()[:200])
            return None
        return wav_path
    except TimeoutError:
        log.error("ffmpeg_timeout")
        return None
    except FileNotFoundError:
        log.error("ffmpeg_not_found")
        return None


_PREPROCESS_FILTER = (
    "highpass=f=80,"
    "lowpass=f=8000,"
    "afftdn=nf=-25,"
    "silenceremove=start_periods=1:start_silence=0.1:start_threshold=-35dB,"
    "areverse,"
    "silenceremove=start_periods=1:start_silence=0.1:start_threshold=-35dB,"
    "areverse,"
    "loudnorm=I=-16:LRA=11:TP=-1.5"
)

# Minimum output size: ~1600 bytes ≈ 0.05s of 16kHz mono 16-bit PCM
_MIN_OUTPUT_BYTES = 1600


async def convert_and_preprocess(input_path: str) -> str | None:
    """Convert audio to WAV with preprocessing filters for STT.

    Applies bandpass filtering, noise reduction, silence trimming,
    and loudness normalization via ffmpeg. Falls back to simple
    conversion on failure. Returns None if output is silence-only.
    """
    wav_path = str(Path(input_path).with_suffix(".wav"))

    try:
        proc = await asyncio.create_subprocess_exec(
            "ffmpeg",
            "-i",
            input_path,
            "-af",
            _PREPROCESS_FILTER,
            "-ar",
            "16000",
            "-ac",
            "1",
            "-sample_fmt",
            "s16",
            "-y",
            wav_path,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        _, stderr = await asyncio.wait_for(proc.communicate(), timeout=60)

        if proc.returncode != 0:
            log.warning(
                "audio_preprocess_failed_fallback",
                stderr=stderr.decode()[:200],
            )
            return await convert_ogg_to_wav(input_path)

        # Check if output is too short (silence-only audio)
        output = Path(wav_path)
        if output.exists() and output.stat().st_size < _MIN_OUTPUT_BYTES:
            log.warning("audio_preprocess_output_too_short", size=output.stat().st_size)
            output.unlink(missing_ok=True)
            return None

        return wav_path

    except TimeoutError:
        log.warning("audio_preprocess_timeout_fallback")
        await _kill_process(proc)
        return await convert_ogg_to_wav(input_path)
    except FileNotFoundError:
        log.error("ffmpeg_not_found")
        return None


async def convert_to_wav(audio_path: str, *, preprocess: bool = False) -> str | None:
    """Convert any audio file to WAV using ffmpeg.

    Returns the WAV file path, or None on failure.
    If already WAV, returns the original path.
    When preprocess=True and AUDIO_PREPROCESS is enabled, applies
    STT-optimized audio filtering via convert_and_preprocess().
    """
    if Path(audio_path).suffix.lower() == ".wav":
        return audio_path
    if not is_ffmpeg_available():
        log.error("ffmpeg_required_for_audio_conversion")
        return None
    if preprocess and AUDIO_PREPROCESS:
        return await convert_and_preprocess(audio_path)
    return await convert_ogg_to_wav(audio_path)


async def transcribe_audio(
    audio_path: str,
    *,
    provider: str | None = None,
    model: str | None = None,
    language: str | None = None,
) -> str | None:
    """Transcribe an audio file using the configured transcription backend."""
    runtime_provider = ""
    runtime_model = ""
    runtime_language = ""
    if provider in (None, "") or model in (None, "") or language in (None, ""):
        runtime_provider, runtime_model, runtime_language = _runtime_transcription_defaults()

    resolved_provider = (provider or runtime_provider or TRANSCRIPTION_PROVIDER or "whispercpp").strip().lower()
    resolved_model = (model or runtime_model or TRANSCRIPTION_MODEL or "whisper-cpp-local").strip()
    resolved_language = (language or runtime_language or WHISPER_LANGUAGE or "").strip()

    if resolved_provider == "codex":
        text = await _transcribe_openai_audio(audio_path, resolved_model, language=resolved_language)
        if text:
            return text
        log.warning("openai_audio_transcription_fallback_to_whispercpp", model=resolved_model)
    elif resolved_provider == "elevenlabs":
        text = await _transcribe_elevenlabs_audio(audio_path, resolved_model, language=resolved_language)
        if text:
            return text
        log.warning("elevenlabs_audio_transcription_fallback_to_whispercpp", model=resolved_model)

    if not WHISPER_ENABLED:
        log.info("whisper_disabled")
        return None

    return await _transcribe_with_whisper_cpp(audio_path, language=resolved_language)


async def _transcribe_with_whisper_cpp(audio_path: str, *, language: str = "") -> str | None:
    """Transcribe an audio file using whisper-cli.

    Returns the transcribed text, or None on failure.
    """
    if not shutil.which(WHISPER_BIN):
        log.error("whisper_bin_not_found", bin=WHISPER_BIN)
        return None

    if not Path(WHISPER_MODEL).exists():
        log.error("whisper_model_not_found", model=WHISPER_MODEL)
        return None

    # Convert to WAV if needed
    wav_path = await convert_to_wav(audio_path, preprocess=True)
    if not wav_path:
        log.error("whisper_wav_conversion_failed")
        return None

    try:
        proc = await asyncio.create_subprocess_exec(
            WHISPER_BIN,
            "-m",
            WHISPER_MODEL,
            "-l",
            language or WHISPER_LANGUAGE,
            "-f",
            wav_path,
            "--no-prints",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=WHISPER_TIMEOUT)

        if proc.returncode != 0:
            log.error("whisper_transcription_failed", stderr=stderr.decode()[:200])
            return None

        text = stdout.decode().strip()
        if not text:
            log.warning("whisper_empty_transcription")
            return None

        log.info("whisper_transcription_ok", length=len(text))
        return text

    except TimeoutError:
        log.error("whisper_timeout", timeout=WHISPER_TIMEOUT)
        return None
    except FileNotFoundError:
        log.error("whisper_bin_not_found", bin=WHISPER_BIN)
        return None
    finally:
        # Clean up WAV if we created it (different from original)
        if wav_path and wav_path != audio_path:
            Path(wav_path).unlink(missing_ok=True)


async def _transcribe_openai_audio(audio_path: str, model: str, *, language: str = "") -> str | None:
    api_key = str(os.environ.get("OPENAI_API_KEY") or "").strip()
    if not api_key:
        log.warning("openai_audio_transcription_missing_api_key", model=model)
        return None

    wav_path = await convert_to_wav(audio_path, preprocess=True)
    if not wav_path:
        log.error("openai_audio_transcription_wav_conversion_failed", model=model)
        return None

    try:
        import aiohttp

        timeout = aiohttp.ClientTimeout(total=WHISPER_TIMEOUT)
        form = aiohttp.FormData()
        form.add_field("model", model or "whisper-1")
        if language or WHISPER_LANGUAGE:
            form.add_field("language", language or WHISPER_LANGUAGE)
        with open(wav_path, "rb") as audio_file:
            form.add_field(
                "file",
                audio_file,
                filename=Path(wav_path).name,
                content_type="audio/wav",
            )
            async with (
                aiohttp.ClientSession(timeout=timeout) as session,
                session.post(
                    "https://api.openai.com/v1/audio/transcriptions",
                    data=form,
                    headers={"Authorization": f"Bearer {api_key}"},
                ) as response,
            ):
                if response.status != 200:
                    body = await response.text()
                    log.error("openai_audio_transcription_failed", status=response.status, body=body[:200], model=model)
                    return None
                payload = await response.json()
        text = str(payload.get("text") or "").strip()
        if not text:
            log.warning("openai_audio_transcription_empty", model=model)
            return None
        log.info("openai_audio_transcription_ok", model=model, length=len(text))
        return text
    except Exception:
        log.exception("openai_audio_transcription_error", model=model)
        return None
    finally:
        if wav_path and wav_path != audio_path:
            Path(wav_path).unlink(missing_ok=True)


async def _transcribe_elevenlabs_audio(audio_path: str, model: str, *, language: str = "") -> str | None:
    api_key = str(ELEVENLABS_API_KEY or os.environ.get("ELEVENLABS_API_KEY") or "").strip()
    if not api_key:
        log.warning("elevenlabs_audio_transcription_missing_api_key", model=model)
        return None

    wav_path = await convert_to_wav(audio_path, preprocess=True)
    if not wav_path:
        log.error("elevenlabs_audio_transcription_wav_conversion_failed", model=model)
        return None

    try:
        import aiohttp

        timeout = aiohttp.ClientTimeout(total=ELEVENLABS_TIMEOUT)
        form = aiohttp.FormData()
        form.add_field("model_id", model or "scribe_v2")
        language_code = _normalize_elevenlabs_language_code(language or WHISPER_LANGUAGE)
        if language_code:
            form.add_field("language_code", language_code)
        with open(wav_path, "rb") as audio_file:
            form.add_field(
                "file",
                audio_file,
                filename=Path(wav_path).name,
                content_type="audio/wav",
            )
            async with (
                aiohttp.ClientSession(timeout=timeout) as session,
                session.post(
                    "https://api.elevenlabs.io/v1/speech-to-text",
                    data=form,
                    headers={"xi-api-key": api_key},
                ) as response,
            ):
                if response.status != 200:
                    body = await response.text()
                    log.error(
                        "elevenlabs_audio_transcription_failed",
                        status=response.status,
                        body=body[:200],
                        model=model,
                    )
                    return None
                payload = await response.json()
        text = str(
            payload.get("text")
            or payload.get("transcript")
            or payload.get("transcription")
            or payload.get("full_transcript")
            or ""
        ).strip()
        if not text:
            log.warning("elevenlabs_audio_transcription_empty", model=model)
            return None
        log.info("elevenlabs_audio_transcription_ok", model=model, length=len(text))
        return text
    except Exception:
        log.exception("elevenlabs_audio_transcription_error", model=model)
        return None
    finally:
        if wav_path and wav_path != audio_path:
            Path(wav_path).unlink(missing_ok=True)


async def download_voice(update: Update) -> str | None:
    """Download a voice message from Telegram.

    Returns the local file path, or None on failure.
    """
    message = require_message(update)
    uid = require_user_id(update)
    msg_id = message.message_id

    voice = message.voice
    if not voice:
        return None

    ogg_path = str(IMAGE_TEMP_DIR / f"{uid}_{msg_id}_voice.ogg")

    try:
        file = await voice.get_file()
        await file.download_to_drive(ogg_path)
        return ogg_path
    except Exception:
        log.exception("voice_download_failed")
        return None


async def download_audio(update: Update) -> str | None:
    """Download an audio file from Telegram.

    Returns the local file path, or None on failure.
    """
    message = require_message(update)
    uid = require_user_id(update)
    msg_id = message.message_id

    audio = message.audio
    if not audio:
        return None

    ext = Path(audio.file_name or "audio.mp3").suffix or ".mp3"
    audio_path = str(IMAGE_TEMP_DIR / f"{uid}_{msg_id}_audio{ext}")

    try:
        file = await audio.get_file()
        await file.download_to_drive(audio_path)
        return audio_path
    except Exception:
        log.exception("audio_download_failed")
        return None


def transcribe_audio_sync(
    audio_path: str,
    *,
    provider: str | None = None,
    model: str | None = None,
    language: str | None = None,
) -> str | None:
    """Synchronous wrapper around transcribe_audio for use in threads.

    Safe to call from threads spawned by asyncio.to_thread() since those
    threads do not have a running event loop.
    """
    return asyncio.run(transcribe_audio(audio_path, provider=provider, model=model, language=language))


def build_audio_prompt(transcription: str, caption: str | None = None) -> str:
    """Build prompt with audio transcription for provider execution."""
    if caption:
        return f"[Transcrição do áudio]:\n{transcription}\n\n{caption}"
    return f"[Transcrição do áudio]:\n{transcription}\n\nResponda ao conteúdo do áudio acima."
