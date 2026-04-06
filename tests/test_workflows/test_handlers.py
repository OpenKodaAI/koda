"""Tests for workflow tool dispatcher handlers."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from koda.services.tool_dispatcher import (
    ToolContext,
    _handle_workflow_create,
    _handle_workflow_delete,
    _handle_workflow_get,
    _handle_workflow_list,
    _handle_workflow_run,
)
from koda.workflows.model import Workflow, WorkflowStep
from koda.workflows.store import WorkflowStore


def _ctx(user_id: int = 1) -> ToolContext:
    return ToolContext(
        user_id=user_id,
        chat_id=1,
        work_dir="/tmp",
        user_data={},
        agent=None,
        agent_mode="auto",
    )


class TestWorkflowDisabled:
    """All handlers should fail gracefully when WORKFLOW_ENABLED is False."""

    @pytest.mark.asyncio
    async def test_create_disabled(self):
        with patch("koda.services.tool_dispatcher.WORKFLOW_ENABLED", False):
            r = await _handle_workflow_create({"name": "x", "steps": [{"tool": "t"}]}, _ctx())
        assert not r.success
        assert "not enabled" in r.output

    @pytest.mark.asyncio
    async def test_run_disabled(self):
        with patch("koda.services.tool_dispatcher.WORKFLOW_ENABLED", False):
            r = await _handle_workflow_run({"name": "x"}, _ctx())
        assert not r.success

    @pytest.mark.asyncio
    async def test_list_disabled(self):
        with patch("koda.services.tool_dispatcher.WORKFLOW_ENABLED", False):
            r = await _handle_workflow_list({}, _ctx())
        assert not r.success

    @pytest.mark.asyncio
    async def test_get_disabled(self):
        with patch("koda.services.tool_dispatcher.WORKFLOW_ENABLED", False):
            r = await _handle_workflow_get({"name": "x"}, _ctx())
        assert not r.success

    @pytest.mark.asyncio
    async def test_delete_disabled(self):
        with patch("koda.services.tool_dispatcher.WORKFLOW_ENABLED", False):
            r = await _handle_workflow_delete({"name": "x"}, _ctx())
        assert not r.success


class TestWorkflowCreate:
    @pytest.mark.asyncio
    async def test_missing_name(self):
        with patch("koda.services.tool_dispatcher.WORKFLOW_ENABLED", True):
            r = await _handle_workflow_create({"steps": [{"tool": "t"}]}, _ctx())
        assert not r.success
        assert "name" in r.output.lower()

    @pytest.mark.asyncio
    async def test_missing_steps(self):
        with patch("koda.services.tool_dispatcher.WORKFLOW_ENABLED", True):
            r = await _handle_workflow_create({"name": "x"}, _ctx())
        assert not r.success
        assert "steps" in r.output.lower()

    @pytest.mark.asyncio
    async def test_success(self):
        store = WorkflowStore()
        with (
            patch("koda.services.tool_dispatcher.WORKFLOW_ENABLED", True),
            patch("koda.workflows.store.get_workflow_store", return_value=store),
        ):
            r = await _handle_workflow_create(
                {"name": "my-wf", "steps": [{"id": "s1", "tool": "web_search"}]},
                _ctx(),
            )
        assert r.success
        assert "created" in r.output.lower()
        assert store.get("my-wf") is not None

    @pytest.mark.asyncio
    async def test_parse_error(self):
        store = WorkflowStore()
        with (
            patch("koda.services.tool_dispatcher.WORKFLOW_ENABLED", True),
            patch("koda.workflows.store.get_workflow_store", return_value=store),
        ):
            r = await _handle_workflow_create(
                {"name": "bad", "steps": [{"id": "s1"}]},  # missing tool
                _ctx(),
            )
        assert not r.success
        assert "missing" in r.output.lower()


class TestWorkflowRun:
    @pytest.mark.asyncio
    async def test_missing_name(self):
        with patch("koda.services.tool_dispatcher.WORKFLOW_ENABLED", True):
            r = await _handle_workflow_run({}, _ctx())
        assert not r.success

    @pytest.mark.asyncio
    async def test_not_found(self):
        store = WorkflowStore()
        with (
            patch("koda.services.tool_dispatcher.WORKFLOW_ENABLED", True),
            patch("koda.workflows.store.get_workflow_store", return_value=store),
        ):
            r = await _handle_workflow_run({"name": "nope"}, _ctx())
        assert not r.success
        assert "not found" in r.output.lower()

    @pytest.mark.asyncio
    async def test_success(self):
        store = WorkflowStore()
        wf = Workflow(
            name="ok-wf",
            steps=[WorkflowStep(id="s1", tool="web_search", params={})],
        )
        store.save(wf)

        from koda.workflows.model import WorkflowRun

        fake_run = WorkflowRun(
            workflow_name="ok-wf",
            status="completed",
            step_results={"s1": {"success": True, "output": "done", "tool": "web_search"}},
        )

        with (
            patch("koda.services.tool_dispatcher.WORKFLOW_ENABLED", True),
            patch("koda.workflows.store.get_workflow_store", return_value=store),
            patch(
                "koda.workflows.engine.WorkflowEngine.run",
                new_callable=AsyncMock,
                return_value=fake_run,
            ),
        ):
            r = await _handle_workflow_run({"name": "ok-wf"}, _ctx())
        assert r.success
        assert "completed" in r.output.lower()


class TestWorkflowList:
    @pytest.mark.asyncio
    async def test_empty(self):
        store = WorkflowStore()
        with (
            patch("koda.services.tool_dispatcher.WORKFLOW_ENABLED", True),
            patch("koda.workflows.store.get_workflow_store", return_value=store),
        ):
            r = await _handle_workflow_list({}, _ctx())
        assert r.success
        assert "no workflows" in r.output.lower()

    @pytest.mark.asyncio
    async def test_with_items(self):
        store = WorkflowStore()
        store.save(Workflow(name="a", steps=[WorkflowStep(id="s1", tool="t")]))
        store.save(Workflow(name="b", steps=[WorkflowStep(id="s1", tool="t")]))
        with (
            patch("koda.services.tool_dispatcher.WORKFLOW_ENABLED", True),
            patch("koda.workflows.store.get_workflow_store", return_value=store),
        ):
            r = await _handle_workflow_list({}, _ctx())
        assert r.success
        assert "2" in r.output


class TestWorkflowGet:
    @pytest.mark.asyncio
    async def test_missing_name(self):
        with patch("koda.services.tool_dispatcher.WORKFLOW_ENABLED", True):
            r = await _handle_workflow_get({}, _ctx())
        assert not r.success

    @pytest.mark.asyncio
    async def test_not_found(self):
        store = WorkflowStore()
        with (
            patch("koda.services.tool_dispatcher.WORKFLOW_ENABLED", True),
            patch("koda.workflows.store.get_workflow_store", return_value=store),
        ):
            r = await _handle_workflow_get({"name": "nope"}, _ctx())
        assert not r.success

    @pytest.mark.asyncio
    async def test_success(self):
        store = WorkflowStore()
        store.save(
            Workflow(
                name="wf1",
                description="test wf",
                steps=[WorkflowStep(id="s1", tool="web_search", params={"q": "x"})],
            )
        )
        with (
            patch("koda.services.tool_dispatcher.WORKFLOW_ENABLED", True),
            patch("koda.workflows.store.get_workflow_store", return_value=store),
        ):
            r = await _handle_workflow_get({"name": "wf1"}, _ctx())
        assert r.success
        assert "wf1" in r.output
        assert "web_search" in r.output


class TestWorkflowDelete:
    @pytest.mark.asyncio
    async def test_missing_name(self):
        with patch("koda.services.tool_dispatcher.WORKFLOW_ENABLED", True):
            r = await _handle_workflow_delete({}, _ctx())
        assert not r.success

    @pytest.mark.asyncio
    async def test_not_found(self):
        store = WorkflowStore()
        with (
            patch("koda.services.tool_dispatcher.WORKFLOW_ENABLED", True),
            patch("koda.workflows.store.get_workflow_store", return_value=store),
        ):
            r = await _handle_workflow_delete({"name": "nope"}, _ctx())
        assert not r.success

    @pytest.mark.asyncio
    async def test_success(self):
        store = WorkflowStore()
        store.save(Workflow(name="del-me", steps=[WorkflowStep(id="s1", tool="t")]))
        with (
            patch("koda.services.tool_dispatcher.WORKFLOW_ENABLED", True),
            patch("koda.workflows.store.get_workflow_store", return_value=store),
        ):
            r = await _handle_workflow_delete({"name": "del-me"}, _ctx())
        assert r.success
        assert "deleted" in r.output.lower()
        assert store.get("del-me") is None


class TestWorkflowPrompt:
    def test_workflow_section_when_enabled(self):
        from koda.services.tool_prompt import build_agent_tools_prompt

        with patch("koda.services.tool_prompt.WORKFLOW_ENABLED", True):
            prompt = build_agent_tools_prompt(feature_flags={"workflows": True})
        assert "workflow_create" not in prompt
        assert "workflow_run" not in prompt
        assert "{{ steps." not in prompt

    def test_no_workflow_section_when_disabled(self):
        from koda.services.tool_prompt import build_agent_tools_prompt

        with patch("koda.services.tool_prompt.WORKFLOW_ENABLED", False):
            prompt = build_agent_tools_prompt(feature_flags={"workflows": False})
        assert "workflow_create" not in prompt
