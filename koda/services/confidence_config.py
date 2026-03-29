"""Configuration for execution-confidence gating."""

from koda.config import _env

EXECUTION_CONFIDENCE_ENABLED: bool = _env("EXECUTION_CONFIDENCE_ENABLED", "true").lower() == "true"
EXECUTION_CONFIDENCE_THRESHOLD: float = float(_env("EXECUTION_CONFIDENCE_THRESHOLD", "0.65"))
EXECUTION_CONFIDENCE_REQUIRE_PLAN_FOR_WRITES: bool = (
    _env("EXECUTION_CONFIDENCE_REQUIRE_PLAN_FOR_WRITES", "true").lower() == "true"
)
EXECUTION_CONFIDENCE_REQUIRE_FRESH_SOURCES: bool = (
    _env("EXECUTION_CONFIDENCE_REQUIRE_FRESH_SOURCES", "false").lower() == "true"
)
