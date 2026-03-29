"""Dual-engine TTS — ElevenLabs (primary) + Kokoro (fallback) for Telegram voice notes."""

import asyncio
import os
import re
import tempfile
import threading
from collections import namedtuple
from pathlib import Path
from typing import Any

from koda.config import (
    AGENT_ID,
    ELEVENLABS_API_KEY,
    ELEVENLABS_MODEL,
    ELEVENLABS_TIMEOUT,
    KOKORO_DEFAULT_LANGUAGE,
    KOKORO_DEFAULT_VOICE,
    KOKORO_VOICES_PATH,
    TTS_DEFAULT_VOICE,
    TTS_MAX_CHARS,
)
from koda.logging_config import get_logger
from koda.services.kokoro_manager import (
    ensure_default_kokoro_assets,
    ensure_kokoro_model,
    ensure_kokoro_voice_downloaded,
    kokoro_managed_voices_path,
    kokoro_voice_metadata,
    resolve_kokoro_language,
)
from koda.services.metrics import DEPENDENCY_LATENCY
from koda.services.resilience import (
    check_breaker,
    elevenlabs_breaker,
    record_failure,
    record_success,
)

log = get_logger(__name__)

# --- Voice configuration ---

VoiceConfig = namedtuple("VoiceConfig", ["label", "engine", "engine_voice_id", "fallback_kokoro"])

AVAILABLE_VOICES: dict[str, VoiceConfig] = {
    # ElevenLabs voices (primary — cloud, alta qualidade)
    "alice": VoiceConfig("Alice (feminina)", "elevenlabs", "Xb7hH8MSUJpSbSDYk0k2", "pf_dora"),
    "bill": VoiceConfig("Bill (masculino)", "elevenlabs", "pqHfZKP75CvOlQylNhV4", "pm_alex"),
    "brian": VoiceConfig("Brian (masculino)", "elevenlabs", "nPczCjzI2devNBz1zQrb", "pm_alex"),
    # Kokoro voices (fallback — local, gratuito)
    "pf_dora": VoiceConfig("Dora (feminina, local)", "kokoro", "pf_dora", None),
    "pm_alex": VoiceConfig("Alex (masculino, local)", "kokoro", "pm_alex", None),
    "pm_santa": VoiceConfig("Santa (masculino, local)", "kokoro", "pm_santa", None),
}

# --- Kokoro lazy singleton ---
_kokoro_instance = None
_kokoro_instance_signature: tuple[str, str, int] | None = None
_kokoro_lock = threading.Lock()


def _resolve_kokoro_assets(preferred_voice: str = KOKORO_DEFAULT_VOICE) -> tuple[Path, Path]:
    ensure_kokoro_model()
    managed_voice_path = Path(KOKORO_VOICES_PATH).expanduser() if KOKORO_VOICES_PATH else kokoro_managed_voices_path()
    if preferred_voice and kokoro_voice_metadata(preferred_voice) is not None:
        ensure_kokoro_voice_downloaded(preferred_voice)
    elif not managed_voice_path.exists():
        ensure_default_kokoro_assets()
    if not managed_voice_path.exists():
        ensure_default_kokoro_assets()
    return ensure_kokoro_model(), managed_voice_path


def _get_kokoro(preferred_voice: str = KOKORO_DEFAULT_VOICE) -> Any:
    """Return cached Kokoro instance, initializing on first call (thread-safe)."""
    global _kokoro_instance, _kokoro_instance_signature
    model_path, voices_path = _resolve_kokoro_assets(preferred_voice)
    signature = (
        str(model_path),
        str(voices_path),
        voices_path.stat().st_mtime_ns if voices_path.exists() else 0,
    )
    if _kokoro_instance is not None and _kokoro_instance_signature == signature:
        return _kokoro_instance

    with _kokoro_lock:
        model_path, voices_path = _resolve_kokoro_assets(preferred_voice)
        signature = (
            str(model_path),
            str(voices_path),
            voices_path.stat().st_mtime_ns if voices_path.exists() else 0,
        )
        if _kokoro_instance is not None and _kokoro_instance_signature == signature:
            return _kokoro_instance

        from kokoro_onnx import Kokoro

        log.info("tts_init_start")
        _kokoro_instance = Kokoro(str(model_path), str(voices_path))
        _kokoro_instance_signature = signature
        log.info("tts_init_done")
        return _kokoro_instance


# --- Text cleaning ---

_CODE_BLOCK_RE = re.compile(r"```[\s\S]*?```")
_INLINE_CODE_RE = re.compile(r"`[^`]+`")
_LINK_RE = re.compile(r"\[([^\]]+)\]\([^)]+\)")
_BARE_URL_RE = re.compile(r"https?://\S+")
_HTML_ENTITY_RE = re.compile(r"&\w+;")
_MD_FORMATTING_RE = re.compile(r"[*~#>]+")
_MULTI_NEWLINE_RE = re.compile(r"\n{3,}")


def strip_for_tts(text: str) -> str:
    """Clean text for speech synthesis — remove code, markdown, URLs."""
    # Replace code blocks with placeholder
    text = _CODE_BLOCK_RE.sub(" bloco de código omitido ", text)
    # Remove inline code
    text = _INLINE_CODE_RE.sub("", text)
    # Convert markdown links to just the text
    text = _LINK_RE.sub(r"\1", text)
    # Remove bare URLs
    text = _BARE_URL_RE.sub("", text)
    # Remove HTML entities
    text = _HTML_ENTITY_RE.sub("", text)
    # Remove markdown formatting characters
    text = _MD_FORMATTING_RE.sub("", text)
    # Collapse multiple newlines
    text = _MULTI_NEWLINE_RE.sub("\n\n", text)
    text = text.strip()

    # Truncate at TTS_MAX_CHARS on nearest sentence boundary
    if len(text) > TTS_MAX_CHARS:
        truncated = text[:TTS_MAX_CHARS]
        # Find last sentence-ending punctuation
        for sep in [".\n", ". ", "!\n", "! ", "?\n", "? "]:
            idx = truncated.rfind(sep)
            if idx > TTS_MAX_CHARS // 2:
                truncated = truncated[: idx + 1]
                break
        text = truncated.strip()

    return text


def is_mostly_code(text: str) -> bool:
    """Return True if >60% of the text consists of code blocks."""
    code_blocks = _CODE_BLOCK_RE.findall(text)
    if not code_blocks:
        return False
    code_len = sum(len(b) for b in code_blocks)
    return code_len / len(text) > 0.6


# --- ElevenLabs synthesis ---


async def _elevenlabs_synthesize(
    text: str,
    voice_id: str,
    speed: float = 1.0,
    *,
    model_id: str | None = None,
) -> str | None:
    """Call ElevenLabs TTS API. Returns OGG Opus file path or None."""
    if not ELEVENLABS_API_KEY:
        return None

    if check_breaker(elevenlabs_breaker):
        log.warning("elevenlabs_breaker_open")
        return None

    import time

    import aiohttp

    url = f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}?output_format=opus_48000_64"
    headers = {"xi-api-key": ELEVENLABS_API_KEY, "Content-Type": "application/json"}
    payload = {
        "text": text,
        "model_id": model_id or ELEVENLABS_MODEL,
        "voice_settings": {"stability": 0.5, "similarity_boost": 0.75, "speed": speed},
    }

    try:
        timeout = aiohttp.ClientTimeout(total=ELEVENLABS_TIMEOUT)
        t0 = time.monotonic()
        async with (
            aiohttp.ClientSession(timeout=timeout) as session,
            session.post(url, json=payload, headers=headers) as resp,
        ):
            if resp.status != 200:
                body = await resp.text()
                log.error("elevenlabs_api_error", status=resp.status, body=body[:300])
                record_failure(elevenlabs_breaker)
                return None
            audio_bytes = await resp.read()

        duration = time.monotonic() - t0
        log.info("elevenlabs_synthesized", duration_s=round(duration, 2), chars=len(text), size=len(audio_bytes))

        record_success(elevenlabs_breaker)

        DEPENDENCY_LATENCY.labels(agent_id=AGENT_ID or "default", dependency="elevenlabs").observe(duration)

        ogg_fd, ogg_path = tempfile.mkstemp(suffix=".ogg")
        os.close(ogg_fd)
        with open(ogg_path, "wb") as f:
            f.write(audio_bytes)
        return ogg_path

    except Exception:
        log.exception("elevenlabs_synthesis_error")
        record_failure(elevenlabs_breaker)
        return None


# --- Kokoro synthesis ---


async def _kokoro_synthesize(
    text: str,
    voice: str = TTS_DEFAULT_VOICE,
    speed: float = 1.0,
    *,
    language: str | None = None,
) -> str | None:
    """Synthesize text via Kokoro (local). Returns OGG Opus file path or None."""
    try:
        loop = asyncio.get_running_loop()
        if kokoro_voice_metadata(voice) is not None:
            await loop.run_in_executor(None, lambda: ensure_kokoro_voice_downloaded(voice))
        synth_language = resolve_kokoro_language(voice, language or KOKORO_DEFAULT_LANGUAGE)

        # Init kokoro in executor (CPU-bound, may download models)
        kokoro = await loop.run_in_executor(None, lambda: _get_kokoro(voice))

        # Synthesize in executor
        import time

        t0 = time.monotonic()
        samples, sample_rate = await loop.run_in_executor(
            None, lambda: kokoro.create(text, voice=voice, lang=synth_language, speed=speed)
        )
        duration = time.monotonic() - t0
        log.info("tts_synthesized", duration_s=round(duration, 2), sample_rate=sample_rate, chars=len(text))

        # Write WAV temp file
        import soundfile as sf

        wav_fd, wav_path = tempfile.mkstemp(suffix=".wav")
        os.close(wav_fd)
        try:
            sf.write(wav_path, samples, sample_rate)

            # Convert WAV -> OGG Opus via ffmpeg
            ogg_fd, ogg_path = tempfile.mkstemp(suffix=".ogg")
            os.close(ogg_fd)
            try:
                proc = await asyncio.create_subprocess_exec(
                    "ffmpeg",
                    "-y",
                    "-i",
                    wav_path,
                    "-c:a",
                    "libopus",
                    "-b:a",
                    "64k",
                    ogg_path,
                    stdout=asyncio.subprocess.DEVNULL,
                    stderr=asyncio.subprocess.PIPE,
                )
                try:
                    _, stderr = await asyncio.wait_for(proc.communicate(), timeout=30)
                except TimeoutError:
                    proc.kill()
                    log.error("tts_ffmpeg_timeout")
                    Path(ogg_path).unlink(missing_ok=True)
                    return None

                if proc.returncode != 0:
                    err_msg = stderr.decode(errors="replace")[:500] if stderr else ""
                    log.error("tts_ffmpeg_failed", returncode=proc.returncode, stderr=err_msg)
                    Path(ogg_path).unlink(missing_ok=True)
                    return None

                return ogg_path
            except Exception:
                Path(ogg_path).unlink(missing_ok=True)
                raise
        finally:
            Path(wav_path).unlink(missing_ok=True)

    except Exception:
        log.exception("tts_synthesis_error")
        return None


# --- Orchestrator ---


async def synthesize_speech(
    text: str,
    voice: str = TTS_DEFAULT_VOICE,
    speed: float = 1.0,
    *,
    provider: str | None = None,
    model: str | None = None,
    language: str | None = None,
) -> str | None:
    """Synthesize text to OGG Opus. Tries ElevenLabs first, falls back to Kokoro."""
    voice_cfg = AVAILABLE_VOICES.get(voice)
    preferred_provider = (provider or "").strip().lower()
    resolved_language = (language or "").strip().lower() or None

    # Unknown voice — if it looks like an ElevenLabs voice_id, try it; otherwise Kokoro
    if voice_cfg is None:
        if preferred_provider == "kokoro":
            return await _kokoro_synthesize(text, voice, speed, language=resolved_language)
        if len(voice) >= 20 and voice.isalnum():
            log.info("tts_custom_elevenlabs_voice", voice_id=voice)
            result = await _elevenlabs_synthesize(text, voice, speed, model_id=model)
            if result is not None:
                return result
            log.info("tts_custom_elevenlabs_fallback_kokoro", voice_id=voice)
            return await _kokoro_synthesize(text, KOKORO_DEFAULT_VOICE, speed, language=resolved_language)
        log.warning("tts_unknown_voice", voice=voice)
        return await _kokoro_synthesize(text, voice, speed, language=resolved_language)

    # ElevenLabs path
    if preferred_provider == "elevenlabs" or (not preferred_provider and voice_cfg.engine == "elevenlabs"):
        elevenlabs_voice_id = voice_cfg.engine_voice_id
        if voice_cfg.engine != "elevenlabs" and len(voice) >= 20 and voice.isalnum():
            elevenlabs_voice_id = voice
        result = await _elevenlabs_synthesize(text, elevenlabs_voice_id, speed, model_id=model)
        if result is not None:
            return result
        # Fallback to Kokoro
        if voice_cfg.fallback_kokoro:
            log.info("tts_fallback_to_kokoro", original=voice, kokoro=voice_cfg.fallback_kokoro)
            return await _kokoro_synthesize(text, voice_cfg.fallback_kokoro, speed, language=resolved_language)
        return None

    # Kokoro path
    return await _kokoro_synthesize(text, voice_cfg.engine_voice_id, speed, language=resolved_language)


# --- ElevenLabs voice search ---

ElevenLabsVoice = namedtuple("ElevenLabsVoice", ["voice_id", "name", "category", "gender", "accent", "language"])


def _parse_elevenlabs_voice(v: dict) -> ElevenLabsVoice:
    """Parse a voice dict from the ElevenLabs API into ElevenLabsVoice."""
    labels = v.get("labels") or {}
    gender = labels.get("gender", labels.get("Gender", ""))
    accent = labels.get("accent", labels.get("Accent", ""))
    langs = v.get("verified_languages") or []
    lang_str = ", ".join(dict.fromkeys(la.get("language", "") for la in langs if la.get("language")))
    return ElevenLabsVoice(
        voice_id=v["voice_id"],
        name=v.get("name", "Unknown"),
        category=v.get("category", ""),
        gender=gender,
        accent=accent,
        language=lang_str,
    )


# Common search aliases → ElevenLabs label values
_SEARCH_ALIASES: dict[str, str] = {
    "portuguese": "pt",
    "português": "pt",
    "brazil": "pt",
    "brazilian": "pt",
    "brasil": "pt",
    "spanish": "es",
    "espanhol": "es",
    "french": "fr",
    "francês": "fr",
    "german": "de",
    "alemão": "de",
    "italian": "it",
    "italiano": "it",
    "japanese": "ja",
    "japonês": "ja",
    "chinese": "zh",
    "chinês": "zh",
    "arabic": "ar",
    "árabe": "ar",
    "hindi": "hi",
    "dutch": "nl",
    "holandês": "nl",
    "polish": "pl",
    "polonês": "pl",
    "feminina": "female",
    "masculino": "male",
    "masculina": "male",
    "woman": "female",
    "man": "male",
}


def _voice_matches_query(voice: ElevenLabsVoice, terms: list[str]) -> bool:
    """Check if a voice matches all search terms (name, gender, accent, language)."""
    # Use word set for gender to avoid "male" matching "female"
    searchable_text = f"{voice.name} {voice.accent} {voice.language}".lower()
    searchable_words = set(searchable_text.split() + [voice.gender.lower()])
    # Add comma-separated languages as individual words
    searchable_words.update(voice.language.lower().replace(",", " ").split())

    for t in terms:
        resolved = _SEARCH_ALIASES.get(t, t)
        if resolved in ("male", "female", "neutral"):
            if resolved not in searchable_words:
                return False
        elif resolved not in searchable_text:
            return False
    return True


async def search_elevenlabs_voices(query: str, page_size: int = 10) -> list[ElevenLabsVoice]:
    """Search ElevenLabs voice library. Returns list of matching voices.

    First tries the API's `search` parameter. If no results, fetches all
    premade voices and filters locally by name/gender/accent/language.
    """
    if not ELEVENLABS_API_KEY:
        return []

    import aiohttp

    url = "https://api.elevenlabs.io/v2/voices"
    headers = {"xi-api-key": ELEVENLABS_API_KEY}

    try:
        timeout = aiohttp.ClientTimeout(total=ELEVENLABS_TIMEOUT)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            # Try API search first
            params = {"search": query, "page_size": str(page_size)}
            async with session.get(url, headers=headers, params=params) as resp:
                if resp.status != 200:
                    log.error("elevenlabs_search_error", status=resp.status)
                    return []
                data = await resp.json()

            voices = [_parse_elevenlabs_voice(v) for v in data.get("voices", [])]
            if voices:
                return voices[:page_size]

            # API search returned nothing — fetch all premade and filter locally
            params = {"page_size": "100", "category": "premade"}
            async with session.get(url, headers=headers, params=params) as resp:
                if resp.status != 200:
                    return []
                data = await resp.json()

        all_voices = [_parse_elevenlabs_voice(v) for v in data.get("voices", [])]
        terms = query.lower().split()
        matched = [v for v in all_voices if _voice_matches_query(v, terms)]
        return matched[:page_size]

    except Exception:
        log.exception("elevenlabs_search_error")
        return []
