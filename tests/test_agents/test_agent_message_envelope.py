from __future__ import annotations

from koda.agents.models import AgentMessage


def test_agent_message_legacy_fields_populate_envelope() -> None:
    msg = AgentMessage(
        from_agent="PM",
        to_agent="FE",
        content="Build UI",
        message_type="delegation_request",
        metadata={"thread_id": "00000000-0000-0000-0000-000000000001", "request_id": "r1"},
        message_id="msg-1",
    )
    assert msg.to_agent_ids == ["FE"]
    assert msg.thread_id == "00000000-0000-0000-0000-000000000001"
    assert msg.kind == "delegation_request"
    assert msg.correlation_id == "r1"
    assert msg.payload["text"] == "Build UI"


def test_agent_message_from_envelope_keeps_legacy_adapter() -> None:
    msg = AgentMessage.from_envelope(
        message_id="msg-2",
        thread_id="00000000-0000-0000-0000-000000000001",
        from_agent="FE",
        to_agent_ids=["PM"],
        kind="task_result",
        payload={"output_md": "Done", "status": "ok"},
        correlation_id="task-1",
    )
    assert msg.to_agent == "PM"
    assert msg.content == "Done"
    assert msg.message_type == "task_result"
    assert msg.to_envelope_dict()["payload"]["status"] == "ok"
    assert msg.to_legacy_dict()["content"] == "Done"
