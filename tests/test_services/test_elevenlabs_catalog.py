from koda.services.elevenlabs_catalog import (
    elevenlabs_language_supported,
    elevenlabs_languages_for_model,
    elevenlabs_tts_model_ids,
)


def test_elevenlabs_tts_model_ids_exclude_non_tts_models() -> None:
    ids = elevenlabs_tts_model_ids()

    assert "eleven_flash_v2_5" in ids
    assert "eleven_v3" in ids
    assert "eleven_multilingual_sts_v2" not in ids
    assert "eleven_multilingual_ttv_v2" not in ids
    assert "eleven_text_to_sound_v2" not in ids
    assert "scribe_v2" not in ids


def test_elevenlabs_v3_exposes_expanded_language_set() -> None:
    codes = {item["code"] for item in elevenlabs_languages_for_model("eleven_v3")}

    assert len(codes) >= 70
    assert {"en", "pt", "es", "fr", "de", "zh", "hy", "cy"} <= codes
    assert elevenlabs_language_supported("eleven_v3", "pt-br") is True
