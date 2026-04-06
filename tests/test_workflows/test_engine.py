"""Tests for the workflow engine."""

from __future__ import annotations

from dataclasses import dataclass
from unittest.mock import AsyncMock, patch

import pytest

from koda.workflows.engine import WorkflowEngine, _evaluate_condition, _resolve_variables
from koda.workflows.model import Workflow, WorkflowStep

# ---------------------------------------------------------------------------
# Variable resolution
# ---------------------------------------------------------------------------


class TestResolveVariables:
    def test_simple_string(self):
        results = {"s1": {"output": "hello", "success": "True"}}
        assert _resolve_variables("{{ steps.s1.output }}", results) == "hello"

    def test_multiple_vars(self):
        results = {"s1": {"output": "A"}, "s2": {"output": "B"}}
        val = _resolve_variables("{{ steps.s1.output }}-{{ steps.s2.output }}", results)
        assert val == "A-B"

    def test_missing_step(self):
        val = _resolve_variables("{{ steps.missing.output }}", {})
        assert "steps.missing.output" in val

    def test_dict_resolution(self):
        results = {"s1": {"output": "val"}}
        out = _resolve_variables({"key": "{{ steps.s1.output }}"}, results)
        assert out == {"key": "val"}

    def test_list_resolution(self):
        results = {"s1": {"output": "item"}}
        out = _resolve_variables(["{{ steps.s1.output }}"], results)
        assert out == ["item"]

    def test_non_string_passthrough(self):
        assert _resolve_variables(42, {}) == 42
        assert _resolve_variables(None, {}) is None

    def test_nested_dict(self):
        results = {"a": {"output": "x"}}
        out = _resolve_variables({"outer": {"inner": "{{ steps.a.output }}"}}, results)
        assert out == {"outer": {"inner": "x"}}


# ---------------------------------------------------------------------------
# Condition evaluation
# ---------------------------------------------------------------------------


class TestEvaluateCondition:
    def test_true_values(self):
        results = {"s1": {"success": "True"}}
        assert _evaluate_condition("{{ steps.s1.success }}", results) is True

    def test_false_values(self):
        results = {"s1": {"success": "False"}}
        assert _evaluate_condition("{{ steps.s1.success }}", results) is False

    def test_missing_ref(self):
        assert _evaluate_condition("{{ steps.missing.success }}", {}) is False


# ---------------------------------------------------------------------------
# Engine execution
# ---------------------------------------------------------------------------


@dataclass
class _FakeResult:
    tool: str = "test"
    success: bool = True
    output: str = "ok"
    duration_ms: float | None = 10.0


@pytest.fixture()
def _workflow_max_steps():
    with patch("koda.config.WORKFLOW_MAX_STEPS", 50):
        yield


class TestWorkflowEngine:
    @pytest.mark.asyncio
    @pytest.mark.usefixtures("_workflow_max_steps")
    async def test_basic_two_step(self):
        wf = Workflow(
            name="test",
            steps=[
                WorkflowStep(id="s1", tool="web_search", params={"query": "hello"}),
                WorkflowStep(
                    id="s2",
                    tool="fetch_url",
                    params={"url": "{{ steps.s1.output }}"},
                ),
            ],
        )

        fake_result = _FakeResult(output="http://example.com")
        fake_result2 = _FakeResult(output="page content")

        with patch(
            "koda.services.tool_dispatcher.execute_tool",
            new_callable=AsyncMock,
            side_effect=[fake_result, fake_result2],
        ):
            engine = WorkflowEngine()
            run = await engine.run(wf, None)

        assert run.status == "completed"
        assert "s1" in run.step_results
        assert "s2" in run.step_results
        assert run.step_results["s2"]["output"] == "page content"

    @pytest.mark.asyncio
    @pytest.mark.usefixtures("_workflow_max_steps")
    async def test_condition_skip(self):
        wf = Workflow(
            name="test",
            steps=[
                WorkflowStep(id="s1", tool="web_search", params={}),
                WorkflowStep(
                    id="s2",
                    tool="fetch_url",
                    params={},
                    condition="{{ steps.s1.success }}",
                ),
            ],
        )

        fake_result = _FakeResult(success=False, output="err")

        with patch(
            "koda.services.tool_dispatcher.execute_tool",
            new_callable=AsyncMock,
            return_value=fake_result,
        ):
            engine = WorkflowEngine()
            run = await engine.run(wf, None)

        # s1 fails -> stop (default on_failure)
        assert run.status == "failed"

    @pytest.mark.asyncio
    @pytest.mark.usefixtures("_workflow_max_steps")
    async def test_on_failure_continue(self):
        wf = Workflow(
            name="test",
            steps=[
                WorkflowStep(
                    id="s1",
                    tool="web_search",
                    params={},
                    on_failure="continue",
                ),
                WorkflowStep(id="s2", tool="fetch_url", params={}),
            ],
        )

        fail_result = _FakeResult(success=False, output="err")
        ok_result = _FakeResult(success=True, output="ok")

        with patch(
            "koda.services.tool_dispatcher.execute_tool",
            new_callable=AsyncMock,
            side_effect=[fail_result, ok_result],
        ):
            engine = WorkflowEngine()
            run = await engine.run(wf, None)

        assert run.status == "completed"

    @pytest.mark.asyncio
    @pytest.mark.usefixtures("_workflow_max_steps")
    async def test_on_failure_skip(self):
        wf = Workflow(
            name="test",
            steps=[
                WorkflowStep(id="s1", tool="web_search", params={}, on_failure="skip"),
                WorkflowStep(id="s2", tool="fetch_url", params={}),
            ],
        )

        fail_result = _FakeResult(success=False, output="err")
        ok_result = _FakeResult(success=True, output="ok")

        with patch(
            "koda.services.tool_dispatcher.execute_tool",
            new_callable=AsyncMock,
            side_effect=[fail_result, ok_result],
        ):
            engine = WorkflowEngine()
            run = await engine.run(wf, None)

        assert run.status == "completed"

    @pytest.mark.asyncio
    async def test_too_many_steps(self):
        steps = [WorkflowStep(id=f"s{i}", tool="noop", params={}) for i in range(60)]
        wf = Workflow(name="big", steps=steps)

        with patch("koda.config.WORKFLOW_MAX_STEPS", 50):
            engine = WorkflowEngine()
            run = await engine.run(wf, None)

        assert run.status == "failed"
        assert "Too many steps" in (run.error or "")

    @pytest.mark.asyncio
    @pytest.mark.usefixtures("_workflow_max_steps")
    async def test_exception_in_execute_tool(self):
        wf = Workflow(
            name="test",
            steps=[WorkflowStep(id="s1", tool="bad_tool", params={})],
        )

        with patch(
            "koda.services.tool_dispatcher.execute_tool",
            new_callable=AsyncMock,
            side_effect=RuntimeError("boom"),
        ):
            engine = WorkflowEngine()
            run = await engine.run(wf, None)

        assert run.status == "failed"
        assert run.step_results["s1"]["success"] is False
        assert "boom" in run.step_results["s1"]["output"]

    @pytest.mark.asyncio
    @pytest.mark.usefixtures("_workflow_max_steps")
    async def test_condition_true_runs_step(self):
        wf = Workflow(
            name="test",
            steps=[
                WorkflowStep(id="s1", tool="web_search", params={}),
                WorkflowStep(
                    id="s2",
                    tool="fetch_url",
                    params={},
                    condition="{{ steps.s1.success }}",
                ),
            ],
        )

        ok_result = _FakeResult(success=True, output="found")
        ok_result2 = _FakeResult(success=True, output="fetched")

        with patch(
            "koda.services.tool_dispatcher.execute_tool",
            new_callable=AsyncMock,
            side_effect=[ok_result, ok_result2],
        ):
            engine = WorkflowEngine()
            run = await engine.run(wf, None)

        assert run.status == "completed"
        assert run.step_results["s2"]["output"] == "fetched"
        assert run.step_results["s2"].get("skipped") is None
