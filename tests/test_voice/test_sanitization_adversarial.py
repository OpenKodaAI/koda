"""Adversarial sanitization tests for koda.utils.tts.strip_for_tts.

Authoritative against the current regex-chain implementation. Cases are
loaded from tests/fixtures/voice/sanitization_dataset.yaml. Categories:

  covered    — strip_for_tts produces the documented output
  gap        — input passes through unchanged; documents the gap
  edge       — empty / whitespace / boundary
  acceptance — real-world responses; happy-path coverage

When the underlying regex chain is extended in the future (e.g. to strip
list markers, table pipes, emojis, or HTML tags), the corresponding
case's category should change from `gap` to `covered` and the expected
output updated. The test itself never special-cases by category — it
asserts ``cleaned == expected`` for every case.
"""

from __future__ import annotations

from typing import Any

import pytest

from koda.utils.tts import is_mostly_code, strip_for_tts
from tests.test_voice.conftest import case_ids, load_sanitization_dataset

_DATASET = load_sanitization_dataset()


@pytest.mark.parametrize("case", _DATASET, ids=case_ids(_DATASET))
def test_strip_for_tts_exact_output(case: dict[str, Any]) -> None:
    """strip_for_tts(input) must equal expected, byte-for-byte."""
    cleaned = strip_for_tts(case["input"])
    assert cleaned == case["expected"], (
        f"\n  case_id: {case['id']}\n  category: {case.get('category')}\n"
        f"  input    : {case['input']!r}\n"
        f"  expected : {case['expected']!r}\n"
        f"  actual   : {cleaned!r}"
    )


@pytest.mark.parametrize("case", _DATASET, ids=case_ids(_DATASET))
def test_strip_for_tts_forbidden_substrings(case: dict[str, Any]) -> None:
    """For each case, the output must not contain any forbidden substring."""
    cleaned = strip_for_tts(case["input"])
    for forbidden in case.get("forbidden") or []:
        assert forbidden not in cleaned, (
            f"\n  case_id: {case['id']}\n  forbidden substring leaked: {forbidden!r}\n  cleaned: {cleaned!r}"
        )


@pytest.mark.parametrize("case", _DATASET, ids=case_ids(_DATASET))
def test_strip_for_tts_idempotent(case: dict[str, Any]) -> None:
    """Running strip_for_tts twice yields the same output."""
    once = strip_for_tts(case["input"])
    twice = strip_for_tts(once)
    assert once == twice, f"non-idempotent on {case['id']}: once={once!r} twice={twice!r}"


def test_dataset_has_minimum_diversity() -> None:
    """Dataset has at least 50 cases covering all categories."""
    cases = load_sanitization_dataset()
    assert len(cases) >= 50, f"dataset too small: {len(cases)} cases"
    categories = {c.get("category") for c in cases}
    assert {"covered", "gap", "edge", "acceptance"}.issubset(categories), f"missing categories; got: {categories}"


def test_dataset_ids_unique() -> None:
    cases = load_sanitization_dataset()
    ids = [c["id"] for c in cases]
    duplicates = {i for i in ids if ids.count(i) > 1}
    assert not duplicates, f"duplicate case ids: {sorted(duplicates)}"


def test_is_mostly_code_returns_false_when_no_code_blocks() -> None:
    assert is_mostly_code("Texto puro sem código") is False
    assert is_mostly_code("") is False


def test_is_mostly_code_majority_code_block() -> None:
    """When 60%+ of the text is in code blocks, is_mostly_code returns True."""
    code = "```\n" + "x" * 200 + "\n```"
    text = code + " short tail"
    assert is_mostly_code(text) is True


def test_is_mostly_code_minority_code_block() -> None:
    """A small code block in a long prose response stays under threshold."""
    code = "```\nx = 1\n```"
    text = "muito texto antes " * 30 + code + " e muito depois " * 30
    assert is_mostly_code(text) is False
