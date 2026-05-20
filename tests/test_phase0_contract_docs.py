from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _read(relative: str) -> str:
    return (ROOT / relative).read_text(encoding="utf-8")


def test_phase0_docs_are_indexed() -> None:
    docs_index = _read("docs/README.md")
    operations_index = _read("docs/operations/README.md")
    architecture_overview = _read("docs/architecture/overview.md")
    observability = _read("docs/operations/observability.md")

    assert "architecture/top-tier-phase-contracts.md" in docs_index
    assert "operations/scaling-resilience-runbook.md" in docs_index
    assert "top-tier-phase-contracts.md" in architecture_overview
    assert "scaling-resilience-runbook.md" in operations_index
    assert "top-tier-release-train.md" in operations_index
    assert "scaling-resilience-runbook.md" in observability


def test_phase_contract_defines_delivery_and_resilience_contracts() -> None:
    contract = _read("docs/architecture/top-tier-phase-contracts.md")

    required_terms = [
        "KG-15",
        "KG-14",
        "Error Envelope",
        '"code"',
        '"category"',
        '"retryable"',
        '"user_action"',
        "Runtime State Model",
        "queued",
        "running",
        "retrying",
        "stalled",
        "degraded",
        "failed",
        "cancelled",
        "completed",
        "RunGraph",
        "queue_wait",
        "lease_acquire",
        "breaker_open",
        "dlq_inserted",
        "user_facing_error",
    ]
    for term in required_terms:
        assert term in contract


def test_release_train_maps_all_kg_epics() -> None:
    release_train = _read("docs/operations/top-tier-release-train.md")

    for epic_id in [f"KG-{number:02d}" for number in range(1, 16)]:
        assert epic_id in release_train

    for blocked_rule in [
        "No broad `queue_manager.py` rewrite",
        "No public marketplace before scanner",
        "No channel routing before identity",
    ]:
        assert blocked_rule in release_train or blocked_rule in _read("docs/architecture/top-tier-phase-contracts.md")


def test_scaling_runbook_preserves_current_phase0_budgets() -> None:
    runbook = _read("docs/operations/scaling-resilience-runbook.md")

    required_budgets = [
        "Task lease duration | 60s",
        "Task lease heartbeat | 15s",
        "Task lease janitor interval | 30s",
        "Global max concurrent tasks | 10",
        "Per-user max concurrent tasks | 3",
        "Max queued tasks per user | 25",
        "Runtime/control-plane frontend fetch timeout | 10s",
    ]
    for budget in required_budgets:
        assert budget in runbook

    for marker in ["`bench`", "`chaos`", "Security / deny", "Observability / replay"]:
        assert marker in runbook
