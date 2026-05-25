"""Runtime constants and state enums."""

from __future__ import annotations

RUNTIME_CLASSIFICATIONS = ("light", "standard", "heavy")
RUNTIME_ENVIRONMENT_KINDS = ("dev_worktree", "dev_worktree_browser")
RUNTIME_PHASES = (
    "queued",
    "classified",
    "provisioning",
    "planning",
    "executing",
    "validating",
    "operator_pause_requested",
    "paused_for_operator",
    "operator_attached",
    "resuming",
    "save_verifying",
    "checkpoint_blocked",
    "checkpointing",
    "completed_retained",
    "cancelled_retained",
    "recoverable_failed_retained",
    "terminal_failed",
    "cancel_requested",
    "cleanup_pending",
    "cleaning",
    "cleaned",
    "orphaned",
)
MUTATION_BLOCKED_PHASES = frozenset({"checkpointing", "cleaning"})
FINAL_PHASES = frozenset(
    {"completed_retained", "cancelled_retained", "recoverable_failed_retained", "terminal_failed", "cleaned"}
)
RECOVERABLE_PHASES = frozenset({"recoverable_failed_retained", "orphaned"})
PAUSE_STATES = ("none", "pause_requested", "paused_for_operator", "operator_attached", "resuming")
ATTACH_KINDS = ("terminal", "browser")
GUARDRAIL_TYPES = (
    "repeated_command",
    "repeated_diff",
    "repeated_failure",
    "no_change",
    "budget_exceeded",
    "retry_exhausted",
)
RUNTIME_EVENT_TYPES = (
    "task.created",
    "task.classified",
    "env.provisioning.started",
    "env.provisioning.finished",
    "env.provisioning.failed",
    "worktree.created",
    "worktree.removed",
    "plan.updated",
    "decision.recorded",
    "command.started",
    "command.stdout",
    "command.stderr",
    "command.finished",
    "process.spawned",
    "process.exited",
    "environment.paused",
    "environment.resumed",
    "terminal.attached",
    "terminal.detached",
    "browser.attached",
    "browser.detached",
    "browser.started",
    "browser.frame",
    "browser.video_ready",
    "browser.trace_ready",
    "browser.closed",
    "validation.started",
    "validation.passed",
    "validation.failed",
    "checkpoint.started",
    "checkpoint.saved",
    "checkpoint.failed",
    "retry.scheduled",
    "warning.issued",
    "resource.sampled",
    "recovery.detected",
    "recovery.reattached",
    "recovery.failed",
    "cleanup.started",
    "cleanup.finished",
    "cleanup.blocked",
)
