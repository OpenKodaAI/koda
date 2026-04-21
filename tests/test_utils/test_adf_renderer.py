"""Tests for ADF renderer and URL extraction."""

from koda.utils.adf_renderer import classify_url, extract_urls_from_adf, render_adf


class TestRenderAdf:
    def test_empty_doc(self):
        assert render_adf(None) == ""
        assert render_adf({}) == ""
        assert render_adf({"type": "doc"}) == ""
        assert render_adf({"type": "doc", "content": []}) == ""

    def test_paragraph(self):
        doc = {
            "type": "doc",
            "content": [
                {
                    "type": "paragraph",
                    "content": [{"type": "text", "text": "Hello world"}],
                }
            ],
        }
        assert render_adf(doc) == "Hello world"

    def test_heading(self):
        doc = {
            "type": "doc",
            "content": [
                {
                    "type": "heading",
                    "attrs": {"level": 2},
                    "content": [{"type": "text", "text": "Title"}],
                }
            ],
        }
        assert render_adf(doc) == "## Title"

    def test_heading_levels(self):
        for level in (1, 2, 3, 4):
            doc = {
                "type": "doc",
                "content": [
                    {
                        "type": "heading",
                        "attrs": {"level": level},
                        "content": [{"type": "text", "text": "T"}],
                    }
                ],
            }
            assert render_adf(doc).startswith("#" * level + " ")

    def test_text_marks(self):
        doc = {
            "type": "doc",
            "content": [
                {
                    "type": "paragraph",
                    "content": [
                        {"type": "text", "text": "bold", "marks": [{"type": "strong"}]},
                        {"type": "text", "text": " "},
                        {"type": "text", "text": "italic", "marks": [{"type": "em"}]},
                        {"type": "text", "text": " "},
                        {"type": "text", "text": "code", "marks": [{"type": "code"}]},
                    ],
                }
            ],
        }
        result = render_adf(doc)
        assert "**bold**" in result
        assert "*italic*" in result
        assert "`code`" in result

    def test_text_link_mark(self):
        doc = {
            "type": "doc",
            "content": [
                {
                    "type": "paragraph",
                    "content": [
                        {
                            "type": "text",
                            "text": "click here",
                            "marks": [{"type": "link", "attrs": {"href": "https://example.com"}}],
                        }
                    ],
                }
            ],
        }
        assert render_adf(doc) == "[click here](https://example.com)"

    def test_strikethrough(self):
        doc = {
            "type": "doc",
            "content": [
                {
                    "type": "paragraph",
                    "content": [
                        {"type": "text", "text": "removed", "marks": [{"type": "strike"}]},
                    ],
                }
            ],
        }
        assert render_adf(doc) == "~~removed~~"

    def test_bullet_list(self):
        doc = {
            "type": "doc",
            "content": [
                {
                    "type": "bulletList",
                    "content": [
                        {
                            "type": "listItem",
                            "content": [
                                {"type": "paragraph", "content": [{"type": "text", "text": "A"}]},
                            ],
                        },
                        {
                            "type": "listItem",
                            "content": [
                                {"type": "paragraph", "content": [{"type": "text", "text": "B"}]},
                            ],
                        },
                    ],
                }
            ],
        }
        result = render_adf(doc)
        assert "- A" in result
        assert "- B" in result

    def test_ordered_list(self):
        doc = {
            "type": "doc",
            "content": [
                {
                    "type": "orderedList",
                    "content": [
                        {
                            "type": "listItem",
                            "content": [
                                {"type": "paragraph", "content": [{"type": "text", "text": "First"}]},
                            ],
                        },
                        {
                            "type": "listItem",
                            "content": [
                                {"type": "paragraph", "content": [{"type": "text", "text": "Second"}]},
                            ],
                        },
                    ],
                }
            ],
        }
        result = render_adf(doc)
        assert "1. First" in result
        assert "2. Second" in result

    def test_code_block(self):
        doc = {
            "type": "doc",
            "content": [
                {
                    "type": "codeBlock",
                    "attrs": {"language": "python"},
                    "content": [{"type": "text", "text": "print('hi')"}],
                }
            ],
        }
        result = render_adf(doc)
        assert "```python" in result
        assert "print('hi')" in result
        assert result.endswith("```")

    def test_blockquote(self):
        doc = {
            "type": "doc",
            "content": [
                {
                    "type": "blockquote",
                    "content": [
                        {"type": "paragraph", "content": [{"type": "text", "text": "quoted text"}]},
                    ],
                }
            ],
        }
        result = render_adf(doc)
        assert "> quoted text" in result

    def test_table(self):
        doc = {
            "type": "doc",
            "content": [
                {
                    "type": "table",
                    "content": [
                        {
                            "type": "tableRow",
                            "content": [
                                {"type": "tableHeader", "content": [{"type": "text", "text": "Name"}]},
                                {"type": "tableHeader", "content": [{"type": "text", "text": "Value"}]},
                            ],
                        },
                        {
                            "type": "tableRow",
                            "content": [
                                {"type": "tableCell", "content": [{"type": "text", "text": "A"}]},
                                {"type": "tableCell", "content": [{"type": "text", "text": "1"}]},
                            ],
                        },
                    ],
                }
            ],
        }
        result = render_adf(doc)
        assert "| Name | Value |" in result
        assert "| A | 1 |" in result
        assert "---" in result

    def test_inline_card(self):
        doc = {
            "type": "doc",
            "content": [
                {
                    "type": "paragraph",
                    "content": [
                        {"type": "inlineCard", "attrs": {"url": "https://jira.example.com/browse/PROJ-1"}},
                    ],
                }
            ],
        }
        result = render_adf(doc)
        assert "https://jira.example.com/browse/PROJ-1" in result

    def test_mention(self):
        doc = {
            "type": "doc",
            "content": [
                {
                    "type": "paragraph",
                    "content": [
                        {"type": "mention", "attrs": {"text": "@John Doe"}},
                    ],
                }
            ],
        }
        result = render_adf(doc)
        assert "@John Doe" in result

    def test_media(self):
        doc = {
            "type": "doc",
            "content": [
                {"type": "media", "attrs": {"alt": "screenshot.png"}},
            ],
        }
        result = render_adf(doc)
        assert "[attachment: screenshot.png]" in result

    def test_emoji(self):
        doc = {
            "type": "doc",
            "content": [
                {
                    "type": "paragraph",
                    "content": [
                        {"type": "emoji", "attrs": {"shortName": ":thumbsup:"}},
                    ],
                }
            ],
        }
        result = render_adf(doc)
        assert ":thumbsup:" in result

    def test_rule(self):
        doc = {
            "type": "doc",
            "content": [{"type": "rule"}],
        }
        assert render_adf(doc) == "---"

    def test_hard_break(self):
        doc = {
            "type": "doc",
            "content": [
                {
                    "type": "paragraph",
                    "content": [
                        {"type": "text", "text": "line1"},
                        {"type": "hardBreak"},
                        {"type": "text", "text": "line2"},
                    ],
                }
            ],
        }
        result = render_adf(doc)
        assert "line1" in result
        assert "line2" in result

    def test_nested_list(self):
        doc = {
            "type": "doc",
            "content": [
                {
                    "type": "bulletList",
                    "content": [
                        {
                            "type": "listItem",
                            "content": [
                                {"type": "paragraph", "content": [{"type": "text", "text": "Parent"}]},
                                {
                                    "type": "bulletList",
                                    "content": [
                                        {
                                            "type": "listItem",
                                            "content": [
                                                {"type": "paragraph", "content": [{"type": "text", "text": "Child"}]},
                                            ],
                                        },
                                    ],
                                },
                            ],
                        },
                    ],
                }
            ],
        }
        result = render_adf(doc)
        assert "- Parent" in result
        assert "  - Child" in result

    def test_expand(self):
        doc = {
            "type": "doc",
            "content": [
                {
                    "type": "expand",
                    "attrs": {"title": "Details"},
                    "content": [
                        {"type": "paragraph", "content": [{"type": "text", "text": "Hidden content"}]},
                    ],
                }
            ],
        }
        result = render_adf(doc)
        assert "[Details]" in result
        assert "Hidden content" in result

    def test_panel(self):
        doc = {
            "type": "doc",
            "content": [
                {
                    "type": "panel",
                    "attrs": {"panelType": "warning"},
                    "content": [
                        {"type": "paragraph", "content": [{"type": "text", "text": "Be careful"}]},
                    ],
                }
            ],
        }
        result = render_adf(doc)
        assert "[warning]" in result
        assert "Be careful" in result

    def test_status(self):
        doc = {
            "type": "doc",
            "content": [
                {
                    "type": "paragraph",
                    "content": [
                        {"type": "status", "attrs": {"text": "IN PROGRESS"}},
                    ],
                }
            ],
        }
        result = render_adf(doc)
        assert "[IN PROGRESS]" in result

    def test_table_with_block_content(self):
        """Table cells with paragraphs should render properly."""
        doc = {
            "type": "doc",
            "content": [
                {
                    "type": "table",
                    "content": [
                        {
                            "type": "tableRow",
                            "content": [
                                {
                                    "type": "tableCell",
                                    "content": [
                                        {
                                            "type": "paragraph",
                                            "content": [{"type": "text", "text": "Cell with paragraph"}],
                                        },
                                    ],
                                },
                            ],
                        },
                    ],
                }
            ],
        }
        result = render_adf(doc)
        assert "Cell with paragraph" in result

    def test_unknown_node_graceful(self):
        """Unknown node types should not crash."""
        doc = {
            "type": "doc",
            "content": [
                {"type": "someNewNodeType", "content": [{"type": "text", "text": "inner"}]},
            ],
        }
        result = render_adf(doc)
        assert "inner" in result

    def test_malformed_input(self):
        assert render_adf(42) == ""
        assert render_adf("not a dict") == ""
        assert render_adf([]) == ""

    def test_multiple_paragraphs(self):
        doc = {
            "type": "doc",
            "content": [
                {"type": "paragraph", "content": [{"type": "text", "text": "First"}]},
                {"type": "paragraph", "content": [{"type": "text", "text": "Second"}]},
            ],
        }
        result = render_adf(doc)
        assert result == "First\nSecond"


class TestExtractUrls:
    def test_no_urls(self):
        doc = {
            "type": "doc",
            "content": [
                {"type": "paragraph", "content": [{"type": "text", "text": "plain text"}]},
            ],
        }
        assert extract_urls_from_adf(doc) == []

    def test_link_mark(self):
        doc = {
            "type": "doc",
            "content": [
                {
                    "type": "paragraph",
                    "content": [
                        {
                            "type": "text",
                            "text": "link",
                            "marks": [{"type": "link", "attrs": {"href": "https://example.com"}}],
                        }
                    ],
                }
            ],
        }
        assert extract_urls_from_adf(doc) == ["https://example.com"]

    def test_inline_card_url(self):
        doc = {
            "type": "doc",
            "content": [
                {
                    "type": "paragraph",
                    "content": [
                        {"type": "inlineCard", "attrs": {"url": "https://jira.test.com/browse/X-1"}},
                    ],
                }
            ],
        }
        assert extract_urls_from_adf(doc) == ["https://jira.test.com/browse/X-1"]

    def test_deduplicate_urls(self):
        doc = {
            "type": "doc",
            "content": [
                {
                    "type": "paragraph",
                    "content": [
                        {
                            "type": "text",
                            "text": "a",
                            "marks": [{"type": "link", "attrs": {"href": "https://example.com"}}],
                        },
                        {
                            "type": "text",
                            "text": "b",
                            "marks": [{"type": "link", "attrs": {"href": "https://example.com"}}],
                        },
                    ],
                }
            ],
        }
        assert extract_urls_from_adf(doc) == ["https://example.com"]

    def test_multiple_different_urls(self):
        doc = {
            "type": "doc",
            "content": [
                {
                    "type": "paragraph",
                    "content": [
                        {
                            "type": "text",
                            "text": "a",
                            "marks": [{"type": "link", "attrs": {"href": "https://a.com"}}],
                        },
                        {"type": "inlineCard", "attrs": {"url": "https://b.com"}},
                    ],
                }
            ],
        }
        result = extract_urls_from_adf(doc)
        assert "https://a.com" in result
        assert "https://b.com" in result

    def test_empty_input(self):
        assert extract_urls_from_adf(None) == []
        assert extract_urls_from_adf({}) == []


class TestClassifyUrl:
    def test_jira_url(self):
        assert (
            classify_url(
                "https://team.atlassian.net/browse/PROJ-1",
                "https://team.atlassian.net",
                "https://team.atlassian.net/wiki",
            )
            == "jira"
        )

    def test_confluence_url(self):
        assert (
            classify_url(
                "https://team.atlassian.net/wiki/spaces/DEV/pages/123",
                "https://team.atlassian.net",
                "https://team.atlassian.net/wiki",
            )
            == "confluence"
        )

    def test_confluence_wiki_heuristic(self):
        assert (
            classify_url(
                "https://other.atlassian.net/wiki/spaces/X/pages/1",
                "",
                "",
            )
            == "confluence"
        )

    def test_external_url(self):
        assert (
            classify_url(
                "https://github.com/org/repo",
                "https://team.atlassian.net",
                "https://team.atlassian.net/wiki",
            )
            == "external"
        )

    def test_empty_base_urls(self):
        assert classify_url("https://github.com/x", "", "") == "external"

    def test_case_insensitive(self):
        assert (
            classify_url(
                "https://Team.Atlassian.Net/browse/X-1",
                "https://team.atlassian.net",
                "",
            )
            == "jira"
        )
