"""Fire-and-forget telemetry for the skills v2 system."""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

from koda.services.audit import AuditEvent, emit

if TYPE_CHECKING:
    from koda.skills._selector import SkillMatch


def emit_skill_selection(
    *,
    user_id: int | None = None,
    task_id: int | None = None,
    query_text: str,
    matches: list[SkillMatch],
    resolved: list[SkillMatch],
    included_in_prompt: bool,
) -> None:
    """Fire-and-forget skill selection telemetry."""
    emit(
        AuditEvent(
            event_type="skill.selection",
            user_id=user_id,
            task_id=task_id,
            details={
                "query_length": len(query_text),
                "candidates_evaluated": len(matches),
                "skills_selected": [
                    {
                        "id": m.skill.id,
                        "composite_score": round(m.composite_score, 3),
                        "semantic_score": round(m.semantic_score, 3),
                        "trigger_matched": m.trigger_matched,
                        "reason": m.selection_reason,
                    }
                    for m in resolved
                ],
                "included_in_prompt": included_in_prompt,
            },
        )
    )


def emit_skill_invocation(
    *,
    user_id: int | None = None,
    task_id: int | None = None,
    skill_id: str,
    explicit: bool,
) -> None:
    """Track when a skill is invoked via ``/skill`` command."""
    emit(
        AuditEvent(
            event_type="skill.invocation",
            user_id=user_id,
            task_id=task_id,
            details={"skill_id": skill_id, "explicit": explicit},
        )
    )


def emit_skill_reload(
    *,
    skills_added: list[str],
    skills_removed: list[str],
    skills_modified: list[str],
) -> None:
    """Track hot-reload events."""
    if skills_added or skills_removed or skills_modified:
        emit(
            AuditEvent(
                event_type="skill.reload",
                details={
                    "added": skills_added,
                    "removed": skills_removed,
                    "modified": skills_modified,
                },
            )
        )


# ---------------------------------------------------------------------------
# Compliance feedback
# ---------------------------------------------------------------------------


def _extract_format_markers(enforcement_text: str) -> list[str]:
    """Extract structural markers from an output format enforcement string.

    Looks for:
    - Bold markers: **Strengths**, **Issues**, **Risk Assessment**
    - Bracketed markers: [Severity:], [Critical], [OWASP]
    - Numbered sections: 1), 2), 3)
    - Section headers mentioned: "Strengths", "Findings", "Summary"
    """
    markers: list[str] = []

    # Extract **bold** markers
    bold = re.findall(r"\*\*([^*]+)\*\*", enforcement_text)
    markers.extend(bold)

    # Extract [bracketed] markers
    bracketed = re.findall(r"\[([^\]]+)\]", enforcement_text)
    markers.extend(bracketed)

    # If no structural markers found, try splitting on common delimiters
    if not markers:
        # Look for "then" as section separator
        parts = re.split(r",\s*then\s+", enforcement_text, flags=re.IGNORECASE)
        if len(parts) > 1:
            for part in parts:
                # Extract the first significant word/phrase
                words = part.strip().split()[:3]
                if words:
                    markers.append(" ".join(words))

    return markers


def emit_skill_compliance(
    *,
    user_id: int | None = None,
    task_id: int | None = None,
    skill_id: str,
    response_text: str,
    output_format_enforcement: str,
) -> float:
    """Measure if the model's response follows the skill's output format.

    Uses simple heuristic matching:
    - Extract key structural markers from *output_format_enforcement*
    - Check if those markers appear in the response
    - Return compliance score 0.0-1.0

    Emits a ``skill.compliance`` audit event.
    """
    if not output_format_enforcement or not response_text:
        return 0.0

    markers = _extract_format_markers(output_format_enforcement)

    if not markers:
        return 0.0

    response_lower = response_text.lower()
    found = sum(
        1
        for marker in markers
        if f"**{marker.lower()}**" in response_lower  # Check bold markdown heading
        or f"## {marker.lower()}" in response_lower  # Check markdown heading
        or f"[{marker.lower()}]" in response_lower  # Check bracketed usage
    )
    compliance_score = found / len(markers)

    emit(
        AuditEvent(
            event_type="skill.compliance",
            user_id=user_id,
            task_id=task_id,
            details={
                "skill_id": skill_id,
                "markers_total": len(markers),
                "markers_found": found,
                "compliance_score": round(compliance_score, 3),
            },
        )
    )

    return compliance_score
