from __future__ import annotations

import ast
import inspect
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import koda.agent_turn as agent_turn
from koda.agent_turn import AgentTurnInput, AgentTurnOutput, from_query_context, from_run_result


class FakePolicy:
    def to_dict(self) -> dict[str, Any]:
        return {"mode": "guarded", "constraints": {"read_only": False}}


@dataclass(slots=True)
class FakeQueryContext:
    provider: str = "codex"
    model: str = "gpt-5-codex"
    session_id: str = "sess_123"
    provider_session_id: str | None = "prov_sess_456"
    work_dir: Path = Path("/tmp/koda-work")
    system_prompt: str = "compiled prompt"
    agent_mode: str = "autonomous"
    permission_mode: str = "guarded"
    max_turns: int = 8
    task_id: int = 42
    warnings: list[str] = field(default_factory=lambda: ["memory timeout"])
    fallback_chain: list[str] = field(default_factory=lambda: ["codex", "claude"])
    prompt_budget: dict[str, Any] = field(
        default_factory=lambda: {
            "compiled_prompt": "compiled prompt",
            "max_input_tokens": 12000,
            "compiled_tokens": 420,
            "overflow_tokens": 0,
            "within_budget": True,
            "final_segment_order": ["immutable_base_policy", "memory_context"],
            "category_token_caps": {"memory": 2048},
            "included_segments": [
                {
                    "segment_id": "immutable_base_policy",
                    "category": "base",
                    "priority": 0,
                    "compression_strategy": "truncate_tail",
                    "drop_policy": "hard_floor",
                    "token_estimate": 120,
                    "final_token_estimate": 120,
                    "compressed": False,
                    "metadata": {"source": "control_plane_agent_prompt"},
                }
            ],
            "dropped_segments": [
                {
                    "segment_id": "asset_memory",
                    "category": "scripts_assets",
                    "priority": 75,
                    "compression_strategy": "truncate_tail",
                    "drop_policy": "drop",
                    "token_estimate": 900,
                    "reason": "budget_exhausted",
                }
            ],
        }
    )
    knowledge_hits: list[object] = field(default_factory=lambda: [object(), object()])
    memory_trust_score: float = 0.82
    confidence_reports: list[dict[str, Any]] = field(default_factory=lambda: [{"score": 0.91}])
    effective_policy: FakePolicy = field(default_factory=FakePolicy)
    ungrounded_operationally: bool = False
    stale_sources_present: bool = True
    verified_before_finalize: bool = True
    human_approval_used: bool = False
    execution_episode_id: int = 314
    task_kind: str = "implementation"
    turn_mode: str = "resume"
    resume_requested: bool = True
    supports_native_resume: bool = True
    provider_available: bool = True
    dry_run: bool = False
    scheduled_job_id: int | None = None
    scheduled_run_id: int | None = 7
    runtime_env_id: int | None = 9
    runtime_classification: str = "standard"
    runtime_environment_kind: str = "dev_worktree"
    asset_refs: list[dict[str, Any]] = field(default_factory=lambda: [{"path": "README.md"}])
    visual_paths: list[str] = field(default_factory=lambda: ["/tmp/a.png"])
    temp_paths: list[str] = field(default_factory=lambda: ["/tmp/a.png"])
    effort: str = "high"
    force_audio_response: bool = True
    executing_agent_id: str = "agent_backend"
    squad_thread_id: str = "thread_1"
    squad_task_id: str = "task_1"
    parent_message_id: str = "msg_parent"
    delegation_chain: list[str] = field(default_factory=lambda: ["agent_lead", "agent_backend"])
    delegation_request_id: str = "delegation_1"
    delegation_origin_agent_id: str = "agent_lead"
    telegram_message_thread_id: int = 99


@dataclass(slots=True)
class FakeRunResult:
    provider: str = "codex"
    model: str = "gpt-5-codex"
    result: str = "Done."
    session_id: str = "sess_123"
    provider_session_id: str | None = "prov_sess_456"
    cost_usd: float = 0.037
    error: bool = False
    stop_reason: str = "completed"
    usage: dict[str, Any] = field(default_factory=lambda: {"input_tokens": 100, "output_tokens": 40})
    tool_uses: list[dict[str, Any]] = field(default_factory=lambda: [{"name": "shell", "status": "ok"}])
    native_items: list[dict[str, Any]] = field(default_factory=lambda: [{"type": "message"}])
    tool_execution_trace: list[dict[str, Any]] = field(default_factory=lambda: [{"tool": "shell", "duration_ms": 15}])
    raw_output: str = "raw stream"
    warnings: list[str] = field(default_factory=lambda: ["minor warning"])
    fallback_chain: list[str] = field(default_factory=lambda: ["codex"])
    turn_mode: str = "resume"
    supports_native_resume: bool = True
    error_kind: str = ""
    retryable: bool = False
    runtime_terminal_id: int = 12
    runtime_terminal_path: str = "kernel-stream://stdout"


def test_from_query_context_builds_versioned_snapshot_without_runtime_imports() -> None:
    snapshot = from_query_context(FakeQueryContext())

    assert snapshot.to_dict() == {
        "contract_version": "agent_turn.v1",
        "task_id": 42,
        "provider": "codex",
        "model": "gpt-5-codex",
        "session_id": "sess_123",
        "provider_session_id": "prov_sess_456",
        "work_dir": "/tmp/koda-work",
        "compiled_prompt": "compiled prompt",
        "agent_mode": "autonomous",
        "permission_mode": "guarded",
        "max_turns": 8,
        "turn_mode": "resume",
        "resume_requested": True,
        "supports_native_resume": True,
        "provider_available": True,
        "dry_run": False,
        "scheduled_job_id": None,
        "scheduled_run_id": 7,
        "runtime_env_id": 9,
        "runtime_classification": "standard",
        "runtime_environment_kind": "dev_worktree",
        "task_kind": "implementation",
        "warnings": ["memory timeout"],
        "fallback_chain": ["codex", "claude"],
        "compiled_context_blocks": [
            {
                "contract_version": "agent_turn.v1",
                "block_id": "immutable_base_policy",
                "category": "base",
                "status": "included",
                "priority": 0,
                "token_estimate": 120,
                "final_token_estimate": 120,
                "compression_strategy": "truncate_tail",
                "drop_policy": "hard_floor",
                "compressed": False,
                "reason": None,
                "metadata": {"source": "control_plane_agent_prompt"},
            },
            {
                "contract_version": "agent_turn.v1",
                "block_id": "asset_memory",
                "category": "scripts_assets",
                "status": "dropped",
                "priority": 75,
                "token_estimate": 900,
                "final_token_estimate": None,
                "compression_strategy": "truncate_tail",
                "drop_policy": "drop",
                "compressed": False,
                "reason": "budget_exhausted",
                "metadata": {},
            },
        ],
        "prompt_budget": {
            "max_input_tokens": 12000,
            "compiled_tokens": 420,
            "overflow_tokens": 0,
            "within_budget": True,
            "final_segment_order": ["immutable_base_policy", "memory_context"],
            "category_token_caps": {"memory": 2048},
        },
        "knowledge_hit_count": 2,
        "memory_trust_score": 0.82,
        "confidence_reports": [{"score": 0.91}],
        "effective_policy": {"mode": "guarded", "constraints": {"read_only": False}},
        "ungrounded_operationally": False,
        "stale_sources_present": True,
        "verified_before_finalize": True,
        "human_approval_used": False,
        "execution_episode_id": 314,
        "asset_refs": [{"path": "README.md"}],
        "visual_paths": ["/tmp/a.png"],
        "temp_paths": ["/tmp/a.png"],
        "effort": "high",
        "force_audio_response": True,
        "executing_agent_id": "agent_backend",
        "squad_thread_id": "thread_1",
        "squad_task_id": "task_1",
        "parent_message_id": "msg_parent",
        "delegation_chain": ["agent_lead", "agent_backend"],
        "delegation_request_id": "delegation_1",
        "delegation_origin_agent_id": "agent_lead",
        "telegram_message_thread_id": 99,
    }
    assert AgentTurnInput.from_json(snapshot.to_json()).to_dict() == snapshot.to_dict()


def test_from_run_result_builds_success_snapshot_and_round_trips() -> None:
    snapshot = from_run_result(FakeRunResult())

    assert snapshot.to_dict() == {
        "contract_version": "agent_turn.v1",
        "status": "completed",
        "provider": "codex",
        "model": "gpt-5-codex",
        "result": "Done.",
        "session_id": "sess_123",
        "provider_session_id": "prov_sess_456",
        "cost_usd": 0.037,
        "error": False,
        "stop_reason": "completed",
        "usage": {"input_tokens": 100, "output_tokens": 40},
        "tool_uses": [{"name": "shell", "status": "ok"}],
        "native_items": [{"type": "message"}],
        "tool_execution_trace": [{"tool": "shell", "duration_ms": 15}],
        "raw_output": "raw stream",
        "warnings": ["minor warning"],
        "fallback_chain": ["codex"],
        "turn_mode": "resume",
        "supports_native_resume": True,
        "error_kind": "",
        "retryable": False,
        "runtime_terminal_id": 12,
        "runtime_terminal_path": "kernel-stream://stdout",
        "events": [],
        "error_details": None,
    }
    assert AgentTurnOutput.from_dict(snapshot.to_dict()).to_dict() == snapshot.to_dict()


def test_from_run_result_builds_error_envelope() -> None:
    snapshot = from_run_result(
        FakeRunResult(
            result="Provider timed out.",
            error=True,
            stop_reason="timeout",
            error_kind="provider_timeout",
            retryable=True,
        )
    )

    assert snapshot.status == "failed"
    assert snapshot.error_details is not None
    assert snapshot.error_details.to_dict() == {
        "contract_version": "agent_turn.v1",
        "code": "runtime.provider_timeout",
        "category": "timeout",
        "message": "Provider timed out.",
        "retryable": True,
        "user_action": "Retry, cancel, or reduce scope.",
        "trace_id": None,
        "run_graph_node_id": None,
        "detail_ref": None,
        "provider": "codex",
        "error_kind": "provider_timeout",
    }


def test_agent_turn_module_does_not_import_queue_manager() -> None:
    tree = ast.parse(inspect.getsource(agent_turn))

    imported_modules = {alias.name for node in ast.walk(tree) if isinstance(node, ast.Import) for alias in node.names}
    imported_modules.update(node.module or "" for node in ast.walk(tree) if isinstance(node, ast.ImportFrom))

    assert "koda.services.queue_manager" not in imported_modules
    assert "queue_manager" not in imported_modules
