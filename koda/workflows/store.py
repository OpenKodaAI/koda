"""Workflow persistence (in-memory with singleton access)."""

from __future__ import annotations

import json
import os
import time
from typing import Any

from koda.logging_config import get_logger
from koda.workflows.model import Workflow, WorkflowStep

log = get_logger(__name__)


class WorkflowStore:
    def __init__(self) -> None:
        self._workflows: dict[str, Workflow] = {}
        self._persistence_path: str | None = None

    def set_persistence_path(self, path: str) -> None:
        self._persistence_path = path
        self._load_from_disk()

    def _load_from_disk(self) -> None:
        if not self._persistence_path or not os.path.isfile(self._persistence_path):
            return
        try:
            with open(self._persistence_path) as f:
                data = json.load(f)
            for name, wf_data in data.items():
                steps = [WorkflowStep(**s) for s in wf_data.get("steps", [])]
                self._workflows[name] = Workflow(
                    name=name,
                    steps=steps,
                    description=wf_data.get("description", ""),
                    created_by=wf_data.get("created_by"),
                    created_at=wf_data.get("created_at"),
                )
            log.info("workflows_loaded", count=len(self._workflows))
        except Exception as e:
            log.warning("workflows_load_failed", error=str(e))

    def _save_to_disk(self) -> None:
        if not self._persistence_path:
            return
        try:
            data = {}
            for name, wf in self._workflows.items():
                data[name] = {
                    "name": wf.name,
                    "description": wf.description,
                    "created_by": wf.created_by,
                    "created_at": wf.created_at,
                    "steps": [
                        {
                            "id": s.id,
                            "tool": s.tool,
                            "params": s.params,
                            "condition": s.condition,
                            "on_failure": s.on_failure,
                            "timeout": s.timeout,
                            "max_retries": s.max_retries,
                            "retry_delay": s.retry_delay,
                        }
                        for s in wf.steps
                    ],
                }
            os.makedirs(os.path.dirname(self._persistence_path) or ".", exist_ok=True)
            with open(self._persistence_path, "w") as f:
                json.dump(data, f, default=str)
        except Exception as e:
            log.warning("workflows_save_failed", error=str(e))

    def save(self, workflow: Workflow) -> None:
        workflow.created_at = workflow.created_at or time.time()
        self._workflows[workflow.name] = workflow
        log.info("workflow_saved", name=workflow.name, steps=len(workflow.steps))
        self._save_to_disk()

    def get(self, name: str) -> Workflow | None:
        return self._workflows.get(name)

    def list_all(self, user_id: int | None = None) -> list[dict[str, Any]]:
        results = []
        for w in self._workflows.values():
            if user_id and w.created_by != user_id:
                continue
            results.append(
                {
                    "name": w.name,
                    "description": w.description,
                    "step_count": len(w.steps),
                    "created_by": w.created_by,
                    "created_at": w.created_at,
                }
            )
        return results

    def delete(self, name: str) -> str | None:
        if name not in self._workflows:
            return f"Workflow '{name}' not found."
        del self._workflows[name]
        self._save_to_disk()
        return None

    def parse_workflow(
        self,
        name: str,
        steps_data: list[dict[str, Any]],
        description: str = "",
        user_id: int | None = None,
    ) -> Workflow | str:
        """Parse step dicts into a Workflow. Returns Workflow or error string."""
        if not steps_data:
            return "Workflow must have at least one step."
        steps: list[WorkflowStep] = []
        seen_ids: set[str] = set()
        for i, s in enumerate(steps_data):
            step_id = s.get("id", f"step_{i}")
            if step_id in seen_ids:
                return f"Duplicate step ID: '{step_id}'."
            seen_ids.add(step_id)
            tool = s.get("tool", "")
            if not tool:
                return f"Step '{step_id}' missing required field: 'tool'."
            steps.append(
                WorkflowStep(
                    id=step_id,
                    tool=tool,
                    params=s.get("params", {}),
                    condition=s.get("condition"),
                    on_failure=s.get("on_failure", "stop"),
                    timeout=int(s.get("timeout", 60)),
                    max_retries=int(s.get("max_retries", 0)),
                    retry_delay=float(s.get("retry_delay", 1.0)),
                )
            )
        return Workflow(name=name, steps=steps, description=description, created_by=user_id)


_store: WorkflowStore | None = None


def get_workflow_store() -> WorkflowStore:
    global _store
    if _store is None:
        _store = WorkflowStore()
    return _store
