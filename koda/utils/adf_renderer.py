"""Render Atlassian Document Format (ADF v3) to plain text and extract URLs."""

from __future__ import annotations

from typing import Any, cast


def render_adf(adf_doc: dict | None) -> str:
    """Render an ADF document to human-readable text.

    Handles the standard ADF v3 node types used by Jira Cloud.
    Unknown nodes are silently skipped to avoid crashes on new types.
    """
    if not adf_doc or not isinstance(adf_doc, dict):
        return ""
    content = adf_doc.get("content")
    if not content:
        return ""
    return _render_nodes(content).strip()


def extract_urls_from_adf(adf_doc: dict | None) -> list[str]:
    """Collect all URLs found in an ADF document (links, inlineCards, media)."""
    urls: list[str] = []
    if adf_doc and isinstance(adf_doc, dict):
        _collect_urls(adf_doc, urls)
    # Deduplicate preserving order
    seen: set[str] = set()
    result: list[str] = []
    for u in urls:
        if u not in seen:
            seen.add(u)
            result.append(u)
    return result


def classify_url(url: str, jira_url: str, confluence_url: str) -> str:
    """Classify a URL as ``"jira"``, ``"confluence"``, or ``"external"``."""
    url_lower = url.lower()
    jira_lower = jira_url.rstrip("/").lower() if jira_url else ""
    confluence_lower = confluence_url.rstrip("/").lower() if confluence_url else ""
    # Confluence check first — Confluence URLs often share the Jira domain
    if confluence_lower and (
        url_lower.startswith(confluence_lower)
        or ("/wiki/" in url_lower and jira_lower and url_lower.startswith(jira_lower))
    ):
        return "confluence"
    if jira_lower and url_lower.startswith(jira_lower):
        return "jira"
    # Heuristic: atlassian.net/wiki paths are Confluence
    if "atlassian.net/wiki/" in url_lower:
        return "confluence"
    return "external"


# ---------------------------------------------------------------------------
# Internal rendering helpers
# ---------------------------------------------------------------------------


def _render_nodes(nodes: list[dict], list_level: int = 0) -> str:
    """Render a list of ADF nodes into text."""
    parts: list[str] = []
    for node in nodes:
        rendered = _render_node(node, list_level)
        if rendered is not None:
            parts.append(rendered)
    return "\n".join(parts)


def _render_node(node: dict, list_level: int = 0) -> str | None:
    """Render a single ADF node."""
    if not isinstance(node, dict):
        return None
    ntype = node.get("type", "")
    content = node.get("content", [])

    if ntype == "doc":
        return _render_nodes(content, list_level)

    if ntype == "paragraph":
        return _render_inline(content)

    if ntype == "heading":
        level = node.get("attrs", {}).get("level", 1)
        text = _render_inline(content)
        return f"{'#' * level} {text}"

    if ntype == "bulletList":
        return _render_list_items(content, ordered=False, level=list_level)

    if ntype == "orderedList":
        return _render_list_items(content, ordered=True, level=list_level)

    if ntype == "listItem":
        # Rendered by _render_list_items; fallback if called directly
        return _render_nodes(content, list_level)

    if ntype == "codeBlock":
        lang = node.get("attrs", {}).get("language", "")
        code = _render_inline(content)
        return f"```{lang}\n{code}\n```"

    if ntype == "blockquote":
        inner = _render_nodes(content, list_level)
        return "\n".join(f"> {line}" for line in inner.split("\n"))

    if ntype == "table":
        return _render_table(content)

    if ntype == "tableRow":
        cells = []
        for cell in content:
            cells.append(_render_table_cell(cell.get("content", [])))
        return "| " + " | ".join(cells) + " |"

    if ntype in ("tableCell", "tableHeader"):
        return _render_table_cell(content)

    if ntype == "rule":
        return "---"

    if ntype == "mediaSingle":
        # Contains a media node
        return _render_nodes(content, list_level)

    if ntype == "media":
        attrs = node.get("attrs", {})
        filename = attrs.get("alt", "") or attrs.get("id", "media")
        att_id = attrs.get("id", "")
        if att_id and att_id != filename:
            return f"[attachment: {filename} (id={att_id})]"
        return f"[attachment: {filename}]"

    if ntype == "mediaInline":
        attrs = node.get("attrs", {})
        filename = attrs.get("alt", "") or attrs.get("id", "media")
        att_id = attrs.get("id", "")
        if att_id and att_id != filename:
            return f"[attachment: {filename} (id={att_id})]"
        return f"[attachment: {filename}]"

    if ntype == "inlineCard":
        attrs = node.get("attrs", {})
        url = attrs.get("url", "")
        return url if url else None

    if ntype == "expand" or ntype == "nestedExpand":
        title = node.get("attrs", {}).get("title", "")
        inner = _render_nodes(content, list_level)
        if title:
            return f"[{title}]\n{inner}"
        return inner

    if ntype == "panel":
        inner = _render_nodes(content, list_level)
        panel_type = node.get("attrs", {}).get("panelType", "info")
        return f"[{panel_type}] {inner}"

    if ntype == "status":
        text = node.get("attrs", {}).get("text", "")
        return f"[{text}]" if text else None

    # Inline-level nodes that might appear at block level
    if ntype == "text":
        return _render_text(node)

    if ntype == "mention":
        attrs = cast(dict[str, Any], node.get("attrs", {}))
        return f"@{str(attrs.get('text', '')).lstrip('@')}"

    if ntype == "emoji":
        attrs = cast(dict[str, Any], node.get("attrs", {}))
        return str(attrs.get("shortName", attrs.get("text", "")))

    if ntype == "hardBreak":
        return ""

    # Unknown node — try rendering children if any
    if content:
        return _render_nodes(content, list_level)
    return None


def _render_inline(nodes: list[dict]) -> str:
    """Render a list of inline nodes (text, mentions, emoji, etc.) into a single line."""
    parts: list[str] = []
    for node in nodes:
        if not isinstance(node, dict):
            continue
        ntype = node.get("type", "")
        if ntype == "text":
            parts.append(_render_text(node))
        elif ntype == "mention":
            attrs = cast(dict[str, Any], node.get("attrs", {}))
            parts.append(f"@{str(attrs.get('text', '')).lstrip('@')}")
        elif ntype == "emoji":
            attrs = cast(dict[str, Any], node.get("attrs", {}))
            parts.append(str(attrs.get("shortName", attrs.get("text", ""))))
        elif ntype == "hardBreak":
            parts.append("\n")
        elif ntype == "inlineCard":
            attrs = cast(dict[str, Any], node.get("attrs", {}))
            url = str(attrs.get("url", ""))
            if url:
                parts.append(url)
        elif ntype in ("media", "mediaInline"):
            attrs = cast(dict[str, Any], node.get("attrs", {}))
            filename = str(attrs.get("alt", "") or attrs.get("id", "media"))
            att_id = str(attrs.get("id", ""))
            if att_id and att_id != filename:
                parts.append(f"[attachment: {filename} (id={att_id})]")
            else:
                parts.append(f"[attachment: {filename}]")
        elif ntype == "status":
            attrs = cast(dict[str, Any], node.get("attrs", {}))
            text = str(attrs.get("text", ""))
            if text:
                parts.append(f"[{text}]")
        else:
            # Try rendering content recursively for unknown inline types
            content = node.get("content", [])
            if isinstance(content, list):
                parts.append(_render_inline(cast(list[dict], content)))
    return "".join(parts)


def _render_text(node: dict) -> str:
    """Render a text node, applying marks (bold, italic, code, link)."""
    text = str(node.get("text", ""))
    marks = cast(list[dict[str, Any]], node.get("marks", []))
    for mark in marks:
        mtype = mark.get("type", "")
        if mtype == "strong":
            text = f"**{text}**"
        elif mtype == "em":
            text = f"*{text}*"
        elif mtype == "code":
            text = f"`{text}`"
        elif mtype == "link":
            attrs = cast(dict[str, Any], mark.get("attrs", {}))
            url = str(attrs.get("href", ""))
            if url:
                text = f"[{text}]({url})"
        elif mtype == "strike":
            text = f"~~{text}~~"
    return text


def _render_list_items(items: list[dict], ordered: bool, level: int) -> str:
    """Render list items with proper indentation."""
    lines: list[str] = []
    indent = "  " * level
    for i, item in enumerate(items):
        if not isinstance(item, dict):
            continue
        content = cast(list[dict[str, Any]], item.get("content", []))
        # First child is usually a paragraph — render inline
        first_parts: list[str] = []
        rest_parts: list[str] = []
        for j, child in enumerate(content):
            if j == 0 and child.get("type") == "paragraph":
                first_parts.append(_render_inline(child.get("content", [])))
            elif child.get("type") in ("bulletList", "orderedList"):
                rest_parts.append(_render_node(child, level + 1) or "")
            else:
                rendered = _render_node(child, level + 1)
                if rendered:
                    rest_parts.append(rendered)
        prefix = f"{i + 1}." if ordered else "-"
        line_text = "".join(first_parts)
        lines.append(f"{indent}{prefix} {line_text}")
        for part in rest_parts:
            lines.append(part)
    return "\n".join(lines)


def _render_table_cell(nodes: list[dict]) -> str:
    """Render table cell content, flattening block-level nodes into a single line."""
    # Use _render_nodes for block-level support, then collapse to single line for table format
    rendered = _render_nodes(nodes)
    return " ".join(rendered.split("\n")).strip()


def _render_table(rows: list[dict]) -> str:
    """Render a table as markdown-style."""
    rendered_rows: list[list[str]] = []
    for row in rows:
        if not isinstance(row, dict) or row.get("type") not in ("tableRow",):
            continue
        cells: list[str] = []
        for cell in cast(list[dict[str, Any]], row.get("content", [])):
            cells.append(_render_table_cell(cast(list[dict], cell.get("content", []))))
        rendered_rows.append(cells)
    if not rendered_rows:
        return ""
    # Build markdown table
    lines: list[str] = []
    lines.append("| " + " | ".join(rendered_rows[0]) + " |")
    lines.append("| " + " | ".join("---" for _ in rendered_rows[0]) + " |")
    for rendered_row in rendered_rows[1:]:
        lines.append("| " + " | ".join(rendered_row) + " |")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# URL collection
# ---------------------------------------------------------------------------


def _collect_urls(node: dict, urls: list[str]) -> None:
    """Recursively traverse ADF and collect URLs."""
    ntype = node.get("type", "")

    # Link marks on text nodes
    if ntype == "text":
        for mark in node.get("marks", []):
            if mark.get("type") == "link":
                href = mark.get("attrs", {}).get("href", "")
                if href:
                    urls.append(href)

    # inlineCard
    if ntype == "inlineCard":
        url = node.get("attrs", {}).get("url", "")
        if url:
            urls.append(url)

    # media / mediaInline with URL
    if ntype in ("media", "mediaInline"):
        url = node.get("attrs", {}).get("url", "")
        if url:
            urls.append(url)

    # Recurse into content
    for child in node.get("content", []):
        if isinstance(child, dict):
            _collect_urls(child, urls)


# ---------------------------------------------------------------------------
# Media reference extraction
# ---------------------------------------------------------------------------


def extract_media_refs_from_adf(adf_doc: dict | None) -> list[dict]:
    """Extract attachment references from media/mediaInline nodes in an ADF document.

    Returns a list of dicts with 'id' and 'alt' keys.
    """
    refs: list[dict] = []
    if adf_doc and isinstance(adf_doc, dict):
        _collect_media_refs(adf_doc, refs)
    return refs


def _collect_media_refs(node: dict, refs: list[dict]) -> None:
    """Recursively collect media references from ADF nodes."""
    ntype = node.get("type", "")
    if ntype in ("media", "mediaInline"):
        attrs = node.get("attrs", {})
        media_id = attrs.get("id", "")
        if media_id:
            refs.append(
                {
                    "id": media_id,
                    "alt": attrs.get("alt", ""),
                }
            )
    for child in node.get("content", []):
        if isinstance(child, dict):
            _collect_media_refs(child, refs)
