from __future__ import annotations

from koda.channels import gateway
from koda.channels.types import ChannelIdentity, IncomingMessage


def _message(text: str = "hello", *, user_id: str = "42") -> IncomingMessage:
    return IncomingMessage(
        id="msg-1",
        channel=ChannelIdentity(
            channel_type="telegram",
            channel_id="chat-1",
            user_id=user_id,
            user_display_name="Alice",
        ),
        text=text,
        timestamp=1.0,
    )


def _isolate_gateway(monkeypatch, tmp_path):
    monkeypatch.setattr(gateway, "STATE_ROOT_DIR", tmp_path)
    monkeypatch.setattr(gateway, "_primary_backend", lambda _agent_id: None)
    monkeypatch.setattr(gateway, "_emit_observability", lambda *_args, **_kwargs: None)


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


def test_legacy_allowed_user_still_allows_when_fallback_lock_is_unwritable(tmp_path, monkeypatch):
    blocked_root = tmp_path / "not-a-directory"
    blocked_root.write_text("nope", encoding="utf-8")
    _isolate_gateway(monkeypatch, blocked_root)

    decision = gateway.evaluate_incoming_message("ATLAS", _message(user_id="7"), legacy_allowed_user_ids={7})

    assert decision.allowed is True
    assert decision.reason_code == "channel.identity_allowed"


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
    monkeypatch.setattr(gateway.secrets, "token_urlsafe", lambda _length: "ABC12345")

    code = gateway.create_pairing_code("ATLAS", channel_type="telegram", created_by="owner")
    paired = gateway.evaluate_incoming_message("ATLAS", _message(code["code"]), legacy_allowed_user_ids=set())
    next_message = gateway.evaluate_incoming_message("ATLAS", _message("real task"), legacy_allowed_user_ids=set())

    assert paired.allowed is False
    assert paired.reason_code == "channel.pairing_complete"
    assert next_message.allowed is True
    assert gateway.list_pairing_codes("ATLAS") == []
