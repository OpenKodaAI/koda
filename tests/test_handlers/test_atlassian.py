"""Tests for Atlassian command handlers."""

from unittest.mock import AsyncMock, patch

import pytest

from koda.handlers.atlassian import (
    _format_atlassian_output,
    cmd_confluence,
    cmd_jboard,
    cmd_jira,
    cmd_jissue,
    cmd_jsprint,
)


class TestFormatAtlassianOutput:
    def test_json_output(self):
        raw = 'Exit 0:\n{"key": "PROJ-1"}'
        result = _format_atlassian_output(raw)
        assert '"key"' in result
        assert "Exit 0:" in result

    def test_non_json_output(self):
        raw = "Exit 0:\nsome plain text output"
        result = _format_atlassian_output(raw)
        assert result == raw

    def test_passes_through_large_json(self):
        """Handler does not truncate — service layer owns truncation at 4000 chars."""
        raw = f'Exit 0:\n{{"key": "{"x" * 4000}"}}'
        result = _format_atlassian_output(raw)
        assert '"key"' in result


class TestJiraHandler:
    @pytest.mark.asyncio
    async def test_jira_disabled(self, mock_update, mock_context):
        mock_context.args = ["issues", "search", "--jql", "project = PROJ"]
        with (
            patch("koda.handlers.atlassian.JIRA_ENABLED", False),
            patch("koda.services.execution_policy.JIRA_ENABLED", False),
        ):
            await cmd_jira(mock_update, mock_context)
        assert "disabled" in mock_update.message.reply_text.call_args[0][0].lower()

    @pytest.mark.asyncio
    async def test_jira_no_args(self, mock_update, mock_context):
        mock_context.args = []
        with (
            patch("koda.handlers.atlassian.JIRA_ENABLED", True),
            patch("koda.services.execution_policy.JIRA_ENABLED", True),
        ):
            await cmd_jira(mock_update, mock_context)
        assert "Usage" in mock_update.message.reply_text.call_args[0][0]

    @pytest.mark.asyncio
    async def test_jira_blocked_pattern(self, mock_update, mock_context):
        mock_context.args = ["projects", "delete", "--key", "PROJ"]
        with (
            patch("koda.handlers.atlassian.JIRA_ENABLED", True),
            patch("koda.services.execution_policy.JIRA_ENABLED", True),
        ):
            await cmd_jira(mock_update, mock_context)
        assert "blocked" in mock_update.message.reply_text.call_args[0][0].lower()

    @pytest.mark.asyncio
    async def test_jira_runs_command(self, mock_update, mock_context):
        mock_context.args = ["issues", "search", "--jql", "project = PROJ"]
        with (
            patch("koda.handlers.atlassian.JIRA_ENABLED", True),
            patch("koda.services.execution_policy.JIRA_ENABLED", True),
            patch("koda.handlers.atlassian.get_jira_service") as mock_svc,
            patch("koda.handlers.atlassian.send_long_message", new_callable=AsyncMock),
        ):
            mock_svc.return_value.execute = AsyncMock(return_value='Exit 0:\n{"issues": []}')
            await cmd_jira(mock_update, mock_context)
            mock_svc.return_value.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_jissue_prepends_issues(self, mock_update, mock_context):
        mock_context.args = ["search", "--jql", "project = PROJ"]
        with (
            patch("koda.handlers.atlassian.JIRA_ENABLED", True),
            patch("koda.services.execution_policy.JIRA_ENABLED", True),
            patch("koda.handlers.atlassian.get_jira_service") as mock_svc,
            patch("koda.handlers.atlassian.send_long_message", new_callable=AsyncMock),
        ):
            mock_svc.return_value.execute = AsyncMock(return_value="Exit 0:\n{}")
            await cmd_jissue(mock_update, mock_context)
            call_args = mock_svc.return_value.execute.call_args[0]
            assert call_args[0] == "issues"
            assert call_args[1] == "search"

    @pytest.mark.asyncio
    async def test_jissue_routes_new_comment_action_without_special_case(self, mock_update, mock_context):
        mock_context.args = ["comment_get", "--key", "PROJ-1", "--comment-id", "100"]
        with (
            patch("koda.handlers.atlassian.JIRA_ENABLED", True),
            patch("koda.services.execution_policy.JIRA_ENABLED", True),
            patch("koda.handlers.atlassian.get_jira_service") as mock_svc,
            patch("koda.handlers.atlassian.send_long_message", new_callable=AsyncMock),
        ):
            mock_svc.return_value.execute = AsyncMock(return_value="Exit 0:\n{}")
            await cmd_jissue(mock_update, mock_context)
            call_args = mock_svc.return_value.execute.call_args[0]
            assert call_args[0] == "issues"
            assert call_args[1] == "comment_get"

    @pytest.mark.asyncio
    async def test_jboard_prepends_boards(self, mock_update, mock_context):
        mock_context.args = ["list"]
        with (
            patch("koda.handlers.atlassian.JIRA_ENABLED", True),
            patch("koda.services.execution_policy.JIRA_ENABLED", True),
            patch("koda.handlers.atlassian.get_jira_service") as mock_svc,
            patch("koda.handlers.atlassian.send_long_message", new_callable=AsyncMock),
        ):
            mock_svc.return_value.execute = AsyncMock(return_value="Exit 0:\n{}")
            await cmd_jboard(mock_update, mock_context)
            call_args = mock_svc.return_value.execute.call_args[0]
            assert call_args[0] == "boards"

    @pytest.mark.asyncio
    async def test_jsprint_prepends_sprints(self, mock_update, mock_context):
        mock_context.args = ["list", "--board-id", "42"]
        with (
            patch("koda.handlers.atlassian.JIRA_ENABLED", True),
            patch("koda.services.execution_policy.JIRA_ENABLED", True),
            patch("koda.handlers.atlassian.get_jira_service") as mock_svc,
            patch("koda.handlers.atlassian.send_long_message", new_callable=AsyncMock),
        ):
            mock_svc.return_value.execute = AsyncMock(return_value="Exit 0:\n{}")
            await cmd_jsprint(mock_update, mock_context)
            call_args = mock_svc.return_value.execute.call_args[0]
            assert call_args[0] == "sprints"


class TestConfluenceHandler:
    @pytest.mark.asyncio
    async def test_confluence_disabled(self, mock_update, mock_context):
        mock_context.args = ["pages", "search", "--cql", "space = DEV"]
        with (
            patch("koda.handlers.atlassian.CONFLUENCE_ENABLED", False),
            patch("koda.services.execution_policy.CONFLUENCE_ENABLED", False),
        ):
            await cmd_confluence(mock_update, mock_context)
        assert "disabled" in mock_update.message.reply_text.call_args[0][0].lower()

    @pytest.mark.asyncio
    async def test_confluence_no_args(self, mock_update, mock_context):
        mock_context.args = []
        with (
            patch("koda.handlers.atlassian.CONFLUENCE_ENABLED", True),
            patch("koda.services.execution_policy.CONFLUENCE_ENABLED", True),
        ):
            await cmd_confluence(mock_update, mock_context)
        assert "Usage" in mock_update.message.reply_text.call_args[0][0]

    @pytest.mark.asyncio
    async def test_confluence_blocked_pattern(self, mock_update, mock_context):
        mock_context.args = ["spaces", "delete", "--key", "DEV"]
        with (
            patch("koda.handlers.atlassian.CONFLUENCE_ENABLED", True),
            patch("koda.services.execution_policy.CONFLUENCE_ENABLED", True),
        ):
            await cmd_confluence(mock_update, mock_context)
        assert "blocked" in mock_update.message.reply_text.call_args[0][0].lower()

    @pytest.mark.asyncio
    async def test_confluence_runs_command(self, mock_update, mock_context):
        mock_context.args = ["pages", "search", "--cql", "space = DEV"]
        with (
            patch("koda.handlers.atlassian.CONFLUENCE_ENABLED", True),
            patch("koda.services.execution_policy.CONFLUENCE_ENABLED", True),
            patch("koda.handlers.atlassian.get_confluence_service") as mock_svc,
            patch("koda.handlers.atlassian.send_long_message", new_callable=AsyncMock),
        ):
            mock_svc.return_value.execute = AsyncMock(return_value='Exit 0:\n{"results": []}')
            await cmd_confluence(mock_update, mock_context)
            mock_svc.return_value.execute.assert_called_once()


class TestBlockedJiraPatterns:
    """Test that BLOCKED_JIRA_PATTERN correctly blocks dangerous operations."""

    def test_blocked_projects_delete(self):
        from koda.config import BLOCKED_JIRA_PATTERN

        assert BLOCKED_JIRA_PATTERN.search("projects delete --key PROJ")

    def test_blocked_permissions(self):
        from koda.config import BLOCKED_JIRA_PATTERN

        assert BLOCKED_JIRA_PATTERN.search("permissions --project PROJ")

    def test_blocked_workflows_delete(self):
        from koda.config import BLOCKED_JIRA_PATTERN

        assert BLOCKED_JIRA_PATTERN.search("workflows delete --id 123")

    def test_blocked_users_create(self):
        from koda.config import BLOCKED_JIRA_PATTERN

        assert BLOCKED_JIRA_PATTERN.search("users create --email test@test.com")

    def test_blocked_bulk_delete(self):
        from koda.config import BLOCKED_JIRA_PATTERN

        assert BLOCKED_JIRA_PATTERN.search("bulk delete --jql 'project = X'")

    def test_blocked_reindex(self):
        from koda.config import BLOCKED_JIRA_PATTERN

        assert BLOCKED_JIRA_PATTERN.search("reindex --full")

    def test_allowed_issues_search(self):
        from koda.config import BLOCKED_JIRA_PATTERN

        assert not BLOCKED_JIRA_PATTERN.search("issues search --jql 'project = PROJ'")

    def test_allowed_issues_create(self):
        from koda.config import BLOCKED_JIRA_PATTERN

        assert not BLOCKED_JIRA_PATTERN.search("issues create --project PROJ --summary Test")

    def test_allowed_projects_list(self):
        from koda.config import BLOCKED_JIRA_PATTERN

        assert not BLOCKED_JIRA_PATTERN.search("projects list")


class TestBlockedConfluencePatterns:
    """Test that BLOCKED_CONFLUENCE_PATTERN correctly blocks dangerous operations."""

    def test_blocked_spaces_delete(self):
        from koda.config import BLOCKED_CONFLUENCE_PATTERN

        assert BLOCKED_CONFLUENCE_PATTERN.search("spaces delete --key DEV")

    def test_blocked_spaces_permissions(self):
        from koda.config import BLOCKED_CONFLUENCE_PATTERN

        assert BLOCKED_CONFLUENCE_PATTERN.search("spaces permissions --key DEV")

    def test_blocked_users_delete(self):
        from koda.config import BLOCKED_CONFLUENCE_PATTERN

        assert BLOCKED_CONFLUENCE_PATTERN.search("users delete --id abc123")

    def test_allowed_pages_search(self):
        from koda.config import BLOCKED_CONFLUENCE_PATTERN

        assert not BLOCKED_CONFLUENCE_PATTERN.search("pages search --cql 'space = DEV'")

    def test_allowed_pages_create(self):
        from koda.config import BLOCKED_CONFLUENCE_PATTERN

        assert not BLOCKED_CONFLUENCE_PATTERN.search("pages create --space DEV --title Test")

    def test_allowed_spaces_list(self):
        from koda.config import BLOCKED_CONFLUENCE_PATTERN

        assert not BLOCKED_CONFLUENCE_PATTERN.search("spaces list")
