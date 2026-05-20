#!/usr/bin/env python3
"""Credential-aware live smoke gate manifest for external top-tier evidence.

The deterministic offline gates remain the default release checks. This script
records whether live Telegram, Slack, Discord, provider parity, and authenticated
browser E2E gates are runnable in the current environment. Missing credentials
are reported as Blocked evidence, not as a silent pass.
"""

from __future__ import annotations

import argparse
import json
import os
from typing import Any

LIVE_GATE_SCHEMA_VERSION = "live_gate_smoke.v1"

_GATES: tuple[dict[str, Any], ...] = (
    {
        "gate_id": "telegram_live_e2e",
        "kind": "channel",
        "required_env": ("TELEGRAM_BOT_TOKEN", "TELEGRAM_TEST_CHAT_ID"),
        "coverage": ["unknown_sender", "pair", "approve", "block", "revoke", "group_mention"],
    },
    {
        "gate_id": "slack_live_e2e",
        "kind": "channel",
        "required_env": ("SLACK_BOT_TOKEN", "SLACK_SIGNING_SECRET", "SLACK_TEST_CHANNEL_ID"),
        "coverage": ["unknown_sender", "approve", "block", "revoke", "mention"],
    },
    {
        "gate_id": "discord_live_e2e",
        "kind": "channel",
        "required_env": ("DISCORD_BOT_TOKEN", "DISCORD_TEST_CHANNEL_ID"),
        "coverage": ["unknown_sender", "approve", "block", "revoke", "mention"],
    },
    {
        "gate_id": "provider_live_parity",
        "kind": "provider",
        "required_env": ("KODA_PROVIDER_PARITY_LIVE",),
        "coverage": ["native", "fallback", "redaction", "cost"],
    },
    {
        "gate_id": "browser_authenticated_e2e",
        "kind": "browser",
        "required_env": ("KODA_AUTH_E2E_BASE_URL", "KODA_AUTH_E2E_OWNER_EMAIL", "KODA_AUTH_E2E_OWNER_PASSWORD"),
        "coverage": ["setup", "proposals", "memory", "skills", "handoffs", "quality_cockpit", "release_blockers"],
    },
)


def build_live_gate_report(env: dict[str, str] | None = None) -> dict[str, Any]:
    source_env = env if env is not None else os.environ
    gates: list[dict[str, Any]] = []
    for spec in _GATES:
        missing = [key for key in spec["required_env"] if not str(source_env.get(key) or "").strip()]
        gates.append(
            {
                "schema_version": LIVE_GATE_SCHEMA_VERSION,
                "gate_id": spec["gate_id"],
                "kind": spec["kind"],
                "status": "ready" if not missing else "blocked",
                "required_env": list(spec["required_env"]),
                "missing_env": missing,
                "coverage": list(spec["coverage"]),
                "block_reason": (
                    "" if not missing else "External credentials/infrastructure are not configured for this live gate."
                ),
            }
        )
    return {
        "schema_version": LIVE_GATE_SCHEMA_VERSION,
        "status": "ready" if all(item["status"] == "ready" for item in gates) else "blocked",
        "gates": gates,
    }


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true", help="Print live gate status as JSON.")
    parser.add_argument(
        "--fail-on-blocked",
        action="store_true",
        help="Return exit code 1 when any live gate is blocked.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    report = build_live_gate_report()
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        print(f"live gates {report['status']}")
        for gate in report["gates"]:
            missing = ", ".join(gate["missing_env"])
            suffix = f" ({missing})" if missing else ""
            print(f"- {gate['gate_id']}: {gate['status']}{suffix}")
    if args.fail_on_blocked and report["status"] == "blocked":
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
