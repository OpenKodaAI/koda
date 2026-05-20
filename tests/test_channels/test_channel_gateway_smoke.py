from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path

import pytest

import scripts.channel_gateway_smoke as channel_gateway_smoke
from koda.channels import gateway
from koda.channels.manager import ChannelManager
from koda.channels.types import ChannelIdentity, IncomingMessage

FIXTURE_ROOT = Path(__file__).resolve().parents[1] / "fixtures" / "channels"


def _fixture(name: str) -> dict[str, object]:
    return json.loads((FIXTURE_ROOT / name).read_text(encoding="utf-8"))


def _message(text: str = "hello", *, user_id: str = "42", is_group: bool = False) -> IncomingMessage:
    return IncomingMessage(
        id="msg-1",
        channel=ChannelIdentity(
            channel_type="telegram",
            channel_id="-100" if is_group else "chat-1",
            user_id=user_id,
            user_display_name="Alice",
            is_group=is_group,
        ),
        text=text,
        timestamp=1.0,
    )


def _isolate_gateway(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(gateway, "STATE_ROOT_DIR", tmp_path)
    monkeypatch.setattr(gateway, "_primary_backend", lambda _agent_id: None)
    monkeypatch.setattr(gateway, "_emit_observability", lambda *_args, **_kwargs: None)


def test_kat_060_channel_gateway_smoke_fixture_passes() -> None:
    payload = _fixture("channel_gateway_smoke.v1.json")

    result = channel_gateway_smoke.execute_offline_smoke(payload)
    failures = channel_gateway_smoke.evaluate_channel_gateway_smoke(result, payload)

    assert failures == []


def test_channel_gateway_smoke_script_passes_fixture(capsys: pytest.CaptureFixture[str]) -> None:
    result = channel_gateway_smoke.main(["--input", str(FIXTURE_ROOT / "channel_gateway_smoke.v1.json")])

    assert result == 0
    assert "channel gateway smoke passed" in capsys.readouterr().out


def test_channel_gateway_smoke_fails_when_denied_sender_would_queue() -> None:
    payload = deepcopy(_fixture("channel_gateway_smoke.v1.json"))
    payload["expectations"][0]["allowed"] = True

    result = channel_gateway_smoke.execute_offline_smoke(payload)
    failures = channel_gateway_smoke.evaluate_channel_gateway_smoke(result, payload)

    assert any("unknown_sender.allowed" in failure for failure in failures)


def test_channel_gateway_smoke_fails_when_revoked_or_blocked_is_allowed() -> None:
    payload = deepcopy(_fixture("channel_gateway_smoke.v1.json"))
    for expectation in payload["expectations"]:
        if expectation["step"] in {"block", "revoke"}:
            expectation["allowed"] = True

    result = channel_gateway_smoke.execute_offline_smoke(payload)
    failures = channel_gateway_smoke.evaluate_channel_gateway_smoke(result, payload)

    assert any("block.allowed" in failure for failure in failures)
    assert any("revoke.allowed" in failure for failure in failures)


def test_channel_gateway_smoke_fails_when_group_unmentioned_is_not_ignored() -> None:
    payload = deepcopy(_fixture("channel_gateway_smoke.v1.json"))
    for expectation in payload["expectations"]:
        if expectation["step"] == "group_unmentioned":
            expectation["delivered"] = True

    result = channel_gateway_smoke.execute_offline_smoke(payload)
    failures = channel_gateway_smoke.evaluate_channel_gateway_smoke(result, payload)

    assert any("group_unmentioned.delivered" in failure for failure in failures)


def test_channel_gateway_smoke_fails_when_group_mention_does_not_route() -> None:
    payload = deepcopy(_fixture("channel_gateway_smoke.v1.json"))
    for expectation in payload["expectations"]:
        if expectation["step"] == "group_mention":
            expectation["delivered"] = False

    result = channel_gateway_smoke.execute_offline_smoke(payload)
    failures = channel_gateway_smoke.evaluate_channel_gateway_smoke(result, payload)

    assert any("group_mention.delivered" in failure for failure in failures)


def test_channel_gateway_smoke_fails_when_room_squad_route_mismatches() -> None:
    payload = deepcopy(_fixture("channel_gateway_smoke.v1.json"))
    payload["scenario"]["room"]["binding_squad_id"] = "ops"

    result = channel_gateway_smoke.execute_offline_smoke(payload)
    failures = channel_gateway_smoke.evaluate_channel_gateway_smoke(result, payload)

    assert any("room_squad_routing.binding_matches_room" in failure for failure in failures)


def test_channel_gateway_smoke_fails_when_reply_obligation_is_not_delivered() -> None:
    payload = deepcopy(_fixture("channel_gateway_smoke.v1.json"))
    for expectation in payload["expectations"]:
        if expectation["step"] == "reply_obligation_channel":
            expectation["reply_to_id"] = None

    result = channel_gateway_smoke.execute_offline_smoke(payload)
    failures = channel_gateway_smoke.evaluate_channel_gateway_smoke(result, payload)

    assert any("reply_obligation_channel.reply_to_id" in failure for failure in failures)


def test_denied_sender_stays_before_queue_until_gateway_allows(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _isolate_gateway(monkeypatch, tmp_path)
    queued: list[str] = []

    decision = gateway.evaluate_incoming_message("WORKER", _message(), legacy_allowed_user_ids=set())
    if decision.allowed:
        queued.append("task")

    assert queued == []
    assert decision.reason_code == "channel.identity_unknown"


def test_revoked_identity_remains_fail_closed_with_legacy_allowlist(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _isolate_gateway(monkeypatch, tmp_path)

    allowed = gateway.evaluate_incoming_message("WORKER", _message(user_id="7"), legacy_allowed_user_ids={7})
    gateway.revoke_identity("WORKER", allowed.identity_id, revoked_by="owner")
    revoked = gateway.evaluate_incoming_message("WORKER", _message(user_id="7"), legacy_allowed_user_ids={7})

    assert revoked.allowed is False
    assert revoked.reason_code == "channel.policy_denied"


def test_blocked_identity_remains_fail_closed_with_legacy_allowlist(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _isolate_gateway(monkeypatch, tmp_path)

    pending = gateway.evaluate_incoming_message("WORKER", _message(user_id="8"), legacy_allowed_user_ids=set())
    gateway.block_identity("WORKER", pending.identity_id, blocked_by="owner")
    blocked = gateway.evaluate_incoming_message("WORKER", _message(user_id="8"), legacy_allowed_user_ids={8})

    assert blocked.allowed is False
    assert blocked.reason_code == "channel.policy_denied"


@pytest.mark.asyncio
async def test_channel_manager_gateway_failure_is_fail_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    delivered: list[IncomingMessage] = []

    async def callback(inbound: IncomingMessage) -> None:
        delivered.append(inbound)

    manager = ChannelManager(agent_id="WORKER", legacy_allowed_user_ids=set())
    manager.set_message_callback(callback)

    def fail_gateway(*_args: object, **_kwargs: object) -> None:
        raise RuntimeError("boom")

    monkeypatch.setattr("koda.channels.manager.evaluate_incoming_message", fail_gateway)

    await manager._dispatch_allowed_message(_message("@FE please check", is_group=True))

    assert delivered == []
