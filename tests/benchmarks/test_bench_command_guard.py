"""Bench: blocked-pattern matcher hot path.

The dispatcher checks every ``<agent_cmd>`` invocation against the
shell guard. The native DFA replaces Python re.search; this
test pins the speedup so a future refactor that loses the native
backend (``koda_command_guard`` wheel missing → Python fallback) is
caught at PR time."""

from __future__ import annotations

from .conftest import load_baseline, measure_ns_per_op


def test_command_guard_is_blocked_shell_within_baseline() -> None:
    from koda.services.blocked_patterns import is_blocked_shell

    samples_inputs = [
        "ls -la $HOME",
        "git status",
        "rm -rf /etc",
        "cat /var/log/system.log",
        "echo hello",
    ]
    idx = {"i": 0}

    def _call() -> None:
        is_blocked_shell(samples_inputs[idx["i"] % len(samples_inputs)])
        idx["i"] += 1

    measured = measure_ns_per_op(_call, iters=20_000)
    baseline = load_baseline("command_guard")
    assert measured < baseline["max_ns"], (
        f"command_guard regressed: {measured:.0f}ns/op > {baseline['max_ns']}ns/op baseline. "
        f"This usually means the native koda_command_guard wheel is not installed "
        f"and the Python re.search fallback is being used."
    )
