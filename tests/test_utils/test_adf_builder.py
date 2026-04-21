"""Tests for ADF document builder."""

from koda.utils.adf_builder import (
    make_mention_node,
    make_paragraph,
    make_text_node,
    text_to_adf,
)
from koda.utils.adf_renderer import render_adf


class TestTextToAdf:
    def test_simple_text(self):
        adf = text_to_adf("Hello world")
        assert adf["type"] == "doc"
        assert adf["version"] == 1
        assert len(adf["content"]) == 1
        para = adf["content"][0]
        assert para["type"] == "paragraph"
        assert para["content"] == [{"type": "text", "text": "Hello world"}]

    def test_multiline(self):
        adf = text_to_adf("First paragraph\n\nSecond paragraph")
        assert len(adf["content"]) == 2
        assert adf["content"][0]["content"][0]["text"] == "First paragraph"
        assert adf["content"][1]["content"][0]["text"] == "Second paragraph"

    def test_mention_parsing(self):
        adf = text_to_adf("Hello [~accountId:abc123]")
        nodes = adf["content"][0]["content"]
        assert len(nodes) == 2
        assert nodes[0] == {"type": "text", "text": "Hello "}
        assert nodes[1] == {
            "type": "mention",
            "attrs": {"id": "abc123", "accessLevel": ""},
        }

    def test_multiple_mentions(self):
        adf = text_to_adf("CC [~accountId:user1] and [~accountId:user2] please review")
        nodes = adf["content"][0]["content"]
        assert len(nodes) == 5
        assert nodes[0]["type"] == "text"
        assert nodes[1]["type"] == "mention"
        assert nodes[1]["attrs"]["id"] == "user1"
        assert nodes[2]["type"] == "text"
        assert nodes[3]["type"] == "mention"
        assert nodes[3]["attrs"]["id"] == "user2"
        assert nodes[4]["type"] == "text"

    def test_empty_text(self):
        adf = text_to_adf("")
        assert adf["type"] == "doc"
        assert adf["version"] == 1
        assert len(adf["content"]) == 1
        assert adf["content"][0]["content"][0]["text"] == ""

    def test_roundtrip(self):
        original = "This is a test comment"
        adf = text_to_adf(original)
        rendered = render_adf(adf)
        assert rendered == original

    def test_multiline_roundtrip(self):
        original = "First paragraph\n\nSecond paragraph"
        adf = text_to_adf(original)
        rendered = render_adf(adf)
        assert "First paragraph" in rendered
        assert "Second paragraph" in rendered


class TestHelpers:
    def test_make_text_node(self):
        node = make_text_node("hello")
        assert node == {"type": "text", "text": "hello"}

    def test_make_mention_node(self):
        node = make_mention_node("abc123")
        assert node["type"] == "mention"
        assert node["attrs"]["id"] == "abc123"

    def test_make_paragraph(self):
        nodes = [make_text_node("test")]
        para = make_paragraph(nodes)
        assert para["type"] == "paragraph"
        assert para["content"] == nodes
