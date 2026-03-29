"""Tests for new command handlers (Sprints 4-6)."""

import tempfile
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from koda.handlers.commands import (
    cmd_bookmarks,
    cmd_delbookmark,
    cmd_file,
    cmd_jobs,
    cmd_knowledge,
    cmd_ls,
    cmd_memory,
    cmd_name,
    cmd_napkin,
    cmd_remind,
    cmd_session,
    cmd_sessions,
    cmd_template,
    cmd_templates,
    init_user_data,
)


class TestCmdFile:
    @pytest.mark.asyncio
    async def test_no_args(self, mock_update, mock_context):
        mock_context.args = []
        init_user_data(mock_context.user_data)
        await cmd_file(mock_update, mock_context)
        call_text = mock_update.message.reply_text.call_args[0][0]
        assert "Usage" in call_text

    @pytest.mark.asyncio
    async def test_path_traversal_blocked(self, mock_update, mock_context):
        mock_context.args = ["../../etc/passwd"]
        mock_context.user_data["work_dir"] = tempfile.gettempdir()
        init_user_data(mock_context.user_data)
        await cmd_file(mock_update, mock_context)
        call_text = mock_update.message.reply_text.call_args[0][0]
        assert "Access denied" in call_text

    @pytest.mark.asyncio
    async def test_file_not_found(self, mock_update, mock_context, tmp_path):
        mock_context.args = ["nonexistent.txt"]
        mock_context.user_data["work_dir"] = str(tmp_path)
        init_user_data(mock_context.user_data)
        await cmd_file(mock_update, mock_context)
        call_text = mock_update.message.reply_text.call_args[0][0]
        assert "not found" in call_text

    @pytest.mark.asyncio
    async def test_sends_file(self, mock_update, mock_context, tmp_path):
        target = tmp_path / "test.txt"
        target.write_text("hello")
        mock_context.args = ["test.txt"]
        mock_context.user_data["work_dir"] = str(tmp_path)
        init_user_data(mock_context.user_data)
        await cmd_file(mock_update, mock_context)
        mock_update.message.reply_document.assert_called_once()

    @pytest.mark.asyncio
    async def test_directory_rejected(self, mock_update, mock_context, tmp_path):
        sub = tmp_path / "subdir"
        sub.mkdir()
        mock_context.args = ["subdir"]
        mock_context.user_data["work_dir"] = str(tmp_path)
        init_user_data(mock_context.user_data)
        await cmd_file(mock_update, mock_context)
        call_text = mock_update.message.reply_text.call_args[0][0]
        assert "directory" in call_text.lower()


class TestCmdLs:
    @pytest.mark.asyncio
    async def test_list_work_dir(self, mock_update, mock_context, tmp_path):
        (tmp_path / "a.txt").touch()
        mock_context.args = []
        mock_context.user_data["work_dir"] = str(tmp_path)
        init_user_data(mock_context.user_data)

        with patch("koda.handlers.commands.send_long_message", new_callable=AsyncMock) as mock_send:
            await cmd_ls(mock_update, mock_context)
            mock_send.assert_called_once()
            text = mock_send.call_args[0][1]
            assert "a.txt" in text

    @pytest.mark.asyncio
    async def test_list_traversal_blocked(self, mock_update, mock_context, tmp_path):
        mock_context.args = ["../../etc"]
        mock_context.user_data["work_dir"] = str(tmp_path)
        init_user_data(mock_context.user_data)
        await cmd_ls(mock_update, mock_context)
        call_text = mock_update.message.reply_text.call_args[0][0]
        assert "Access denied" in call_text


class TestCmdTemplates:
    @pytest.mark.asyncio
    async def test_list_templates(self, mock_update, mock_context):
        init_user_data(mock_context.user_data)
        with patch("koda.handlers.commands.list_template_names", return_value=(["code-review"], ["debug"], [])):
            await cmd_templates(mock_update, mock_context)
        call_text = mock_update.message.reply_text.call_args[0][0]
        assert "code-review" in call_text


class TestCmdTemplate:
    @pytest.mark.asyncio
    async def test_no_args_lists(self, mock_update, mock_context):
        mock_context.args = []
        init_user_data(mock_context.user_data)
        with patch("koda.handlers.commands.list_template_names", return_value=(["code-review"], ["debug"], [])):
            await cmd_template(mock_update, mock_context)
        call_text = mock_update.message.reply_text.call_args[0][0]
        assert "code-review" in call_text

    @pytest.mark.asyncio
    async def test_add_template(self, mock_update, mock_context):
        mock_context.args = ["add", "mytemplate", "Do", "something"]
        init_user_data(mock_context.user_data)
        with patch("koda.handlers.commands.add_template") as mock_add:
            await cmd_template(mock_update, mock_context)
            mock_add.assert_called_once_with("mytemplate", "Do something")

    @pytest.mark.asyncio
    async def test_del_template(self, mock_update, mock_context):
        mock_context.args = ["del", "mytemplate"]
        init_user_data(mock_context.user_data)
        with patch("koda.handlers.commands.delete_template", return_value=True):
            await cmd_template(mock_update, mock_context)
        call_text = mock_update.message.reply_text.call_args[0][0]
        assert "deleted" in call_text

    @pytest.mark.asyncio
    async def test_use_template(self, mock_update, mock_context):
        mock_context.args = ["use", "code-review", "Check", "this"]
        init_user_data(mock_context.user_data)
        with (
            patch("koda.handlers.commands.get_template", return_value="Review this code"),
            patch("koda.handlers.commands.acquire_rate_limit", return_value=True),
            patch("koda.handlers.commands.enqueue") as mock_enqueue,
        ):
            await cmd_template(mock_update, mock_context)
            mock_enqueue.assert_called_once()
            query = mock_enqueue.call_args[0][3]
            assert "Review this code" in query
            assert "Check this" in query

    @pytest.mark.asyncio
    async def test_use_missing_template(self, mock_update, mock_context):
        mock_context.args = ["use", "nonexistent"]
        init_user_data(mock_context.user_data)
        with patch("koda.handlers.commands.get_template", return_value=None):
            await cmd_template(mock_update, mock_context)
        call_text = mock_update.message.reply_text.call_args[0][0]
        assert "not found" in call_text


class TestCmdBookmarks:
    @pytest.mark.asyncio
    async def test_no_bookmarks(self, mock_update, mock_context):
        init_user_data(mock_context.user_data)
        with patch("koda.handlers.commands.get_bookmarks", return_value=[]):
            await cmd_bookmarks(mock_update, mock_context)
        call_text = mock_update.message.reply_text.call_args[0][0]
        assert "No bookmarks" in call_text

    @pytest.mark.asyncio
    async def test_show_bookmarks(self, mock_update, mock_context):
        init_user_data(mock_context.user_data)
        rows = [(1, "Some response text", "2026-01-01T12:00:00")]
        with (
            patch("koda.handlers.commands.get_bookmarks", return_value=rows),
            patch("koda.handlers.commands.send_long_message", new_callable=AsyncMock) as mock_send,
        ):
            await cmd_bookmarks(mock_update, mock_context)
            text = mock_send.call_args[0][1]
            assert "Some response text" in text


class TestCmdDelbookmark:
    @pytest.mark.asyncio
    async def test_delete_success(self, mock_update, mock_context):
        mock_context.args = ["1"]
        init_user_data(mock_context.user_data)
        with patch("koda.handlers.commands.delete_bookmark", return_value=True):
            await cmd_delbookmark(mock_update, mock_context)
        call_text = mock_update.message.reply_text.call_args[0][0]
        assert "deleted" in call_text

    @pytest.mark.asyncio
    async def test_delete_not_found(self, mock_update, mock_context):
        mock_context.args = ["999"]
        init_user_data(mock_context.user_data)
        with patch("koda.handlers.commands.delete_bookmark", return_value=False):
            await cmd_delbookmark(mock_update, mock_context)
        call_text = mock_update.message.reply_text.call_args[0][0]
        assert "not found" in call_text

    @pytest.mark.asyncio
    async def test_no_args(self, mock_update, mock_context):
        mock_context.args = []
        init_user_data(mock_context.user_data)
        await cmd_delbookmark(mock_update, mock_context)
        call_text = mock_update.message.reply_text.call_args[0][0]
        assert "Usage" in call_text


class TestCmdSessions:
    @pytest.mark.asyncio
    async def test_no_sessions(self, mock_update, mock_context):
        init_user_data(mock_context.user_data)
        with patch("koda.handlers.commands.get_sessions", return_value=[]):
            await cmd_sessions(mock_update, mock_context)
        call_text = mock_update.message.reply_text.call_args[0][0]
        assert "No saved sessions" in call_text

    @pytest.mark.asyncio
    async def test_list_sessions(self, mock_update, mock_context):
        init_user_data(mock_context.user_data)
        rows = [(1, "sess-abc", "My Project", "2026-01-01T12:00:00", "2026-01-02T12:00:00")]
        with (
            patch("koda.handlers.commands.get_sessions", return_value=rows),
            patch("koda.handlers.commands.send_long_message", new_callable=AsyncMock) as mock_send,
        ):
            await cmd_sessions(mock_update, mock_context)
            text = mock_send.call_args[0][1]
            assert "My Project" in text


class TestCmdSession:
    @pytest.mark.asyncio
    async def test_resume_session(self, mock_update, mock_context):
        mock_context.args = ["1"]
        init_user_data(mock_context.user_data)
        mock_context.user_data["provider_sessions"] = {"claude": "stale-session"}
        with patch("koda.handlers.commands.get_session_by_id", return_value=("sess-abc", "My Project")):
            await cmd_session(mock_update, mock_context)
        assert mock_context.user_data["session_id"] == "sess-abc"
        assert mock_context.user_data["provider_sessions"] == {}

    @pytest.mark.asyncio
    async def test_session_not_found(self, mock_update, mock_context):
        mock_context.args = ["999"]
        init_user_data(mock_context.user_data)
        with patch("koda.handlers.commands.get_session_by_id", return_value=None):
            await cmd_session(mock_update, mock_context)
        call_text = mock_update.message.reply_text.call_args[0][0]
        assert "not found" in call_text

    @pytest.mark.asyncio
    async def test_no_args(self, mock_update, mock_context):
        mock_context.args = []
        init_user_data(mock_context.user_data)
        await cmd_session(mock_update, mock_context)
        call_text = mock_update.message.reply_text.call_args[0][0]
        assert "Usage" in call_text


class TestCmdName:
    @pytest.mark.asyncio
    async def test_name_session(self, mock_update, mock_context):
        mock_context.args = ["My", "Session"]
        mock_context.user_data["session_id"] = "sess-abc"
        init_user_data(mock_context.user_data)
        with patch("koda.handlers.commands.rename_session", return_value=True):
            await cmd_name(mock_update, mock_context)
        call_text = mock_update.message.reply_text.call_args[0][0]
        assert "named" in call_text.lower()

    @pytest.mark.asyncio
    async def test_no_session(self, mock_update, mock_context):
        mock_context.args = ["Name"]
        init_user_data(mock_context.user_data)
        await cmd_name(mock_update, mock_context)
        call_text = mock_update.message.reply_text.call_args[0][0]
        assert "No active session" in call_text


class TestCmdRemind:
    @pytest.mark.asyncio
    async def test_no_args(self, mock_update, mock_context):
        mock_context.args = []
        init_user_data(mock_context.user_data)
        await cmd_remind(mock_update, mock_context)
        call_text = mock_update.message.reply_text.call_args[0][0]
        assert "Usage" in call_text

    @pytest.mark.asyncio
    async def test_invalid_time(self, mock_update, mock_context):
        mock_context.args = ["abc", "check", "something"]
        init_user_data(mock_context.user_data)
        await cmd_remind(mock_update, mock_context)
        call_text = mock_update.message.reply_text.call_args[0][0]
        assert "Invalid" in call_text

    @pytest.mark.asyncio
    async def test_valid_reminder(self, mock_update, mock_context):
        mock_context.args = ["5m", "Check", "the", "build"]
        init_user_data(mock_context.user_data)

        mock_job_queue = MagicMock()
        mock_context.job_queue = mock_job_queue

        await cmd_remind(mock_update, mock_context)
        call_text = mock_update.message.reply_text.call_args[0][0]
        assert "Reminder set" in call_text


class TestCmdJobs:
    @pytest.mark.asyncio
    async def test_jobs_list(self, mock_update, mock_context):
        init_user_data(mock_context.user_data)
        mock_context.args = []
        with (
            patch(
                "koda.services.scheduler.list_user_jobs",
                return_value=["#7 | agent_query | validated | next: 2026-03-18T12:00:00+00:00 | Check deploy status"],
            ),
            patch("koda.handlers.commands.send_long_message", new_callable=AsyncMock) as mock_send,
        ):
            await cmd_jobs(mock_update, mock_context)
        call_text = mock_send.call_args[0][1]
        assert "Scheduled jobs" in call_text
        assert "#7" in call_text

    @pytest.mark.asyncio
    async def test_jobs_pause_all(self, mock_update, mock_context):
        init_user_data(mock_context.user_data)
        mock_context.args = ["pause", "all"]
        with patch("koda.services.scheduler.cancel_user_jobs", return_value=2):
            await cmd_jobs(mock_update, mock_context)
        assert mock_update.message.reply_text.call_args[0][0] == "Paused 2 active jobs."

    @pytest.mark.asyncio
    async def test_jobs_activate(self, mock_update, mock_context):
        init_user_data(mock_context.user_data)
        mock_context.args = ["activate", "7"]
        with patch("koda.services.scheduled_jobs.activate_job", return_value=(True, "Job activated.")):
            await cmd_jobs(mock_update, mock_context)
        assert mock_update.message.reply_text.call_args[0][0] == "Job activated."


class TestCmdKnowledge:
    @pytest.mark.asyncio
    async def test_review_lists_pending_candidates(self, mock_update, mock_context):
        mock_context.args = ["review"]
        init_user_data(mock_context.user_data)
        with (
            patch(
                "koda.handlers.commands.list_knowledge_candidates",
                return_value=[
                    {
                        "id": 7,
                        "task_kind": "deploy",
                        "candidate_type": "success_pattern",
                        "support_count": 3,
                        "success_count": 3,
                        "failure_count": 0,
                        "confidence_score": 0.88,
                        "summary": "Deploy safely",
                    }
                ],
            ),
            patch("koda.handlers.commands.send_long_message", new_callable=AsyncMock) as mock_send,
        ):
            await cmd_knowledge(mock_update, mock_context)
        assert "#7" in mock_send.call_args[0][1]

    @pytest.mark.asyncio
    async def test_approve_candidate(self, mock_update, mock_context):
        mock_context.args = ["approve", "7"]
        init_user_data(mock_context.user_data)
        with (
            patch("koda.handlers.commands.approve_knowledge_candidate", return_value=11),
            patch("koda.services.metrics.CANDIDATE_PROMOTIONS"),
        ):
            await cmd_knowledge(mock_update, mock_context)
        call_text = mock_update.message.reply_text.call_args[0][0]
        assert "Runbook #11" in call_text

    @pytest.mark.asyncio
    async def test_sources_lists_registered_sources(self, mock_update, mock_context):
        mock_context.args = ["sources"]
        init_user_data(mock_context.user_data)
        with (
            patch(
                "koda.handlers.commands.list_knowledge_sources",
                return_value=[
                    {
                        "source_label": "agent_a.toml",
                        "layer": "canonical_policy",
                        "project_key": "workspace",
                        "owner": "ops",
                        "updated_at": "2026-03-17T00:00:00",
                        "source_path": "/tmp/agent_a.toml",
                    }
                ],
            ),
            patch("koda.handlers.commands.send_long_message", new_callable=AsyncMock) as mock_send,
        ):
            await cmd_knowledge(mock_update, mock_context)
        assert "agent_a.toml" in mock_send.call_args[0][1]

    @pytest.mark.asyncio
    async def test_denies_non_operator(self, mock_update, mock_context):
        mock_update.effective_user.id = 222
        mock_context.args = ["review"]
        init_user_data(mock_context.user_data)
        with patch("koda.handlers.commands.KNOWLEDGE_ADMIN_USER_IDS", {111}):
            await cmd_knowledge(mock_update, mock_context)
        call_text = mock_update.message.reply_text.call_args[0][0]
        assert "Access denied" in call_text

    @pytest.mark.asyncio
    async def test_runbooks_shows_latest_governance_reason(self, mock_update, mock_context):
        mock_context.args = ["runbooks"]
        init_user_data(mock_context.user_data)
        with (
            patch("koda.handlers.commands.KNOWLEDGE_ADMIN_USER_IDS", {111}),
            patch(
                "koda.handlers.commands.list_approved_runbooks",
                return_value=[
                    {
                        "id": 9,
                        "version": 2,
                        "task_kind": "deploy",
                        "title": "Deploy safely",
                        "status": "approved",
                        "lifecycle_status": "needs_review",
                        "project_key": "workspace",
                    }
                ],
            ),
            patch(
                "koda.handlers.commands.get_latest_runbook_governance_actions",
                return_value={9: {"action": "needs_review", "reason": "source_aged"}},
            ),
            patch("koda.handlers.commands.send_long_message", new_callable=AsyncMock) as mock_send,
        ):
            await cmd_knowledge(mock_update, mock_context)
        text = mock_send.call_args[0][1]
        assert "source_aged" in text
        assert "needs_review" in text

    @pytest.mark.asyncio
    async def test_health_lists_lifecycle_counts(self, mock_update, mock_context):
        mock_context.args = ["health"]
        init_user_data(mock_context.user_data)
        with (
            patch("koda.handlers.commands.KNOWLEDGE_ADMIN_USER_IDS", {111}),
            patch(
                "koda.handlers.commands.list_approved_runbooks",
                return_value=[
                    {"id": 1, "title": "A", "status": "approved", "lifecycle_status": "approved"},
                    {"id": 2, "title": "B", "status": "needs_review", "lifecycle_status": "needs_review"},
                    {"id": 3, "title": "C", "status": "expired", "lifecycle_status": "expired"},
                ],
            ),
            patch(
                "koda.handlers.commands.get_latest_runbook_governance_actions",
                return_value={2: {"reason": "low_success_rate"}},
            ),
            patch("koda.handlers.commands.send_long_message", new_callable=AsyncMock) as mock_send,
        ):
            await cmd_knowledge(mock_update, mock_context)
        text = mock_send.call_args[0][1]
        assert "approved: 1" in text
        assert "needs_review: 1" in text
        assert "expired: 1" in text
        assert "low_success_rate" in text

    @pytest.mark.asyncio
    async def test_revalidate_runbook(self, mock_update, mock_context):
        mock_context.args = ["revalidate", "15"]
        init_user_data(mock_context.user_data)
        with (
            patch("koda.handlers.commands.KNOWLEDGE_ADMIN_USER_IDS", {111}),
            patch("koda.handlers.commands.revalidate_approved_runbook", return_value=True) as mock_revalidate,
        ):
            await cmd_knowledge(mock_update, mock_context)
        mock_revalidate.assert_called_once_with(15, reviewer="user:111")
        assert "marked as approved" in mock_update.message.reply_text.call_args[0][0]


class TestCmdMemory:
    @pytest.mark.asyncio
    async def test_memory_quality_shows_snapshot(self, mock_update, mock_context):
        init_user_data(mock_context.user_data)
        mock_context.args = ["quality"]
        with patch(
            "koda.memory.quality.get_memory_quality_snapshot",
            return_value={
                "extraction": {"total": 12, "accepted": 7, "rejected": 5},
                "dedup": {"exact": 1, "semantic": 2, "batch": 3},
                "recall": {"considered": 20, "selected": 6, "discarded": 14},
                "memory": {"active": 4, "superseded": 1, "stale": 1, "invalidated": 0},
                "embedding_jobs": {"pending": 2, "failed": 1, "repaired": 5},
                "promotions": {"pending": 2, "approved": 3, "rejected": 1},
                "utility": {"useful": 4, "noise": 1, "misleading": 2},
                "runbooks": {"approved": 3, "needs_review": 1, "expired": 0, "deprecated": 1},
                "governance": {"approved": 2, "needs_review": 1, "expired": 0, "deprecated": 1},
            },
        ):
            await cmd_memory(mock_update, mock_context)
        text = mock_update.message.reply_text.call_args[0][0]
        assert "total 12" in text
        assert "Governance" in text
        assert "review 1" in text

    @pytest.mark.asyncio
    async def test_memory_audit_passes_filters(self, mock_update, mock_context):
        init_user_data(mock_context.user_data)
        mock_context.args = ["audit", "task:42", "layer:episodic", "retrieval:query_link", "query:deploy"]
        with (
            patch(
                "koda.memory.napkin.get_memory_recall_audits",
                return_value=[
                    {
                        "id": 1,
                        "trust_score": 0.8,
                        "considered": [{}],
                        "selected": [{}],
                        "discarded": [],
                        "query_preview": "deploy service",
                        "project_key": "proj",
                        "environment": "prod",
                        "team": "ops",
                        "selected_layers": ["episodic"],
                        "retrieval_sources": ["query_link"],
                        "conflicts": [],
                    }
                ],
            ) as mock_audits,
            patch("koda.handlers.commands.send_long_message", new_callable=AsyncMock),
        ):
            await cmd_memory(mock_update, mock_context)
        mock_audits.assert_called_once_with(
            mock_update.effective_user.id,
            agent_id="default",
            limit=8,
            task_id=42,
            query_contains="deploy",
            episode="",
            layer="episodic",
            retrieval="query_link",
        )

    @pytest.mark.asyncio
    async def test_memory_search_passes_layer_and_query_link(self, mock_update, mock_context):
        init_user_data(mock_context.user_data)
        mock_context.user_data["session_id"] = "sess-1"
        mock_context.args = ["search", "layer:episodic", "retrieval:query_link", "query:7", "deploy"]
        mock_store = MagicMock()
        mock_store.search = AsyncMock(return_value=[])
        mock_manager = MagicMock()
        mock_manager.store = mock_store
        with patch("koda.memory.get_memory_manager", return_value=mock_manager):
            await cmd_memory(mock_update, mock_context)
        mock_store.search.assert_awaited_once()
        kwargs = mock_store.search.await_args.kwargs
        assert kwargs["session_id"] == "sess-1"
        assert kwargs["source_query_id"] == 7
        assert kwargs["allowed_layers"] == ["episodic"]
        assert kwargs["allowed_retrieval_sources"] == ["query_link"]

    @pytest.mark.asyncio
    async def test_memory_search_denies_cross_agent_for_non_admin(self, mock_update, mock_context):
        init_user_data(mock_context.user_data)
        mock_context.args = ["search", "agent:other", "deploy"]
        with patch("koda.handlers.commands.KNOWLEDGE_ADMIN_USER_IDS", {999}):
            await cmd_memory(mock_update, mock_context)
        assert "Access denied" in mock_update.message.reply_text.call_args[0][0]

    @pytest.mark.asyncio
    async def test_memory_quality_allows_cross_agent_for_admin(self, mock_update, mock_context):
        init_user_data(mock_context.user_data)
        mock_context.args = ["quality", "agent:other"]
        with (
            patch("koda.handlers.commands.KNOWLEDGE_ADMIN_USER_IDS", {111}),
            patch(
                "koda.memory.quality.get_memory_quality_snapshot",
                return_value={
                    "extraction": {"total": 0, "accepted": 0, "rejected": 0},
                    "dedup": {"exact": 0, "semantic": 0, "batch": 0},
                    "recall": {"considered": 0, "selected": 0, "discarded": 0},
                    "memory": {"active": 0, "superseded": 0, "stale": 0, "invalidated": 0},
                    "embedding_jobs": {"pending": 0, "failed": 0, "repaired": 0},
                    "promotions": {"pending": 0, "approved": 0, "rejected": 0},
                    "utility": {"useful": 0, "noise": 0, "misleading": 0},
                    "runbooks": {"approved": 0, "needs_review": 0, "expired": 0, "deprecated": 0},
                    "governance": {"approved": 0, "needs_review": 0, "expired": 0, "deprecated": 0},
                },
            ) as mock_snapshot,
        ):
            await cmd_memory(mock_update, mock_context)
        mock_snapshot.assert_called_once_with("other")
        assert "agent: other" in mock_update.message.reply_text.call_args[0][0].lower()

    @pytest.mark.asyncio
    async def test_memory_audit_allows_cross_agent_for_admin(self, mock_update, mock_context):
        init_user_data(mock_context.user_data)
        mock_context.args = ["audit", "agent:other", "task:42"]
        with (
            patch("koda.handlers.commands.KNOWLEDGE_ADMIN_USER_IDS", {111}),
            patch(
                "koda.memory.napkin.get_memory_recall_audits",
                return_value=[
                    {
                        "id": 3,
                        "trust_score": 0.91,
                        "total_considered": 10,
                        "total_selected": 3,
                        "total_discarded": 7,
                        "query_preview": "deploy api",
                        "project_key": "proj",
                        "environment": "prod",
                        "team": "ops",
                        "selected_layers": ["episodic"],
                        "retrieval_sources": ["task_link"],
                        "conflicts": [],
                        "conflict_group_count": 0,
                        "selected": [],
                        "discarded": [],
                    }
                ],
            ) as mock_audits,
            patch("koda.handlers.commands.send_long_message", new_callable=AsyncMock) as mock_send,
        ):
            await cmd_memory(mock_update, mock_context)
        mock_audits.assert_called_once_with(
            mock_update.effective_user.id,
            agent_id="other",
            limit=8,
            task_id=42,
            query_contains="",
            episode="",
            layer="",
            retrieval="",
        )
        assert "agent: other" in mock_send.call_args[0][1].lower()


class TestCmdNapkin:
    @pytest.mark.asyncio
    async def test_napkin_cross_agent_denied_for_non_admin(self, mock_update, mock_context):
        init_user_data(mock_context.user_data)
        mock_context.args = ["agent:other"]
        with patch("koda.handlers.commands.KNOWLEDGE_ADMIN_USER_IDS", {999}):
            await cmd_napkin(mock_update, mock_context)
        assert "Access denied" in mock_update.message.reply_text.call_args[0][0]

    @pytest.mark.asyncio
    async def test_napkin_cross_agent_allowed_for_admin(self, mock_update, mock_context):
        init_user_data(mock_context.user_data)
        mock_context.args = ["agent:other", "origin:procedural_memory"]
        with (
            patch("koda.handlers.commands.KNOWLEDGE_ADMIN_USER_IDS", {111}),
            patch(
                "koda.memory.napkin.get_entries",
                return_value=[],
            ) as mock_get_entries,
        ):
            await cmd_napkin(mock_update, mock_context)
        mock_get_entries.assert_called_once()
        assert mock_get_entries.call_args.kwargs["agent_id"] == "other"
