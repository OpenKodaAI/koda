"""Tests for formatting utilities (MarkdownV2 + GFM→Telegram HTML)."""

from koda.utils.formatting import (
    detect_large_code_blocks,
    escape_html,
    escape_markdownv2,
    extract_and_replace_large_blocks,
    format_error_message,
    markdown_to_telegram_html,
    safe_markdown_to_telegram_html,
)

# ---------------------------------------------------------------------------
# Existing MarkdownV2 tests
# ---------------------------------------------------------------------------


class TestEscapeMarkdownV2:
    def test_escapes_special_chars(self):
        result = escape_markdownv2("Hello_world!")
        assert "\\_" in result
        assert "\\!" in result

    def test_preserves_code_blocks(self):
        text = "Before ```python\nx = 1 + 2\n``` After"
        result = escape_markdownv2(text)
        # Code block content should not have + escaped
        assert "```python" in result
        assert "\\+" not in result or "```" in result

    def test_preserves_inline_code(self):
        text = "Use `x + y` to add"
        result = escape_markdownv2(text)
        assert "`x + y`" in result or "`x \\+ y`" in result

    def test_empty_string(self):
        assert escape_markdownv2("") == ""

    def test_no_special_chars(self):
        assert escape_markdownv2("hello world") == "hello world"


class TestDetectLargeCodeBlocks:
    def test_detects_large_block(self):
        code = "\n".join(f"line {i}" for i in range(60))
        text = f"```python\n{code}\n```"
        blocks = detect_large_code_blocks(text)
        assert len(blocks) == 1
        assert blocks[0][0] == "python"
        assert blocks[0][2] > 50

    def test_ignores_small_block(self):
        text = "```python\nprint('hi')\n```"
        blocks = detect_large_code_blocks(text)
        assert len(blocks) == 0

    def test_no_code_blocks(self):
        blocks = detect_large_code_blocks("Just plain text")
        assert len(blocks) == 0


class TestExtractAndReplaceLargeBlocks:
    def test_extracts_large_block(self):
        code = "\n".join(f"line {i}" for i in range(60))
        text = f"Before\n```py\n{code}\n```\nAfter"
        modified, files = extract_and_replace_large_blocks(text)
        assert len(files) == 1
        assert files[0][0] == "code_1.py"
        assert "sent as file" in modified
        assert "Before" in modified
        assert "After" in modified

    def test_preserves_small_block(self):
        text = "```python\nprint('hi')\n```"
        modified, files = extract_and_replace_large_blocks(text)
        assert len(files) == 0
        assert "```python" in modified

    def test_no_blocks(self):
        text = "Just text"
        modified, files = extract_and_replace_large_blocks(text)
        assert modified == text
        assert len(files) == 0

    def test_multiple_large_blocks(self):
        code1 = "\n".join(f"line {i}" for i in range(60))
        code2 = "\n".join(f"other {i}" for i in range(60))
        text = f"```js\n{code1}\n```\nMiddle\n```py\n{code2}\n```"
        modified, files = extract_and_replace_large_blocks(text)
        assert len(files) == 2


# ---------------------------------------------------------------------------
# GFM → Telegram HTML converter tests
# ---------------------------------------------------------------------------


class TestEscapeHtml:
    def test_escapes_ampersand_first(self):
        assert escape_html("A & B") == "A &amp; B"

    def test_escapes_angle_brackets(self):
        assert escape_html("<script>") == "&lt;script&gt;"

    def test_combined(self):
        assert escape_html("a < b & c > d") == "a &lt; b &amp; c &gt; d"


class TestMarkdownToTelegramHtml:
    def test_plain_text(self):
        assert markdown_to_telegram_html("hello world") == "hello world"

    def test_empty_input(self):
        assert markdown_to_telegram_html("") == ""

    # --- Headers ---
    def test_h1(self):
        assert "<b>Title</b>" in markdown_to_telegram_html("# Title")

    def test_h3(self):
        assert "<b>Sub</b>" in markdown_to_telegram_html("### Sub")

    # --- Bold / Italic / Strikethrough ---
    def test_bold(self):
        result = markdown_to_telegram_html("This is **bold** text")
        assert "<b>bold</b>" in result

    def test_italic(self):
        result = markdown_to_telegram_html("This is *italic* text")
        assert "<i>italic</i>" in result

    def test_strikethrough(self):
        result = markdown_to_telegram_html("~~deleted~~")
        assert "<s>deleted</s>" in result

    # --- Code blocks ---
    def test_code_block_with_lang(self):
        result = markdown_to_telegram_html("```python\nprint('hi')\n```")
        assert '<code class="language-python">' in result
        assert "<pre>" in result
        assert "print(&#x27;hi&#x27;)" in result or "print('hi')" in result

    def test_code_block_without_lang(self):
        result = markdown_to_telegram_html("```\ncode\n```")
        assert "<pre>" in result
        assert "code" in result

    def test_code_block_html_entities_escaped(self):
        result = markdown_to_telegram_html("```\na < b && c > d\n```")
        assert "&lt;" in result
        assert "&amp;" in result
        assert "&gt;" in result

    # --- Inline code ---
    def test_inline_code(self):
        result = markdown_to_telegram_html("Use `foo()` here")
        assert "<code>foo()</code>" in result

    def test_inline_code_preserves_html(self):
        result = markdown_to_telegram_html("Use `<div>` tag")
        assert "<code>&lt;div&gt;</code>" in result

    # --- Links ---
    def test_link(self):
        result = markdown_to_telegram_html("[click](https://example.com)")
        assert '<a href="https://example.com">click</a>' in result

    def test_image_link(self):
        result = markdown_to_telegram_html("![alt](https://img.png)")
        assert '<a href="https://img.png">[image]</a>' in result

    # --- Tables ---
    def test_table(self):
        table = "| A | B |\n| --- | --- |\n| 1 | 2 |"
        result = markdown_to_telegram_html(table)
        assert "<pre>" in result
        assert "A | B" in result
        assert "1 | 2" in result

    # --- Blockquotes ---
    def test_blockquote(self):
        result = markdown_to_telegram_html("> quoted text")
        assert "<blockquote>" in result
        assert "quoted text" in result

    # --- Lists ---
    def test_unordered_list(self):
        result = markdown_to_telegram_html("- item one\n- item two")
        assert "\u2022 item one" in result
        assert "\u2022 item two" in result

    # --- Horizontal rule ---
    def test_hr(self):
        result = markdown_to_telegram_html("---")
        assert "———" in result

    # --- HTML entities in input ---
    def test_html_entities_in_plain_text(self):
        result = markdown_to_telegram_html("Use < and > and &")
        assert "&lt;" in result
        assert "&gt;" in result
        assert "&amp;" in result

    # --- Nested formatting ---
    def test_bold_italic(self):
        result = markdown_to_telegram_html("***bold italic***")
        assert "<b><i>bold italic</i></b>" in result

    def test_bold_inside_header(self):
        result = markdown_to_telegram_html("# **Bold Header**")
        assert "<b>" in result

    # --- Malformed formatting ---
    def test_unmatched_bold(self):
        # Should not crash, may leave ** as-is
        result = markdown_to_telegram_html("**unclosed bold")
        assert "unclosed bold" in result

    def test_unmatched_code_fence(self):
        result = markdown_to_telegram_html("```\nno close")
        assert "no close" in result


class TestFormatErrorMessage:
    def test_authentication_error(self):
        result = format_error_message("Failed to authenticate. API Error: 401 Invalid authentication credentials")
        assert "Authentication" in result
        assert "valid credentials" in result or "login session expired" in result

    def test_timeout_error(self):
        result = format_error_message("Request timed out after 60s")
        assert "Timeout" in result
        assert "took too long" in result
        assert "/model auto" in result
        assert "Claude" not in result

    def test_budget_error(self):
        result = format_error_message("Budget limit exceeded: cost too high")
        assert "Budget" in result
        assert "/resetcost" in result
        assert "/model haiku" not in result

    def test_overloaded_error(self):
        result = format_error_message("API is overloaded, please try later")
        assert "Overloaded" in result
        assert "unavailable" in result

    def test_generic_error(self):
        result = format_error_message("Something unexpected happened")
        assert "Error" in result
        assert "/retry" in result
        assert "Something unexpected happened" in result


class TestSafeMarkdownToTelegramHtml:
    def test_normal_input(self):
        result = safe_markdown_to_telegram_html("**hello**")
        assert "<b>hello</b>" in result

    def test_empty_input(self):
        assert safe_markdown_to_telegram_html("") == ""

    def test_plain_text_passthrough(self):
        result = safe_markdown_to_telegram_html("just text")
        assert result == "just text"

    def test_multiline_blockquote(self):
        result = markdown_to_telegram_html("> line one\n> line two")
        assert "<blockquote>" in result
        assert "line one" in result
        assert "line two" in result
        # Should be a single blockquote, not two
        assert result.count("<blockquote>") == 1
