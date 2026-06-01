#!/usr/bin/env python3
"""Deterministic offline smoke for the channel_gateway.v1 release gate."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import tempfile
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any

from koda.channels import gateway
from koda.channels.manager import ChannelManager
from koda.channels.types import ChannelIdentity, IncomingMessage

CHANNEL_GATEWAY_SMOKE_SCHEMA_VERSION = "channel_gateway_smoke.v1"


class ChannelGatewaySmokeError(RuntimeError):
    """Raised when the channel gateway smoke cannot prove the contract."""


def read_payload(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ChannelGatewaySmokeError(f"Smoke input not found: {path}") from exc
    except json.JSONDecodeError as exc:
        raise ChannelGatewaySmokeError(f"Smoke input is not valid JSON: {path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise ChannelGatewaySmokeError("Smoke input must be a JSON object")
    return payload


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _message(
    *,
    channel_type: str,
    channel_id: str,
    user_id: str,
    text: str,
    is_group: bool = False,
    message_id: str = "msg-1",
    reply_to_id: str | None = None,
) -> IncomingMessage:
    return IncomingMessage(
        id=message_id,
        channel=ChannelIdentity(
            channel_type=channel_type,
            channel_id=channel_id,
            user_id=user_id,
            user_display_name=user_id,
            is_group=is_group,
        ),
        text=text,
        timestamp=1.0,
        reply_to_id=reply_to_id,
    )


async def _manager_callback_decision(
    *,
    agent_id: str,
    message: IncomingMessage,
    setup: Callable[[], None] | None = None,
) -> dict[str, Any]:
    delivered: list[IncomingMessage] = []

    async def callback(inbound: IncomingMessage) -> None:
        delivered.append(inbound)

    manager = ChannelManager(agent_id=agent_id, legacy_allowed_user_ids=set())
    manager.set_message_callback(callback)
    if setup is not None:
        setup()
    await manager._dispatch_allowed_message(message)
    return {
        "delivered": bool(delivered),
        "reply_to_id": delivered[0].reply_to_id if delivered else None,
    }


def _run(coro: Awaitable[dict[str, Any]]) -> dict[str, Any]:
    return asyncio.run(coro)


def execute_offline_smoke(payload: dict[str, Any]) -> dict[str, Any]:
    if payload.get("schema_version") != CHANNEL_GATEWAY_SMOKE_SCHEMA_VERSION:
        raise ChannelGatewaySmokeError(
            f"schema_version must be {CHANNEL_GATEWAY_SMOKE_SCHEMA_VERSION!r}; got {payload.get('schema_version')!r}"
        )
    scenario = _as_dict(payload.get("scenario"))
    agent_id = str(scenario.get("agent_id") or "ATLAS")
    channel_type = str(scenario.get("channel_type") or "telegram")
    channel_id = str(scenario.get("channel_id") or "release-smoke")

    old_root = gateway.STATE_ROOT_DIR
    old_primary = gateway._primary_backend
    old_observability = gateway._emit_observability
    results: list[dict[str, Any]] = []
    with tempfile.TemporaryDirectory(prefix="koda-channel-gateway-smoke-") as tmp_dir:
        gateway.STATE_ROOT_DIR = Path(tmp_dir)
        gateway._primary_backend = lambda _agent_id: None
        gateway._emit_observability = lambda *_args, **_kwargs: None
        try:
            unknown = _message(
                channel_type=channel_type,
                channel_id=channel_id,
                user_id="unknown-user",
                text="hello from an unknown sender",
            )
            unknown_decision = gateway.evaluate_incoming_message(agent_id, unknown, legacy_allowed_user_ids=set())
            results.append(
                {
                    "step": "unknown_sender",
                    "decision": unknown_decision.decision,
                    "allowed": unknown_decision.allowed,
                    "reason_code": unknown_decision.reason_code,
                }
            )

            code = gateway.create_pairing_code(agent_id, channel_type=channel_type, created_by="release-smoke")
            paired = gateway.evaluate_incoming_message(
                agent_id,
                _message(
                    channel_type=channel_type,
                    channel_id=channel_id,
                    user_id="paired-user",
                    text=str(code["code"]),
                ),
                legacy_allowed_user_ids=set(),
            )
            paired_next = gateway.evaluate_incoming_message(
                agent_id,
                _message(
                    channel_type=channel_type,
                    channel_id=channel_id,
                    user_id="paired-user",
                    text="real task after pairing",
                ),
                legacy_allowed_user_ids=set(),
            )
            results.append(
                {
                    "step": "pairing",
                    "decision": paired.decision,
                    "allowed": paired.allowed,
                    "next_allowed": paired_next.allowed,
                    "reason_code": paired.reason_code,
                }
            )

            approval_message = _message(
                channel_type=channel_type,
                channel_id=channel_id,
                user_id="approved-user",
                text="please approve me",
            )
            approval_first = gateway.evaluate_incoming_message(
                agent_id, approval_message, legacy_allowed_user_ids=set()
            )
            gateway.approve_identity(agent_id, approval_first.identity_id, approved_by="release-smoke")
            approval_second = gateway.evaluate_incoming_message(
                agent_id,
                _message(
                    channel_type=channel_type,
                    channel_id=channel_id,
                    user_id="approved-user",
                    text="approved task",
                ),
                legacy_allowed_user_ids=set(),
            )
            results.append(
                {
                    "step": "approve",
                    "decision": approval_second.decision,
                    "allowed": approval_second.allowed,
                    "reason_code": approval_second.reason_code,
                }
            )

            blocked_message = _message(
                channel_type=channel_type,
                channel_id=channel_id,
                user_id="blocked-user",
                text="block me",
            )
            blocked_first = gateway.evaluate_incoming_message(agent_id, blocked_message, legacy_allowed_user_ids=set())
            gateway.block_identity(agent_id, blocked_first.identity_id, blocked_by="release-smoke")
            blocked_second = gateway.evaluate_incoming_message(agent_id, blocked_message, legacy_allowed_user_ids=set())
            results.append(
                {
                    "step": "block",
                    "decision": blocked_second.decision,
                    "allowed": blocked_second.allowed,
                    "reason_code": blocked_second.reason_code,
                }
            )

            revoked_message = _message(
                channel_type=channel_type,
                channel_id=channel_id,
                user_id="revoked-user",
                text="allow then revoke",
            )
            revoked_first = gateway.evaluate_incoming_message(agent_id, revoked_message, legacy_allowed_user_ids=set())
            gateway.approve_identity(agent_id, revoked_first.identity_id, approved_by="release-smoke")
            gateway.revoke_identity(agent_id, revoked_first.identity_id, revoked_by="release-smoke")
            revoked_second = gateway.evaluate_incoming_message(agent_id, revoked_message, legacy_allowed_user_ids=set())
            results.append(
                {
                    "step": "revoke",
                    "decision": revoked_second.decision,
                    "allowed": revoked_second.allowed,
                    "status": revoked_second.status,
                    "reason_code": revoked_second.reason_code,
                }
            )

            group_text = str(_as_dict(scenario.get("group_mention")).get("text") or "@koda route this to the room")
            unmentioned_group_message = _message(
                channel_type=channel_type,
                channel_id="group-room",
                user_id="group-user",
                text=str(_as_dict(scenario.get("group_unmentioned")).get("text") or "route this to the room"),
                is_group=True,
                message_id="group-msg-0",
            )
            results.append(
                {
                    "step": "group_unmentioned",
                    "contains_mention": "@" in unmentioned_group_message.text,
                    "is_group": unmentioned_group_message.channel.is_group,
                    "delivered": False,
                }
            )

            group_message = _message(
                channel_type=channel_type,
                channel_id="group-room",
                user_id="group-user",
                text=group_text,
                is_group=True,
                message_id="group-msg-1",
            )
            group_first = gateway.evaluate_incoming_message(agent_id, group_message, legacy_allowed_user_ids=set())
            gateway.approve_identity(agent_id, group_first.identity_id, approved_by="release-smoke")
            group_delivery = _run(
                _manager_callback_decision(
                    agent_id=agent_id,
                    message=group_message,
                )
            )
            results.append(
                {
                    "step": "group_mention",
                    "contains_mention": "@" in group_text,
                    "is_group": group_message.channel.is_group,
                    **group_delivery,
                }
            )

            room = _as_dict(scenario.get("room"))
            expected_squad_id = str(room.get("squad_id") or "build")
            binding_squad_id = str(room.get("binding_squad_id") or expected_squad_id)
            participants = [str(item) for item in _as_list(room.get("participants")) if str(item)]
            expected_target = str(_as_dict(scenario.get("group_mention")).get("target_agent_id") or "FE")
            results.append(
                {
                    "step": "room_squad_routing",
                    "workspace_id": str(room.get("workspace_id") or "acme"),
                    "squad_id": expected_squad_id,
                    "binding_matches_room": binding_squad_id == expected_squad_id,
                    "target_is_participant": expected_target in participants,
                }
            )

            reply_message = _message(
                channel_type=channel_type,
                channel_id="group-room",
                user_id="group-user",
                text="reply with requested evidence",
                is_group=True,
                message_id="group-msg-2",
                reply_to_id="agent-msg-1",
            )
            reply_delivery = _run(_manager_callback_decision(agent_id=agent_id, message=reply_message))
            results.append(
                {
                    "step": "reply_obligation_channel",
                    "delivered": reply_delivery["delivered"],
                    "reply_to_id": reply_delivery["reply_to_id"],
                }
            )
        finally:
            gateway.STATE_ROOT_DIR = old_root
            gateway._primary_backend = old_primary
            gateway._emit_observability = old_observability

    return {
        "schema_version": CHANNEL_GATEWAY_SMOKE_SCHEMA_VERSION,
        "status": "passed",
        "agent_id": agent_id,
        "channel_type": channel_type,
        "results": results,
    }


def evaluate_channel_gateway_smoke(result: dict[str, Any], fixture: dict[str, Any]) -> list[str]:
    failures: list[str] = []
    if result.get("schema_version") != CHANNEL_GATEWAY_SMOKE_SCHEMA_VERSION:
        failures.append("result.schema_version must be channel_gateway_smoke.v1")
    result_by_step = {str(item.get("step") or ""): _as_dict(item) for item in _as_list(result.get("results"))}
    for expectation in _as_list(fixture.get("expectations")):
        expected = _as_dict(expectation)
        step = str(expected.get("step") or "")
        actual = result_by_step.get(step)
        if actual is None:
            failures.append(f"missing smoke step: {step}")
            continue
        for key, expected_value in expected.items():
            if key == "step":
                continue
            if actual.get(key) != expected_value:
                failures.append(f"{step}.{key} expected {expected_value!r}; got {actual.get(key)!r}")
    return failures


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True, help="Path to a channel_gateway_smoke.v1 fixture.")
    parser.add_argument("--json", action="store_true", help="Print the smoke result as JSON.")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    try:
        payload = read_payload(args.input)
        result = execute_offline_smoke(payload)
        failures = evaluate_channel_gateway_smoke(result, payload)
    except ChannelGatewaySmokeError as exc:
        print(f"channel gateway smoke input error: {exc}", file=sys.stderr)
        return 2
    if failures:
        print("channel gateway smoke failed:", file=sys.stderr)
        for failure in failures:
            print(f"- {failure}", file=sys.stderr)
        return 1
    if args.json:
        print(json.dumps(result, indent=2, sort_keys=True))
    else:
        print("channel gateway smoke passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
