"""Decision-tree tests for the voice-reply branch.

Voice replies must be spoken cleanly without losing the useful technical
payload. Code-heavy, table-heavy, or very long responses should produce a short
spoken summary while preserving the full answer in text/attachments.
"""

from __future__ import annotations

from dataclasses import dataclass

from koda.services.queue_manager import _prepare_spoken_response_for_tts
from koda.utils.tts import is_mostly_code


@dataclass(frozen=True)
class VoiceDecision:
    """Result of the decision tree, mirroring queue_manager's branch."""

    should_call_tts: bool
    cleaned: str
    reason: str
    send_text_details: bool = False

    @classmethod
    def from_response(cls, response: str, *, audio_enabled: bool, tts_enabled: bool) -> VoiceDecision:
        if not (audio_enabled and tts_enabled):
            return cls(False, "", "audio_disabled")
        plain, send_text_details = _prepare_spoken_response_for_tts(
            response,
            user_data={"tts_voice_language": "pt-br"},
        )
        if not plain.strip():
            return cls(False, plain, "empty_after_strip", send_text_details)
        reason = "summarize_with_text" if send_text_details else "speak"
        return cls(True, plain, reason, send_text_details)


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


def test_summarizes_when_response_is_mostly_code() -> None:
    response = "Veja:\n```\n" + "x = 1\n" * 60 + "```\nFim."  # >60% in code blocks
    assert is_mostly_code(response) is True
    d = VoiceDecision.from_response(response, audio_enabled=True, tts_enabled=True)
    assert d.should_call_tts is True
    assert d.reason == "summarize_with_text"
    assert d.send_text_details is True
    assert "codigo ou detalhes tecnicos" in d.cleaned
    assert "x = 1" not in d.cleaned


def test_speaks_when_response_has_minor_code_block() -> None:
    response = "Use o comando ```ls -la``` e veja a saída."
    # Code block is short relative to the rest, so is_mostly_code returns False.
    assert is_mostly_code(response) is False
    d = VoiceDecision.from_response(response, audio_enabled=True, tts_enabled=True)
    assert d.should_call_tts is True
    assert d.reason == "summarize_with_text"
    assert d.send_text_details is True
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
    """Long response is summarized for speech below the dedicated spoken cap."""
    response = "Esta é uma frase. " * 1000
    d = VoiceDecision.from_response(response, audio_enabled=True, tts_enabled=True)
    assert d.should_call_tts is True
    assert d.send_text_details is True
    assert len(d.cleaned) <= 900
