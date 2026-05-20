from __future__ import annotations

import json

from koda.services.evals import build_trajectory_export
from koda.services.run_graph import build_run_graph_from_trace
from koda.services.runtime.redaction import redact_value


def test_streaming_payloads_run_graph_and_exports_do_not_leak_raw_secrets() -> None:
    raw_secret = "sk-live-streaming-secret"
    stream_payload = {
        "event_type": "terminal.stdout",
        "data": f"provider returned Authorization: Bearer abcdefghijklmnopqrstuvwxyz123456 and {raw_secret}",
        "artifact": {"prompt": f"deploy with token={raw_secret}"},
    }

    redacted_stream = redact_value(stream_payload)
    trace = {
        "request": {"query_text": f"Deploy with token={raw_secret}", "model": "gpt-5-codex"},
        "assistant": {"response_text": "Done."},
        "runtime": {"status": "completed", "attempt": 1},
        "tools": [
            {
                "tool": "shell_execute",
                "params": {"api_key": raw_secret, "command": "echo ok"},
                "success": True,
                "output": "Authorization: Bearer abcdefghijklmnopqrstuvwxyz123456",
            }
        ],
        "timeline": [redacted_stream],
    }
    graph = build_run_graph_from_trace(agent_id="KODA", task_id=9991, trace=trace)
    export = build_trajectory_export(
        agent_id="KODA",
        task_id=9991,
        execution={"status": "completed", "query_text": trace["request"]["query_text"]},
        run_graph=graph.to_dict(),
        replay={"schema_version": "run_replay.v1", "steps": []},
    )
    encoded = json.dumps({"stream": redacted_stream, "graph": graph.to_dict(), "export": export}, sort_keys=True)

    assert raw_secret not in encoded
    assert "abcdefghijklmnopqrstuvwxyz123456" not in encoded
    assert "token=sk-live" not in encoded
    assert "[REDACTED]" in encoded or "sha256:" in encoded
