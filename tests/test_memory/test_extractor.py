"""Tests for memory/extractor.py."""

from unittest.mock import AsyncMock, patch

import pytest

from koda.memory.extractor import _parse_extraction_result, _should_skip_extraction, extract
from koda.memory.types import MemoryType


def test_parse_valid_json():
    """Parses valid JSON array."""
    raw = '[{"type": "fact", "content": "API uses REST", "importance": 0.8}]'
    memories = _parse_extraction_result(raw, user_id=111, session_id=None)
    assert len(memories) == 1
    assert memories[0].memory_type == MemoryType.FACT
    assert memories[0].content == "API uses REST"
    assert memories[0].importance == 0.8
    assert memories[0].user_id == 111


def test_parse_json_with_markdown_fence():
    """Handles markdown code fence wrapping."""
    raw = '```json\n[{"type": "event", "content": "Deploy on Monday", "importance": 0.9}]\n```'
    memories = _parse_extraction_result(raw, user_id=111, session_id=None)
    assert len(memories) == 1
    assert memories[0].memory_type == MemoryType.EVENT
    assert memories[0].content == "Deploy on Monday"


def test_parse_json_with_surrounding_text():
    """Extracts JSON from surrounding text."""
    raw = 'Here are the extracted memories:\n[{"type": "fact", "content": "test", "importance": 0.5}]\nDone.'
    memories = _parse_extraction_result(raw, user_id=111, session_id=None)
    assert len(memories) == 1


def test_parse_empty_array():
    """Empty array returns no memories."""
    raw = "[]"
    memories = _parse_extraction_result(raw, user_id=111, session_id=None)
    assert len(memories) == 0


def test_parse_invalid_json():
    """Invalid JSON returns no memories."""
    raw = "This is not JSON at all"
    memories = _parse_extraction_result(raw, user_id=111, session_id=None)
    assert len(memories) == 0


def test_parse_max_items():
    """Limits to MEMORY_MAX_EXTRACTION_ITEMS items."""
    items = [{"type": "fact", "content": f"fact {i}", "importance": 0.5} for i in range(20)]
    import json

    from koda.memory.config import MEMORY_MAX_EXTRACTION_ITEMS

    raw = json.dumps(items)
    memories = _parse_extraction_result(raw, user_id=111, session_id=None)
    assert len(memories) == MEMORY_MAX_EXTRACTION_ITEMS


def test_parse_invalid_type_defaults_to_fact():
    """Unknown memory type defaults to fact."""
    raw = '[{"type": "unknown_type", "content": "test", "importance": 0.5}]'
    memories = _parse_extraction_result(raw, user_id=111, session_id=None)
    assert len(memories) == 1
    assert memories[0].memory_type == MemoryType.FACT


def test_parse_importance_clamped():
    """Importance is clamped to 0.0-1.0."""
    raw = '[{"type": "fact", "content": "test", "importance": 1.5}]'
    memories = _parse_extraction_result(raw, user_id=111, session_id=None)
    assert memories[0].importance == 1.0

    raw = '[{"type": "fact", "content": "test", "importance": -0.3}]'
    memories = _parse_extraction_result(raw, user_id=111, session_id=None)
    assert memories[0].importance == 0.0


def test_parse_skips_empty_content():
    """Entries with empty content are skipped."""
    raw = '[{"type": "fact", "content": "", "importance": 0.5}]'
    memories = _parse_extraction_result(raw, user_id=111, session_id=None)
    assert len(memories) == 0


def test_parse_sets_expiry():
    """All memories get an expiry date."""
    raw = '[{"type": "task", "content": "Fix bug", "importance": 0.7}]'
    memories = _parse_extraction_result(raw, user_id=111, session_id=None)
    assert memories[0].expires_at is not None


def test_parse_multiple_types():
    """Parses multiple types correctly."""
    raw = """[
        {"type": "fact", "content": "API uses REST", "importance": 0.8},
        {"type": "event", "content": "Deploy Monday", "importance": 0.9},
        {"type": "decision", "content": "Use PostgreSQL", "importance": 0.7}
    ]"""
    memories = _parse_extraction_result(raw, user_id=111, session_id="sess-1")
    assert len(memories) == 3
    types = {m.memory_type for m in memories}
    assert types == {MemoryType.FACT, MemoryType.EVENT, MemoryType.DECISION}
    assert all(m.session_id == "sess-1" for m in memories)


@pytest.mark.asyncio
async def test_extract_calls_runner():
    """Extract calls the provider-neutral runner and parses the response."""
    mock_result = {
        "result": '[{"type": "fact", "content": "test extracted", "importance": 0.6}]',
        "error": False,
    }
    with patch("koda.memory.extractor.run_llm", new_callable=AsyncMock, return_value=mock_result):
        memories = await extract("what is the API?", "It uses REST.", user_id=111)
        assert len(memories) == 1
        assert memories[0].content == "test extracted"


@pytest.mark.asyncio
async def test_extract_handles_error():
    """Extract returns empty list on error."""
    mock_result = {"result": "error message", "error": True}
    with patch("koda.memory.extractor.run_llm", new_callable=AsyncMock, return_value=mock_result):
        memories = await extract("query", "response", user_id=111)
        assert memories == []


@pytest.mark.asyncio
async def test_extract_handles_exception():
    """Extract returns empty list on exception."""
    with patch("koda.memory.extractor.run_llm", new_callable=AsyncMock, side_effect=Exception("fail")):
        memories = await extract(
            "a longer query that passes the skip filter",
            "a response that is long enough to pass",
            user_id=111,
        )
        assert memories == []


class TestShouldSkipExtraction:
    def test_skip_short_query_and_response(self):
        assert _should_skip_extraction("ok", "entendi") is True

    def test_skip_greeting(self):
        assert _should_skip_extraction("oi", "olá!") is True

    def test_skip_continuation_prefix(self):
        assert _should_skip_extraction("continua de onde parou", "ok, continuando...") is True
        assert _should_skip_extraction("e sobre o deploy?", "o deploy está ok") is True

    def test_skip_pure_stacktrace(self):
        trace = (
            "Traceback (most recent call last):\n"
            "  File 'app.py', line 10, in <module>\n"
            "    raise ValueError('bad value')\n"
            "ValueError: bad value\n"
            "  at module.func(file.py:20)\n"
            "  at module.other(file.py:30)\n"
            "  at module.third(file.py:40)\n"
            "Error: something went wrong\n"
        )
        assert _should_skip_extraction("what happened?", trace) is True

    def test_no_skip_meaningful_conversation(self):
        assert (
            _should_skip_extraction(
                "como funciona o endpoint de pagamentos?",
                "O endpoint /api/v1/payments usa o Stripe SDK para processar pagamentos.",
            )
            is False
        )

    def test_no_skip_long_query(self):
        assert _should_skip_extraction("Preciso configurar o deploy do projeto com Docker e CI/CD", "ok") is False
