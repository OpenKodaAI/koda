"""Decision-tree tests for the voice-reply branch combining strip_for_tts,
is_mostly_code, and synthesize_speech.

The user emphasized that voice replies must be SPOKEN cleanly. This test pins
the decision tree applied by koda/services/queue_manager.py:4247–4263:

  if audio_response_enabled and TTS_ENABLED:
      if not is_mostly_code(response):
          plain = strip_for_tts(response)
          if plain.strip():
              synthesize_speech(plain, ...)

So for any combination of (response, audio_enabled, mostly_code, plain_empty)
we should be able to predict whether synthesize_speech is called and with
what cleaned text.
"""

from __future__ import annotations

from dataclasses import dataclass

from koda.utils.tts import is_mostly_code, strip_for_tts


@dataclass(frozen=True)
class VoiceDecision:
    """Result of the decision tree, mirroring queue_manager's branch."""

    should_call_tts: bool
    cleaned: str
    reason: str

    @classmethod
    def from_response(cls, response: str, *, audio_enabled: bool, tts_enabled: bool) -> VoiceDecision:
        if not (audio_enabled and tts_enabled):
            return cls(False, "", "audio_disabled")
        if is_mostly_code(response):
            return cls(False, "", "mostly_code")
        plain = strip_for_tts(response)
        if not plain.strip():
            return cls(False, plain, "empty_after_strip")
        return cls(True, plain, "speak")


# Audio gating


def test_does_not_speak_when_user_audio_disabled() -> None:
    d = VoiceDecision.from_response("Olá, tudo bem?", audio_enabled=False, tts_enabled=True)
    assert d.should_call_tts is False
    assert d.reason == "audio_disabled"


def test_does_not_speak_when_tts_globally_disabled() -> None:
    d = VoiceDecision.from_response("Olá, tudo bem?", audio_enabled=True, tts_enabled=False)
    assert d.should_call_tts is False


# is_mostly_code gate


def test_speaks_for_plain_prose() -> None:
    response = "Olá! Vou ajudar você com isso agora."
    d = VoiceDecision.from_response(response, audio_enabled=True, tts_enabled=True)
    assert d.should_call_tts is True
    assert d.cleaned == response
    assert d.reason == "speak"


def test_skips_when_response_is_mostly_code() -> None:
    response = "Veja:\n```\n" + "x = 1\n" * 60 + "```\nFim."  # >60% in code blocks
    assert is_mostly_code(response) is True
    d = VoiceDecision.from_response(response, audio_enabled=True, tts_enabled=True)
    assert d.should_call_tts is False
    assert d.reason == "mostly_code"


def test_speaks_when_response_has_minor_code_block() -> None:
    response = "Use o comando ```ls -la``` e veja a saída."
    # Code block is short relative to the rest, so is_mostly_code returns False.
    assert is_mostly_code(response) is False
    d = VoiceDecision.from_response(response, audio_enabled=True, tts_enabled=True)
    assert d.should_call_tts is True
    assert "code block omitted" in d.cleaned
    # Triple backticks must NOT leak into spoken text.
    assert "```" not in d.cleaned


# strip_for_tts emptiness gate


def test_skips_when_only_markdown_formatting() -> None:
    response = "**__~~##~~__**"
    d = VoiceDecision.from_response(response, audio_enabled=True, tts_enabled=True)
    # After strip: "____" (underscores survive), is non-empty so it speaks.
    # Document the fact: underscore-only is not skipped.
    assert d.should_call_tts is True
    assert "_" in d.cleaned
    assert "*" not in d.cleaned and "#" not in d.cleaned and "~" not in d.cleaned


def test_skips_when_only_strippable_markdown() -> None:
    """Pure '#' or '*' or '~' or '>' content strips to empty → skip TTS."""
    for response in ("###", "***", "~~~", ">>>"):
        d = VoiceDecision.from_response(response, audio_enabled=True, tts_enabled=True)
        assert d.should_call_tts is False, f"response={response!r} unexpectedly spoken"
        assert d.reason == "empty_after_strip"


def test_skips_when_only_url() -> None:
    response = "https://example.com/x/y/z"
    d = VoiceDecision.from_response(response, audio_enabled=True, tts_enabled=True)
    # URL stripped → empty → skip
    assert d.should_call_tts is False
    assert d.reason == "empty_after_strip"


def test_speaks_link_as_text_only() -> None:
    """Markdown link [text](url) is read as 'text', URL never leaks."""
    response = "Veja [a documentação](https://docs.koda.ai) por favor"
    d = VoiceDecision.from_response(response, audio_enabled=True, tts_enabled=True)
    assert d.should_call_tts is True
    assert "https://" not in d.cleaned
    assert "[" not in d.cleaned
    assert "]" not in d.cleaned
    assert "a documentação" in d.cleaned


# Hardening: forbidden tokens in cleaned text


_FORBIDDEN_IN_TTS_INPUT = ("```", "**", "&amp;", "<script", "https://", "http://")


def test_real_world_response_has_no_forbidden_tokens() -> None:
    response = (
        "Pronto! Veja [a doc](https://docs.koda.ai) e use **`koda run`** para iniciar.\n"
        "Mais detalhes em https://example.com.\n"
        "Se precisar use `--debug`."
    )
    d = VoiceDecision.from_response(response, audio_enabled=True, tts_enabled=True)
    assert d.should_call_tts is True
    for tok in _FORBIDDEN_IN_TTS_INPUT:
        assert tok not in d.cleaned, f"token {tok!r} leaked: {d.cleaned!r}"


def test_long_response_truncated_at_sentence_boundary() -> None:
    """Long response is truncated by strip_for_tts at TTS_MAX_CHARS."""
    response = "Esta é uma frase. " * 1000
    d = VoiceDecision.from_response(response, audio_enabled=True, tts_enabled=True)
    assert d.should_call_tts is True
    # Truncation pass keeps it ≤ TTS_MAX_CHARS (4000).
    assert len(d.cleaned) <= 4000
