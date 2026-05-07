"""Sanitize user-provided system prompt text before injection into LLM system prompts.

This module defends against prompt-injection attacks by stripping XML-like
control tags, neutralising markdown heading boundaries that could create fake
prompt sections, removing dangerous control characters, and enforcing a hard
length cap.  The sanitised output is wrapped in explicit ``<user_instructions>``
delimiters so the surrounding system prompt can clearly delineate user-supplied
content.
"""

from __future__ import annotations

import re

# Tags that, if present in user text, could be interpreted as LLM control
# structures.  We strip both opening and closing forms, as well as
# self-closing variants (e.g. ``<system />``).
_DANGEROUS_TAG_RE = re.compile(
    r"</?(?:agent_cmd|tool_result|agent_\w+|system|assistant|human|user_instructions)\b[^>]*/?>",
    re.IGNORECASE,
)

# Control characters excluding tab (\x09) and newline (\x0a).
_CONTROL_CHAR_RE = re.compile(r"[\x00-\x08\x0b-\x1f\x7f]")

# Markdown ATX headings at the start of a line (1-6 ``#`` characters followed
# by a space).  Headings are converted to bold text so they cannot create new
# prompt sections that might override system policy.
_HEADING_RE = re.compile(r"^(#{1,6})\s+", re.MULTILINE)


def sanitize_user_system_prompt(raw: str, *, max_length: int = 8000) -> str:
    """Return *raw* after applying security sanitisation.

    Parameters
    ----------
    raw:
        Untrusted user-provided prompt text.
    max_length:
        Hard character cap applied before any other processing.

    Returns
    -------
    str
        The sanitised text wrapped in ``<user_instructions>`` delimiters, or an
        empty string when *raw* is empty / whitespace-only.
    """

    if not raw or not raw.strip():
        return ""

    text = raw[:max_length]

    # Remove null bytes and control characters (preserve \n and \t).
    text = _CONTROL_CHAR_RE.sub("", text)

    # Strip dangerous XML-like tags.
    text = _DANGEROUS_TAG_RE.sub("", text)

    # Neutralise markdown headings into bold text.
    text = _HEADING_RE.sub(r"**", text)

    return f"<user_instructions>\n{text}\n</user_instructions>"
