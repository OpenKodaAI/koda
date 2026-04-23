"""Build Atlassian Document Format (ADF v3) documents from plain text."""

from __future__ import annotations

import re

_MENTION_RE = re.compile(r"\[~accountId:([^\]]+)\]")


def make_text_node(text: str) -> dict:
    """Return an ADF text node."""
    return {"type": "text", "text": text}


def make_mention_node(account_id: str) -> dict:
    """Return an ADF mention inline node."""
    return {
        "type": "mention",
        "attrs": {"id": account_id, "accessLevel": ""},
    }


def make_paragraph(nodes: list[dict]) -> dict:
    """Return an ADF paragraph block wrapping the given inline nodes."""
    return {"type": "paragraph", "content": nodes}


def _parse_inline(text: str) -> list[dict]:
    """Parse a text segment into inline nodes, converting mention syntax."""
    nodes: list[dict] = []
    last = 0
    for m in _MENTION_RE.finditer(text):
        before = text[last : m.start()]
        if before:
            nodes.append(make_text_node(before))
        nodes.append(make_mention_node(m.group(1)))
        last = m.end()
    tail = text[last:]
    if tail:
        nodes.append(make_text_node(tail))
    return nodes


def text_to_adf(text: str) -> dict:
    """Convert plain text to an ADF document.

    Splits on double newlines into paragraphs and parses
    ``[~accountId:ID]`` mention syntax into ADF mention nodes.
    """
    paragraphs: list[dict] = []
    for block in re.split(r"\n\n+", text):
        block = block.strip()
        if not block:
            continue
        inline_nodes = _parse_inline(block)
        if inline_nodes:
            paragraphs.append(make_paragraph(inline_nodes))
    if not paragraphs:
        paragraphs.append(make_paragraph([make_text_node("")]))
    return {"type": "doc", "version": 1, "content": paragraphs}
