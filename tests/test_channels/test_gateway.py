from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from koda.channels import gateway
from koda.channels.types import ChannelIdentity, IncomingMessage
from scripts.channel_gateway_smoke import InMemoryChannelGatewayBackend


def _message(text: str = "hello", *, user_id: str = "42", channel_id: str = "chat-1") -> IncomingMessage:
    return IncomingMessage(
        id="msg-1",
        channel=ChannelIdentity(
            channel_type="telegram",
            channel_id=channel_id,
            user_id=user_id,
            user_display_name="Alice",
        ),
        text=text,
        timestamp=1.0,
    )


def _isolate_gateway(monkeypatch, tmp_path) -> InMemoryChannelGatewayBackend:
    backend = InMemoryChannelGatewayBackend()
    monkeypatch.setattr(gateway, "_primary_backend", lambda _agent_id: backend)
    monkeypatch.setattr(gateway, "_emit_observability", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(gateway, "_PAIRING_FAILURES", {}, raising=False)
    monkeypatch.setattr(gateway, "_PAIRING_LOCKED_UNTIL", {}, raising=False)
    return backend


def test_unknown_sender_is_queued_and_denied(tmp_path, monkeypatch):
    _isolate_gateway(monkeypatch, tmp_path)

    decision = gateway.evaluate_incoming_message("ATLAS", _message(), legacy_allowed_user_ids=set())

    assert decision.allowed is False
    assert decision.reason_code == "channel.identity_unknown"
    state = gateway.gateway_state("ATLAS")
    assert state["summary"]["pending"] == 1
    assert state["unknown_senders"][0]["user_id"] == "42"


def test_operator_approval_allows_next_message(tmp_path, monkeypatch):
    _isolate_gateway(monkeypatch, tmp_path)

    first = gateway.evaluate_incoming_message("ATLAS", _message(), legacy_allowed_user_ids=set())
    gateway.approve_identity("ATLAS", first.identity_id, approved_by="owner")
    second = gateway.evaluate_incoming_message("ATLAS", _message(), legacy_allowed_user_ids=set())

    assert second.allowed is True
    assert second.reason_code == "channel.identity_allowed"
    state = gateway.gateway_state("ATLAS")
    assert state["summary"]["allowed"] == 1
    assert state["summary"]["pending"] == 0


def test_legacy_allowed_user_id_preserves_compatibility(tmp_path, monkeypatch):
    _isolate_gateway(monkeypatch, tmp_path)

    decision = gateway.evaluate_incoming_message("ATLAS", _message(user_id="7"), legacy_allowed_user_ids={7})

    assert decision.allowed is True
    assert decision.status == "allowed"
    assert gateway.gateway_state("ATLAS")["identities"][0]["source"] == "legacy_allowed_user_ids"


def test_legacy_allowed_user_still_allows_without_a_primary_backend_or_a_state_file(tmp_path, monkeypatch):
    _isolate_gateway(monkeypatch, tmp_path)
    monkeypatch.setattr(gateway, "_primary_backend", lambda _agent_id: None)
    monkeypatch.setattr(gateway, "STATE_ROOT_DIR", tmp_path, raising=False)

    decision = gateway.evaluate_incoming_message("ATLAS", _message(user_id="7"), legacy_allowed_user_ids={7})

    assert decision.allowed is True
    assert decision.reason_code == "channel.identity_allowed"
    assert list(tmp_path.iterdir()) == []


def test_without_a_primary_backend_nothing_is_written_to_a_state_file(tmp_path, monkeypatch):
    _isolate_gateway(monkeypatch, tmp_path)
    monkeypatch.setattr(gateway, "_primary_backend", lambda _agent_id: None)
    monkeypatch.setattr(gateway, "STATE_ROOT_DIR", tmp_path, raising=False)

    unknown = gateway.evaluate_incoming_message("ATLAS", _message(), legacy_allowed_user_ids=set())
    gateway.create_pairing_code("ATLAS", created_by="owner")

    assert unknown.allowed is False
    assert list(tmp_path.iterdir()) == []
    assert gateway.gateway_state("ATLAS")["unknown_senders"] == []


def test_removed_legacy_allowlist_entry_denies_previous_legacy_mirror(tmp_path, monkeypatch):
    _isolate_gateway(monkeypatch, tmp_path)

    first = gateway.evaluate_incoming_message("ATLAS", _message(user_id="7"), legacy_allowed_user_ids={7})
    second = gateway.evaluate_incoming_message("ATLAS", _message(user_id="7"), legacy_allowed_user_ids=set())

    assert first.allowed is True
    assert second.allowed is False
    assert second.reason_code == "channel.identity_unknown"


def test_blocked_identity_remains_fail_closed(tmp_path, monkeypatch):
    _isolate_gateway(monkeypatch, tmp_path)

    decision = gateway.evaluate_incoming_message("ATLAS", _message(), legacy_allowed_user_ids=set())
    gateway.block_identity("ATLAS", decision.identity_id, blocked_by="owner")

    blocked = gateway.evaluate_incoming_message("ATLAS", _message(), legacy_allowed_user_ids={42})

    assert blocked.allowed is False
    assert blocked.reason_code == "channel.policy_denied"


def test_pairing_code_pairs_sender_without_enqueuing_code_text(tmp_path, monkeypatch):
    _isolate_gateway(monkeypatch, tmp_path)

    code = gateway.create_pairing_code("ATLAS", channel_type="telegram", created_by="owner")
    paired = gateway.evaluate_incoming_message("ATLAS", _message(code["code"]), legacy_allowed_user_ids=set())
    next_message = gateway.evaluate_incoming_message("ATLAS", _message("real task"), legacy_allowed_user_ids=set())

    assert paired.allowed is False
    assert paired.reason_code == "channel.pairing_complete"
    assert next_message.allowed is True
    assert gateway.list_pairing_codes("ATLAS") == []


def _code() -> str:
    return str(gateway.create_pairing_code("ATLAS", channel_type="telegram", created_by="owner")["code"])


def _wrong(index: int) -> str:
    """A wrong guess with the shape of a pairing code."""
    return f"WRONG{index:03d}"


def test_start_command_pairing_guesses_count_toward_the_lockout(tmp_path, monkeypatch):
    _isolate_gateway(monkeypatch, tmp_path)
    code = _code()

    reasons = [
        gateway.evaluate_incoming_message(
            "ATLAS", _message(f"/start {_wrong(index)}"), legacy_allowed_user_ids=set()
        ).reason_code
        for index in range(gateway.PAIRING_MAX_FAILURES)
    ]
    locked = gateway.evaluate_incoming_message("ATLAS", _message(f"/start {code}"), legacy_allowed_user_ids=set())
    other = gateway.evaluate_incoming_message(
        "ATLAS", _message(f"/start {code}", user_id="43"), legacy_allowed_user_ids=set()
    )

    assert reasons[-1] == "channel.pairing_locked"
    assert locked.reason_code == "channel.pairing_locked"
    assert other.reason_code == "channel.pairing_complete"


def test_pairing_codes_always_have_the_shape_of_a_pairing_attempt(tmp_path, monkeypatch):
    _isolate_gateway(monkeypatch, tmp_path)

    codes = [_code() for _ in range(200)]

    assert {len(code) for code in codes} == {gateway.PAIRING_CODE_LENGTH}
    assert all(gateway._pairing_attempt(code) == code for code in codes)
    assert all(gateway._pairing_attempt(f"/start {code.lower()}") == code for code in codes)


def test_chit_chat_does_not_use_up_pairing_attempts(tmp_path, monkeypatch):
    _isolate_gateway(monkeypatch, tmp_path)
    code = _code()

    reasons = [
        gateway.evaluate_incoming_message("ATLAS", _message(text), legacy_allowed_user_ids=set()).reason_code
        for text in ("hi", "hello", "test", "ok", "thanks", "please", "/start")
    ]
    paired = gateway.evaluate_incoming_message("ATLAS", _message(code), legacy_allowed_user_ids=set())

    assert set(reasons) == {"channel.identity_unknown"}
    assert paired.reason_code == "channel.pairing_complete"


def test_pairing_failures_count_per_sender_across_chats(tmp_path, monkeypatch):
    _isolate_gateway(monkeypatch, tmp_path)
    code = _code()

    reasons = [
        gateway.evaluate_incoming_message(
            "ATLAS", _message(_wrong(index), channel_id=f"group-{index}"), legacy_allowed_user_ids=set()
        ).reason_code
        for index in range(gateway.PAIRING_MAX_FAILURES)
    ]
    locked = gateway.evaluate_incoming_message(
        "ATLAS", _message(code, channel_id="group-new"), legacy_allowed_user_ids=set()
    )

    assert reasons[-1] == "channel.pairing_locked"
    assert locked.reason_code == "channel.pairing_locked"


def test_expired_pairing_lockouts_are_pruned(tmp_path, monkeypatch):
    _isolate_gateway(monkeypatch, tmp_path)
    monkeypatch.setattr(gateway, "_PAIRING_STATE_MAX", 2, raising=False)
    monkeypatch.setattr(gateway, "_clock", lambda: 10_000.0)
    gateway._PAIRING_LOCKED_UNTIL.update({"stale-1": 1.0, "stale-2": 2.0, "stale-3": 3.0})

    for index in range(gateway.PAIRING_MAX_FAILURES):
        gateway.evaluate_incoming_message("ATLAS", _message(_wrong(index)), legacy_allowed_user_ids=set())

    assert len(gateway._PAIRING_LOCKED_UNTIL) == 1
    assert not {"stale-1", "stale-2", "stale-3"} & set(gateway._PAIRING_LOCKED_UNTIL)


def test_one_message_tries_at_most_one_pairing_code(tmp_path, monkeypatch):
    _isolate_gateway(monkeypatch, tmp_path)
    code = _code()

    guess = gateway.evaluate_incoming_message(
        "ATLAS", _message(f"AAAA111 BBBB222 {code} CCCC333"), legacy_allowed_user_ids=set()
    )

    assert guess.reason_code == "channel.identity_unknown"
    assert len(gateway.list_pairing_codes("ATLAS")) == 1


def test_repeated_pairing_failures_lock_the_sender_out(tmp_path, monkeypatch):
    backend = _isolate_gateway(monkeypatch, tmp_path)
    code = _code()
    clock = [1000.0]
    monkeypatch.setattr(gateway, "_clock", lambda: clock[0])

    reasons = [
        gateway.evaluate_incoming_message("ATLAS", _message(_wrong(index)), legacy_allowed_user_ids=set()).reason_code
        for index in range(gateway.PAIRING_MAX_FAILURES)
    ]
    locked = gateway.evaluate_incoming_message("ATLAS", _message(code), legacy_allowed_user_ids=set())

    assert reasons[:-1] == ["channel.identity_unknown"] * (gateway.PAIRING_MAX_FAILURES - 1)
    assert reasons[-1] == "channel.pairing_locked"
    assert locked.allowed is False
    assert locked.reason_code == "channel.pairing_locked"
    assert len(gateway.list_pairing_codes("ATLAS")) == 1
    assert [event["event_type"] for event in backend.events].count("pairing_locked_out") == 1
    assert "Too many pairing attempts" in gateway.denial_message_for_decision(locked.to_dict())

    # Another sender is not affected, and the lockout ends after its window.
    other = gateway.evaluate_incoming_message("ATLAS", _message("hello", user_id="43"), legacy_allowed_user_ids=set())
    assert other.reason_code == "channel.identity_unknown"
    clock[0] += gateway.PAIRING_LOCKOUT_SECONDS + 1
    paired = gateway.evaluate_incoming_message("ATLAS", _message(code), legacy_allowed_user_ids=set())
    assert paired.reason_code == "channel.pairing_complete"


def test_expired_pairing_code_is_a_failed_attempt(tmp_path, monkeypatch):
    backend = _isolate_gateway(monkeypatch, tmp_path)
    code = _code()
    for row in backend.pairing_codes.values():
        row["expires_at"] = (datetime.now(UTC) - timedelta(seconds=1)).isoformat()

    reasons = [
        gateway.evaluate_incoming_message("ATLAS", _message(code), legacy_allowed_user_ids=set()).reason_code
        for _ in range(gateway.PAIRING_MAX_FAILURES)
    ]

    assert reasons[:-1] == ["channel.identity_unknown"] * (gateway.PAIRING_MAX_FAILURES - 1)
    assert reasons[-1] == "channel.pairing_locked"


def test_identity_is_written_only_on_state_transitions(tmp_path, monkeypatch):
    backend = _isolate_gateway(monkeypatch, tmp_path)

    for _ in range(3):
        gateway.evaluate_incoming_message("ATLAS", _message("hello there"), legacy_allowed_user_ids=set())
    assert backend.identity_writes == 1

    for _ in range(3):
        gateway.evaluate_incoming_message("ATLAS", _message("task", user_id="7"), legacy_allowed_user_ids={7})
    assert backend.identity_writes == 2


def test_message_handling_does_not_overwrite_a_concurrent_approval(tmp_path, monkeypatch):
    _isolate_gateway(monkeypatch, tmp_path)
    first = gateway.evaluate_incoming_message("ATLAS", _message("hello there"), legacy_allowed_user_ids=set())
    original_list = gateway._list_primary_identities
    approved: list[bool] = []

    def stale_read_then_control_plane_approval(agent_id: str):
        rows = original_list(agent_id)
        if not approved:
            approved.append(True)
            gateway.approve_identity("ATLAS", first.identity_id, approved_by="owner")
        return rows

    monkeypatch.setattr(gateway, "_list_primary_identities", stale_read_then_control_plane_approval)
    gateway.evaluate_incoming_message("ATLAS", _message("still waiting"), legacy_allowed_user_ids=set())
    monkeypatch.setattr(gateway, "_list_primary_identities", original_list)

    # The resolved queue entry stays resolved: the dashboard does not show the
    # approved sender as pending review again.
    state = gateway.gateway_state("ATLAS")
    assert [item["status"] for item in state["identities"]] == ["allowed"]
    assert state["unknown_senders"] == []
    assert state["summary"]["pending"] == 0

    after = gateway.evaluate_incoming_message("ATLAS", _message("real task"), legacy_allowed_user_ids=set())

    assert after.allowed is True
    assert after.reason_code == "channel.identity_allowed"


@pytest.mark.parametrize(
    ("operator_action", "legacy_allowed_user_ids", "next_reason"),
    [
        ("block", set(), "channel.policy_denied"),
        ("block", {42}, "channel.policy_denied"),
        ("approve", set(), "channel.identity_allowed"),
    ],
)
def test_failed_identity_read_denies_without_overwriting_the_stored_status(
    tmp_path, monkeypatch, operator_action, legacy_allowed_user_ids, next_reason
):
    backend = _isolate_gateway(monkeypatch, tmp_path)
    first = gateway.evaluate_incoming_message("ATLAS", _message(), legacy_allowed_user_ids=set())
    if operator_action == "block":
        gateway.block_identity("ATLAS", first.identity_id, blocked_by="owner")
    else:
        gateway.approve_identity("ATLAS", first.identity_id, approved_by="owner")
    stored = [dict(row) for row in backend.identities.values()]
    writes = backend.identity_writes
    original_list = backend.list_channel_gateway_identities
    failures = [TimeoutError("pool exhausted")]

    async def read_failing_once(agent_id: str):
        if failures:
            raise failures.pop()
        return await original_list(agent_id)

    monkeypatch.setattr(backend, "list_channel_gateway_identities", read_failing_once)
    code = _code()

    during = gateway.evaluate_incoming_message("ATLAS", _message(code), legacy_allowed_user_ids=legacy_allowed_user_ids)

    assert during.allowed is False
    assert during.decision == "deny"
    assert during.reason_code == "channel.gateway_unavailable"
    assert "try again" in gateway.denial_message_for_decision(during.to_dict())
    assert backend.identity_writes == writes
    assert [dict(row) for row in backend.identities.values()] == stored
    assert gateway.gateway_state("ATLAS")["summary"]["pending"] == 0
    assert len(gateway.list_pairing_codes("ATLAS")) == 1

    after = gateway.evaluate_incoming_message("ATLAS", _message(), legacy_allowed_user_ids=legacy_allowed_user_ids)

    assert after.reason_code == next_reason
