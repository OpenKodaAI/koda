from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _read(relative: str) -> str:
    return (ROOT / relative).read_text(encoding="utf-8")


def test_assurance_doc_is_indexed_and_lists_every_epic() -> None:
    docs_index = _read("docs/README.md")
    operations_index = _read("docs/operations/README.md")
    assurance = _read("docs/operations/top-tier-roadmap-assurance.md")

    assert "operations/top-tier-roadmap-assurance.md" in docs_index
    assert "top-tier-roadmap-assurance.md" in operations_index

    for epic_id in [f"KG-{number:02d}" for number in range(1, 16)]:
        assert f"| {epic_id} " in assurance

    for epic_id in [f"KG-{number:02d}" for number in range(1, 16)]:
        row = next(line for line in assurance.splitlines() if line.startswith(f"| {epic_id} "))
        assert "Implemented" in row

    assert "100% line or" in assurance


def test_assurance_evidence_files_exist_for_implemented_epics() -> None:
    expected_paths = [
        "koda/agent_turn.py",
        "koda/services/tool_registry.py",
        "koda/services/openai_compatible_runner.py",
        "koda/services/approval_broker.py",
        "koda/services/run_graph.py",
        "koda/services/run_graph_store.py",
        "koda/services/sandbox_policy.py",
        "koda/services/sandbox_doctor.py",
        "koda/services/mcp_risk.py",
        "koda/skills/_package.py",
        "koda/services/child_runs.py",
        "koda/services/context_governance.py",
        "koda/services/evals.py",
        "koda/channels/gateway.py",
        "koda/services/onboarding_readiness.py",
        "scripts/eval_smoke.py",
        "docs/architecture/agent-turn-contract.md",
        "docs/architecture/tool-registry-native-tools.md",
        "docs/architecture/run-graph-replay.md",
        "docs/architecture/koda-skill-plugin-sdk.md",
        "docs/architecture/evals-release-quality.md",
        "docs/architecture/channel-gateway-onboarding.md",
        "docs/operations/top-tier-release-train.md",
        "docs/operations/scaling-resilience-runbook.md",
        "docs/operations/channel-gateway-runbook.md",
        "docs/operations/onboarding-readiness-runbook.md",
        "docs/operations/top-tier-roadmap-assurance.md",
    ]

    for relative in expected_paths:
        assert (ROOT / relative).exists(), relative


def test_contract_versions_migrations_and_metrics_are_anchored() -> None:
    checks = [
        ("koda/agent_turn.py", "agent_turn.v1"),
        ("koda/services/tool_registry.py", "tool-definition.v1"),
        ("koda/services/run_graph.py", "run_graph.v1"),
        ("koda/services/sandbox_policy.py", "sandbox_policy.v1"),
        ("koda/services/mcp_risk.py", "mcp_risk.v1"),
        ("koda/skills/_package.py", "koda_skill.v1"),
        ("koda/services/child_runs.py", "child_run.v1"),
        ("koda/services/context_governance.py", "context_governance.v1"),
        ("koda/services/evals.py", "eval_case.v1"),
        ("koda/services/evals.py", "eval_run.v1"),
        ("koda/services/evals.py", "trajectory_export.v1"),
        ("koda/services/evals.py", "release_quality.v1"),
        ("koda/channels/gateway.py", "channel_gateway.v1"),
        ("koda/services/onboarding_readiness.py", "onboarding_readiness.v1"),
        ("koda/knowledge/v2/postgres_backend.py", "036_run_graph_v1"),
        ("koda/knowledge/v2/postgres_backend.py", "037_child_runs_v1"),
        ("koda/knowledge/v2/postgres_backend.py", "038_skill_packages_v1"),
        ("koda/knowledge/v2/postgres_backend.py", "039_evals_release_quality_v1"),
        ("koda/knowledge/v2/postgres_backend.py", "040_channel_gateway_onboarding_v1"),
        ("koda/services/metrics.py", "EVAL_CASE_EVENTS"),
        ("koda/services/metrics.py", "TRAJECTORY_EXPORTS"),
        ("koda/services/metrics.py", "RELEASE_QUALITY_GATES"),
        ("koda/services/metrics.py", "CHANNEL_GATEWAY_EVENTS"),
        ("koda/services/metrics.py", "ONBOARDING_READINESS_CHECKS"),
    ]

    for relative, token in checks:
        assert token in _read(relative), f"{token} missing from {relative}"


def test_phase5_canonical_api_and_release_quality_gates_do_not_drift() -> None:
    api = _read("koda/control_plane/api.py")
    manager = _read("koda/control_plane/manager.py")
    evals_runbook = _read("docs/operations/evals-release-runbook.md")
    web_contract = _read("apps/web/src/lib/contracts/evals.ts")
    smoke = _read("scripts/eval_smoke.py")

    for handler in [
        "create_eval_case_from_run_route",
        "list_eval_cases_route",
        "patch_eval_case_route",
        "run_eval_suite_route",
        "get_eval_run_route",
        "create_trajectory_export_route",
        "get_release_quality_latest_route",
    ]:
        assert handler in api

    for method in [
        "create_eval_case_from_run",
        "run_eval_suite",
        "create_trajectory_export",
        "get_release_quality_latest",
    ]:
        assert f"def {method}" in manager

    for schema in [
        "createEvalFromRunBodySchema",
        "createEvalRunBodySchema",
        "createTrajectoryExportBodySchema",
        "releaseQualitySchema",
    ]:
        assert schema in web_contract

    for gate in [
        "deterministic_eval_suite",
        "trajectory_export_redaction",
        "tool_policy_regression",
        "release_quality.v1",
    ]:
        assert gate in smoke

    assert "scripts/eval_smoke.py --input tests/fixtures/evals/release_quality.v1.pass.json" in evals_runbook
    assert "scripts/eval_smoke.py --suite" not in evals_runbook


def test_phase6_channel_gateway_and_onboarding_do_not_drift() -> None:
    assurance = _read("docs/operations/top-tier-roadmap-assurance.md")
    release_train = _read("docs/operations/top-tier-release-train.md")
    phase_contracts = _read("docs/architecture/top-tier-phase-contracts.md")
    api = _read("koda/control_plane/api.py")
    manager = _read("koda/control_plane/manager.py")
    web_gateway_contract = _read("apps/web/src/lib/contracts/channel-gateway.ts")
    web_readiness_contract = _read("apps/web/src/lib/contracts/onboarding-readiness.ts")
    openapi = _read("docs/openapi/control-plane.json")

    for text in [assurance, release_train, phase_contracts]:
        assert "KG-12" in text
        assert "KG-13" in text

    assert "channel_gateway.v1" in assurance
    assert "onboarding_readiness.v1" in assurance
    assert "No channel routing before identity" in phase_contracts

    for handler in [
        "get_channel_gateway_route",
        "create_channel_gateway_pairing_code_route",
        "list_channel_gateway_unknown_senders_route",
        "approve_channel_gateway_identity_route",
        "block_channel_gateway_identity_route",
        "revoke_channel_gateway_identity_route",
        "onboarding_readiness",
        "onboarding_first_task",
    ]:
        assert handler in api

    for method in [
        "get_channel_gateway_state",
        "create_channel_gateway_pairing_code",
        "approve_channel_gateway_identity",
        "block_channel_gateway_identity",
        "revoke_channel_gateway_identity",
        "get_onboarding_readiness",
        "create_onboarding_first_task",
    ]:
        assert f"def {method}" in manager

    for schema in [
        "channelGatewayStateSchema",
        "channelGatewayIdentitySchema",
        "channelUnknownSenderSchema",
        "createPairingCodeBodySchema",
    ]:
        assert schema in web_gateway_contract

    for schema in [
        "onboardingReadinessSchema",
        "onboardingReadinessCheckSchema",
        "onboardingFirstTaskBodySchema",
    ]:
        assert schema in web_readiness_contract

    for path in [
        "/api/control-plane/onboarding/readiness",
        "/api/control-plane/onboarding/first-task",
        "/api/control-plane/agents/{agent_id}/channels/gateway",
        "/api/control-plane/agents/{agent_id}/channels/gateway/pairing-codes",
        "/api/control-plane/agents/{agent_id}/channels/gateway/unknown-senders",
    ]:
        assert path in openapi
