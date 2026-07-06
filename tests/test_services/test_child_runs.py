from __future__ import annotations

from koda.services.child_runs import (
    MAX_CHILD_RUNS_PER_CALL,
    make_child_run_id,
    make_idempotency_key,
    normalize_child_run_requests,
)


def test_normalize_child_run_requests_supports_single_and_fanout() -> None:
    single = normalize_child_run_requests({"goal": "A", "prompt": "Do A", "toolset": "read_only"})
    assert single == [{"goal": "A", "prompt": "Do A", "toolset": "read_only"}]

    fanout = normalize_child_run_requests(
        {
            "toolset": "read_only",
            "timeout_seconds": 180,
            "tasks": [
                {"goal": "A", "prompt": "Do A"},
                {"goal": "B", "prompt": "Do B", "timeout_seconds": 90},
            ],
        }
    )

    assert len(fanout) == 2
    assert fanout[0]["toolset"] == "read_only"
    assert fanout[0]["timeout_seconds"] == 180
    assert fanout[1]["timeout_seconds"] == 90


def test_child_run_ids_are_stable_by_parent_attempt_signature_and_index() -> None:
    left = make_child_run_id(42, 1, "abc", 0)
    right = make_child_run_id(42, 1, "abc", 0)
    other = make_child_run_id(42, 1, "abc", 1)

    assert left == right
    assert left != other
    assert make_idempotency_key(42, 1, "abc", 0).startswith("42:1:abc")
    assert MAX_CHILD_RUNS_PER_CALL == 4
