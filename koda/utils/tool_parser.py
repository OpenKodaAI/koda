"""Parse tool_use events from Claude CLI JSON output."""

import json
from typing import Any, cast

from koda.utils.progress import _format_elapsed


def parse_tool_uses(raw_output: str) -> list[dict[str, str]]:
    """Parse tool_use entries from Claude CLI output.

    Claude CLI with --output-format json may include tool_use events.
    Returns list of dicts with 'name' and optionally 'input' summary.
    """
    tools: list[dict[str, str]] = []

    # Try parsing as JSON lines (streaming output)
    for line in raw_output.split("\n"):
        line = line.strip()
        if not line:
            continue
        try:
            data = json.loads(line)
        except json.JSONDecodeError:
            continue

        _extract_tools_from_data(data, tools)

    return tools


def _extract_tools_from_data(data: dict[str, Any], tools: list[dict[str, str]]) -> None:
    """Extract tool use information from parsed JSON data."""
    # Direct tool_use type
    if data.get("type") == "tool_use":
        name = data.get("name", "unknown")
        input_data = data.get("input", {})
        summary = _summarize_input(name, input_data)
        tools.append({"name": name, "input": summary})
        return

    # Content array with tool_use blocks
    content = data.get("content", [])
    if isinstance(content, list):
        for block in content:
            if isinstance(block, dict) and block.get("type") == "tool_use":
                name = block.get("name", "unknown")
                input_data = block.get("input", {})
                summary = _summarize_input(name, input_data)
                tools.append({"name": name, "input": summary})


def _summarize_input(name: str, input_data: dict[str, Any]) -> str:
    """Create a short summary of tool input."""
    if not input_data:
        return ""

    # Common tool input summaries
    if name in ("Read", "read_file") and "file_path" in input_data:
        return str(input_data["file_path"]).split("/")[-1]
    if name in ("Edit", "edit_file") and "file_path" in input_data:
        return str(input_data["file_path"]).split("/")[-1]
    if name in ("Write", "write_file") and "file_path" in input_data:
        return str(input_data["file_path"]).split("/")[-1]
    if name == "Bash" and "command" in input_data:
        cmd = str(input_data["command"])
        return cmd[:40] + "..." if len(cmd) > 40 else cmd
    if name == "Grep" and "pattern" in input_data:
        return str(input_data["pattern"])[:30]

    # Generic: show first key's value
    for key in ("path", "query", "url", "name"):
        if key in input_data:
            val = str(input_data[key])
            return val[:40] + "..." if len(val) > 40 else val

    return ""


def summarize_tool_uses(tool_uses: list[dict]) -> str:
    """Convert raw tool_use blocks (from metadata_collector) into a formatted summary.

    Each item in tool_uses should have 'name' and optionally 'input' keys.
    """
    tools: list[dict[str, str]] = []
    for block in tool_uses:
        name = str(block.get("name", "unknown"))
        input_data = cast(dict[str, Any], block.get("input", {}))
        summary = _summarize_input(name, input_data)
        tools.append({"name": name, "input": summary})
    return format_tool_summary(tools)


def format_tool_summary(tools: list[dict[str, str]]) -> str:
    """Format tool uses into a readable summary line.

    For >5 tools, groups by category (read/write/exec).
    For <=5, uses compact flat format.
    """
    if not tools:
        return ""

    # Deduplicate and count
    seen: dict[str, int] = {}
    details: dict[str, str] = {}
    for t in tools:
        key = t["name"]
        seen[key] = seen.get(key, 0) + 1
        if t.get("input") and key not in details:
            details[key] = t["input"]

    total = sum(seen.values())

    # Grouped format for >5 tools
    if total > 5:
        _read_names = {"Read", "read_file", "Glob", "Grep"}
        _write_names = {"Write", "write_file", "Edit", "edit_file"}

        read_parts = []
        write_parts = []
        exec_parts = []
        other_parts = []

        for name, count in seen.items():
            label = f"{name} x{count}" if count > 1 else name
            if name in _read_names:
                read_parts.append(label)
            elif name in _write_names:
                write_parts.append(label)
            elif name == "Bash":
                exec_parts.append(label)
            else:
                other_parts.append(label)

        lines = ["\U0001f527 Ferramentas:"]
        if read_parts:
            lines.append(f"  \U0001f4d6 Leitura: {', '.join(read_parts)}")
        if write_parts:
            lines.append(f"  \u270f\ufe0f Escrita: {', '.join(write_parts)}")
        if exec_parts:
            lines.append(f"  \u26a1 Execu\u00e7\u00e3o: {', '.join(exec_parts)}")
        if other_parts:
            lines.append(f"  \U0001f504 Outros: {', '.join(other_parts)}")
        return "\n".join(lines)

    # Compact format for <=5 tools
    parts: list[str] = []
    for name, count in seen.items():
        detail = details.get(name, "")
        if count > 1:
            parts.append(f"{name}({detail})x{count}" if detail else f"{name}x{count}")
        else:
            parts.append(f"{name}({detail})" if detail else name)

    return "\U0001f527 Used: " + ", ".join(parts)


def format_completion_summary(tool_uses: list[dict], elapsed: float) -> str:
    """Structured summary for tasks with >3 tools and >10s elapsed."""
    if len(tool_uses) <= 3 or elapsed <= 10:
        return ""

    reads = sum(1 for t in tool_uses if t.get("name") in ("Read", "Glob", "Grep"))
    writes = sum(1 for t in tool_uses if t.get("name") in ("Write", "Edit", "write_file", "edit_file"))
    execs = sum(1 for t in tool_uses if t.get("name") == "Bash")

    file_names: set[str] = set()
    for t in tool_uses:
        if t.get("name") in ("Write", "Edit", "write_file", "edit_file"):
            inp = t.get("input", {})
            path = inp.get("file_path", "") if isinstance(inp, dict) else ""
            if path:
                file_names.add(path.rsplit("/", 1)[-1])

    parts = [f"\u2705 Conclu\u00eddo em {_format_elapsed(elapsed)}"]

    counters = []
    if reads:
        counters.append(f"\U0001f4d6 {reads} lidos")
    if writes:
        counters.append(f"\u270f\ufe0f {writes} editados")
    if execs:
        counters.append(f"\u26a1 {execs} comandos")
    if counters:
        parts.append(" | ".join(counters))

    if file_names:
        parts.append(f"Arquivos: {', '.join(sorted(file_names)[:8])}")

    return "\n".join(parts)
