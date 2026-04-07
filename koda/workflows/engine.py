"""Workflow execution engine."""

from __future__ import annotations

import asyncio
import re
import time
from typing import Any

from koda.logging_config import get_logger
from koda.workflows.model import Workflow, WorkflowRun

log = get_logger(__name__)

_VAR_RE = re.compile(r"\{\{\s*steps\.(\w+)\.(\w+)\s*\}\}")


def _resolve_variables(value: Any, step_results: dict[str, dict[str, Any]]) -> Any:
    """Resolve {{ steps.X.field }} variables in a value."""
    if isinstance(value, str):

        def replacer(m: re.Match[str]) -> str:
            step_id, fld = m.group(1), m.group(2)
            result = step_results.get(step_id, {})
            val = result.get(fld)
            if val is None:
                log.warning("workflow_unresolved_variable", step_id=step_id, field=fld)
                return f"{{{{steps.{step_id}.{fld}}}}}"
            return str(val)

        return _VAR_RE.sub(replacer, value)
    if isinstance(value, dict):
        return {k: _resolve_variables(v, step_results) for k, v in value.items()}
    if isinstance(value, list):
        return [_resolve_variables(v, step_results) for v in value]
    return value


def _evaluate_condition(condition: str, step_results: dict[str, dict[str, Any]]) -> bool:
    """Evaluate a simple condition like '{{ steps.query.success }}'."""
    resolved = _resolve_variables(condition, step_results)
    return str(resolved).lower().strip() in ("true", "1", "yes")


class WorkflowEngine:
    """Execute workflow steps sequentially, chaining outputs."""

    async def run(self, workflow: Workflow, ctx: Any) -> WorkflowRun:
        """Execute all steps in a workflow."""
        from koda.config import WORKFLOW_MAX_STEPS
        from koda.services.tool_dispatcher import AgentToolCall, execute_tool

        run = WorkflowRun(workflow_name=workflow.name, status="running", started_at=time.time())

        if len(workflow.steps) > WORKFLOW_MAX_STEPS:
            run.status = "failed"
            run.error = f"Too many steps ({len(workflow.steps)}). Max: {WORKFLOW_MAX_STEPS}"
            run.completed_at = time.time()
            return run

        for step in workflow.steps:
            # Check condition
            if step.condition and not _evaluate_condition(step.condition, run.step_results):
                run.step_results[step.id] = {
                    "success": True,
                    "output": "(skipped: condition false)",
                    "skipped": True,
                }
                continue

            # Resolve variables in params
            resolved_params = _resolve_variables(step.params, run.step_results)

            # Execute tool with timeout and retry support
            call = AgentToolCall(tool=step.tool, params=resolved_params, raw_match="")
            attempts = 0
            max_attempts = 1 + step.max_retries
            step_result: dict[str, Any] | None = None
            while attempts < max_attempts:
                attempts += 1
                try:
                    result = await asyncio.wait_for(execute_tool(call, ctx), timeout=step.timeout)
                    step_result = {
                        "success": result.success,
                        "output": result.output,
                        "tool": result.tool,
                        "duration_ms": result.duration_ms,
                    }
                    if result.success or attempts >= max_attempts:
                        break
                    if step.max_retries > 0 and attempts < max_attempts:
                        delay = step.retry_delay * (2 ** (attempts - 1))
                        log.info(
                            "workflow_step_retry",
                            step=step.id,
                            attempt=attempts,
                            delay=delay,
                        )
                        await asyncio.sleep(delay)
                except TimeoutError:
                    step_result = {
                        "success": False,
                        "output": f"Step timeout ({step.timeout}s) after {attempts} attempt(s)",
                        "tool": step.tool,
                        "timed_out": True,
                    }
                    if attempts >= max_attempts:
                        break
                    delay = step.retry_delay * (2 ** (attempts - 1))
                    await asyncio.sleep(delay)
                except Exception as e:
                    step_result = {
                        "success": False,
                        "output": f"Error: {e}",
                        "tool": step.tool,
                    }
                    break

            if step_result is None:
                step_result = {
                    "success": False,
                    "output": f"Step '{step.id}' produced no result",
                    "tool": step.tool,
                }

            run.step_results[step.id] = step_result

            step_result = run.step_results[step.id]
            if not step_result["success"]:
                if step.on_failure == "stop":
                    run.status = "failed"
                    run.error = f"Step '{step.id}' failed: {step_result['output'][:200]}"
                    run.completed_at = time.time()
                    return run
                elif step.on_failure == "skip":
                    continue
                # "continue" just proceeds

        run.status = "completed"
        run.completed_at = time.time()
        return run
