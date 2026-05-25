"""Tests for message splitting and sending (HTML mode)."""

from koda.utils.messaging import split_message


class TestSplitMessage:
    def test_short_message_not_split(self):
        text = "Hello, world!"
        result = split_message(text)
        assert result == [text]

    def test_exact_max_len_not_split(self):
        text = "a" * 4090
        result = split_message(text)
        assert result == [text]

    def test_splits_at_boundary(self):
        text = "line1\n" * 1000
        result = split_message(text, max_len=100)
        assert len(result) > 1
        for chunk in result:
            assert len(chunk) <= 110  # small overshoot from line concat is ok

    def test_preserves_pre_tags(self):
        text = "before\n<pre>code line 1\ncode line 2</pre>\nafter"
        result = split_message(text, max_len=40)
        assert len(result) >= 2
        full = "".join(result)
        assert "code line 1" in full
        assert "code line 2" in full

    def test_empty_string(self):
        result = split_message("")
        assert result == [""]

    def test_single_long_line_force_split(self):
        long_line = "x" * 10000
        result = split_message(long_line, max_len=100)
        assert len(result) > 1
        reconstructed = "".join(c.rstrip("\n") for c in result)
        assert long_line in reconstructed or len(reconstructed) >= len(long_line)

    def test_pre_tag_state_across_splits(self):
        """<pre> tags should be properly closed/reopened across splits."""
        lines = ["<pre>"]
        for i in range(50):
            lines.append(f"line {i}")
        lines.append("</pre>")
        text = "\n".join(lines)

        result = split_message(text, max_len=100)
        assert len(result) >= 2

        # First chunk should end with </pre>
        assert "</pre>" in result[0]
        # Second chunk should start with <pre>
        assert result[1].lstrip().startswith("<pre>")

    def test_multiple_pre_blocks(self):
        text = "text\n<pre>code1</pre>\nmore text\n<pre>code2</pre>\nend"
        result = split_message(text, max_len=50)
        assert len(result) >= 1
        full = "".join(result)
        assert "code1" in full
        assert "code2" in full
