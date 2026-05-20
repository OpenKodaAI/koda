from __future__ import annotations

import scripts.live_gate_smoke as live_gate_smoke


def test_live_gate_report_marks_missing_external_credentials_blocked() -> None:
    report = live_gate_smoke.build_live_gate_report(env={})

    assert report["schema_version"] == "live_gate_smoke.v1"
    assert report["status"] == "blocked"
    assert all(gate["status"] == "blocked" for gate in report["gates"])
    assert next(gate for gate in report["gates"] if gate["gate_id"] == "telegram_live_e2e")["missing_env"] == [
        "TELEGRAM_BOT_TOKEN",
        "TELEGRAM_TEST_CHAT_ID",
    ]


def test_live_gate_report_becomes_ready_when_every_required_env_is_present() -> None:
    env = {
        "TELEGRAM_BOT_TOKEN": "set",
        "TELEGRAM_TEST_CHAT_ID": "set",
        "SLACK_BOT_TOKEN": "set",
        "SLACK_SIGNING_SECRET": "set",
        "SLACK_TEST_CHANNEL_ID": "set",
        "DISCORD_BOT_TOKEN": "set",
        "DISCORD_TEST_CHANNEL_ID": "set",
        "KODA_PROVIDER_PARITY_LIVE": "1",
        "KODA_AUTH_E2E_BASE_URL": "http://127.0.0.1:3000",
        "KODA_AUTH_E2E_OWNER_EMAIL": "owner@example.com",
        "KODA_AUTH_E2E_OWNER_PASSWORD": "set",
    }

    report = live_gate_smoke.build_live_gate_report(env=env)

    assert report["status"] == "ready"
    assert all(gate["missing_env"] == [] for gate in report["gates"])


def test_live_gate_script_does_not_fail_blocked_by_default(capsys) -> None:  # type: ignore[no-untyped-def]
    result = live_gate_smoke.main([])

    assert result == 0
    assert "live gates" in capsys.readouterr().out
