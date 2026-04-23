"""Formatting utilities for Telegram messages.

Provides:
- GFM Markdown -> Telegram HTML conversion
- HTML entity escaping
- Code block detection and extraction
"""

import re

# Characters that must be escaped in MarkdownV2
_MARKDOWNV2_SPECIAL = re.compile(r"([_*\[\]()~`>#+\-=|{}.!\\])")

# Detect code blocks: ```lang\n...\n```
_CODE_BLOCK_RE = re.compile(r"```(\w*)\n(.*?)```", re.DOTALL)

# Detect inline code: `...`
_INLINE_CODE_RE = re.compile(r"`([^`]+)`")

# Large code block threshold (lines)
LARGE_CODE_BLOCK_THRESHOLD = 50


def escape_markdownv2(text: str) -> str:
    """Escape special characters for MarkdownV2, preserving code blocks and inline code."""
    parts: list[str] = []
    last_end = 0

    # Find all code blocks and inline code first
    protected_ranges: list[tuple[int, int, str]] = []

    for m in _CODE_BLOCK_RE.finditer(text):
        lang = m.group(1)
        code = m.group(2)
        # In MarkdownV2, code inside ``` doesn't need escaping except for ` and \
        escaped_code = code.replace("\\", "\\\\").replace("`", "\\`")
        protected_ranges.append((m.start(), m.end(), f"```{lang}\n{escaped_code}```"))

    for m in _INLINE_CODE_RE.finditer(text):
        # Skip if inside a code block
        in_block = any(start <= m.start() < end for start, end, _ in protected_ranges)
        if not in_block:
            code = m.group(1).replace("\\", "\\\\").replace("`", "\\`")
            protected_ranges.append((m.start(), m.end(), f"`{code}`"))

    # Sort by position
    protected_ranges.sort(key=lambda x: x[0])

    for start, end, replacement in protected_ranges:
        if start > last_end:
            parts.append(_MARKDOWNV2_SPECIAL.sub(r"\\\1", text[last_end:start]))
        parts.append(replacement)
        last_end = end

    if last_end < len(text):
        parts.append(_MARKDOWNV2_SPECIAL.sub(r"\\\1", text[last_end:]))

    return "".join(parts)


def detect_large_code_blocks(text: str) -> list[tuple[str, str, int]]:
    """Detect code blocks with more than LARGE_CODE_BLOCK_THRESHOLD lines.

    Returns list of (language, code_content, line_count) for large blocks.
    """
    large_blocks: list[tuple[str, str, int]] = []
    for m in _CODE_BLOCK_RE.finditer(text):
        lang = m.group(1) or "txt"
        code = m.group(2)
        line_count = code.count("\n") + 1
        if line_count > LARGE_CODE_BLOCK_THRESHOLD:
            large_blocks.append((lang, code, line_count))
    return large_blocks


def extract_and_replace_large_blocks(text: str) -> tuple[str, list[tuple[str, str]]]:
    """Replace large code blocks with placeholders and return file contents.

    Returns (modified_text, [(filename, content), ...])
    """
    files: list[tuple[str, str]] = []
    counter = 0

    def _replacer(m: re.Match[str]) -> str:
        nonlocal counter
        lang = m.group(1) or "txt"
        code = m.group(2)
        line_count = code.count("\n") + 1
        if line_count > LARGE_CODE_BLOCK_THRESHOLD:
            ext = lang if lang in ("py", "js", "ts", "go", "rs", "java", "sh", "sql", "yaml", "json") else "txt"
            counter += 1
            filename = f"code_{counter}.{ext}"
            files.append((filename, code))
            return f"[Code block sent as file: {filename} ({line_count} lines)]"
        return m.group(0) or ""

    modified = _CODE_BLOCK_RE.sub(_replacer, text)
    return modified, files


# ---------------------------------------------------------------------------
# GFM Markdown -> Telegram HTML conversion
# ---------------------------------------------------------------------------

_SENTINEL = "\x00"  # null-byte placeholder prefix


def escape_html(text: str) -> str:
    """Escape ``&``, ``<``, ``>`` for Telegram HTML."""
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def markdown_to_telegram_html(text: str) -> str:
    """Convert GitHub-flavored Markdown to Telegram-compatible HTML.

    Pipeline:
    1. Extract code blocks & inline code → placeholders
    2. Escape HTML entities in remaining text
    3. Convert block-level elements (headers, blockquotes, HR, tables, lists)
    4. Convert inline elements (bold, italic, strikethrough, links, images)
    5. Restore placeholders with pre-formatted HTML
    """
    if not text:
        return ""

    placeholders: dict[str, str] = {}
    counter = 0

    # --- Phase 1: extract code blocks and inline code -----------------------

    def _replace_code_block(m: re.Match) -> str:
        nonlocal counter
        counter += 1
        key = f"{_SENTINEL}CB{counter}{_SENTINEL}"
        lang = m.group(1)
        code = escape_html(m.group(2))
        if lang:
            placeholders[key] = f'<pre><code class="language-{escape_html(lang)}">{code}</code></pre>'
        else:
            placeholders[key] = f"<pre>{code}</pre>"
        return key

    result = _CODE_BLOCK_RE.sub(_replace_code_block, text)

    def _replace_inline_code(m: re.Match) -> str:
        nonlocal counter
        counter += 1
        key = f"{_SENTINEL}IC{counter}{_SENTINEL}"
        placeholders[key] = f"<code>{escape_html(m.group(1))}</code>"
        return key

    result = _INLINE_CODE_RE.sub(_replace_inline_code, result)

    # --- Phase 2: escape HTML entities in remaining text --------------------

    parts: list[str] = []
    last = 0
    for m in re.finditer(re.escape(_SENTINEL) + r"[A-Z]+\d+" + re.escape(_SENTINEL), result):
        if m.start() > last:
            parts.append(escape_html(result[last : m.start()]))
        parts.append(m.group(0))
        last = m.end()
    if last < len(result):
        parts.append(escape_html(result[last:]))
    result = "".join(parts)

    # --- Phase 3: block-level conversions -----------------------------------

    lines = result.split("\n")
    converted: list[str] = []
    i = 0
    while i < len(lines):
        line = lines[i]
        stripped = line.strip()

        # Headers: # → <b>
        header_m = re.match(r"^(#{1,6})\s+(.*)", stripped)
        if header_m:
            converted.append(f"<b>{header_m.group(2)}</b>")
            i += 1
            continue

        # Horizontal rule
        if re.match(r"^-{3,}$", stripped) or re.match(r"^\*{3,}$", stripped):
            converted.append("———")
            i += 1
            continue

        # Blockquote (merge consecutive lines)
        if stripped.startswith("&gt; ") or stripped == "&gt;":
            quote_lines: list[str] = []
            while i < len(lines):
                s = lines[i].strip()
                if s.startswith("&gt; "):
                    quote_lines.append(s[5:])
                elif s == "&gt;":
                    quote_lines.append("")
                else:
                    break
                i += 1
            converted.append(f"<blockquote>{chr(10).join(quote_lines)}</blockquote>")
            continue

        # Table detection: lines with |
        if "|" in stripped and i + 1 < len(lines) and re.match(r"^\|?[\s\-:|]+\|", lines[i + 1].strip()):
            table_lines: list[str] = []
            while i < len(lines) and "|" in lines[i]:
                row = lines[i].strip()
                # Skip separator rows
                if re.match(r"^\|?[\s\-:|]+\|", row):
                    i += 1
                    continue
                # Clean cells
                cells = [c.strip() for c in row.strip("|").split("|")]
                table_lines.append(" | ".join(cells))
                i += 1
            converted.append("<pre>" + "\n".join(table_lines) + "</pre>")
            continue

        # Unordered list items
        list_m = re.match(r"^(\s*)[-*]\s+(.*)", line)
        if list_m:
            indent = list_m.group(1)
            converted.append(f"{indent}\u2022 {list_m.group(2)}")
            i += 1
            continue

        # Ordered list items — keep as-is
        converted.append(line)
        i += 1

    result = "\n".join(converted)

    # --- Phase 4: inline conversions ----------------------------------------

    # Bold+italic: ***text*** → <b><i>text</i></b>
    result = re.sub(r"\*\*\*(.+?)\*\*\*", r"<b><i>\1</i></b>", result)
    # Bold: **text** → <b>text</b>
    result = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", result)
    # Italic: *text* → <i>text</i>  (but not inside words like file*name)
    result = re.sub(r"(?<!\w)\*([^\*]+?)\*(?!\w)", r"<i>\1</i>", result)
    # Strikethrough: ~~text~~ → <s>text</s>
    result = re.sub(r"~~(.+?)~~", r"<s>\1</s>", result)
    # Images: ![alt](url) → <a href="url">[image]</a>
    result = re.sub(r"!\[([^\]]*)\]\(([^)]+)\)", r'<a href="\2">[image]</a>', result)
    # Links: [text](url) → <a href="url">text</a>
    result = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r'<a href="\2">\1</a>', result)

    # --- Phase 5: restore placeholders -------------------------------------

    for key, html in placeholders.items():
        result = result.replace(key, html)

    return result


def format_error_message(error_text: str) -> str:
    """Classify and format errors with actionable suggestions."""
    lower = error_text.lower()
    if (
        "authentication" in lower
        or "authenticate" in lower
        or "invalid authentication credentials" in lower
        or "api error: 401" in lower
        or "not logged in" in lower
        or "login required" in lower
    ):
        return (
            "\U0001f511 <b>Authentication</b>\n"
            "The provider is missing valid credentials or the login session expired.\n\n"
            "<i>Re-authenticate the provider CLI and try again.</i>"
        )
    if "timeout" in lower or "timed out" in lower:
        return (
            "\u23f1 <b>Timeout</b>\n"
            "The provider took too long to complete the task.\n\n"
            "<i>Try simplifying the question or use /model auto to select a lighter model.</i>"
        )
    if "budget" in lower or "cost" in lower:
        return (
            "\U0001f4b0 <b>Budget</b>\n"
            "Cost limit reached.\n\n"
            "<i>Use /resetcost to reset or pick a cheaper model with /model.</i>"
        )
    if "overloaded" in lower:
        return (
            "\U0001f504 <b>Overloaded</b>\n"
            "The service is temporarily unavailable.\n\n"
            "<i>Wait a moment and try again.</i>"
        )
    return f"\u274c <b>Error</b>\n{escape_html(error_text[:500])}\n\n<i>Use /retry to try again.</i>"


def safe_markdown_to_telegram_html(text: str) -> str:
    """Convert Markdown to Telegram HTML with tag-balance validation.

    Falls back to HTML-escaped plain text if tags are unbalanced.
    """
    try:
        html = markdown_to_telegram_html(text)
        # Validate that every opened tag is closed
        for tag in ("b", "i", "s", "code", "pre", "blockquote"):
            opens = html.count(f"<{tag}>") + html.count(f"<{tag} ")
            closes = html.count(f"</{tag}>")
            if opens != closes:
                return escape_html(text)
        return html
    except Exception:
        return escape_html(text)
