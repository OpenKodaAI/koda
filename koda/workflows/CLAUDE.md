# Workflow Engine Guide

Sequential tool pipelines with variable binding.

## Key Files
- `engine.py` -- WorkflowEngine (execute steps, resolve variables)
- `model.py` -- Workflow, WorkflowStep, WorkflowRun dataclasses
- `store.py` -- In-memory + JSON persistence

## Variable Binding
Use `{{ steps.<step_id>.<field> }}` to chain outputs:
- `{{ steps.query.output }}` -- text output of step "query"
- `{{ steps.query.success }}` -- boolean success

## Step Options
- `timeout` -- per-step timeout in seconds (default 60)
- `max_retries` -- retry count (default 0)
- `on_failure` -- "stop" | "continue" | "skip"
