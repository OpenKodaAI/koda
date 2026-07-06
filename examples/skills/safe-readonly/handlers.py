"""Safe read-only handlers for the local KodaSkill example package."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from koda.services.tool_dispatcher import AgentToolResult


async def read_file_summary(params: dict[str, Any], ctx: Any) -> AgentToolResult:
    package_dir = Path(__file__).resolve().parent
    requested = str(params.get("path") or "").strip()
    target = (package_dir / requested).resolve()
    if not requested or not target.is_file() or package_dir not in target.parents:
        return AgentToolResult(
            tool="safe_read_file_summary",
            success=False,
            output="Path must be a file inside the package directory.",
        )
    text = target.read_text(encoding="utf-8")[:1200]
    summary = " ".join(text.split())[:300]
    return AgentToolResult(tool="safe_read_file_summary", success=True, output=summary)
