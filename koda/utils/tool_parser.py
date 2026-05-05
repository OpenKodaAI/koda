"""Parse and summarize provider tool-use events for user-visible text."""

import json
import os
from typing import Any, cast

from koda.utils.progress import _format_elapsed

_READ_TOOL_NAMES = frozenset(
    {
        "Read",
        "read_file",
        "Glob",
        "Grep",
        "file_read",
        "file_list",
        "file_search",
        "file_grep",
    }
)
_WRITE_TOOL_NAMES = frozenset(
    {
        "Write",
        "write_file",
        "Edit",
        "edit_file",
        "file_write",
        "file_edit",
        "file_move",
        "file_delete",
    }
)
_EXEC_TOOL_NAMES = frozenset({"Bash", "shell_execute", "shell_bg", "shell_status", "shell_output"})
_BROWSER_TOOL_PREFIXES = ("browser_",)
_SEARCH_TOOL_NAMES = frozenset({"web_search", "fetch_url", "http_request"})


def _safe_basename(value: object) -> str:
    if not isinstance(value, str) or not value.strip():
        return ""
    return os.path.basename(value.strip().rstrip("/")) or value.strip()


def _first_present(input_data: dict[str, Any], *keys: str) -> object:
    for key in keys:
        if key in input_data:
            return input_data[key]
    return None


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
    """Create a short, safe summary of tool input.

    This text can be displayed to Telegram users. Avoid showing shell
    commands, prompts, URLs, query strings, or arbitrary values because they
    may include secrets or large provider-native traces.
    """
    if not input_data:
        return ""

    if name in _READ_TOOL_NAMES | _WRITE_TOOL_NAMES:
        path = _first_present(input_data, "file_path", "path", "destination", "source")
        return _safe_basename(path)
    if name in _EXEC_TOOL_NAMES:
        return "execucao"
    if name.startswith(_BROWSER_TOOL_PREFIXES):
        return "navegacao"
    if name in _SEARCH_TOOL_NAMES:
        return "consulta"

    safe_name = _safe_basename(_first_present(input_data, "name", "title"))
    if safe_name:
        return safe_name[:40]

    return ""


def _tool_category(name: str) -> str:
    if name in _READ_TOOL_NAMES:
        return "Leitura"
    if name in _WRITE_TOOL_NAMES:
        return "Escrita"
    if name in _EXEC_TOOL_NAMES:
        return "Execucao"
    if name.startswith(_BROWSER_TOOL_PREFIXES):
        return "Navegacao"
    if name in _SEARCH_TOOL_NAMES:
        return "Consulta"
    return "Outras"


def _sanitize_display_detail(name: str, detail: object) -> str:
    value = str(detail or "").strip()
    if not value:
        return ""
    if name in _READ_TOOL_NAMES | _WRITE_TOOL_NAMES:
        return _safe_basename(value)
    if name in _EXEC_TOOL_NAMES:
        return "execucao"
    if name.startswith(_BROWSER_TOOL_PREFIXES):
        return "navegacao"
    if name in _SEARCH_TOOL_NAMES:
        return "consulta"
    return ""


def _format_tool_part(name: str, count: int, details: list[str]) -> str:
    unique_details = list(dict.fromkeys(d for d in details if d and d != "execucao"))
    suffix = f" x{count}" if count > 1 else ""
    if unique_details:
        shown = ", ".join(unique_details[:3])
        more = f", +{len(unique_details) - 3}" if len(unique_details) > 3 else ""
        return f"{name}({shown}{more}){suffix}"
    return f"{name}{suffix}"


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

    # Deduplicate, count, and retain only safe display details.
    seen: dict[str, int] = {}
    details: dict[str, list[str]] = {}
    for t in tools:
        key = t["name"]
        seen[key] = seen.get(key, 0) + 1
        safe_detail = _sanitize_display_detail(key, t.get("input", ""))
        if safe_detail:
            details.setdefault(key, []).append(safe_detail)

    total = sum(seen.values())

    # Grouped format for >5 tools
    if total > 5:
        grouped: dict[str, list[str]] = {
            "Leitura": [],
            "Escrita": [],
            "Execucao": [],
            "Navegacao": [],
            "Consulta": [],
            "Outras": [],
        }

        for name, count in seen.items():
            grouped[_tool_category(name)].append(_format_tool_part(name, count, details.get(name, [])))

        lines = ["Ferramentas:"]
        for category in ("Leitura", "Escrita", "Execucao", "Navegacao", "Consulta", "Outras"):
            grouped_parts = grouped[category]
            if grouped_parts:
                lines.append(f"  {category}: {', '.join(grouped_parts)}")
        return "\n".join(lines)

    # Compact format for <=5 tools
    parts: list[str] = []
    for name, count in seen.items():
        parts.append(_format_tool_part(name, count, details.get(name, [])))

    return "Ferramentas: " + ", ".join(parts)


def format_completion_summary(tool_uses: list[dict], elapsed: float) -> str:
    """Structured summary for tasks with >3 tools and >10s elapsed."""
    if len(tool_uses) <= 3 or elapsed <= 10:
        return ""

    reads = sum(1 for t in tool_uses if t.get("name") in _READ_TOOL_NAMES)
    writes = sum(1 for t in tool_uses if t.get("name") in _WRITE_TOOL_NAMES)
    execs = sum(1 for t in tool_uses if t.get("name") in _EXEC_TOOL_NAMES)

    file_names: set[str] = set()
    for t in tool_uses:
        if t.get("name") in _WRITE_TOOL_NAMES:
            inp = t.get("input", {})
            path = _first_present(inp, "file_path", "path", "destination") if isinstance(inp, dict) else ""
            if path:
                file_names.add(_safe_basename(path))

    parts = [f"Concluido em {_format_elapsed(elapsed)}"]

    counters = []
    if reads:
        counters.append(f"{reads} lidos")
    if writes:
        counters.append(f"{writes} editados")
    if execs:
        counters.append(f"{execs} execucoes")
    if counters:
        parts.append(" | ".join(counters))

    if file_names:
        parts.append(f"Arquivos: {', '.join(sorted(file_names)[:8])}")

    return "\n".join(parts)
