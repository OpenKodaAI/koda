"""Filesystem-backed workspace config scanning and import helpers."""

from __future__ import annotations

import fnmatch
import hashlib
import json
import os
import re
import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from koda.config import DEFAULT_WORK_DIR, PROJECT_DIRS, SENSITIVE_DIRS
from koda.skills._package import SkillPackageError, scan_skill_package
from koda.utils.workdir import validate_work_dir

WORKSPACE_SCAN_SCHEMA_VERSION = "workspace_config_scan.v1"

DEFAULT_MAX_DEPTH = 8
DEFAULT_MAX_ENTRIES = 2500
DEFAULT_MAX_FILE_BYTES = 256 * 1024
DEFAULT_MAX_TOTAL_BYTES = 3 * 1024 * 1024
CONTENT_EXCERPT_CHARS = 1200
IMPORT_CONTENT_CHARS = 12000

IGNORED_DIR_NAMES = frozenset(
    {
        ".cache",
        ".git",
        ".hg",
        ".mypy_cache",
        ".next",
        ".pytest_cache",
        ".ruff_cache",
        ".svn",
        ".tox",
        "__pycache__",
        "build",
        "coverage",
        "dist",
        "logs",
        "node_modules",
        "target",
        "venv",
        ".venv",
    }
)

SKIP_FILE_NAMES = frozenset(
    {
        ".env",
        ".env.local",
        ".env.production",
        ".env.development",
        "id_rsa",
        "id_dsa",
        "id_ecdsa",
        "id_ed25519",
    }
)

SKIP_FILE_PATTERNS = (
    ".env.*",
    "*.key",
    "*.pem",
    "*.p12",
    "*.pfx",
    "*_rsa",
    "*_dsa",
    "*_ecdsa",
    "*_ed25519",
)

SECRET_RE = re.compile(
    r"(?i)\b(api[_-]?key|secret|token|password|credential|private[_-]?key)\b"
    r"(\s*[:=]\s*)"
    r"([\"']?)[A-Za-z0-9_./+=\-]{8,}\3"
)

FRONTMATTER_RE = re.compile(r"\A---\s*\n(.*?)\n---\s*\n?", re.DOTALL)


@dataclass(slots=True)
class WorkspaceScanSource:
    source_id: str
    kind: str
    tool: str
    relative_path: str
    absolute_path: str
    scope: str = "workspace"
    name: str = ""
    description: str = ""
    confidence: str = "high"
    risk: str = "low"
    status: str = "detected"
    import_action: str = "review_only"
    warnings: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    content_excerpt: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_id": self.source_id,
            "kind": self.kind,
            "tool": self.tool,
            "relative_path": self.relative_path,
            "absolute_path": self.absolute_path,
            "scope": self.scope,
            "name": self.name,
            "description": self.description,
            "confidence": self.confidence,
            "risk": self.risk,
            "status": self.status,
            "import_action": self.import_action,
            "warnings": list(self.warnings),
            "metadata": dict(self.metadata),
            "content_excerpt": self.content_excerpt,
        }


@dataclass(slots=True)
class WorkspaceScanResult:
    root_path: str
    root_kind: str = "local_path"
    status: str = "completed"
    sources: list[WorkspaceScanSource] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    truncated: bool = False
    max_depth: int = DEFAULT_MAX_DEPTH
    max_entries: int = DEFAULT_MAX_ENTRIES
    max_file_bytes: int = DEFAULT_MAX_FILE_BYTES
    max_total_bytes: int = DEFAULT_MAX_TOTAL_BYTES

    @property
    def scan_hash(self) -> str:
        payload = [
            {
                "source_id": source.source_id,
                "kind": source.kind,
                "tool": source.tool,
                "relative_path": source.relative_path,
                "risk": source.risk,
                "status": source.status,
                "import_action": source.import_action,
                "content_sha256": source.metadata.get("content_sha256", ""),
            }
            for source in sorted(self.sources, key=lambda item: item.source_id)
        ]
        raw = json.dumps(payload, ensure_ascii=True, sort_keys=True).encode("utf-8")
        return hashlib.sha256(raw).hexdigest()[:24]

    @property
    def summary(self) -> dict[str, Any]:
        by_kind: dict[str, int] = {}
        by_tool: dict[str, int] = {}
        by_risk: dict[str, int] = {}
        for source in self.sources:
            by_kind[source.kind] = by_kind.get(source.kind, 0) + 1
            by_tool[source.tool] = by_tool.get(source.tool, 0) + 1
            by_risk[source.risk] = by_risk.get(source.risk, 0) + 1
        return {
            "total_sources": len(self.sources),
            "by_kind": by_kind,
            "by_tool": by_tool,
            "by_risk": by_risk,
            "review_required": sum(1 for source in self.sources if source.risk in {"review", "high"}),
            "blocked": sum(1 for source in self.sources if source.risk == "blocked"),
            "importable": sum(1 for source in self.sources if source.import_action == "append_workspace_prompt"),
            "truncated": self.truncated,
        }

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": WORKSPACE_SCAN_SCHEMA_VERSION,
            "root_path": self.root_path,
            "root_kind": self.root_kind,
            "scan_hash": self.scan_hash,
            "status": self.status,
            "summary": self.summary,
            "sources": [source.to_dict() for source in self.sources],
            "warnings": list(self.warnings),
            "limits": {
                "max_depth": self.max_depth,
                "max_entries": self.max_entries,
                "max_file_bytes": self.max_file_bytes,
                "max_total_bytes": self.max_total_bytes,
            },
        }


def workspace_source_from_dict(value: dict[str, Any]) -> WorkspaceScanSource:
    return WorkspaceScanSource(
        source_id=str(value.get("source_id") or ""),
        kind=str(value.get("kind") or "unknown"),
        tool=str(value.get("tool") or "generic"),
        relative_path=str(value.get("relative_path") or ""),
        absolute_path=str(value.get("absolute_path") or ""),
        scope=str(value.get("scope") or "workspace"),
        name=str(value.get("name") or ""),
        description=str(value.get("description") or ""),
        confidence=str(value.get("confidence") or "medium"),
        risk=str(value.get("risk") or "review"),
        status=str(value.get("status") or "detected"),
        import_action=str(value.get("import_action") or "review_only"),
        warnings=[str(item) for item in value.get("warnings") or []],
        metadata=dict(value.get("metadata") or {}),
        content_excerpt=str(value.get("content_excerpt") or ""),
    )


def validate_workspace_root(path: str) -> Path:
    validation = validate_work_dir(path)
    if not validation.ok:
        raise ValueError(validation.reason or "Invalid workspace directory.")
    root = Path(validation.path)
    for sensitive in SENSITIVE_DIRS:
        sensitive_path = Path(os.path.realpath(os.path.expanduser(sensitive)))
        if root == sensitive_path or sensitive_path in root.parents:
            raise ValueError(f"Blocked workspace root: {root}")
    return root


def directory_roots_payload() -> dict[str, Any]:
    roots: list[str] = []
    for candidate in [DEFAULT_WORK_DIR, *PROJECT_DIRS]:
        try:
            validated = validate_workspace_root(candidate)
        except ValueError:
            continue
        text = str(validated)
        if text not in roots:
            roots.append(text)
    return {"items": [{"path": item, "label": Path(item).name or item} for item in roots]}


def list_directory_payload(path: str) -> dict[str, Any]:
    root = validate_workspace_root(path)
    items: list[dict[str, Any]] = []
    for child in sorted(root.iterdir(), key=lambda item: (not item.is_dir(), item.name.lower())):
        if child.name in IGNORED_DIR_NAMES:
            continue
        try:
            resolved = child.resolve()
        except OSError:
            continue
        if child.is_symlink() and (resolved != root and root not in resolved.parents):
            continue
        if child.is_dir():
            items.append({"path": str(resolved), "name": child.name, "kind": "directory"})
        elif child.is_file() and child.name in {"AGENTS.md", "CLAUDE.md", ".cursorrules"}:
            items.append({"path": str(resolved), "name": child.name, "kind": "file"})
    return {"path": str(root), "parent": str(root.parent) if root.parent != root else None, "items": items}


def scan_workspace_directory(
    path: str,
    *,
    max_depth: int = DEFAULT_MAX_DEPTH,
    max_entries: int = DEFAULT_MAX_ENTRIES,
    max_file_bytes: int = DEFAULT_MAX_FILE_BYTES,
    max_total_bytes: int = DEFAULT_MAX_TOTAL_BYTES,
) -> WorkspaceScanResult:
    root = validate_workspace_root(path)
    result = WorkspaceScanResult(
        root_path=str(root),
        max_depth=max_depth,
        max_entries=max_entries,
        max_file_bytes=max_file_bytes,
        max_total_bytes=max_total_bytes,
    )
    entries = 0
    total_bytes = 0

    for current, dirnames, filenames in os.walk(root, topdown=True, followlinks=False):
        current_path = Path(current)
        try:
            relative_dir = current_path.relative_to(root)
        except ValueError:
            dirnames[:] = []
            continue
        depth = 0 if str(relative_dir) == "." else len(relative_dir.parts)
        if depth > max_depth:
            dirnames[:] = []
            result.truncated = True
            continue
        dirnames[:] = [
            dirname
            for dirname in dirnames
            if dirname not in IGNORED_DIR_NAMES and not (current_path / dirname).is_symlink()
        ]
        for filename in sorted(filenames):
            entries += 1
            if entries > max_entries:
                result.truncated = True
                result.warnings.append("scan.max_entries_reached")
                return result
            file_path = current_path / filename
            if not _candidate_file(root, file_path):
                continue
            try:
                size = file_path.stat().st_size
            except OSError:
                continue
            if size > max_file_bytes:
                if _path_might_be_source(root, file_path):
                    result.sources.append(
                        _source(
                            root,
                            file_path,
                            kind="unknown",
                            tool=_tool_for_path(root, file_path),
                            risk="review",
                            status="unsupported",
                            import_action="review_only",
                            warnings=["file.too_large"],
                        )
                    )
                continue
            if total_bytes + size > max_total_bytes:
                result.truncated = True
                result.warnings.append("scan.max_total_bytes_reached")
                return result
            text = _read_text_file(file_path)
            if text is None:
                continue
            total_bytes += len(text.encode("utf-8", errors="ignore"))
            result.sources.extend(_detect_sources(root, file_path, text))
    return result


def read_importable_source_content(
    root_path: str, source: WorkspaceScanSource, *, limit: int = IMPORT_CONTENT_CHARS
) -> str:
    root = validate_workspace_root(root_path)
    target = (root / source.relative_path).resolve()
    if target != root and root not in target.parents:
        raise ValueError("source path escapes workspace root")
    text = _read_text_file(target)
    if text is None:
        return ""
    text = _redact_text(text)
    if len(text) > limit:
        return text[:limit].rstrip() + "\n\n[truncated by Koda workspace import]"
    return text


def _candidate_file(root: Path, file_path: Path) -> bool:
    try:
        resolved = file_path.resolve()
    except OSError:
        return False
    if file_path.is_symlink() and (resolved != root and root not in resolved.parents):
        return False
    name = file_path.name
    if name in SKIP_FILE_NAMES:
        return False
    return not any(fnmatch.fnmatch(name, pattern) for pattern in SKIP_FILE_PATTERNS)


def _path_might_be_source(root: Path, file_path: Path) -> bool:
    rel = _rel(root, file_path)
    name = file_path.name
    return (
        name
        in {
            "AGENTS.md",
            "AGENTS.override.md",
            "CLAUDE.md",
            "CLAUDE.local.md",
            ".cursorrules",
            ".mcp.json",
            "mcp.json",
            "SKILL.md",
            "koda-skill.yaml",
            "plugin.yaml",
            "plugin.yml",
            "MEMORY.md",
            "SOUL.md",
        }
        or rel.startswith(".claude/")
        or rel.startswith(".codex/")
        or rel.startswith(".cursor/")
        or rel.startswith(".agents/")
        or rel.startswith(".mcp/")
    )


def _read_text_file(file_path: Path) -> str | None:
    try:
        raw = file_path.read_bytes()
    except OSError:
        return None
    if b"\x00" in raw[:4096]:
        return None
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError:
        try:
            return raw.decode("utf-8", errors="replace")
        except Exception:
            return None


def _detect_sources(root: Path, file_path: Path, text: str) -> list[WorkspaceScanSource]:
    rel = _rel(root, file_path)
    name = file_path.name
    if not _path_might_be_source(root, file_path):
        return []

    if name in {"AGENTS.md", "AGENTS.override.md"}:
        return [
            _source(
                root,
                file_path,
                kind="instructions",
                tool="codex",
                scope=_scope_for_rel(rel),
                name=name,
                description="Codex workspace instructions",
                risk="low",
                import_action="append_workspace_prompt",
                text=text,
            )
        ]
    if name == "CLAUDE.md" or rel == ".claude/CLAUDE.md":
        return [
            _source(
                root,
                file_path,
                kind="instructions",
                tool="claude",
                scope=_scope_for_rel(rel),
                name=name,
                description="Claude project memory",
                risk="low",
                import_action="append_workspace_prompt",
                text=text,
            )
        ]
    if name == "CLAUDE.local.md":
        return [
            _source(
                root,
                file_path,
                kind="memory",
                tool="claude",
                name=name,
                description="Claude local memory requires review",
                risk="review",
                import_action="review_only",
                text=text,
            )
        ]
    if rel.startswith(".claude/rules/") and name.endswith(".md"):
        metadata, _ = _parse_frontmatter(text)
        return [
            _source(
                root,
                file_path,
                kind="rule",
                tool="claude",
                scope=_scope_for_rel(rel),
                name=str(metadata.get("name") or Path(name).stem),
                description=str(metadata.get("description") or "Claude rule"),
                risk="low",
                import_action="append_workspace_prompt",
                metadata={"frontmatter": metadata},
                text=text,
            )
        ]
    if rel.startswith(".cursor/rules/") and name.endswith(".mdc"):
        metadata, _ = _parse_frontmatter(text)
        return [
            _source(
                root,
                file_path,
                kind="rule",
                tool="cursor",
                scope=_scope_for_rel(rel),
                name=str(metadata.get("description") or Path(name).stem),
                description="Cursor project rule",
                risk="low",
                import_action="append_workspace_prompt",
                metadata={"frontmatter": metadata, "globs": metadata.get("globs")},
                text=text,
            )
        ]
    if name == ".cursorrules":
        return [
            _source(
                root,
                file_path,
                kind="instructions",
                tool="cursor",
                name=name,
                description="Cursor legacy project rules",
                risk="low",
                import_action="append_workspace_prompt",
                text=text,
            )
        ]
    if name in {".mcp.json", "mcp.json"} or rel == ".cursor/mcp.json" or rel.startswith(".mcp/"):
        metadata = _parse_mcp_metadata(text)
        return [
            _source(
                root,
                file_path,
                kind="mcp",
                tool="cursor" if rel.startswith(".cursor/") else "claude" if name == ".mcp.json" else "generic",
                name=name,
                description="Project MCP configuration",
                risk="review",
                import_action="mcp_review",
                metadata=metadata,
                text=text,
            )
        ]
    if rel.startswith(".claude/agents/") and name.endswith(".md"):
        metadata, body = _parse_frontmatter(text)
        return [
            _source(
                root,
                file_path,
                kind="agent",
                tool="claude",
                name=str(metadata.get("name") or Path(name).stem),
                description=str(metadata.get("description") or _first_line(body) or "Claude subagent"),
                risk="review",
                import_action="create_agent_draft",
                metadata={"frontmatter": metadata},
                text=text,
            )
        ]
    if rel.startswith(".codex/agents/") and name.endswith(".toml"):
        metadata = _parse_toml_metadata(text)
        return [
            _source(
                root,
                file_path,
                kind="agent",
                tool="codex",
                name=str(metadata.get("name") or Path(name).stem),
                description=str(metadata.get("description") or "Codex subagent"),
                risk="review",
                import_action="create_agent_draft",
                metadata={"toml": metadata},
                text=text,
            )
        ]
    if rel == ".codex/config.toml":
        metadata = _parse_toml_metadata(text)
        action = "mcp_review" if "mcp" in metadata or "mcp_servers" in metadata else "settings_review"
        return [
            _source(
                root,
                file_path,
                kind="settings",
                tool="codex",
                name=name,
                description="Codex project config",
                risk="review",
                import_action=action,
                metadata={"toml_keys": sorted(metadata.keys())},
                text=text,
            )
        ]
    if rel.startswith(".claude/") and fnmatch.fnmatch(name, "settings*.json"):
        return _settings_sources(root, file_path, text)
    if name == "SKILL.md" and (rel.startswith(".agents/skills/") or rel.startswith(".claude/skills/")):
        return [
            _source(
                root,
                file_path,
                kind="skill",
                tool="claude" if rel.startswith(".claude/") else "codex",
                name=Path(file_path.parent).name,
                description="Project skill requires review before installation",
                risk="review",
                import_action="skill_review",
                text=text,
            )
        ]
    if name in {"koda-skill.yaml", "plugin.yaml", "plugin.yml"}:
        manifest_metadata: dict[str, Any] = {"manifest_name": name}
        warnings: list[str] = []
        try:
            scan = scan_skill_package(file_path.parent)
            manifest_metadata["skill_scan"] = {
                "decision": scan.decision,
                "severity": scan.severity,
                "risk_classes": list(scan.risk_classes),
                "package_hash": scan.package_hash,
            }
        except (SkillPackageError, ValueError) as exc:
            warnings.append(str(exc))
        return [
            _source(
                root,
                file_path,
                kind="manifest",
                tool="koda",
                name=Path(file_path.parent).name,
                description="Koda skill package manifest",
                risk="review",
                import_action="skill_review",
                metadata=manifest_metadata,
                warnings=warnings,
                text=text,
            )
        ]
    if name == "MEMORY.md" or rel.startswith(".agents/memory"):
        return [
            _source(
                root,
                file_path,
                kind="memory",
                tool="generic",
                name=name,
                description="Project memory candidate",
                risk="review",
                import_action="review_only",
                text=text,
            )
        ]
    if name == "SOUL.md" or rel.startswith(".agents/soul"):
        return [
            _source(
                root,
                file_path,
                kind="soul",
                tool="generic",
                name=name,
                description="Project identity/personality candidate",
                risk="review",
                import_action="review_only",
                text=text,
            )
        ]
    return [
        _source(
            root,
            file_path,
            kind="unknown",
            tool=_tool_for_path(root, file_path),
            risk="review",
            import_action="review_only",
            text=text,
        )
    ]


def _settings_sources(root: Path, file_path: Path, text: str) -> list[WorkspaceScanSource]:
    metadata = _parse_json_metadata(text)
    sources = [
        _source(
            root,
            file_path,
            kind="settings",
            tool="claude",
            name=file_path.name,
            description="Claude settings require review",
            risk="review",
            import_action="settings_review",
            metadata={"json_keys": sorted(metadata.keys())},
            text=text,
        )
    ]
    hooks = metadata.get("hooks")
    if isinstance(hooks, dict):
        for event_name, hook_value in sorted(hooks.items()):
            for index, command in enumerate(_extract_hook_commands(hook_value)):
                sources.append(
                    _source(
                        root,
                        file_path,
                        kind="hook",
                        tool="claude",
                        name=f"{event_name} hook",
                        description="Claude hook command is blocked during import",
                        risk="blocked",
                        status="blocked",
                        import_action="blocked_hook",
                        metadata={
                            "event": str(event_name),
                            "index": index,
                            "command_preview": _redact_text(command)[:240],
                        },
                        text=command,
                    )
                )
    return sources


def _source(
    root: Path,
    file_path: Path,
    *,
    kind: str,
    tool: str,
    scope: str = "workspace",
    name: str = "",
    description: str = "",
    confidence: str = "high",
    risk: str = "low",
    status: str = "detected",
    import_action: str = "review_only",
    warnings: list[str] | None = None,
    metadata: dict[str, Any] | None = None,
    text: str = "",
) -> WorkspaceScanSource:
    rel = _rel(root, file_path)
    clean = _redact_text(text)
    source_metadata = dict(metadata or {})
    if text:
        source_metadata.setdefault("content_sha256", hashlib.sha256(text.encode("utf-8")).hexdigest())
        source_metadata.setdefault("bytes", len(text.encode("utf-8", errors="ignore")))
    return WorkspaceScanSource(
        source_id=_source_id(str(root), rel, kind, tool, name),
        kind=kind,
        tool=tool,
        relative_path=rel,
        absolute_path=str(file_path.resolve()),
        scope=scope,
        name=name or file_path.name,
        description=description,
        confidence=confidence,
        risk=risk,
        status=status,
        import_action=import_action,
        warnings=list(warnings or []),
        metadata=source_metadata,
        content_excerpt=_clip(clean, CONTENT_EXCERPT_CHARS),
    )


def _source_id(root: str, relative_path: str, kind: str, tool: str, name: str) -> str:
    seed = f"{WORKSPACE_SCAN_SCHEMA_VERSION}:{root}:{relative_path}:{kind}:{tool}:{name}"
    return hashlib.sha256(seed.encode("utf-8")).hexdigest()[:24]


def _rel(root: Path, file_path: Path) -> str:
    return file_path.resolve().relative_to(root).as_posix()


def _scope_for_rel(rel: str) -> str:
    parent = str(Path(rel).parent).replace("\\", "/")
    if parent in {"", "."}:
        return "workspace"
    return parent


def _tool_for_path(root: Path, file_path: Path) -> str:
    rel = _rel(root, file_path)
    if rel.startswith(".claude/") or file_path.name.startswith("CLAUDE"):
        return "claude"
    if rel.startswith(".codex/") or file_path.name.startswith("AGENTS"):
        return "codex"
    if rel.startswith(".cursor/") or file_path.name == ".cursorrules":
        return "cursor"
    if file_path.name in {"koda-skill.yaml", "plugin.yaml", "plugin.yml"}:
        return "koda"
    return "generic"


def _clip(value: str, limit: int) -> str:
    clean = value.strip()
    if len(clean) <= limit:
        return clean
    return clean[: max(0, limit - 1)].rstrip() + "…"


def _redact_text(value: str) -> str:
    return SECRET_RE.sub(lambda match: f"{match.group(1)}{match.group(2)}[REDACTED]", value)


def _parse_frontmatter(text: str) -> tuple[dict[str, Any], str]:
    match = FRONTMATTER_RE.match(text)
    if not match:
        return {}, text
    try:
        metadata = yaml.safe_load(match.group(1)) or {}
    except yaml.YAMLError:
        metadata = {}
    return (metadata if isinstance(metadata, dict) else {}), text[match.end() :]


def _parse_json_metadata(text: str) -> dict[str, Any]:
    try:
        loaded = json.loads(text)
    except json.JSONDecodeError:
        return {}
    return loaded if isinstance(loaded, dict) else {}


def _parse_toml_metadata(text: str) -> dict[str, Any]:
    try:
        loaded = tomllib.loads(text)
    except tomllib.TOMLDecodeError:
        return {}
    return loaded if isinstance(loaded, dict) else {}


def _parse_mcp_metadata(text: str) -> dict[str, Any]:
    raw = _parse_json_metadata(text)
    servers = raw.get("mcpServers") or raw.get("servers") or raw
    parsed_servers: list[dict[str, Any]] = []
    if isinstance(servers, dict):
        for name, server in sorted(servers.items()):
            if not isinstance(server, dict):
                continue
            env_payload = server.get("env")
            env: dict[Any, Any] = env_payload if isinstance(env_payload, dict) else {}
            command = server.get("command")
            args = server.get("args")
            url = server.get("url") or server.get("remote_url")
            parsed_servers.append(
                {
                    "name": str(name),
                    "transport": "remote" if url else "stdio" if command else "unknown",
                    "command": str(command) if isinstance(command, str) else "",
                    "args": [str(item) for item in args] if isinstance(args, list) else [],
                    "url": str(url) if isinstance(url, str) else "",
                    "env_keys": sorted(str(key) for key in env),
                }
            )
    return {"servers": parsed_servers}


def _extract_hook_commands(value: Any) -> list[str]:
    commands: list[str] = []
    if isinstance(value, str):
        commands.append(value)
    elif isinstance(value, dict):
        command = value.get("command")
        if isinstance(command, str):
            commands.append(command)
        for nested in value.values():
            if nested is not command:
                commands.extend(_extract_hook_commands(nested))
    elif isinstance(value, list):
        for item in value:
            commands.extend(_extract_hook_commands(item))
    return commands


def _first_line(value: str) -> str:
    for line in value.splitlines():
        clean = line.strip().strip("#").strip()
        if clean:
            return clean
    return ""
