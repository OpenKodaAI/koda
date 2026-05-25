"""Shared provider runtime contracts and capability helpers."""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Any, Literal

TurnMode = Literal["new_turn", "resume_turn"]
ProviderStatus = Literal["ready", "degraded", "unavailable"]


@dataclass(slots=True)
class ProviderCapabilities:
    """Runtime compatibility snapshot for one provider/subcommand pair."""

    provider: str
    turn_mode: TurnMode
    status: ProviderStatus
    can_execute: bool
    supports_native_resume: bool
    supports_native_tool_calls: bool = False
    supports_streaming_tool_calls: bool = False
    supports_structured_output: bool = True
    supports_json_schema_subset: bool = True
    supports_xml_fallback: bool = True
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    checked_via: str = "static"

    def clone(self) -> ProviderCapabilities:
        """Return a detached copy safe for callers to mutate locally."""
        return replace(self, warnings=list(self.warnings), errors=list(self.errors))


def infer_turn_mode(provider_session_id: str | None) -> TurnMode:
    """Infer the desired provider turn mode from native session state."""
    return "resume_turn" if provider_session_id else "new_turn"


def summarize_provider_health(
    provider: str,
    capabilities: dict[TurnMode, ProviderCapabilities],
) -> dict[str, Any]:
    """Build a health payload for one provider from per-turn capabilities."""
    new_turn = capabilities["new_turn"]
    resume_turn = capabilities["resume_turn"]

    if new_turn.can_execute and resume_turn.can_execute:
        status: ProviderStatus = "ready"
    elif new_turn.can_execute:
        status = "degraded"
    else:
        status = "unavailable"

    warnings = list(dict.fromkeys([*new_turn.warnings, *resume_turn.warnings]))
    errors = list(dict.fromkeys([*new_turn.errors, *resume_turn.errors]))

    return {
        "provider": provider,
        "status": status,
        "can_execute": new_turn.can_execute,
        "supports_native_resume": resume_turn.can_execute and resume_turn.supports_native_resume,
        "warnings": warnings,
        "errors": errors,
        "turn_modes": {
            "new_turn": {
                "status": new_turn.status,
                "can_execute": new_turn.can_execute,
                "supports_native_resume": new_turn.supports_native_resume,
                "supports_native_tool_calls": new_turn.supports_native_tool_calls,
                "supports_streaming_tool_calls": new_turn.supports_streaming_tool_calls,
                "supports_structured_output": new_turn.supports_structured_output,
                "supports_json_schema_subset": new_turn.supports_json_schema_subset,
                "supports_xml_fallback": new_turn.supports_xml_fallback,
                "warnings": list(new_turn.warnings),
                "errors": list(new_turn.errors),
                "checked_via": new_turn.checked_via,
            },
            "resume_turn": {
                "status": resume_turn.status,
                "can_execute": resume_turn.can_execute,
                "supports_native_resume": resume_turn.supports_native_resume,
                "supports_native_tool_calls": resume_turn.supports_native_tool_calls,
                "supports_streaming_tool_calls": resume_turn.supports_streaming_tool_calls,
                "supports_structured_output": resume_turn.supports_structured_output,
                "supports_json_schema_subset": resume_turn.supports_json_schema_subset,
                "supports_xml_fallback": resume_turn.supports_xml_fallback,
                "warnings": list(resume_turn.warnings),
                "errors": list(resume_turn.errors),
                "checked_via": resume_turn.checked_via,
            },
        },
    }
