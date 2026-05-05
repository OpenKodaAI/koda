"""Static ElevenLabs language metadata used around voice selection."""

from __future__ import annotations

import unicodedata
from typing import Any

ELEVENLABS_DEFAULT_TTS_MODEL = "eleven_flash_v2_5"

ELEVENLABS_TTS_MODEL_IDS: tuple[str, ...] = (
    "eleven_v3",
    "eleven_multilingual_v2",
    "eleven_flash_v2_5",
    "eleven_turbo_v2_5",
    "eleven_flash_v2",
    "eleven_turbo_v2",
    "eleven_multilingual_v1",
    "eleven_monolingual_v1",
)

ELEVENLABS_TTS_MODEL_CATALOG: dict[str, dict[str, str]] = {
    "eleven_v3": {
        "title": "Eleven v3",
        "description": "Modelo mais expressivo para fala natural e dialogos.",
        "languages": "70+ idiomas",
        "status": "current",
    },
    "eleven_multilingual_v2": {
        "title": "Multilingual v2",
        "description": "Modelo estavel e natural para geracoes longas.",
        "languages": "29 idiomas",
        "status": "current",
    },
    "eleven_flash_v2_5": {
        "title": "Flash v2.5",
        "description": "Baixa latencia e custo menor para agentes de voz.",
        "languages": "32 idiomas",
        "status": "current",
    },
    "eleven_turbo_v2_5": {
        "title": "Turbo v2.5",
        "description": "Modelo turbo anterior; prefira Flash v2.5 quando possivel.",
        "languages": "32 idiomas",
        "status": "deprecated",
    },
    "eleven_flash_v2": {
        "title": "Flash v2",
        "description": "Versao anterior de baixa latencia, apenas ingles.",
        "languages": "ingles",
        "status": "legacy",
    },
    "eleven_turbo_v2": {
        "title": "Turbo v2",
        "description": "Modelo turbo anterior, apenas ingles; prefira Flash v2.",
        "languages": "ingles",
        "status": "deprecated",
    },
    "eleven_multilingual_v1": {
        "title": "Multilingual v1",
        "description": "Modelo multilingue anterior; prefira Multilingual v2.",
        "languages": "8 idiomas",
        "status": "deprecated",
    },
    "eleven_monolingual_v1": {
        "title": "Monolingual v1",
        "description": "Modelo ingles anterior.",
        "languages": "ingles",
        "status": "deprecated",
    },
}

ELEVENLABS_LANGUAGE_LABELS: dict[str, str] = {
    "af": "Afrikaans",
    "ar": "Arabic",
    "as": "Assamese",
    "az": "Azerbaijani",
    "be": "Belarusian",
    "bg": "Bulgarian",
    "bn": "Bengali",
    "bs": "Bosnian",
    "ca": "Catalan",
    "cs": "Czech",
    "cy": "Welsh",
    "da": "Danish",
    "de": "German",
    "el": "Greek",
    "en": "English",
    "es": "Spanish",
    "et": "Estonian",
    "fa": "Persian",
    "fil": "Filipino",
    "fi": "Finnish",
    "fr": "French",
    "ga": "Irish",
    "gl": "Galician",
    "gu": "Gujarati",
    "ha": "Hausa",
    "he": "Hebrew",
    "hi": "Hindi",
    "hr": "Croatian",
    "hu": "Hungarian",
    "hy": "Armenian",
    "id": "Indonesian",
    "is": "Icelandic",
    "it": "Italian",
    "ja": "Japanese",
    "jv": "Javanese",
    "ka": "Georgian",
    "kk": "Kazakh",
    "kn": "Kannada",
    "ko": "Korean",
    "ky": "Kirghiz",
    "lb": "Luxembourgish",
    "ln": "Lingala",
    "lt": "Lithuanian",
    "lv": "Latvian",
    "mk": "Macedonian",
    "ml": "Malayalam",
    "mr": "Marathi",
    "ms": "Malay",
    "ne": "Nepali",
    "ny": "Chichewa",
    "nl": "Dutch",
    "no": "Norwegian",
    "pa": "Punjabi",
    "ps": "Pashto",
    "pl": "Polish",
    "pt": "Portuguese",
    "ro": "Romanian",
    "ru": "Russian",
    "sd": "Sindhi",
    "sk": "Slovak",
    "sl": "Slovenian",
    "so": "Somali",
    "sr": "Serbian",
    "sw": "Swahili",
    "sv": "Swedish",
    "ta": "Tamil",
    "te": "Telugu",
    "th": "Thai",
    "tr": "Turkish",
    "uk": "Ukrainian",
    "ur": "Urdu",
    "vi": "Vietnamese",
    "zh": "Chinese",
}

_MULTILINGUAL_V2_LANGUAGES: tuple[str, ...] = (
    "en",
    "ja",
    "zh",
    "de",
    "hi",
    "fr",
    "ko",
    "pt",
    "it",
    "es",
    "id",
    "nl",
    "tr",
    "fil",
    "pl",
    "sv",
    "bg",
    "ro",
    "ar",
    "cs",
    "el",
    "fi",
    "hr",
    "ms",
    "sk",
    "da",
    "ta",
    "uk",
    "ru",
)

_FLASH_V25_EXTRA_LANGUAGES: tuple[str, ...] = ("hu", "no", "vi")

_ELEVEN_V3_LANGUAGES: tuple[str, ...] = (
    "af",
    "ar",
    "hy",
    "as",
    "az",
    "be",
    "bn",
    "bs",
    "bg",
    "ca",
    "ny",
    "hr",
    "cs",
    "da",
    "nl",
    "en",
    "et",
    "fil",
    "fi",
    "fr",
    "gl",
    "ka",
    "de",
    "el",
    "gu",
    "ha",
    "he",
    "hi",
    "hu",
    "is",
    "id",
    "ga",
    "it",
    "ja",
    "jv",
    "kn",
    "kk",
    "ky",
    "ko",
    "lv",
    "ln",
    "lt",
    "lb",
    "mk",
    "ms",
    "ml",
    "zh",
    "mr",
    "ne",
    "no",
    "ps",
    "fa",
    "pl",
    "pt",
    "pa",
    "ro",
    "ru",
    "sr",
    "sd",
    "sk",
    "sl",
    "so",
    "es",
    "sw",
    "sv",
    "ta",
    "te",
    "th",
    "tr",
    "uk",
    "ur",
    "vi",
    "cy",
)

ELEVENLABS_MODEL_LANGUAGE_CODES: dict[str, tuple[str, ...]] = {
    "eleven_v3": _ELEVEN_V3_LANGUAGES,
    "eleven_multilingual_v2": _MULTILINGUAL_V2_LANGUAGES,
    "eleven_multilingual_v1": ("en", "fr", "de", "hi", "it", "pl", "pt", "es"),
    "eleven_multilingual_sts_v2": _MULTILINGUAL_V2_LANGUAGES,
    "eleven_multilingual_ttv_v2": _MULTILINGUAL_V2_LANGUAGES,
    "eleven_flash_v2_5": _MULTILINGUAL_V2_LANGUAGES + _FLASH_V25_EXTRA_LANGUAGES,
    "eleven_turbo_v2_5": _MULTILINGUAL_V2_LANGUAGES + _FLASH_V25_EXTRA_LANGUAGES,
    "eleven_flash_v2": ("en",),
    "eleven_turbo_v2": ("en",),
    "eleven_monolingual_v1": ("en",),
    "eleven_english_sts_v2": ("en",),
}

_LANGUAGE_ALIASES: dict[str, str] = {
    "arabic": "ar",
    "arabe": "ar",
    "bulgarian": "bg",
    "bulgaro": "bg",
    "chinese": "zh",
    "chines": "zh",
    "cmn": "zh",
    "czech": "cs",
    "dinamarques": "da",
    "dutch": "nl",
    "english": "en",
    "espanhol": "es",
    "french": "fr",
    "frances": "fr",
    "german": "de",
    "alemao": "de",
    "greek": "el",
    "hindi": "hi",
    "italian": "it",
    "italiano": "it",
    "japanese": "ja",
    "japones": "ja",
    "korean": "ko",
    "coreano": "ko",
    "malay": "ms",
    "mandarin": "zh",
    "norwegian": "no",
    "polish": "pl",
    "polones": "pl",
    "por": "pt",
    "portuguese": "pt",
    "portugues": "pt",
    "portuguesa": "pt",
    "brazil": "pt",
    "brazilian": "pt",
    "brasil": "pt",
    "romanian": "ro",
    "russian": "ru",
    "spanish": "es",
    "svenska": "sv",
    "swedish": "sv",
    "tamil": "ta",
    "turkish": "tr",
    "turco": "tr",
    "ukrainian": "uk",
    "vietnamese": "vi",
}


def _fold_text(value: Any) -> str:
    text = str(value or "").strip().lower().replace("_", "-")
    text = "".join(char for char in unicodedata.normalize("NFKD", text) if not unicodedata.combining(char))
    return text


def canonicalize_elevenlabs_language(value: Any) -> str:
    """Return the model/API language code for user, locale or docs language input."""
    text = _fold_text(value)
    if not text:
        return ""
    if text in _LANGUAGE_ALIASES:
        return _LANGUAGE_ALIASES[text]
    if text in ELEVENLABS_LANGUAGE_LABELS:
        return text
    if "-" in text:
        prefix = text.split("-", 1)[0]
        if prefix in _LANGUAGE_ALIASES:
            return _LANGUAGE_ALIASES[prefix]
        if prefix in ELEVENLABS_LANGUAGE_LABELS:
            return prefix
    return text


def elevenlabs_language_label(language_code: Any) -> str:
    code = canonicalize_elevenlabs_language(language_code)
    return ELEVENLABS_LANGUAGE_LABELS.get(code, str(language_code or "").strip() or code.upper())


def elevenlabs_languages_for_model(model_id: str) -> list[dict[str, str]]:
    normalized_model = str(model_id or ELEVENLABS_DEFAULT_TTS_MODEL).strip()
    codes = ELEVENLABS_MODEL_LANGUAGE_CODES.get(normalized_model)
    if codes is None:
        codes = ELEVENLABS_MODEL_LANGUAGE_CODES[ELEVENLABS_DEFAULT_TTS_MODEL]
    return [{"code": code, "label": elevenlabs_language_label(code)} for code in codes]


def elevenlabs_tts_models() -> list[dict[str, str]]:
    """Return Text-to-Speech model choices safe for the speech synthesis API."""
    return [
        {
            "model_id": model_id,
            **ELEVENLABS_TTS_MODEL_CATALOG[model_id],
        }
        for model_id in ELEVENLABS_TTS_MODEL_IDS
    ]


def elevenlabs_tts_model_ids() -> set[str]:
    return set(ELEVENLABS_TTS_MODEL_IDS)


def elevenlabs_model_label(model_id: Any) -> str:
    normalized = str(model_id or "").strip()
    return ELEVENLABS_TTS_MODEL_CATALOG.get(normalized, {}).get("title") or normalized or ELEVENLABS_DEFAULT_TTS_MODEL


def elevenlabs_language_supported(model_id: str, language_code: Any) -> bool:
    code = canonicalize_elevenlabs_language(language_code)
    if not code:
        return False
    return code in {item["code"] for item in elevenlabs_languages_for_model(model_id)}


def elevenlabs_voice_language_matches(requested_language: Any, entry: dict[str, Any]) -> bool:
    requested = canonicalize_elevenlabs_language(requested_language)
    if not requested:
        return False
    language = canonicalize_elevenlabs_language(entry.get("language"))
    locale = canonicalize_elevenlabs_language(entry.get("locale"))
    code = canonicalize_elevenlabs_language(entry.get("code"))
    return requested in {language, locale, code}
