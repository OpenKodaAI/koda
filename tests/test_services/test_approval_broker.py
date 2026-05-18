"""Tests for dashboard approval broker."""

from __future__ import annotations

import asyncio

import pytest

import koda.utils.approval as approval_module
from koda.services.approval_broker import (
    find_pending,
    list_pending_for_session,
    resolve_approval,
)


@pytest.fixture(autouse=True)
def _clear_pending_state(monkeypatch):
    approval_module._PENDING_AGENT_CMD_OPS.clear()
    approval_module._APPROVAL_GRANTS.clear()
    yield
    approval_module._PENDING_AGENT_CMD_OPS.clear()
    approval_module._APPROVAL_GRANTS.clear()


def _register(
    op_id: str,
    *,
    agent_id: str = "atlas",
    session_id: str = "sess-1",
    user_id: int = 7,
    chat_id: int | None = 42,
    task_id: int | None = None,
    description: str = "shell rm -rf tmp",
) -> None:
    approval_module._PENDING_AGENT_CMD_OPS[op_id] = {
        "user_id": user_id,
        "timestamp": 1.0,
        "event": asyncio.Event(),
        "decision": None,
        "description": description,
        "agent_id": agent_id,
        "session_id": session_id,
        "chat_id": chat_id,
        "task_id": task_id,
        "requests": [],
        "grants": [],
        "preview_text": "",
        "tool_id": "file_write",
        "original_params": {"path": "a.txt", "content": "old"},
        "args_schema": {
            "type": "object",
            "properties": {
                "path": {"type": "string"},
                "content": {"type": "string"},
            },
            "required": ["path", "content"],
            "additionalProperties": False,
        },
        "risk_class": "write",
    }


def test_list_pending_filters_by_agent_and_session():
    _register("op-a", agent_id="atlas", session_id="sess-1")
    _register("op-b", agent_id="atlas", session_id="sess-2")
    _register("op-c", agent_id="other", session_id="sess-1")

    pending = list_pending_for_session(agent_id="atlas", session_id="sess-1")
    ids = [item["approval_id"] for item in pending]
    assert ids == ["op-a"]
    assert pending[0]["tool_id"] == "file_write"
    assert pending[0]["original_params"] == {"path": "a.txt", "content": "old"}
    assert pending[0]["args_schema"]["required"] == ["path", "content"]


def test_find_pending_by_task_id():
    _register("op-a", task_id=None)
    _register("op-b", task_id=99)

    assert find_pending(agent_id="atlas", session_id="sess-1", task_id=99) == "op-b"
    assert find_pending(agent_id="atlas", session_id="sess-1") == "op-a"
    # No fallback: if task_id is provided and there's no match, return None
    assert find_pending(agent_id="atlas", session_id="sess-1", task_id=123) is None


@pytest.mark.asyncio
async def test_resolve_approval_marks_decision_and_signals_event(monkeypatch):
    _register("op-x")
    event = approval_module._PENDING_AGENT_CMD_OPS["op-x"]["event"]

    monkeypatch.setattr("koda.services.approval_broker._runtime_broker", lambda: None)
    monkeypatch.setattr(
        approval_module,
        "_issue_agent_approval_grants",
        lambda **_: [],
    )

    summary = await resolve_approval(approval_id="op-x", decision="approve")

    assert summary["decision"] == "approved"
    assert event.is_set()
    assert approval_module._PENDING_AGENT_CMD_OPS["op-x"]["decision"] == "approved"


@pytest.mark.asyncio
async def test_resolve_approval_rejects_unknown_id(monkeypatch):
    monkeypatch.setattr("koda.services.approval_broker._runtime_broker", lambda: None)
    with pytest.raises(KeyError):
        await resolve_approval(approval_id="missing", decision="approve")


@pytest.mark.asyncio
async def test_resolve_approval_validates_decision(monkeypatch):
    _register("op-y")
    monkeypatch.setattr("koda.services.approval_broker._runtime_broker", lambda: None)
    with pytest.raises(ValueError):
        await resolve_approval(approval_id="op-y", decision="abstain")


@pytest.mark.asyncio
async def test_resolve_approval_accepts_schema_valid_edit(monkeypatch):
    _register("op-edit")
    event = approval_module._PENDING_AGENT_CMD_OPS["op-edit"]["event"]
    monkeypatch.setattr("koda.services.approval_broker._runtime_broker", lambda: None)

    summary = await resolve_approval(
        approval_id="op-edit",
        decision="edit",
        edited_params={"path": "a.txt", "content": "new"},
        rationale="tightened content",
    )

    assert summary["decision"] == "edited"
    assert summary["edited_params"] == {"path": "a.txt", "content": "new"}
    assert summary["rationale"] == "tightened content"
    assert event.is_set()
    assert approval_module._PENDING_AGENT_CMD_OPS["op-edit"]["edited_params"] == {
        "path": "a.txt",
        "content": "new",
    }


@pytest.mark.asyncio
async def test_resolve_approval_rejects_schema_invalid_edit(monkeypatch):
    _register("op-bad-edit")
    monkeypatch.setattr("koda.services.approval_broker._runtime_broker", lambda: None)

    with pytest.raises(ValueError, match="missing required field: content"):
        await resolve_approval(
            approval_id="op-bad-edit",
            decision="edit",
            edited_params={"path": "a.txt"},
        )


@pytest.mark.asyncio
async def test_resolve_approval_accepts_operator_response(monkeypatch):
    _register("op-respond")
    monkeypatch.setattr("koda.services.approval_broker._runtime_broker", lambda: None)

    summary = await resolve_approval(
        approval_id="op-respond",
        decision="respond",
        response_text="Use a safer path instead.",
        rationale="avoid overwrite",
    )

    assert summary["decision"] == "responded"
    assert summary["response_text"] == "Use a safer path instead."
    assert approval_module._PENDING_AGENT_CMD_OPS["op-respond"]["response_text"] == "Use a safer path instead."
