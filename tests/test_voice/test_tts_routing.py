"""TTS routing tests — voice resolution, ElevenLabs/Kokoro fallback chain.

Covers koda.utils.tts.synthesize_speech without booting real synthesis. The
ElevenLabs and Kokoro adapters are mocked so the test focuses on:

  * Voice → engine routing (ElevenLabs voice → _elevenlabs_synthesize first)
  * Provider override (provider="kokoro" forces local synthesis)
  * Custom ElevenLabs voice_id (>=20 alphanumeric chars) goes to ElevenLabs
  * ElevenLabs failure → Kokoro fallback when fallback_kokoro is set
  * Unknown voice with non-ElevenLabs ID falls through to Kokoro
  * VoiceConfig integrity for all 6 advertised voices

Voice config is the contract surface for /voice; if the table breaks, the
command and queue_manager TTS branch ship the wrong audio.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from koda.utils.tts import AVAILABLE_VOICES, VoiceConfig, synthesize_speech

# ---------------------------------------------------------------------------
# AVAILABLE_VOICES — contract surface
# ---------------------------------------------------------------------------


_EXPECTED_VOICE_IDS = {"alice", "bill", "brian", "pf_dora", "pm_alex", "pm_santa"}


def test_voice_table_advertises_six_voices() -> None:
    assert set(AVAILABLE_VOICES.keys()) == _EXPECTED_VOICE_IDS


def test_elevenlabs_voices_have_kokoro_fallback() -> None:
    """Every ElevenLabs voice declares a Kokoro fallback to survive outages."""
    for vid in ("alice", "bill", "brian"):
        cfg = AVAILABLE_VOICES[vid]
        assert cfg.engine == "elevenlabs"
        assert cfg.fallback_kokoro, f"{vid} must declare a kokoro fallback"
        assert cfg.fallback_kokoro in _EXPECTED_VOICE_IDS


def test_kokoro_voices_have_no_fallback() -> None:
    """Local Kokoro voices terminate the fallback chain."""
    for vid in ("pf_dora", "pm_alex", "pm_santa"):
        cfg = AVAILABLE_VOICES[vid]
        assert cfg.engine == "kokoro"
        assert cfg.fallback_kokoro is None


def test_voice_config_engine_voice_id_consistency() -> None:
    """For Kokoro voices, engine_voice_id matches the voice key."""
    for vid in ("pf_dora", "pm_alex", "pm_santa"):
        assert AVAILABLE_VOICES[vid].engine_voice_id == vid


def test_voice_config_namedtuple_shape() -> None:
    """VoiceConfig is a namedtuple with exactly 4 fields."""
    cfg = AVAILABLE_VOICES["alice"]
    assert isinstance(cfg, VoiceConfig)
    assert hasattr(cfg, "label")
    assert hasattr(cfg, "engine")
    assert hasattr(cfg, "engine_voice_id")
    assert hasattr(cfg, "fallback_kokoro")


# ---------------------------------------------------------------------------
# synthesize_speech — routing
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_synthesizers():
    """Patch both backend synthesizers and yield (eleven, kokoro) AsyncMocks."""
    with (
        patch("koda.utils.tts._elevenlabs_synthesize", new_callable=AsyncMock) as eleven,
        patch("koda.utils.tts._kokoro_synthesize", new_callable=AsyncMock) as kokoro,
    ):
        eleven.return_value = "/tmp/elevenlabs.ogg"
        kokoro.return_value = "/tmp/kokoro.ogg"
        yield eleven, kokoro


async def test_elevenlabs_voice_routes_to_elevenlabs(mock_synthesizers) -> None:
    eleven, kokoro = mock_synthesizers
    out = await synthesize_speech("texto", voice="alice")
    assert out == "/tmp/elevenlabs.ogg"
    eleven.assert_awaited_once()
    kokoro.assert_not_awaited()


async def test_kokoro_voice_routes_to_kokoro(mock_synthesizers) -> None:
    eleven, kokoro = mock_synthesizers
    out = await synthesize_speech("texto", voice="pf_dora")
    assert out == "/tmp/kokoro.ogg"
    kokoro.assert_awaited_once()
    eleven.assert_not_awaited()


async def test_explicit_kokoro_override_forces_kokoro(mock_synthesizers) -> None:
    """provider='kokoro' forces local synthesis even for an ElevenLabs voice."""
    eleven, kokoro = mock_synthesizers
    out = await synthesize_speech("texto", voice="alice", provider="kokoro")
    assert out == "/tmp/kokoro.ogg"
    eleven.assert_not_awaited()


async def test_elevenlabs_failure_falls_back_to_kokoro(mock_synthesizers) -> None:
    eleven, kokoro = mock_synthesizers
    eleven.return_value = None  # simulate ElevenLabs failure / breaker open
    out = await synthesize_speech("texto", voice="alice")
    assert out == "/tmp/kokoro.ogg"
    eleven.assert_awaited_once()
    kokoro.assert_awaited_once()
    # Fallback uses the configured Kokoro voice (pf_dora for alice).
    assert kokoro.call_args.args[1] == "pf_dora"


async def test_elevenlabs_failure_without_fallback_returns_none(mock_synthesizers) -> None:
    """If voice_cfg.fallback_kokoro is None and EL fails, return None."""
    eleven, kokoro = mock_synthesizers
    eleven.return_value = None
    # Use a voice that has fallback_kokoro=None (none in default table).
    # Patch a temporary entry to test the logic.
    fake_cfg = VoiceConfig("X", "elevenlabs", "voice123", None)
    with patch.dict("koda.utils.tts.AVAILABLE_VOICES", {"_test": fake_cfg}, clear=False):
        out = await synthesize_speech("texto", voice="_test")
    assert out is None


async def test_custom_elevenlabs_voice_id_routes_to_elevenlabs(mock_synthesizers) -> None:
    """An unknown voice that looks like a 20+ char alnum ElevenLabs ID goes to EL."""
    eleven, kokoro = mock_synthesizers
    custom_id = "Xb7hH8MSUJpSbSDYk0k2"  # 20 chars, alphanumeric
    out = await synthesize_speech("texto", voice=custom_id)
    assert out == "/tmp/elevenlabs.ogg"
    eleven.assert_awaited_once()


async def test_custom_elevenlabs_id_failure_falls_back_to_default_kokoro(mock_synthesizers) -> None:
    eleven, kokoro = mock_synthesizers
    eleven.return_value = None
    custom_id = "Xb7hH8MSUJpSbSDYk0k2"
    out = await synthesize_speech("texto", voice=custom_id)
    assert out == "/tmp/kokoro.ogg"
    eleven.assert_awaited_once()
    kokoro.assert_awaited_once()


async def test_unknown_short_voice_routes_to_kokoro(mock_synthesizers) -> None:
    """An unknown short voice name (not a custom EL id) falls through to Kokoro."""
    eleven, kokoro = mock_synthesizers
    out = await synthesize_speech("texto", voice="completelyunknown")
    assert out == "/tmp/kokoro.ogg"
    kokoro.assert_awaited_once()
    eleven.assert_not_awaited()


async def test_speed_passthrough(mock_synthesizers) -> None:
    eleven, _kokoro = mock_synthesizers
    await synthesize_speech("texto", voice="alice", speed=1.5)
    # speed is the third positional arg in the implementation.
    assert eleven.call_args.args[2] == 1.5


async def test_language_passthrough_to_kokoro(mock_synthesizers) -> None:
    _eleven, kokoro = mock_synthesizers
    await synthesize_speech("texto", voice="pf_dora", language="pt-br")
    assert kokoro.call_args.kwargs.get("language") == "pt-br"


async def test_empty_language_normalized_to_none(mock_synthesizers) -> None:
    _eleven, kokoro = mock_synthesizers
    await synthesize_speech("texto", voice="pf_dora", language="   ")
    assert kokoro.call_args.kwargs.get("language") is None


async def test_model_passthrough_to_elevenlabs(mock_synthesizers) -> None:
    eleven, _kokoro = mock_synthesizers
    await synthesize_speech("texto", voice="alice", model="eleven_v3_alpha")
    assert eleven.call_args.kwargs.get("model_id") == "eleven_v3_alpha"
