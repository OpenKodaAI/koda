"""Tests for `_validate_general_payload` structural validation."""

from __future__ import annotations

import pytest

from koda.control_plane.manager import ControlPlaneManager, GeneralPayloadValidationError


def _manager() -> ControlPlaneManager:
    """Instantiate without __init__ so auto-seed and DB connects are skipped."""
    return ControlPlaneManager.__new__(ControlPlaneManager)


def test_accepts_empty_payload() -> None:
    _manager()._validate_general_payload({})


def test_accepts_typed_values() -> None:
    payload = {
        "account": {"rate_limit_per_minute": 30},
        "models": {
            "max_budget_usd": 5.0,
            "max_total_budget_usd": 50.0,
            "providers_enabled": ["claude"],
            "default_provider": "claude",
        },
        "memory_and_knowledge": {
            "autonomy_policy": {"default_autonomy_tier": "t1"},
            "knowledge_policy": {"provenance_policy": "strict"},
        },
        "variables": [{"key": "MY_VAR", "type": "text", "scope": "system_only"}],
    }
    _manager()._validate_general_payload(payload)


def test_rejects_negative_budget() -> None:
    with pytest.raises(GeneralPayloadValidationError) as excinfo:
        _manager()._validate_general_payload({"models": {"max_budget_usd": -1}})
    codes = {err["code"] for err in excinfo.value.errors}
    assert "must_be_positive" in codes


def test_rejects_total_budget_below_task_budget() -> None:
    with pytest.raises(GeneralPayloadValidationError) as excinfo:
        _manager()._validate_general_payload({"models": {"max_budget_usd": 10.0, "max_total_budget_usd": 5.0}})
    fields = {err["field"] for err in excinfo.value.errors}
    assert "models.max_total_budget_usd" in fields
    codes = {err["code"] for err in excinfo.value.errors}
    assert "must_gte_max_budget" in codes


def test_rejects_non_numeric_budget() -> None:
    with pytest.raises(GeneralPayloadValidationError) as excinfo:
        _manager()._validate_general_payload({"models": {"max_budget_usd": "abc"}})
    assert any(err["code"] == "invalid_type" for err in excinfo.value.errors)


def test_rejects_zero_rate_limit() -> None:
    with pytest.raises(GeneralPayloadValidationError) as excinfo:
        _manager()._validate_general_payload({"account": {"rate_limit_per_minute": 0}})
    assert any(err["code"] == "min_value" for err in excinfo.value.errors)


def test_rejects_unknown_provider_in_enabled_list() -> None:
    with pytest.raises(GeneralPayloadValidationError) as excinfo:
        _manager()._validate_general_payload({"models": {"providers_enabled": ["claude", "not-a-real-provider"]}})
    assert any(err["code"] == "unknown_provider" for err in excinfo.value.errors)


def test_rejects_default_provider_not_in_enabled() -> None:
    with pytest.raises(GeneralPayloadValidationError) as excinfo:
        _manager()._validate_general_payload(
            {"models": {"providers_enabled": ["claude"], "default_provider": "gemini"}}
        )
    assert any(err["code"] == "must_be_enabled" for err in excinfo.value.errors)


def test_rejects_invalid_autonomy_tier() -> None:
    with pytest.raises(GeneralPayloadValidationError) as excinfo:
        _manager()._validate_general_payload(
            {"memory_and_knowledge": {"autonomy_policy": {"default_autonomy_tier": "t9"}}}
        )
    assert any(err["code"] == "invalid_enum" for err in excinfo.value.errors)


def test_rejects_invalid_provenance_policy() -> None:
    with pytest.raises(GeneralPayloadValidationError) as excinfo:
        _manager()._validate_general_payload(
            {"memory_and_knowledge": {"knowledge_policy": {"provenance_policy": "loose"}}}
        )
    assert any(err["code"] == "invalid_enum" for err in excinfo.value.errors)


def test_rejects_variable_with_lowercase_key() -> None:
    with pytest.raises(GeneralPayloadValidationError) as excinfo:
        _manager()._validate_general_payload({"variables": [{"key": "my_var", "type": "text", "scope": "system_only"}]})
    assert any(err["code"] == "invalid_format" for err in excinfo.value.errors)


def test_rejects_variable_with_unknown_scope() -> None:
    with pytest.raises(GeneralPayloadValidationError) as excinfo:
        _manager()._validate_general_payload({"variables": [{"key": "OK_VAR", "type": "text", "scope": "mystery"}]})
    assert any(err["code"] == "invalid_enum" for err in excinfo.value.errors)


def test_rejects_variable_with_empty_key() -> None:
    with pytest.raises(GeneralPayloadValidationError) as excinfo:
        _manager()._validate_general_payload({"variables": [{"key": "", "type": "text", "scope": "system_only"}]})
    assert any(err["code"] == "required" for err in excinfo.value.errors)


def test_rejects_functional_default_pointing_to_disabled_provider() -> None:
    with pytest.raises(GeneralPayloadValidationError) as excinfo:
        _manager()._validate_general_payload(
            {
                "models": {
                    "providers_enabled": ["claude"],
                    "functional_defaults": {
                        "general": {"provider_id": "gemini", "model_id": "gemini-2.5-pro"},
                    },
                }
            }
        )
    fields = {err["field"] for err in excinfo.value.errors}
    assert "models.functional_defaults.general.provider_id" in fields


def test_accepts_functional_default_when_providers_unspecified() -> None:
    # When the payload does not re-declare providers_enabled, we skip the
    # cross-reference check because we don't have authoritative state here.
    _manager()._validate_general_payload(
        {"models": {"functional_defaults": {"general": {"provider_id": "gemini", "model_id": "x"}}}}
    )


def test_accepts_valid_scheduler_block() -> None:
    payload = {
        "scheduler": {
            "scheduler_enabled": True,
            "scheduler_poll_interval_seconds": 10,
            "scheduler_lease_seconds": 60,
            "scheduler_run_max_attempts": 3,
            "runbook_governance_enabled": True,
            "runbook_governance_hour": 4,
            "runbook_revalidation_stale_days": 30,
            "runbook_revalidation_min_verified_runs": 5,
            "runbook_revalidation_min_success_rate": 0.85,
            "runbook_revalidation_correction_threshold": 3,
            "runbook_revalidation_rollback_threshold": 2,
        }
    }
    _manager()._validate_general_payload(payload)


def test_rejects_zero_scheduler_interval() -> None:
    with pytest.raises(GeneralPayloadValidationError) as excinfo:
        _manager()._validate_general_payload({"scheduler": {"scheduler_poll_interval_seconds": 0}})
    fields = {err["field"] for err in excinfo.value.errors}
    assert "scheduler.scheduler_poll_interval_seconds" in fields


def test_rejects_runbook_governance_hour_out_of_range() -> None:
    with pytest.raises(GeneralPayloadValidationError) as excinfo:
        _manager()._validate_general_payload({"scheduler": {"runbook_governance_hour": 25}})
    assert any(err["code"] == "out_of_range" for err in excinfo.value.errors)


def test_rejects_runbook_governance_hour_below_zero() -> None:
    with pytest.raises(GeneralPayloadValidationError) as excinfo:
        _manager()._validate_general_payload({"scheduler": {"runbook_governance_hour": -1}})
    assert any(err["code"] == "out_of_range" for err in excinfo.value.errors)


def test_rejects_min_success_rate_above_one() -> None:
    with pytest.raises(GeneralPayloadValidationError) as excinfo:
        _manager()._validate_general_payload({"scheduler": {"runbook_revalidation_min_success_rate": 1.5}})
    assert any(err["code"] == "out_of_range" for err in excinfo.value.errors)


def test_rejects_non_numeric_min_success_rate() -> None:
    with pytest.raises(GeneralPayloadValidationError) as excinfo:
        _manager()._validate_general_payload({"scheduler": {"runbook_revalidation_min_success_rate": "muito"}})
    assert any(err["code"] == "invalid_type" for err in excinfo.value.errors)


def test_accepts_known_time_formats() -> None:
    _manager()._validate_general_payload({"account": {"time_format": "24h"}})
    _manager()._validate_general_payload({"account": {"time_format": "12h"}})


def test_rejects_unknown_time_format() -> None:
    with pytest.raises(GeneralPayloadValidationError) as excinfo:
        _manager()._validate_general_payload({"account": {"time_format": "36h"}})
    fields = {err["field"] for err in excinfo.value.errors}
    assert "account.time_format" in fields


def test_accumulates_multiple_errors() -> None:
    with pytest.raises(GeneralPayloadValidationError) as excinfo:
        _manager()._validate_general_payload(
            {
                "account": {"rate_limit_per_minute": -1},
                "models": {"max_budget_usd": 0},
                "memory_and_knowledge": {"autonomy_policy": {"default_autonomy_tier": "invalid"}},
                "variables": [{"key": "bad-key", "type": "wrong", "scope": "also_wrong"}],
            }
        )
    assert len(excinfo.value.errors) >= 4
