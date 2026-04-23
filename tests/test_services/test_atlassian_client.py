"""Tests for Atlassian service layer."""

from unittest.mock import MagicMock, patch

import pytest

from koda.services.atlassian_client import (
    _SEARCH_FIELDS,
    COMMENT_META_PROPERTY_KEY,
    MAX_AUDIO_SIZE,
    MAX_IMAGE_SIZE,
    ConfluenceService,
    JiraService,
    _format_issue_analysis,
    _format_links,
    _format_size,
    _require,
    parse_atlassian_args,
)
from koda.utils.adf_renderer import render_adf


class TestParseAtlassianArgs:
    def test_basic(self):
        resource, action, params = parse_atlassian_args("issues search")
        assert resource == "issues"
        assert action == "search"
        assert params == {}

    def test_with_params(self):
        resource, action, params = parse_atlassian_args("issues get --key PROJ-123")
        assert resource == "issues"
        assert action == "get"
        assert params == {"key": "PROJ-123"}

    def test_quoted_strings(self):
        resource, action, params = parse_atlassian_args('issues search --jql "project = PROJ AND status = Done"')
        assert resource == "issues"
        assert action == "search"
        assert params["jql"] == "project = PROJ AND status = Done"

    def test_multiple_params(self):
        resource, action, params = parse_atlassian_args("issues create --project PROJ --summary Fix --type Bug")
        assert resource == "issues"
        assert action == "create"
        assert params["project"] == "PROJ"
        assert params["summary"] == "Fix"
        assert params["type"] == "Bug"

    def test_missing_resource_action(self):
        with pytest.raises(ValueError, match="Expected"):
            parse_atlassian_args("issues")

    def test_empty_input(self):
        with pytest.raises(ValueError, match="Expected"):
            parse_atlassian_args("")

    def test_case_insensitive_resource_action(self):
        resource, action, _ = parse_atlassian_args("Issues Search")
        assert resource == "issues"
        assert action == "search"


class TestRequire:
    def test_all_present(self):
        _require({"key": "PROJ-1", "status": "Done"}, "key", "status")

    def test_missing_param(self):
        with pytest.raises(ValueError, match="--key"):
            _require({}, "key")

    def test_missing_one_of_many(self):
        with pytest.raises(ValueError, match="--status"):
            _require({"key": "PROJ-1"}, "key", "status")


class TestJiraService:
    @patch("koda.services.atlassian_client.Jira" if False else "atlassian.Jira")
    def _make_service(self, mock_jira_cls=None):
        """Helper to create JiraService with mocked Jira client."""
        mock_client = MagicMock()
        mock_jira_cls.return_value = mock_client
        with (
            patch("koda.services.atlassian_client.JIRA_URL", "https://test.atlassian.net"),
            patch("koda.services.atlassian_client.JIRA_USERNAME", "test@test.com"),
            patch("koda.services.atlassian_client.JIRA_API_TOKEN", "token"),
            patch("koda.services.atlassian_client.JIRA_CLOUD", True),
        ):
            service = JiraService()
        return service, mock_client

    @pytest.mark.asyncio
    async def test_unknown_resource(self):
        with patch("atlassian.Jira"):
            with (
                patch("koda.services.atlassian_client.JIRA_URL", "https://test.atlassian.net"),
                patch("koda.services.atlassian_client.JIRA_USERNAME", "test@test.com"),
                patch("koda.services.atlassian_client.JIRA_API_TOKEN", "token"),
                patch("koda.services.atlassian_client.JIRA_CLOUD", True),
            ):
                service = JiraService()
            result = await service.execute("unknown", "action", {})
        assert "Unknown command" in result

    def test_service_falls_back_to_legacy_config_when_broker_is_unavailable(self):
        with (
            patch(
                "koda.services.core_connection_broker.get_core_connection_broker",
                side_effect=RuntimeError("offline"),
            ),
            patch("atlassian.Jira") as mock_cls,
            patch("koda.services.atlassian_client.JIRA_URL", "https://test.atlassian.net"),
            patch("koda.services.atlassian_client.JIRA_USERNAME", "test@test.com"),
            patch("koda.services.atlassian_client.JIRA_API_TOKEN", "token"),
            patch("koda.services.atlassian_client.JIRA_CLOUD", True),
        ):
            JiraService()

        mock_cls.assert_called_once_with(
            api_version="3",
            url="https://test.atlassian.net",
            username="test@test.com",
            password="token",
            cloud=True,
        )

    @pytest.mark.asyncio
    async def test_issues_search(self):
        with patch("atlassian.Jira") as mock_cls:
            mock_client = MagicMock()
            mock_cls.return_value = mock_client
            mock_client.jql.return_value = {"issues": [{"key": "PROJ-1"}]}
            with (
                patch("koda.services.atlassian_client.JIRA_URL", "https://test.atlassian.net"),
                patch("koda.services.atlassian_client.JIRA_USERNAME", "test@test.com"),
                patch("koda.services.atlassian_client.JIRA_API_TOKEN", "token"),
                patch("koda.services.atlassian_client.JIRA_CLOUD", True),
            ):
                service = JiraService()
            result = await service.execute("issues", "search", {"jql": "project = PROJ"})
        assert "Exit 0:" in result
        assert "PROJ-1" in result
        mock_client.jql.assert_called_once_with("project = PROJ", limit=20, fields=_SEARCH_FIELDS)

    @pytest.mark.asyncio
    async def test_issues_get(self):
        with patch("atlassian.Jira") as mock_cls:
            mock_client = MagicMock()
            mock_cls.return_value = mock_client
            mock_client.issue.return_value = {"key": "PROJ-123", "fields": {"summary": "Test"}}
            with (
                patch("koda.services.atlassian_client.JIRA_URL", "https://test.atlassian.net"),
                patch("koda.services.atlassian_client.JIRA_USERNAME", "test@test.com"),
                patch("koda.services.atlassian_client.JIRA_API_TOKEN", "token"),
                patch("koda.services.atlassian_client.JIRA_CLOUD", True),
            ):
                service = JiraService()
            result = await service.execute("issues", "get", {"key": "PROJ-123"})
        assert "PROJ-123" in result
        mock_client.issue.assert_called_once_with("PROJ-123")

    @pytest.mark.asyncio
    async def test_issues_create(self):
        with patch("atlassian.Jira") as mock_cls:
            mock_client = MagicMock()
            mock_cls.return_value = mock_client
            mock_client.issue_create.return_value = {"key": "PROJ-124"}
            with (
                patch("koda.services.atlassian_client.JIRA_URL", "https://test.atlassian.net"),
                patch("koda.services.atlassian_client.JIRA_USERNAME", "test@test.com"),
                patch("koda.services.atlassian_client.JIRA_API_TOKEN", "token"),
                patch("koda.services.atlassian_client.JIRA_CLOUD", True),
            ):
                service = JiraService()
            result = await service.execute(
                "issues",
                "create",
                {
                    "project": "PROJ",
                    "summary": "New issue",
                    "type": "Bug",
                },
            )
        assert "PROJ-124" in result
        mock_client.issue_create.assert_called_once()

    @pytest.mark.asyncio
    async def test_api_error_handling(self):
        with patch("atlassian.Jira") as mock_cls:
            mock_client = MagicMock()
            mock_cls.return_value = mock_client
            mock_client.jql.side_effect = Exception("API connection failed")
            with (
                patch("koda.services.atlassian_client.JIRA_URL", "https://test.atlassian.net"),
                patch("koda.services.atlassian_client.JIRA_USERNAME", "test@test.com"),
                patch("koda.services.atlassian_client.JIRA_API_TOKEN", "token"),
                patch("koda.services.atlassian_client.JIRA_CLOUD", True),
            ):
                service = JiraService()
            result = await service.execute("issues", "search", {"jql": "project = X"})
        assert "Exit 1:" in result
        assert "API connection failed" in result

    @pytest.mark.asyncio
    async def test_output_truncation(self):
        with patch("atlassian.Jira") as mock_cls:
            mock_client = MagicMock()
            mock_cls.return_value = mock_client
            mock_client.jql.return_value = {"data": "x" * 9000}
            with (
                patch("koda.services.atlassian_client.JIRA_URL", "https://test.atlassian.net"),
                patch("koda.services.atlassian_client.JIRA_USERNAME", "test@test.com"),
                patch("koda.services.atlassian_client.JIRA_API_TOKEN", "token"),
                patch("koda.services.atlassian_client.JIRA_CLOUD", True),
            ):
                service = JiraService()
            result = await service.execute("issues", "search", {"jql": ""})
        assert "truncated" in result

    @pytest.mark.asyncio
    async def test_missing_required_param(self):
        with patch("atlassian.Jira") as mock_cls:
            mock_cls.return_value = MagicMock()
            with (
                patch("koda.services.atlassian_client.JIRA_URL", "https://test.atlassian.net"),
                patch("koda.services.atlassian_client.JIRA_USERNAME", "test@test.com"),
                patch("koda.services.atlassian_client.JIRA_API_TOKEN", "token"),
                patch("koda.services.atlassian_client.JIRA_CLOUD", True),
            ):
                service = JiraService()
            result = await service.execute("issues", "get", {})
        assert "Exit 1:" in result
        assert "Missing required parameter: --key" in result

    @pytest.mark.asyncio
    async def test_issues_analyze(self):
        with patch("atlassian.Jira") as mock_cls:
            mock_client = MagicMock()
            mock_cls.return_value = mock_client
            mock_client.issue.return_value = {
                "key": "PROJ-123",
                "fields": {
                    "summary": "Fix login bug",
                    "status": {"name": "In Progress"},
                    "issuetype": {"name": "Bug"},
                    "priority": {"name": "High"},
                    "assignee": {"displayName": "João Silva"},
                    "reporter": {"displayName": "Maria Santos"},
                    "created": "2025-01-15T10:00:00.000+0000",
                    "updated": "2025-03-10T14:00:00.000+0000",
                    "labels": ["backend", "urgent"],
                    "description": {
                        "type": "doc",
                        "content": [
                            {"type": "paragraph", "content": [{"type": "text", "text": "Login fails on mobile"}]},
                        ],
                    },
                    "attachment": [
                        {
                            "filename": "screenshot.png",
                            "size": 245000,
                            "mimeType": "image/png",
                            "author": {"displayName": "João Silva"},
                            "created": "2025-03-01T10:00:00.000+0000",
                        },
                    ],
                    "issuelinks": [],
                    "components": [{"name": "API"}],
                },
            }
            mock_client.issue_get_comments.return_value = {
                "comments": [
                    {
                        "author": {"displayName": "João Silva"},
                        "created": "2025-03-01T12:00:00.000+0000",
                        "body": {
                            "type": "doc",
                            "content": [
                                {"type": "paragraph", "content": [{"type": "text", "text": "Looking into this"}]},
                            ],
                        },
                    },
                ],
            }
            mock_client.get_issue_remote_links.return_value = []
            with (
                patch("koda.services.atlassian_client.JIRA_URL", "https://test.atlassian.net"),
                patch("koda.services.atlassian_client.JIRA_USERNAME", "test@test.com"),
                patch("koda.services.atlassian_client.JIRA_API_TOKEN", "token"),
                patch("koda.services.atlassian_client.JIRA_CLOUD", True),
            ):
                service = JiraService()
            result = await service.execute("issues", "analyze", {"key": "PROJ-123"})
        assert "Exit 0:" in result
        assert "PROJ-123" in result
        assert "Fix login bug" in result
        assert "In Progress" in result
        assert "João Silva" in result
        assert "Login fails on mobile" in result
        assert "screenshot.png" in result
        assert "Comments (1)" in result

    @pytest.mark.asyncio
    async def test_issues_attachments(self):
        with patch("atlassian.Jira") as mock_cls:
            mock_client = MagicMock()
            mock_cls.return_value = mock_client
            mock_client.issue.return_value = {
                "key": "PROJ-123",
                "fields": {
                    "attachment": [
                        {
                            "filename": "doc.pdf",
                            "size": 1200000,
                            "mimeType": "application/pdf",
                            "author": {"displayName": "Maria"},
                            "created": "2025-02-15T10:00:00.000+0000",
                            "id": "10001",
                        },
                    ],
                },
            }
            with (
                patch("koda.services.atlassian_client.JIRA_URL", "https://test.atlassian.net"),
                patch("koda.services.atlassian_client.JIRA_USERNAME", "test@test.com"),
                patch("koda.services.atlassian_client.JIRA_API_TOKEN", "token"),
                patch("koda.services.atlassian_client.JIRA_CLOUD", True),
            ):
                service = JiraService()
            result = await service.execute("issues", "attachments", {"key": "PROJ-123"})
        assert "Exit 0:" in result
        assert "doc.pdf" in result
        assert "Maria" in result

    @pytest.mark.asyncio
    async def test_issues_links(self):
        with patch("atlassian.Jira") as mock_cls:
            mock_client = MagicMock()
            mock_cls.return_value = mock_client
            mock_client.issue.return_value = {
                "key": "PROJ-123",
                "fields": {
                    "issuelinks": [
                        {
                            "type": {"name": "Blocks", "outward": "blocks", "inward": "is blocked by"},
                            "outwardIssue": {
                                "key": "PROJ-456",
                                "fields": {
                                    "summary": "API timeout",
                                    "status": {"name": "Done"},
                                },
                            },
                        },
                    ],
                },
            }
            mock_client.get_issue_remote_links.return_value = [
                {
                    "object": {
                        "url": "https://github.com/org/repo/issues/42",
                        "title": "GitHub Issue #42",
                    },
                },
            ]
            with (
                patch("koda.services.atlassian_client.JIRA_URL", "https://test.atlassian.net"),
                patch("koda.services.atlassian_client.JIRA_USERNAME", "test@test.com"),
                patch("koda.services.atlassian_client.JIRA_API_TOKEN", "token"),
                patch("koda.services.atlassian_client.JIRA_CLOUD", True),
            ):
                service = JiraService()
            result = await service.execute("issues", "links", {"key": "PROJ-123"})
        assert "Exit 0:" in result
        assert "PROJ-456" in result
        assert "GitHub Issue #42" in result

    @pytest.mark.asyncio
    async def test_analyze_output_limit(self):
        """Verify analyze uses the higher MAX_ANALYZE_OUTPUT limit."""
        with patch("atlassian.Jira") as mock_cls:
            mock_client = MagicMock()
            mock_cls.return_value = mock_client
            # Create issue with very long description
            mock_client.issue.return_value = {
                "key": "PROJ-123",
                "fields": {
                    "summary": "Test",
                    "description": {
                        "type": "doc",
                        "content": [
                            {"type": "paragraph", "content": [{"type": "text", "text": "x" * 12000}]},
                        ],
                    },
                    "issuelinks": [],
                    "attachment": [],
                },
            }
            mock_client.issue_get_comments.return_value = {"comments": []}
            mock_client.get_issue_remote_links.return_value = []
            with (
                patch("koda.services.atlassian_client.JIRA_URL", "https://test.atlassian.net"),
                patch("koda.services.atlassian_client.JIRA_USERNAME", "test@test.com"),
                patch("koda.services.atlassian_client.JIRA_API_TOKEN", "token"),
                patch("koda.services.atlassian_client.JIRA_CLOUD", True),
            ):
                service = JiraService()
            result = await service.execute("issues", "analyze", {"key": "PROJ-123"})
        # Should NOT be truncated at 8000 — the output is ~12000+ chars
        assert len(result) > 8000
        assert "truncated" not in result


class TestFormatIssueAnalysis:
    def test_basic_structure(self):
        issue = {
            "key": "PROJ-1",
            "fields": {
                "summary": "Test issue",
                "status": {"name": "Open"},
                "issuetype": {"name": "Task"},
                "priority": {"name": "Medium"},
                "assignee": {"displayName": "Dev"},
                "reporter": {"displayName": "PM"},
                "created": "2025-01-01T00:00:00.000+0000",
                "updated": "2025-01-02T00:00:00.000+0000",
                "labels": ["test"],
                "description": None,
                "issuelinks": [],
                "attachment": [],
            },
        }
        result = _format_issue_analysis(issue, {"comments": []}, [])
        assert "## PROJ-1: Test issue" in result
        assert "**Status:** Open" in result
        assert "**Type:** Task" in result
        assert "(no description)" in result

    @pytest.mark.asyncio
    async def test_issues_analyze_remote_links_failure(self):
        """When get_issue_remote_links fails, analyze should still return valid output."""
        with patch("atlassian.Jira") as mock_cls:
            mock_client = MagicMock()
            mock_cls.return_value = mock_client
            mock_client.issue.return_value = {
                "key": "PROJ-1",
                "fields": {
                    "summary": "Test",
                    "description": None,
                    "issuelinks": [],
                    "attachment": [],
                },
            }
            mock_client.issue_get_comments.return_value = {"comments": []}
            mock_client.get_issue_remote_links.side_effect = Exception("API error")
            with (
                patch("koda.services.atlassian_client.JIRA_URL", "https://test.atlassian.net"),
                patch("koda.services.atlassian_client.JIRA_USERNAME", "test@test.com"),
                patch("koda.services.atlassian_client.JIRA_API_TOKEN", "token"),
                patch("koda.services.atlassian_client.JIRA_CLOUD", True),
            ):
                service = JiraService()
            result = await service.execute("issues", "analyze", {"key": "PROJ-1"})
        assert "Exit 0:" in result
        assert "PROJ-1" in result

    @pytest.mark.asyncio
    async def test_issues_links_remote_links_failure(self):
        """When get_issue_remote_links fails, links should still return valid output."""
        with patch("atlassian.Jira") as mock_cls:
            mock_client = MagicMock()
            mock_cls.return_value = mock_client
            mock_client.issue.return_value = {
                "key": "PROJ-1",
                "fields": {"issuelinks": []},
            }
            mock_client.get_issue_remote_links.side_effect = Exception("API error")
            with (
                patch("koda.services.atlassian_client.JIRA_URL", "https://test.atlassian.net"),
                patch("koda.services.atlassian_client.JIRA_USERNAME", "test@test.com"),
                patch("koda.services.atlassian_client.JIRA_API_TOKEN", "token"),
                patch("koda.services.atlassian_client.JIRA_CLOUD", True),
            ):
                service = JiraService()
            result = await service.execute("issues", "links", {"key": "PROJ-1"})
        assert "Exit 0:" in result


class TestFormatSize:
    def test_bytes(self):
        assert _format_size(500) == "500 B"

    def test_kilobytes(self):
        assert _format_size(1024) == "1 KB"
        assert _format_size(2048) == "2 KB"

    def test_megabytes(self):
        assert _format_size(1024 * 1024) == "1.0 MB"
        assert _format_size(1536 * 1024) == "1.5 MB"

    def test_zero(self):
        assert _format_size(0) == "0 B"


class TestFormatLinks:
    def test_outward_link(self):
        result = _format_links(
            [
                {
                    "type": {"name": "Blocks", "outward": "blocks"},
                    "outwardIssue": {"key": "X-1", "fields": {"summary": "S", "status": {"name": "Done"}}},
                }
            ],
            [],
        )
        assert len(result) == 1
        assert result[0]["direction"] == "outward"
        assert result[0]["key"] == "X-1"

    def test_inward_link(self):
        result = _format_links(
            [
                {
                    "type": {"name": "Blocks", "inward": "is blocked by"},
                    "inwardIssue": {"key": "X-2", "fields": {"summary": "S", "status": {"name": "Open"}}},
                }
            ],
            [],
        )
        assert len(result) == 1
        assert result[0]["direction"] == "inward"

    def test_remote_link(self):
        result = _format_links(
            [],
            [{"object": {"url": "https://github.com/x", "title": "GH"}}],
        )
        assert len(result) == 1
        assert result[0]["direction"] == "remote"
        assert result[0]["url"] == "https://github.com/x"

    def test_empty(self):
        assert _format_links([], []) == []

    def test_missing_fields(self):
        result = _format_links(
            [{"type": {}, "outwardIssue": {"key": "X-1", "fields": {}}}],
            [],
        )
        assert len(result) == 1
        assert result[0]["key"] == "X-1"


class TestJiraAdfAndTransitions:
    """Tests for ADF comment/description and transition fixes."""

    def _make_service(self):
        with patch("atlassian.Jira") as mock_cls:
            mock_client = MagicMock()
            mock_cls.return_value = mock_client
            with (
                patch("koda.services.atlassian_client.JIRA_URL", "https://test.atlassian.net"),
                patch("koda.services.atlassian_client.JIRA_USERNAME", "test@test.com"),
                patch("koda.services.atlassian_client.JIRA_API_TOKEN", "token"),
                patch("koda.services.atlassian_client.JIRA_CLOUD", True),
            ):
                service = JiraService()
        return service, mock_client

    @pytest.mark.asyncio
    async def test_issues_comment_sends_adf(self):
        service, mock_client = self._make_service()
        mock_client.issue_add_comment.return_value = {
            "id": "100",
            "author": {"displayName": "Agent", "accountId": "agent-123"},
            "body": {"type": "doc", "version": 1, "content": []},
        }
        mock_client.resource_url.side_effect = lambda resource: f"rest/api/3/{resource}"
        mock_client.get_comment_property.return_value = {
            "mode": "comment",
            "issue_key": "PROJ-1",
        }
        await service.execute("issues", "comment", {"key": "PROJ-1", "body": "Test comment"})
        args = mock_client.issue_add_comment.call_args
        adf_body = args[0][1]
        assert isinstance(adf_body, dict)
        assert adf_body["type"] == "doc"
        assert adf_body["version"] == 1
        mock_client.put.assert_called_once()
        path = mock_client.put.call_args.args[0]
        metadata = mock_client.put.call_args.kwargs["data"]
        assert path == f"rest/api/3/comment/100/properties/{COMMENT_META_PROPERTY_KEY}"
        assert metadata["mode"] == "comment"
        assert metadata["issue_key"] == "PROJ-1"

    @pytest.mark.asyncio
    async def test_issues_comment_with_mention(self):
        service, mock_client = self._make_service()
        mock_client.issue_add_comment.return_value = {
            "id": "101",
            "author": {"displayName": "Agent", "accountId": "agent-123"},
            "body": {"type": "doc", "version": 1, "content": []},
        }
        mock_client.resource_url.side_effect = lambda resource: f"rest/api/3/{resource}"
        mock_client.get_comment_property.return_value = {"mode": "comment"}
        await service.execute(
            "issues",
            "comment",
            {
                "key": "PROJ-1",
                "body": "Hello [~accountId:abc123]",
            },
        )
        adf_body = mock_client.issue_add_comment.call_args[0][1]
        nodes = adf_body["content"][0]["content"]
        assert any(n["type"] == "mention" and n["attrs"]["id"] == "abc123" for n in nodes)

    @pytest.mark.asyncio
    async def test_comment_get_returns_single_comment(self):
        service, mock_client = self._make_service()
        mock_client.issue_get_comment.return_value = {
            "id": "100",
            "author": {"displayName": "Agent", "accountId": "agent-123"},
            "created": "2026-03-18T10:00:00.000+0000",
            "body": {
                "type": "doc",
                "version": 1,
                "content": [
                    {"type": "paragraph", "content": [{"type": "text", "text": "Single comment"}]},
                ],
            },
        }
        mock_client.get_comment_property.return_value = {"mode": "comment"}

        result = await service.execute("issues", "comment_get", {"key": "PROJ-1", "comment-id": "100"})

        assert "Exit 0:" in result
        assert "Single comment" in result
        assert '"comment_meta_status": "present"' in result
        mock_client.issue_get_comment.assert_called_once_with("PROJ-1", "100")

    @pytest.mark.asyncio
    async def test_comment_edit_owned_comment(self):
        service, mock_client = self._make_service()
        mock_client.myself.return_value = {"accountId": "agent-123"}
        mock_client.issue_get_comment.return_value = {
            "id": "100",
            "author": {"displayName": "Agent", "accountId": "agent-123"},
            "body": {"type": "doc", "version": 1, "content": []},
        }
        mock_client.issue_edit_comment.return_value = {
            "id": "100",
            "author": {"displayName": "Agent", "accountId": "agent-123"},
            "body": {
                "type": "doc",
                "version": 1,
                "content": [
                    {"type": "paragraph", "content": [{"type": "text", "text": "Updated comment"}]},
                ],
            },
        }
        mock_client.get_comment_property.return_value = {
            "value": {
                "mode": "reply_linked",
                "reply_to_comment_id": "55",
                "created_at": "2026-03-18T09:00:00+00:00",
            }
        }
        mock_client.resource_url.side_effect = lambda resource: f"rest/api/3/{resource}"

        result = await service.execute(
            "issues",
            "comment_edit",
            {"key": "PROJ-1", "comment-id": "100", "body": "Updated comment"},
        )

        assert "Exit 0:" in result
        assert "Updated comment" in result
        mock_client.issue_edit_comment.assert_called_once()
        metadata = mock_client.put.call_args.kwargs["data"]
        assert metadata["mode"] == "reply_linked"
        assert metadata["reply_to_comment_id"] == "55"
        assert metadata["created_at"] == "2026-03-18T09:00:00+00:00"
        assert "updated_at" in metadata

    @pytest.mark.asyncio
    async def test_comment_edit_blocks_when_metadata_shape_is_invalid(self):
        service, mock_client = self._make_service()
        mock_client.myself.return_value = {"accountId": "agent-123"}
        mock_client.issue_get_comment.return_value = {
            "id": "100",
            "author": {"displayName": "Agent", "accountId": "agent-123"},
            "body": {"type": "doc", "version": 1, "content": []},
        }
        mock_client.get_comment_property.return_value = {"unexpected": "shape"}

        result = await service.execute(
            "issues",
            "comment_edit",
            {"key": "PROJ-1", "comment-id": "100", "body": "Should stay blocked"},
        )

        assert "unable to safely verify the existing Jira comment metadata" in result
        mock_client.issue_edit_comment.assert_not_called()

    @pytest.mark.asyncio
    async def test_comment_edit_refuses_non_owned_comment(self):
        service, mock_client = self._make_service()
        mock_client.myself.return_value = {"accountId": "agent-123"}
        mock_client.issue_get_comment.return_value = {
            "id": "100",
            "author": {"displayName": "Someone Else", "accountId": "other-999"},
            "body": {"type": "doc", "version": 1, "content": []},
        }

        with patch("koda.services.audit.emit_security") as mock_emit_security:
            result = await service.execute(
                "issues",
                "comment_edit",
                {"key": "PROJ-1", "comment-id": "100", "body": "Should not work"},
            )

        assert "Blocked:" in result
        mock_client.issue_edit_comment.assert_not_called()
        mock_emit_security.assert_called_once()

    @pytest.mark.asyncio
    async def test_comment_delete_owned_comment(self):
        service, mock_client = self._make_service()
        mock_client.myself.return_value = {"accountId": "agent-123"}
        mock_client.issue_get_comment.return_value = {
            "id": "100",
            "author": {"displayName": "Agent", "accountId": "agent-123"},
            "body": {"type": "doc", "version": 1, "content": []},
        }
        mock_client.resource_url.return_value = "rest/api/3/issue"

        result = await service.execute("issues", "comment_delete", {"key": "PROJ-1", "comment-id": "100"})

        assert '"deleted": true' in result.lower()
        mock_client.delete.assert_called_once_with("rest/api/3/issue/PROJ-1/comment/100")

    @pytest.mark.asyncio
    async def test_comment_delete_refuses_non_owned_comment(self):
        service, mock_client = self._make_service()
        mock_client.myself.return_value = {"accountId": "agent-123"}
        mock_client.issue_get_comment.return_value = {
            "id": "100",
            "author": {"displayName": "Someone Else", "accountId": "other-999"},
            "body": {"type": "doc", "version": 1, "content": []},
        }

        with patch("koda.services.audit.emit_security") as mock_emit_security:
            result = await service.execute("issues", "comment_delete", {"key": "PROJ-1", "comment-id": "100"})

        assert "Blocked:" in result
        mock_client.delete.assert_not_called()
        mock_emit_security.assert_called_once()

    @pytest.mark.asyncio
    async def test_comment_reply_creates_linked_reply_and_tags_metadata(self):
        service, mock_client = self._make_service()
        mock_client.issue_get_comment.return_value = {
            "id": "100",
            "author": {"displayName": "Reviewer", "accountId": "reviewer-1"},
            "body": {
                "type": "doc",
                "version": 1,
                "content": [
                    {
                        "type": "paragraph",
                        "content": [{"type": "text", "text": "Can you confirm the rollout window?"}],
                    },
                ],
            },
        }
        mock_client.issue_add_comment.return_value = {
            "id": "200",
            "author": {"displayName": "Agent", "accountId": "agent-123"},
            "body": {"type": "doc", "version": 1, "content": []},
        }
        mock_client.resource_url.side_effect = lambda resource: f"rest/api/3/{resource}"
        mock_client.get_comment_property.return_value = {
            "mode": "reply_linked",
            "reply_to_comment_id": "100",
        }

        result = await service.execute(
            "issues",
            "comment_reply",
            {"key": "PROJ-1", "comment-id": "100", "body": "Yes, rollout starts at 15:00."},
        )

        assert "Exit 0:" in result
        reply_body = mock_client.issue_add_comment.call_args[0][1]
        assert "Replying to comment #100 by Reviewer" in render_adf(reply_body)
        assert "Original excerpt:" in render_adf(reply_body)
        assert "Yes, rollout starts at 15:00." in render_adf(reply_body)
        path = mock_client.put.call_args.args[0]
        metadata = mock_client.put.call_args.kwargs["data"]
        assert path == f"rest/api/3/comment/200/properties/{COMMENT_META_PROPERTY_KEY}"
        assert metadata["mode"] == "reply_linked"
        assert metadata["reply_to_comment_id"] == "100"
        assert "Can you confirm the rollout window?" in result

    @pytest.mark.asyncio
    async def test_comment_create_rolls_back_when_metadata_attach_fails(self):
        service, mock_client = self._make_service()
        mock_client.issue_add_comment.return_value = {
            "id": "100",
            "author": {"displayName": "Agent", "accountId": "agent-123"},
            "body": {"type": "doc", "version": 1, "content": []},
        }
        mock_client.resource_url.side_effect = lambda resource: f"rest/api/3/{resource}"
        mock_client.put.side_effect = RuntimeError("metadata failed")

        result = await service.execute("issues", "comment", {"key": "PROJ-1", "body": "Test comment"})

        assert "rolled back for safety" in result
        mock_client.delete.assert_called_once_with("rest/api/3/issue/PROJ-1/comment/100")

    @pytest.mark.asyncio
    async def test_comment_reply_rolls_back_when_metadata_attach_fails(self):
        service, mock_client = self._make_service()
        mock_client.issue_get_comment.return_value = {
            "id": "100",
            "author": {"displayName": "Reviewer", "accountId": "reviewer-1"},
            "body": {"type": "doc", "version": 1, "content": []},
        }
        mock_client.issue_add_comment.return_value = {
            "id": "200",
            "author": {"displayName": "Agent", "accountId": "agent-123"},
            "body": {"type": "doc", "version": 1, "content": []},
        }
        mock_client.resource_url.side_effect = lambda resource: f"rest/api/3/{resource}"
        mock_client.put.side_effect = RuntimeError("metadata failed")

        result = await service.execute(
            "issues",
            "comment_reply",
            {"key": "PROJ-1", "comment-id": "100", "body": "Reply body"},
        )

        assert "linked reply was rolled back for safety" in result
        mock_client.delete.assert_called_once_with("rest/api/3/issue/PROJ-1/comment/200")

    @pytest.mark.asyncio
    async def test_comment_edit_rolls_back_when_metadata_attach_fails(self):
        service, mock_client = self._make_service()
        original_body = {"type": "doc", "version": 1, "content": []}
        mock_client.myself.return_value = {"accountId": "agent-123"}
        mock_client.issue_get_comment.return_value = {
            "id": "100",
            "author": {"displayName": "Agent", "accountId": "agent-123"},
            "body": original_body,
        }
        mock_client.get_comment_property.return_value = {"mode": "reply_linked", "reply_to_comment_id": "55"}
        mock_client.issue_edit_comment.side_effect = [
            {
                "id": "100",
                "author": {"displayName": "Agent", "accountId": "agent-123"},
                "body": {"type": "doc", "version": 1, "content": []},
            },
            {
                "id": "100",
                "author": {"displayName": "Agent", "accountId": "agent-123"},
                "body": original_body,
            },
        ]
        mock_client.resource_url.side_effect = lambda resource: f"rest/api/3/{resource}"
        mock_client.put.side_effect = RuntimeError("metadata failed")

        result = await service.execute(
            "issues",
            "comment_edit",
            {"key": "PROJ-1", "comment-id": "100", "body": "Updated comment"},
        )

        assert "edit was rolled back for safety" in result
        assert mock_client.issue_edit_comment.call_count == 2
        rollback_call = mock_client.issue_edit_comment.call_args_list[1]
        assert rollback_call.args == ("PROJ-1", "100", original_body)

    @pytest.mark.asyncio
    async def test_jira_identity_lookup_is_cached(self):
        service, mock_client = self._make_service()
        mock_client.myself.return_value = {"accountId": "agent-123"}
        mock_client.issue_get_comment.return_value = {
            "id": "100",
            "author": {"displayName": "Agent", "accountId": "agent-123"},
            "body": {"type": "doc", "version": 1, "content": []},
        }
        mock_client.issue_edit_comment.return_value = {
            "id": "100",
            "author": {"displayName": "Agent", "accountId": "agent-123"},
            "body": {"type": "doc", "version": 1, "content": []},
        }
        mock_client.get_comment_property.return_value = {"mode": "comment"}
        mock_client.resource_url.side_effect = lambda resource: f"rest/api/3/{resource}"

        await service.execute(
            "issues",
            "comment_edit",
            {"key": "PROJ-1", "comment-id": "100", "body": "Updated once"},
        )
        await service.execute("issues", "comment_delete", {"key": "PROJ-1", "comment-id": "100"})

        mock_client.myself.assert_called_once()

    def test_verify_identity_returns_authenticated_profile(self):
        service, mock_client = self._make_service()
        mock_client.myself.return_value = {
            "accountId": "agent-123",
            "displayName": "Agent User",
            "emailAddress": "agent@example.com",
        }

        profile = service.verify_identity()

        assert profile["accountId"] == "agent-123"
        assert profile["displayName"] == "Agent User"
        mock_client.myself.assert_called_once_with()

    @pytest.mark.asyncio
    async def test_issues_create_description_adf(self):
        service, mock_client = self._make_service()
        mock_client.issue_create.return_value = {"key": "PROJ-10"}
        await service.execute(
            "issues",
            "create",
            {
                "project": "PROJ",
                "summary": "Test",
                "description": "A description",
            },
        )
        fields = mock_client.issue_create.call_args[1]["fields"]
        desc = fields["description"]
        assert isinstance(desc, dict)
        assert desc["type"] == "doc"

    @pytest.mark.asyncio
    async def test_issues_transitions_list(self):
        service, mock_client = self._make_service()
        mock_client.get_issue_transitions.return_value = [
            {"id": "21", "name": "Start Progress", "to": {"name": "In Progress"}},
        ]
        result = await service.execute("issues", "transitions", {"key": "PROJ-1"})
        assert "Exit 0:" in result
        assert "Start Progress" in result

    @pytest.mark.asyncio
    async def test_issues_transition_by_name(self):
        service, mock_client = self._make_service()
        mock_client.get_issue_transitions.return_value = [
            {"id": "21", "name": "Start Progress", "to": {"name": "In Progress"}},
            {"id": "31", "name": "Done", "to": {"name": "Done"}},
        ]
        mock_client.set_issue_status_by_transition_id.return_value = {}
        result = await service.execute("issues", "transition", {"key": "PROJ-1", "status": "In Progress"})
        mock_client.set_issue_status_by_transition_id.assert_called_once_with("PROJ-1", "21")
        assert '"transitioned": true' in result.lower()
        assert '"issue_key": "PROJ-1"' in result
        assert '"transition_id": "21"' in result
        assert '"to_status": "In Progress"' in result

    @pytest.mark.asyncio
    async def test_issues_transition_case_insensitive(self):
        service, mock_client = self._make_service()
        mock_client.get_issue_transitions.return_value = [
            {"id": "41", "name": "Em Progresso", "to": {"name": "Em Progresso"}},
        ]
        mock_client.set_issue_status_by_transition_id.return_value = {}
        await service.execute("issues", "transition", {"key": "PROJ-1", "status": "em progresso"})
        mock_client.set_issue_status_by_transition_id.assert_called_once_with("PROJ-1", "41")

    @pytest.mark.asyncio
    async def test_issues_transition_by_numeric_id_returns_explicit_ack(self):
        service, mock_client = self._make_service()
        mock_client.get_issue_transitions.return_value = [
            {"id": "21", "name": "Start Progress", "to": {"name": "In Progress"}},
        ]
        mock_client.set_issue_status_by_transition_id.return_value = None

        result = await service.execute("issues", "transition", {"key": "PROJ-1", "status": "21"})

        mock_client.set_issue_status_by_transition_id.assert_called_once_with("PROJ-1", "21")
        assert "Exit 0:" in result
        assert "null" not in result.lower()
        assert '"transition_name": "Start Progress"' in result
        assert '"to_status": "In Progress"' in result

    @pytest.mark.asyncio
    async def test_issues_transition_no_match_shows_available(self):
        service, mock_client = self._make_service()
        mock_client.get_issue_transitions.return_value = [
            {"id": "21", "name": "Start Progress", "to": {"name": "In Progress"}},
            {"id": "31", "name": "Resolve", "to": {"name": "Done"}},
        ]
        result = await service.execute("issues", "transition", {"key": "PROJ-1", "status": "Invalid"})
        assert "Exit 1:" in result
        assert "No transition matching" in result
        assert "Start Progress" in result
        assert "Resolve" in result

    @pytest.mark.asyncio
    async def test_issues_transition_by_numeric_id(self):
        service, mock_client = self._make_service()
        mock_client.get_issue_transitions.return_value = [
            {"id": "21", "name": "Start Progress", "to": {"name": "In Progress"}},
        ]
        mock_client.set_issue_status_by_transition_id.return_value = {}
        await service.execute("issues", "transition", {"key": "PROJ-1", "status": "21"})
        mock_client.set_issue_status_by_transition_id.assert_called_once_with("PROJ-1", "21")

    @pytest.mark.asyncio
    async def test_issues_transition_invalid_numeric_id(self):
        service, mock_client = self._make_service()
        mock_client.get_issue_transitions.return_value = [
            {"id": "21", "name": "Start Progress", "to": {"name": "In Progress"}},
        ]
        result = await service.execute("issues", "transition", {"key": "PROJ-1", "status": "999"})
        assert "Exit 1:" in result
        assert "No transition matching" in result
        assert "Start Progress" in result

    @pytest.mark.asyncio
    async def test_issues_delete_returns_explicit_ack(self):
        service, mock_client = self._make_service()
        mock_client.issue_delete.return_value = None

        result = await service.execute("issues", "delete", {"key": "PROJ-1"})

        mock_client.issue_delete.assert_called_once_with("PROJ-1")
        assert "Exit 0:" in result
        assert '"deleted": true' in result.lower()
        assert '"issue_key": "PROJ-1"' in result

    @pytest.mark.asyncio
    async def test_issues_assign_returns_explicit_ack(self):
        service, mock_client = self._make_service()
        mock_client.assign_issue.return_value = None

        result = await service.execute("issues", "assign", {"key": "PROJ-1", "account-id": "acct-123"})

        mock_client.assign_issue.assert_called_once_with("PROJ-1", "acct-123")
        assert "Exit 0:" in result
        assert '"assigned": true' in result.lower()
        assert '"account_id": "acct-123"' in result

    @pytest.mark.asyncio
    async def test_issues_link_returns_explicit_ack(self):
        service, mock_client = self._make_service()
        mock_client.create_issue_link.return_value = None

        result = await service.execute(
            "issues",
            "link",
            {"type": "Blocks", "inward": "PROJ-1", "outward": "PROJ-2"},
        )

        expected_payload = {
            "type": {"name": "Blocks"},
            "inwardIssue": {"key": "PROJ-1"},
            "outwardIssue": {"key": "PROJ-2"},
        }
        mock_client.create_issue_link.assert_called_once_with(expected_payload)
        assert "Exit 0:" in result
        assert '"linked": true' in result.lower()
        assert '"link_type": "Blocks"' in result
        assert '"outward_issue_key": "PROJ-2"' in result


class TestIssuesViewVideo:
    """Tests for the issues view_video handler."""

    def _make_service(self):
        """Helper to create JiraService with mocked Jira client."""
        with patch("atlassian.Jira") as mock_cls:
            mock_client = MagicMock()
            mock_cls.return_value = mock_client
            with (
                patch("koda.services.atlassian_client.JIRA_URL", "https://test.atlassian.net"),
                patch("koda.services.atlassian_client.JIRA_USERNAME", "test@test.com"),
                patch("koda.services.atlassian_client.JIRA_API_TOKEN", "token"),
                patch("koda.services.atlassian_client.JIRA_CLOUD", True),
            ):
                service = JiraService()
        return service, mock_client

    @pytest.mark.asyncio
    async def test_issues_view_video(self):
        service, mock_client = self._make_service()
        mock_client.issue.return_value = {
            "key": "PROJ-123",
            "fields": {
                "attachment": [
                    {
                        "id": "10001",
                        "filename": "bug_repro.mp4",
                        "mimeType": "video/mp4",
                        "size": 5000000,
                        "content": "https://test.atlassian.net/attachment/10001",
                    },
                ],
            },
        }
        mock_response = MagicMock()
        mock_response.content = b"fake video data"
        mock_client._session.get.return_value = mock_response

        with patch(
            "koda.utils.video.process_video_attachment",
            return_value=(["/tmp/frame_001.jpg"], "Extracted 1 frames from 'bug_repro.mp4'"),
        ):
            result = await service.execute(
                "issues",
                "view_video",
                {
                    "key": "PROJ-123",
                    "attachment-id": "10001",
                },
            )
        assert "Video Analysis" in result
        assert "bug_repro.mp4" in result

    @pytest.mark.asyncio
    async def test_issues_view_video_not_video(self):
        service, mock_client = self._make_service()
        mock_client.issue.return_value = {
            "key": "PROJ-123",
            "fields": {
                "attachment": [
                    {
                        "id": "10002",
                        "filename": "doc.pdf",
                        "mimeType": "application/pdf",
                        "size": 1000,
                    },
                ],
            },
        }
        result = await service.execute(
            "issues",
            "view_video",
            {
                "key": "PROJ-123",
                "attachment-id": "10002",
            },
        )
        assert "not a video" in result

    @pytest.mark.asyncio
    async def test_issues_view_video_not_found(self):
        service, mock_client = self._make_service()
        mock_client.issue.return_value = {
            "key": "PROJ-123",
            "fields": {"attachment": []},
        }
        result = await service.execute(
            "issues",
            "view_video",
            {
                "key": "PROJ-123",
                "attachment-id": "99999",
            },
        )
        assert "not found" in result

    @pytest.mark.asyncio
    async def test_issues_view_video_too_large(self):
        service, mock_client = self._make_service()
        mock_client.issue.return_value = {
            "key": "PROJ-123",
            "fields": {
                "attachment": [
                    {
                        "id": "10003",
                        "filename": "huge.mp4",
                        "mimeType": "video/mp4",
                        "size": 100 * 1024 * 1024,  # 100 MB
                    },
                ],
            },
        }
        result = await service.execute(
            "issues",
            "view_video",
            {
                "key": "PROJ-123",
                "attachment-id": "10003",
            },
        )
        assert "too large" in result


class TestConfluenceService:
    @pytest.mark.asyncio
    async def test_pages_search(self):
        with patch("atlassian.Confluence") as mock_cls:
            mock_client = MagicMock()
            mock_cls.return_value = mock_client
            mock_client.cql.return_value = {"results": [{"title": "Test Page"}]}
            with (
                patch("koda.services.atlassian_client.CONFLUENCE_URL", "https://test.atlassian.net"),
                patch("koda.services.atlassian_client.CONFLUENCE_USERNAME", "test@test.com"),
                patch("koda.services.atlassian_client.CONFLUENCE_API_TOKEN", "token"),
            ):
                service = ConfluenceService()
            result = await service.execute("pages", "search", {"cql": "space = DEV"})
        assert "Exit 0:" in result
        assert "Test Page" in result

    @pytest.mark.asyncio
    async def test_pages_create(self):
        with patch("atlassian.Confluence") as mock_cls:
            mock_client = MagicMock()
            mock_cls.return_value = mock_client
            mock_client.create_page.return_value = {"id": "12345", "title": "New Page"}
            with (
                patch("koda.services.atlassian_client.CONFLUENCE_URL", "https://test.atlassian.net"),
                patch("koda.services.atlassian_client.CONFLUENCE_USERNAME", "test@test.com"),
                patch("koda.services.atlassian_client.CONFLUENCE_API_TOKEN", "token"),
            ):
                service = ConfluenceService()
            result = await service.execute(
                "pages",
                "create",
                {
                    "space": "DEV",
                    "title": "New Page",
                    "body": "<p>Content</p>",
                },
            )
        assert "New Page" in result
        mock_client.create_page.assert_called_once()

    @pytest.mark.asyncio
    async def test_spaces_list(self):
        with patch("atlassian.Confluence") as mock_cls:
            mock_client = MagicMock()
            mock_cls.return_value = mock_client
            mock_client.get_all_spaces.return_value = {"results": [{"key": "DEV"}]}
            with (
                patch("koda.services.atlassian_client.CONFLUENCE_URL", "https://test.atlassian.net"),
                patch("koda.services.atlassian_client.CONFLUENCE_USERNAME", "test@test.com"),
                patch("koda.services.atlassian_client.CONFLUENCE_API_TOKEN", "token"),
            ):
                service = ConfluenceService()
            result = await service.execute("spaces", "list", {})
        assert "Exit 0:" in result
        assert "DEV" in result

    def test_verify_read_access_returns_first_space_summary(self):
        with patch("atlassian.Confluence") as mock_cls:
            mock_client = MagicMock()
            mock_cls.return_value = mock_client
            mock_client.get_all_spaces.return_value = {
                "results": [{"key": "DEV", "name": "Developer Docs"}],
            }
            with (
                patch("koda.services.atlassian_client.CONFLUENCE_URL", "https://wiki.example.com"),
                patch("koda.services.atlassian_client.CONFLUENCE_USERNAME", "agent@example.com"),
                patch("koda.services.atlassian_client.CONFLUENCE_API_TOKEN", "token"),
                patch("koda.services.atlassian_client.CONFLUENCE_CLOUD", True),
            ):
                service = ConfluenceService()

        probe = service.verify_read_access()

        assert probe == {
            "space_count": 1,
            "first_space_key": "DEV",
            "first_space_name": "Developer Docs",
        }
        mock_client.get_all_spaces.assert_called_once_with(start=0, limit=1)

    @pytest.mark.asyncio
    async def test_unknown_command(self):
        with patch("atlassian.Confluence") as mock_cls:
            mock_cls.return_value = MagicMock()
            with (
                patch("koda.services.atlassian_client.CONFLUENCE_URL", "https://test.atlassian.net"),
                patch("koda.services.atlassian_client.CONFLUENCE_USERNAME", "test@test.com"),
                patch("koda.services.atlassian_client.CONFLUENCE_API_TOKEN", "token"),
            ):
                service = ConfluenceService()
            result = await service.execute("unknown", "action", {})
        assert "Unknown command" in result


class TestIssuesViewImage:
    """Tests for the issues view_image handler."""

    def _make_service(self):
        with patch("atlassian.Jira") as mock_cls:
            mock_client = MagicMock()
            mock_cls.return_value = mock_client
            with (
                patch("koda.services.atlassian_client.JIRA_URL", "https://test.atlassian.net"),
                patch("koda.services.atlassian_client.JIRA_USERNAME", "test@test.com"),
                patch("koda.services.atlassian_client.JIRA_API_TOKEN", "token"),
                patch("koda.services.atlassian_client.JIRA_CLOUD", True),
            ):
                service = JiraService()
        return service, mock_client

    @pytest.mark.asyncio
    async def test_happy_path(self):
        service, mock_client = self._make_service()
        mock_client.issue.return_value = {
            "key": "PROJ-1",
            "fields": {
                "attachment": [
                    {
                        "id": "100",
                        "filename": "screenshot.png",
                        "mimeType": "image/png",
                        "size": 50000,
                        "content": "https://test.atlassian.net/attachment/100",
                    },
                ],
            },
        }
        mock_response = MagicMock()
        mock_response.content = b"fake png data"
        mock_client._session.get.return_value = mock_response

        with patch("koda.services.atlassian_client.IMAGE_TEMP_DIR") as mock_dir:
            mock_dir.mkdir = MagicMock()
            mock_dir.__truediv__ = lambda self, name: MagicMock(__str__=lambda s: f"/tmp/images/{name}")
            with patch("koda.services.atlassian_client.Path") as mock_path:
                mock_path.return_value.suffix = ".png"
                mock_path.return_value.write_bytes = MagicMock()
                result = await service.execute(
                    "issues",
                    "view_image",
                    {
                        "key": "PROJ-1",
                        "attachment-id": "100",
                    },
                )
        assert "Image:" in result
        assert "screenshot.png" in result

    @pytest.mark.asyncio
    async def test_wrong_mime(self):
        service, mock_client = self._make_service()
        mock_client.issue.return_value = {
            "key": "PROJ-1",
            "fields": {
                "attachment": [
                    {
                        "id": "101",
                        "filename": "doc.pdf",
                        "mimeType": "application/pdf",
                        "size": 1000,
                    },
                ],
            },
        }
        result = await service.execute(
            "issues",
            "view_image",
            {
                "key": "PROJ-1",
                "attachment-id": "101",
            },
        )
        assert "not an image" in result

    @pytest.mark.asyncio
    async def test_not_found(self):
        service, mock_client = self._make_service()
        mock_client.issue.return_value = {
            "key": "PROJ-1",
            "fields": {"attachment": []},
        }
        result = await service.execute(
            "issues",
            "view_image",
            {
                "key": "PROJ-1",
                "attachment-id": "999",
            },
        )
        assert "not found" in result

    @pytest.mark.asyncio
    async def test_too_large(self):
        service, mock_client = self._make_service()
        mock_client.issue.return_value = {
            "key": "PROJ-1",
            "fields": {
                "attachment": [
                    {
                        "id": "102",
                        "filename": "huge.png",
                        "mimeType": "image/png",
                        "size": MAX_IMAGE_SIZE + 1,
                    },
                ],
            },
        }
        result = await service.execute(
            "issues",
            "view_image",
            {
                "key": "PROJ-1",
                "attachment-id": "102",
            },
        )
        assert "too large" in result

    @pytest.mark.asyncio
    async def test_download_error(self):
        service, mock_client = self._make_service()
        mock_client.issue.return_value = {
            "key": "PROJ-1",
            "fields": {
                "attachment": [
                    {
                        "id": "103",
                        "filename": "img.jpg",
                        "mimeType": "image/jpeg",
                        "size": 5000,
                        "content": "https://test.atlassian.net/attachment/103",
                    },
                ],
            },
        }
        mock_client._session.get.side_effect = Exception("Network error")
        result = await service.execute(
            "issues",
            "view_image",
            {
                "key": "PROJ-1",
                "attachment-id": "103",
            },
        )
        assert "Failed to download" in result


class TestIssuesViewAudio:
    """Tests for the issues view_audio handler."""

    def _make_service(self):
        with patch("atlassian.Jira") as mock_cls:
            mock_client = MagicMock()
            mock_cls.return_value = mock_client
            with (
                patch("koda.services.atlassian_client.JIRA_URL", "https://test.atlassian.net"),
                patch("koda.services.atlassian_client.JIRA_USERNAME", "test@test.com"),
                patch("koda.services.atlassian_client.JIRA_API_TOKEN", "token"),
                patch("koda.services.atlassian_client.JIRA_CLOUD", True),
            ):
                service = JiraService()
        return service, mock_client

    @pytest.mark.asyncio
    async def test_happy_path(self):
        service, mock_client = self._make_service()
        mock_client.issue.return_value = {
            "key": "PROJ-1",
            "fields": {
                "attachment": [
                    {
                        "id": "200",
                        "filename": "meeting.mp3",
                        "mimeType": "audio/mpeg",
                        "size": 500000,
                        "content": "https://test.atlassian.net/attachment/200",
                    },
                ],
            },
        }
        mock_response = MagicMock()
        mock_response.content = b"fake audio data"
        mock_client._session.get.return_value = mock_response

        with (
            patch("koda.utils.audio.is_ffmpeg_available", return_value=True),
            patch("koda.services.atlassian_client.IMAGE_TEMP_DIR") as mock_dir,
            patch("koda.services.atlassian_client.Path") as mock_path,
            patch("koda.utils.audio.transcribe_audio_sync", return_value="This is the transcription"),
        ):
            mock_dir.mkdir = MagicMock()
            mock_dir.__truediv__ = lambda self, name: MagicMock(__str__=lambda s: f"/tmp/images/{name}")
            mock_path.return_value.suffix = ".mp3"
            mock_path.return_value.write_bytes = MagicMock()
            mock_path.return_value.unlink = MagicMock()
            result = await service.execute(
                "issues",
                "view_audio",
                {
                    "key": "PROJ-1",
                    "attachment-id": "200",
                },
            )
        assert "Audio:" in result
        assert "Transcription" in result

    @pytest.mark.asyncio
    async def test_remote_transcription_still_works_when_local_whisper_is_disabled(self):
        service, mock_client = self._make_service()
        mock_client.issue.return_value = {
            "key": "PROJ-1",
            "fields": {
                "attachment": [
                    {
                        "id": "200",
                        "filename": "meeting.mp3",
                        "mimeType": "audio/mpeg",
                        "size": 500000,
                        "content": "https://test.atlassian.net/attachment/200",
                    },
                ],
            },
        }
        mock_response = MagicMock()
        mock_response.content = b"fake audio data"
        mock_client._session.get.return_value = mock_response

        with (
            patch("koda.utils.audio.WHISPER_ENABLED", False),
            patch("koda.utils.audio.is_ffmpeg_available", return_value=True),
            patch("koda.services.atlassian_client.IMAGE_TEMP_DIR") as mock_dir,
            patch("koda.services.atlassian_client.Path") as mock_path,
            patch("koda.utils.audio.transcribe_audio_sync", return_value="Texto remoto"),
        ):
            mock_dir.mkdir = MagicMock()
            mock_dir.__truediv__ = lambda self, name: MagicMock(__str__=lambda s: f"/tmp/images/{name}")
            mock_path.return_value.suffix = ".mp3"
            mock_path.return_value.write_bytes = MagicMock()
            mock_path.return_value.unlink = MagicMock()
            result = await service.execute(
                "issues",
                "view_audio",
                {
                    "key": "PROJ-1",
                    "attachment-id": "200",
                },
            )
        assert "Texto remoto" in result

    @pytest.mark.asyncio
    async def test_wrong_mime(self):
        service, mock_client = self._make_service()
        mock_client.issue.return_value = {
            "key": "PROJ-1",
            "fields": {
                "attachment": [
                    {
                        "id": "201",
                        "filename": "doc.pdf",
                        "mimeType": "application/pdf",
                        "size": 1000,
                    },
                ],
            },
        }
        with (
            patch("koda.utils.audio.is_ffmpeg_available", return_value=True),
        ):
            result = await service.execute(
                "issues",
                "view_audio",
                {
                    "key": "PROJ-1",
                    "attachment-id": "201",
                },
            )
        assert "not audio" in result

    @pytest.mark.asyncio
    async def test_not_found(self):
        service, mock_client = self._make_service()
        mock_client.issue.return_value = {
            "key": "PROJ-1",
            "fields": {"attachment": []},
        }
        with (
            patch("koda.utils.audio.is_ffmpeg_available", return_value=True),
        ):
            result = await service.execute(
                "issues",
                "view_audio",
                {
                    "key": "PROJ-1",
                    "attachment-id": "999",
                },
            )
        assert "not found" in result

    @pytest.mark.asyncio
    async def test_too_large(self):
        service, mock_client = self._make_service()
        mock_client.issue.return_value = {
            "key": "PROJ-1",
            "fields": {
                "attachment": [
                    {
                        "id": "202",
                        "filename": "huge.wav",
                        "mimeType": "audio/wav",
                        "size": MAX_AUDIO_SIZE + 1,
                    },
                ],
            },
        }
        with (
            patch("koda.utils.audio.is_ffmpeg_available", return_value=True),
        ):
            result = await service.execute(
                "issues",
                "view_audio",
                {
                    "key": "PROJ-1",
                    "attachment-id": "202",
                },
            )
        assert "too large" in result

    @pytest.mark.asyncio
    async def test_transcription_fails(self):
        service, mock_client = self._make_service()
        mock_client.issue.return_value = {
            "key": "PROJ-1",
            "fields": {
                "attachment": [
                    {
                        "id": "203",
                        "filename": "audio.mp3",
                        "mimeType": "audio/mpeg",
                        "size": 5000,
                        "content": "https://test.atlassian.net/attachment/203",
                    },
                ],
            },
        }
        mock_response = MagicMock()
        mock_response.content = b"fake audio"
        mock_client._session.get.return_value = mock_response

        with (
            patch("koda.utils.audio.is_ffmpeg_available", return_value=True),
            patch("koda.services.atlassian_client.IMAGE_TEMP_DIR") as mock_dir,
            patch("koda.services.atlassian_client.Path") as mock_path,
            patch("koda.utils.audio.transcribe_audio_sync", side_effect=Exception("whisper crashed")),
        ):
            mock_dir.mkdir = MagicMock()
            mock_dir.__truediv__ = lambda self, name: MagicMock(__str__=lambda s: f"/tmp/images/{name}")
            mock_path.return_value.suffix = ".mp3"
            mock_path.return_value.write_bytes = MagicMock()
            mock_path.return_value.unlink = MagicMock()
            result = await service.execute(
                "issues",
                "view_audio",
                {
                    "key": "PROJ-1",
                    "attachment-id": "203",
                },
            )
        assert "Transcription failed" in result


class TestAnalyzeMediaProcessing:
    """Tests for auto-media processing in issues analyze."""

    def _make_service(self):
        with patch("atlassian.Jira") as mock_cls:
            mock_client = MagicMock()
            mock_cls.return_value = mock_client
            with (
                patch("koda.services.atlassian_client.JIRA_URL", "https://test.atlassian.net"),
                patch("koda.services.atlassian_client.JIRA_USERNAME", "test@test.com"),
                patch("koda.services.atlassian_client.JIRA_API_TOKEN", "token"),
                patch("koda.services.atlassian_client.JIRA_CLOUD", True),
            ):
                service = JiraService()
        return service, mock_client

    @pytest.mark.asyncio
    async def test_analyze_with_image_attachments(self):
        service, mock_client = self._make_service()
        mock_client.issue.return_value = {
            "key": "PROJ-1",
            "fields": {
                "summary": "Test",
                "description": None,
                "issuelinks": [],
                "attachment": [
                    {
                        "id": "300",
                        "filename": "screen.png",
                        "mimeType": "image/png",
                        "size": 50000,
                        "content": "https://test.atlassian.net/attachment/300",
                        "author": {"displayName": "Dev"},
                        "created": "2025-01-01T00:00:00.000+0000",
                    },
                ],
            },
        }
        mock_client.issue_get_comments.return_value = {"comments": []}
        mock_client.get_issue_remote_links.return_value = []
        mock_response = MagicMock()
        mock_response.content = b"png data"
        mock_client._session.get.return_value = mock_response

        with (
            patch("koda.services.atlassian_client.IMAGE_TEMP_DIR") as mock_dir,
            patch("koda.services.atlassian_client.Path") as mock_path,
        ):
            mock_dir.mkdir = MagicMock()
            mock_dir.__truediv__ = lambda self, name: MagicMock(__str__=lambda s: f"/tmp/images/{name}")
            mock_path.return_value.write_bytes = MagicMock()
            mock_path.return_value.suffix = ".png"
            result = await service.execute("issues", "analyze", {"key": "PROJ-1"})
        assert "Exit 0:" in result
        assert "image downloaded for visual analysis" in result
        assert "Downloaded Images" in result

    @pytest.mark.asyncio
    async def test_analyze_with_video_hints(self):
        service, mock_client = self._make_service()
        mock_client.issue.return_value = {
            "key": "PROJ-1",
            "fields": {
                "summary": "Test",
                "description": None,
                "issuelinks": [],
                "attachment": [
                    {
                        "id": "400",
                        "filename": "demo.mp4",
                        "mimeType": "video/mp4",
                        "size": 5000000,
                        "content": "https://test.atlassian.net/attachment/400",
                        "author": {"displayName": "Dev"},
                        "created": "2025-01-01T00:00:00.000+0000",
                    },
                ],
            },
        }
        mock_client.issue_get_comments.return_value = {"comments": []}
        mock_client.get_issue_remote_links.return_value = []

        result = await service.execute("issues", "analyze", {"key": "PROJ-1"})
        assert "Exit 0:" in result
        assert "view_video" in result

    @pytest.mark.asyncio
    async def test_analyze_graceful_on_media_failure(self):
        service, mock_client = self._make_service()
        mock_client.issue.return_value = {
            "key": "PROJ-1",
            "fields": {
                "summary": "Test",
                "description": None,
                "issuelinks": [],
                "attachment": [
                    {
                        "id": "500",
                        "filename": "img.jpg",
                        "mimeType": "image/jpeg",
                        "size": 50000,
                        "content": "https://test.atlassian.net/attachment/500",
                        "author": {"displayName": "Dev"},
                        "created": "2025-01-01T00:00:00.000+0000",
                    },
                ],
            },
        }
        mock_client.issue_get_comments.return_value = {"comments": []}
        mock_client.get_issue_remote_links.return_value = []
        mock_client._session.get.side_effect = Exception("network error")

        result = await service.execute("issues", "analyze", {"key": "PROJ-1"})
        # Should still return successfully even if media processing fails
        assert "Exit 0:" in result
        assert "PROJ-1" in result
