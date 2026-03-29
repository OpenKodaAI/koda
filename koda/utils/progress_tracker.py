"""Progress tracking with phase detection for streaming responses."""

from __future__ import annotations

from dataclasses import dataclass, field

from koda.utils.progress import _format_elapsed, compact_tool_label

_READ_TOOLS = frozenset({"Read", "Glob", "Grep"})
_WRITE_TOOLS = frozenset({"Write", "Edit", "write_file", "edit_file"})
_TEST_PATTERNS = frozenset({"pytest", "npm test", "yarn test", "vitest", "jest", "make test"})
_DEFAULT_PHASE_LABEL = "\u2699\ufe0f Processando"


@dataclass
class ProgressTracker:
    """Track task progress and detect phases from tool uses."""

    start_time: float
    _last_milestone_time: float = 0.0
    _milestone_messages: list[int] = field(default_factory=list)

    def detect_phase(self, tool_uses: list[dict]) -> str:
        """Infer phase from recent tool uses."""
        if not tool_uses:
            return "analyzing"
        recent = tool_uses[-5:]
        names = {t.get("name", "") for t in recent}
        # Check for test patterns in Bash commands
        for t in recent:
            if t.get("name") == "Bash":
                cmd = (t.get("input", {}).get("command", "") or "").lower()
                if any(p in cmd for p in _TEST_PATTERNS):
                    return "testing"
        if names & _WRITE_TOOLS:
            return "implementing"
        return "analyzing"

    def build_status(self, elapsed: float, tool_uses: list[dict]) -> str:
        """Rich status line with phase, counters, and last tool."""
        phase = self.detect_phase(tool_uses)
        phase_icons = {
            "analyzing": "\U0001f50d Analisando",
            "implementing": "\U0001f528 Implementando",
            "testing": "\U0001f9ea Testando",
        }

        elapsed_str = _format_elapsed(elapsed)
        header = f"{phase_icons.get(phase, _DEFAULT_PHASE_LABEL)} | {elapsed_str}"

        if not tool_uses:
            return header

        reads = sum(1 for t in tool_uses if t.get("name") in _READ_TOOLS)
        writes = sum(1 for t in tool_uses if t.get("name") in _WRITE_TOOLS)
        execs = sum(1 for t in tool_uses if t.get("name") == "Bash")

        counters = []
        if reads:
            counters.append(f"\U0001f4d6 {reads}")
        if writes:
            counters.append(f"\u270f\ufe0f {writes}")
        if execs:
            counters.append(f"\u26a1 {execs}")

        counter_line = " ".join(counters) if counters else f"{len(tool_uses)} tools"

        last = tool_uses[-1]
        last_label = compact_tool_label(last.get("name", "?"), last.get("input"))

        return f"{header} | {counter_line}\n\u21b3 {last_label}"

    def check_milestone(self, elapsed: float, tool_uses: list[dict]) -> str | None:
        """Return milestone text if >= 45s since last. None otherwise."""
        if elapsed < 30:
            return None
        if elapsed - self._last_milestone_time < 45:
            return None
        self._last_milestone_time = elapsed

        phase = self.detect_phase(tool_uses)
        phase_label = {
            "analyzing": "Analisando",
            "implementing": "Implementando",
            "testing": "Testando",
        }.get(phase, "Processando")

        reads = sum(1 for t in tool_uses if t.get("name") in _READ_TOOLS)
        writes = sum(1 for t in tool_uses if t.get("name") in _WRITE_TOOLS)
        execs = sum(1 for t in tool_uses if t.get("name") == "Bash")

        parts = []
        if reads:
            parts.append(f"{reads} leituras")
        if writes:
            parts.append(f"{writes} edi\u00e7\u00f5es")
        if execs:
            parts.append(f"{execs} comandos")

        return f"\U0001f4ca {_format_elapsed(elapsed)} \u2014 {phase_label} | {', '.join(parts) or 'processando...'}"

    def add_milestone_message(self, message_id: int) -> None:
        """Record a milestone message ID for later cleanup."""
        self._milestone_messages.append(message_id)

    @property
    def milestone_message_ids(self) -> list[int]:
        """Message IDs of milestone notifications to clean up."""
        return list(self._milestone_messages)
