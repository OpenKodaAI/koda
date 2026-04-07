"""Tests for the workflow store."""

from __future__ import annotations

from koda.workflows.model import Workflow, WorkflowStep
from koda.workflows.store import WorkflowStore


class TestWorkflowStore:
    def test_save_and_get(self):
        store = WorkflowStore()
        wf = Workflow(name="my-wf", steps=[WorkflowStep(id="s1", tool="web_search")])
        store.save(wf)
        got = store.get("my-wf")
        assert got is not None
        assert got.name == "my-wf"
        assert got.created_at is not None

    def test_get_missing(self):
        store = WorkflowStore()
        assert store.get("nope") is None

    def test_list_all(self):
        store = WorkflowStore()
        store.save(Workflow(name="a", steps=[WorkflowStep(id="s1", tool="t")]))
        store.save(Workflow(name="b", steps=[WorkflowStep(id="s1", tool="t")]))
        items = store.list_all()
        assert len(items) == 2
        names = {item["name"] for item in items}
        assert names == {"a", "b"}

    def test_list_filter_by_user(self):
        store = WorkflowStore()
        store.save(Workflow(name="a", steps=[WorkflowStep(id="s1", tool="t")], created_by=1))
        store.save(Workflow(name="b", steps=[WorkflowStep(id="s1", tool="t")], created_by=2))
        items = store.list_all(user_id=1)
        assert len(items) == 1
        assert items[0]["name"] == "a"

    def test_delete(self):
        store = WorkflowStore()
        store.save(Workflow(name="x", steps=[WorkflowStep(id="s1", tool="t")]))
        err = store.delete("x")
        assert err is None
        assert store.get("x") is None

    def test_delete_missing(self):
        store = WorkflowStore()
        err = store.delete("nope")
        assert err is not None
        assert "not found" in err

    def test_parse_workflow_success(self):
        store = WorkflowStore()
        result = store.parse_workflow(
            "test",
            [
                {"id": "s1", "tool": "web_search", "params": {"query": "x"}},
                {"id": "s2", "tool": "fetch_url", "params": {"url": "y"}, "on_failure": "continue"},
            ],
            description="a test",
            user_id=42,
        )
        assert isinstance(result, Workflow)
        assert result.name == "test"
        assert len(result.steps) == 2
        assert result.steps[0].tool == "web_search"
        assert result.steps[1].on_failure == "continue"
        assert result.created_by == 42

    def test_parse_workflow_empty_steps(self):
        store = WorkflowStore()
        result = store.parse_workflow("test", [])
        assert isinstance(result, str)
        assert "at least one step" in result

    def test_parse_workflow_duplicate_id(self):
        store = WorkflowStore()
        result = store.parse_workflow(
            "test",
            [
                {"id": "dup", "tool": "a"},
                {"id": "dup", "tool": "b"},
            ],
        )
        assert isinstance(result, str)
        assert "Duplicate" in result

    def test_parse_workflow_missing_tool(self):
        store = WorkflowStore()
        result = store.parse_workflow("test", [{"id": "s1"}])
        assert isinstance(result, str)
        assert "missing required field" in result

    def test_parse_auto_id(self):
        store = WorkflowStore()
        result = store.parse_workflow("test", [{"tool": "web_search"}, {"tool": "fetch_url"}])
        assert isinstance(result, Workflow)
        assert result.steps[0].id == "step_0"
        assert result.steps[1].id == "step_1"

    def test_parse_with_condition(self):
        store = WorkflowStore()
        result = store.parse_workflow(
            "test",
            [{"id": "s1", "tool": "a", "condition": "{{ steps.s0.success }}"}],
        )
        assert isinstance(result, Workflow)
        assert result.steps[0].condition == "{{ steps.s0.success }}"
