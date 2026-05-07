"""Voice test fixtures and dataset loaders."""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path
from typing import Any

import pytest
import yaml

DATASET_PATH = Path(__file__).resolve().parents[1] / "fixtures" / "voice" / "sanitization_dataset.yaml"


def _generate_long_period() -> str:
    """Build a >TTS_MAX_CHARS string ending with `.` for truncation tests.

    The string is a long sequence of period-terminated sentences so the
    truncation pass at strip_for_tts() can find a `. ` boundary in the
    second half of the budget.
    """
    sentence = "Esta é uma frase de teste com vários caracteres e tamanho razoável. "
    text = sentence * 80  # ~5600 chars, well above TTS_MAX_CHARS=4000
    return text


def _generate_long_period_truncated(raw: str) -> str:
    """Compute the expected truncation outcome for the long_period template.

    Mirrors strip_for_tts logic for predictability:
      1. apply regex chain (no-op here, raw is plain prose)
      2. .strip() (no-op for the generated string)
      3. since len > TTS_MAX_CHARS, truncate at TTS_MAX_CHARS, then look for
         a sentence-ending separator past TTS_MAX_CHARS // 2.
    """
    from koda.config import TTS_MAX_CHARS

    text = raw  # already pre-stripped
    if len(text) <= TTS_MAX_CHARS:
        return text
    truncated = text[:TTS_MAX_CHARS]
    for sep in [".\n", ". ", "!\n", "! ", "?\n", "? "]:
        idx = truncated.rfind(sep)
        if idx > TTS_MAX_CHARS // 2:
            truncated = truncated[: idx + 1]
            break
    return truncated.strip()


_TEMPLATES_INPUT: dict[str, str] = {
    "long_period": _generate_long_period(),
}

_TEMPLATES_EXPECTED: dict[str, str] = {
    "long_period_truncated": _generate_long_period_truncated(_TEMPLATES_INPUT["long_period"]),
}


def _expand(case: dict[str, Any]) -> dict[str, Any]:
    if "input_template" in case:
        case = dict(case)
        case["input"] = _TEMPLATES_INPUT[case["input_template"]]
    if "expected_template" in case:
        case["expected"] = _TEMPLATES_EXPECTED[case["expected_template"]]
    return case


def load_sanitization_dataset() -> list[dict[str, Any]]:
    """Load and expand all sanitization cases from the YAML dataset."""
    raw = yaml.safe_load(DATASET_PATH.read_text(encoding="utf-8"))
    return [_expand(case) for case in raw["cases"]]


@pytest.fixture(scope="session")
def sanitization_cases() -> list[dict[str, Any]]:
    return load_sanitization_dataset()


@pytest.fixture(scope="session")
def acoustic_cases(sanitization_cases: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [c for c in sanitization_cases if c.get("acoustic")]


def case_ids(cases: Iterable[dict[str, Any]]) -> list[str]:
    return [c["id"] for c in cases]
