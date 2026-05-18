"""KodaSkill package contracts, scanner, install state, and rollback helpers."""

from __future__ import annotations

import ast
import hashlib
import json
import re
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml

from koda.agent_contract import CORE_TOOL_CATALOG
from koda.config import AGENT_ID, PLUGIN_SYSTEM_ENABLED, STATE_ROOT_DIR
from koda.logging_config import get_logger
from koda.services.tool_registry import ToolDefinition, ToolSchemaError, validate_json_schema_object

KODA_SKILL_SCHEMA_VERSION = "koda_skill.v1"
SKILL_SCAN_VERSION = "skill_scan.v1"
SKILL_LOCK_VERSION = "skill_lock.v1"
SKILL_PACKAGE_SCANNER_VERSION = "skill_package_scanner.v1"

_MANIFEST_NAMES = ("koda-skill.yaml", "koda-skill.yml", "plugin.yaml", "plugin.yml")
_MAX_FILE_BYTES = 512 * 1024
_MAX_PACKAGE_BYTES = 5 * 1024 * 1024
_MAX_PACKAGE_FILES = 200
_ALLOWED_PERMISSION_KEYS = frozenset({"filesystem", "network", "secrets", "shell", "mcp", "packages", "browser"})
_HIGH_RISK_CLASSES = frozenset({"secret_access", "code_execution", "destructive_write", "unknown"})
_REVIEW_RISK_CLASSES = frozenset({"network_write", "low_risk_write"})
_DANGEROUS_IMPORTS = frozenset({"subprocess", "pexpect"})
_NETWORK_IMPORTS = frozenset({"socket", "requests", "httpx", "urllib", "paramiko"})
_SECRET_RE = re.compile(
    r"(-----BEGIN [A-Z ]*PRIVATE KEY-----|"
    r"\b(?:api[_-]?key|secret|token|password)\b\s*[:=]\s*['\"][^'\"]{12,}|"
    r"\bsk-[A-Za-z0-9_-]{20,}|"
    r"\bAKIA[0-9A-Z]{16}\b)",
    re.IGNORECASE,
)
_VALID_PACKAGE_ID = re.compile(r"^[a-z][a-z0-9_-]{1,63}$")
_VALID_TOOL_ID = re.compile(r"^[a-z][a-z0-9_]{1,63}$")

log = get_logger(__name__)
_REGISTERED_PACKAGE_IDS: set[tuple[str, str]] = set()


class SkillPackageError(ValueError):
    """Raised when a package operation cannot proceed."""

    def __init__(
        self,
        code: str,
        message: str,
        *,
        category: str = "validation",
        retryable: bool = False,
        user_action: str = "Inspect the package scan findings.",
        payload: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.error = {
            "code": code,
            "category": category,
            "message": message,
            "retryable": retryable,
            "user_action": user_action,
            **dict(payload or {}),
        }


@dataclass(frozen=True, slots=True)
class SkillScanFinding:
    id: str
    severity: str
    category: str
    message: str
    path: str = ""
    user_action: str = "Review the package before installing."

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "severity": self.severity,
            "category": self.category,
            "message": self.message,
            "path": self.path,
            "user_action": self.user_action,
        }


@dataclass(frozen=True, slots=True)
class KodaSkillPackage:
    package_dir: Path
    manifest_path: Path
    manifest_kind: str
    id: str
    name: str
    version: str
    description: str
    author: str
    license: str = ""
    source: str = ""
    permissions: dict[str, Any] = field(default_factory=dict)
    docs: dict[str, Any] = field(default_factory=dict)
    tests: dict[str, Any] = field(default_factory=dict)
    skills: tuple[dict[str, Any], ...] = ()
    tools: tuple[dict[str, Any], ...] = ()
    raw_manifest: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": KODA_SKILL_SCHEMA_VERSION,
            "manifest_kind": self.manifest_kind,
            "id": self.id,
            "name": self.name,
            "version": self.version,
            "description": self.description,
            "author": self.author,
            "license": self.license,
            "source": self.source,
            "permissions": dict(self.permissions),
            "docs": dict(self.docs),
            "tests": dict(self.tests),
            "skills": [dict(item) for item in self.skills],
            "tools": [dict(item) for item in self.tools],
            "path": str(self.package_dir),
            "manifest_path": str(self.manifest_path),
        }


@dataclass(frozen=True, slots=True)
class SkillScanResult:
    package: KodaSkillPackage
    decision: str
    severity: str
    findings: tuple[SkillScanFinding, ...]
    permissions_requested: dict[str, Any]
    risk_classes: tuple[str, ...]
    redactions: tuple[str, ...]
    package_hash: str
    file_hashes: dict[str, str]
    scanner_version: str = SKILL_PACKAGE_SCANNER_VERSION

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": SKILL_SCAN_VERSION,
            "decision": self.decision,
            "severity": self.severity,
            "findings": [finding.to_dict() for finding in self.findings],
            "permissions_requested": dict(self.permissions_requested),
            "risk_classes": list(self.risk_classes),
            "redactions": list(self.redactions),
            "package_hash": self.package_hash,
            "file_hashes": dict(self.file_hashes),
            "scanner_version": self.scanner_version,
            "package": self.package.to_dict(),
        }


def parse_skill_package(path: str | Path) -> KodaSkillPackage:
    """Parse `koda-skill.yaml` or legacy `plugin.yaml` without importing code."""

    package_dir = Path(path).expanduser()
    if package_dir.is_file():
        manifest_path = package_dir
        package_dir = manifest_path.parent
    else:
        found_manifest = next((package_dir / name for name in _MANIFEST_NAMES if (package_dir / name).exists()), None)
        if found_manifest is None:
            raise SkillPackageError(
                "skill.validation_failed",
                f"No koda-skill.yaml or plugin.yaml found under {package_dir}.",
            )
        manifest_path = found_manifest
    if not package_dir.exists() or not package_dir.is_dir():
        raise SkillPackageError("skill.validation_failed", f"Package directory not found: {package_dir}")

    try:
        raw = yaml.safe_load(manifest_path.read_text(encoding="utf-8")) or {}
    except Exception as exc:  # pragma: no cover - yaml detail varies
        raise SkillPackageError("skill.validation_failed", f"Failed to parse manifest: {exc}") from exc
    if not isinstance(raw, dict):
        raise SkillPackageError("skill.validation_failed", "Manifest must be a YAML mapping.")

    manifest_kind = "legacy_plugin" if manifest_path.name.startswith("plugin.") else "koda_skill"
    if manifest_kind == "legacy_plugin":
        return _parse_legacy_plugin_manifest(package_dir, manifest_path, raw)
    return _parse_koda_skill_manifest(package_dir, manifest_path, raw)


def scan_skill_package(
    path: str | Path,
    *,
    agent_id: str | None = None,
    installed_tool_ids: set[str] | None = None,
) -> SkillScanResult:
    """Scan a package statically and return a `skill_scan.v1` result."""

    package = parse_skill_package(path)
    findings: list[SkillScanFinding] = []
    risk_classes: set[str] = set()
    redactions: set[str] = set()
    package_hash, file_hashes = _hash_package(package.package_dir, findings)

    if not _VALID_PACKAGE_ID.match(package.id):
        findings.append(
            _finding(
                "manifest.invalid_id",
                "error",
                "manifest",
                f"Invalid package id: {package.id}",
                package.manifest_path,
                "Use lowercase letters, numbers, hyphen, or underscore.",
            )
        )

    _scan_permissions(package, findings, risk_classes)
    _scan_skills(package, findings)
    _scan_tools(package, findings, risk_classes, agent_id=agent_id, installed_tool_ids=installed_tool_ids)
    _scan_files(package, findings, risk_classes, redactions)

    severities = [finding.severity for finding in findings]
    severity = _highest_severity(severities)
    decision = "allow"
    if any(item in {"error", "critical"} for item in severities):
        decision = "deny"
    elif severities:
        decision = "review_required"

    return SkillScanResult(
        package=package,
        decision=decision,
        severity=severity,
        findings=tuple(findings),
        permissions_requested=package.permissions,
        risk_classes=tuple(sorted(risk_classes)),
        redactions=tuple(sorted(redactions)),
        package_hash=package_hash,
        file_hashes=file_hashes,
    )


def install_skill_package(
    path: str | Path,
    *,
    agent_id: str | None = None,
    review_accepted: bool = False,
) -> dict[str, Any]:
    """Install a scanned package and persist a `skill_lock.v1` payload."""

    normalized_agent = _normalize_agent_id(agent_id)
    scan = scan_skill_package(path, agent_id=normalized_agent)
    if scan.decision == "deny":
        _emit_package_audit("skill_package.denied", normalized_agent, {"scan": scan.to_dict()})
        raise SkillPackageError(
            "skill.scan_denied",
            "Skill package scan denied installation.",
            category="policy_denied",
            user_action="Resolve scanner findings before installing.",
            payload={"scan": scan.to_dict()},
        )
    if scan.decision == "review_required" and not review_accepted:
        raise SkillPackageError(
            "skill.policy_denied",
            "Skill package requires explicit review before install.",
            category="policy_denied",
            user_action="Review findings and retry with review_accepted=true.",
            payload={"scan": scan.to_dict()},
        )

    previous_lock = get_skill_package_lock(normalized_agent, scan.package.id)
    lock = _build_lock(scan, normalized_agent, previous_lock=previous_lock)
    _persist_skill_package_lock(normalized_agent, lock)
    _emit_package_audit("skill_package.install", normalized_agent, {"lock": _lock_summary(lock)})
    _clear_tool_registry_cache()
    if PLUGIN_SYSTEM_ENABLED:
        ensure_installed_package_tools_registered(normalized_agent, force=True)
    return {"ok": True, "lock": lock, "scan": scan.to_dict()}


def uninstall_skill_package(agent_id: str | None, package_id: str) -> dict[str, Any]:
    normalized_agent = _normalize_agent_id(agent_id)
    lock = get_skill_package_lock(normalized_agent, package_id)
    if not lock:
        raise SkillPackageError("skill.validation_failed", f"Skill package '{package_id}' is not installed.")
    _delete_skill_package_lock(normalized_agent, package_id)
    _emit_package_audit("skill_package.uninstall", normalized_agent, {"lock": _lock_summary(lock)})
    _unregister_plugin_if_present(package_id)
    _clear_tool_registry_cache()
    return {"ok": True, "package_id": package_id, "uninstalled": True}


def rollback_skill_package(agent_id: str | None, package_id: str) -> dict[str, Any]:
    normalized_agent = _normalize_agent_id(agent_id)
    current = get_skill_package_lock(normalized_agent, package_id)
    previous = _safe_dict(current.get("previous_revision") if current else None)
    if not current or not previous:
        raise SkillPackageError(
            "skill.rollback_unavailable",
            f"No rollback revision is available for package '{package_id}'.",
            category="non_retryable",
            user_action="Reinstall a known-good package version manually.",
        )
    restored = dict(previous)
    restored["rolled_back_at"] = _now_iso()
    restored["previous_revision"] = current
    _persist_skill_package_lock(normalized_agent, restored)
    _emit_package_audit("skill_package.rollback", normalized_agent, {"lock": _lock_summary(restored)})
    _clear_tool_registry_cache()
    if PLUGIN_SYSTEM_ENABLED:
        ensure_installed_package_tools_registered(normalized_agent, force=True)
    return {"ok": True, "lock": restored}


def list_skill_package_locks(agent_id: str | None = None) -> list[dict[str, Any]]:
    normalized_agent = _normalize_agent_id(agent_id)
    db_rows = _list_db_locks(normalized_agent)
    if db_rows is not None:
        return db_rows
    return _fallback_locks(normalized_agent)


def get_skill_package_lock(agent_id: str | None, package_id: str) -> dict[str, Any] | None:
    normalized_agent = _normalize_agent_id(agent_id)
    db_lock = _get_db_lock(normalized_agent, package_id)
    if db_lock is not None:
        return db_lock
    for lock in _fallback_locks(normalized_agent):
        if str(lock.get("package_id") or "") == package_id:
            return lock
    return None


def get_installed_package_skills(agent_id: str | None = None) -> list[dict[str, Any]]:
    skills: list[dict[str, Any]] = []
    for lock in list_skill_package_locks(agent_id):
        for skill in lock.get("installed_skills") or []:
            if isinstance(skill, dict) and skill.get("enabled", True):
                skills.append(dict(skill))
    return skills


def get_installed_package_tool_definitions(agent_id: str | None = None) -> list[ToolDefinition]:
    definitions: list[ToolDefinition] = []
    for lock in list_skill_package_locks(agent_id):
        package_id = str(lock.get("package_id") or "")
        for raw_tool in lock.get("installed_tools") or []:
            if not isinstance(raw_tool, dict):
                continue
            definitions.append(_tool_definition_from_package_tool(raw_tool, package_id=package_id))
    return definitions


def ensure_installed_package_tools_registered(agent_id: str | None = None, *, force: bool = False) -> None:
    """Register installed package handlers in the process plugin registry."""

    if not PLUGIN_SYSTEM_ENABLED:
        return
    normalized_agent = _normalize_agent_id(agent_id)
    from koda.plugins import get_registry
    from koda.plugins.registry import PluginManifest, PluginToolDef

    registry = get_registry()
    for lock in list_skill_package_locks(normalized_agent):
        package_id = str(lock.get("package_id") or "")
        key = (normalized_agent, package_id)
        if not force and key in _REGISTERED_PACKAGE_IDS:
            continue
        tools = [
            PluginToolDef(
                id=str(tool.get("id") or ""),
                title=str(tool.get("title") or tool.get("id") or ""),
                category=str(tool.get("category") or "skill_package"),
                description=str(tool.get("description") or ""),
                handler_path=str(tool.get("handler") or tool.get("handler_path") or ""),
                read_only=str(tool.get("access_level") or "write") == "read",
                params=_safe_dict(tool.get("args_schema")),
                integration_id=f"skill_package:{package_id}",
                access_level=str(tool.get("access_level") or "write"),
            )
            for tool in lock.get("installed_tools") or []
            if isinstance(tool, dict)
        ]
        if not tools:
            continue
        _unregister_plugin_if_present(package_id)
        manifest = PluginManifest(
            name=package_id,
            version=str(lock.get("version") or "0.0.0"),
            description=str(lock.get("description") or ""),
            author=str(lock.get("author") or ""),
            plugin_dir=Path(str(lock.get("package_path") or ".")),
            tools=tools,
            prompt_section="",
            requires={"source": "skill_package"},
        )
        err = registry.register(manifest)
        if err:
            log.warning("skill_package_tool_registration_failed", package_id=package_id, error=err)
            continue
        _REGISTERED_PACKAGE_IDS.add(key)


def skill_package_error_response(exc: SkillPackageError) -> dict[str, Any]:
    return {"ok": False, "error": dict(exc.error)}


def _parse_koda_skill_manifest(package_dir: Path, manifest_path: Path, raw: dict[str, Any]) -> KodaSkillPackage:
    package_id = _text(raw.get("id") or raw.get("name"))
    if not package_id:
        raise SkillPackageError("skill.validation_failed", "Manifest missing required field: id.")
    return KodaSkillPackage(
        package_dir=package_dir.resolve(),
        manifest_path=manifest_path.resolve(),
        manifest_kind="koda_skill",
        id=package_id,
        name=_text(raw.get("name") or package_id),
        version=_text(raw.get("version") or "0.0.0"),
        description=_text(raw.get("description")),
        author=_text(raw.get("author") or "unknown"),
        license=_text(raw.get("license")),
        source=_text(raw.get("source") or str(package_dir)),
        permissions=_safe_dict(raw.get("permissions")),
        docs=_safe_dict(raw.get("docs")),
        tests=_safe_dict(raw.get("tests")),
        skills=tuple(_normalize_manifest_skill(item, package_dir) for item in _safe_list(raw.get("skills"))),
        tools=tuple(_normalize_manifest_tool(item) for item in _safe_list(raw.get("tools"))),
        raw_manifest=dict(raw),
    )


def _parse_legacy_plugin_manifest(package_dir: Path, manifest_path: Path, raw: dict[str, Any]) -> KodaSkillPackage:
    package_id = _text(raw.get("id") or raw.get("name"))
    if not package_id:
        raise SkillPackageError("skill.validation_failed", "Manifest missing required field: name.")
    tools: list[dict[str, Any]] = []
    for item in _safe_list(raw.get("tools")):
        if not isinstance(item, dict):
            continue
        tools.append(
            _normalize_manifest_tool(
                {
                    "id": item.get("id"),
                    "title": item.get("title") or item.get("id"),
                    "category": item.get("category") or "plugin",
                    "description": item.get("description") or "",
                    "handler": item.get("handler") or item.get("handler_path"),
                    "access_level": item.get("access_level") or ("read" if item.get("read_only") else "write"),
                    "args_schema": (
                        item.get("args_schema") or item.get("params") or {"type": "object", "properties": {}}
                    ),
                    "risk_class": item.get("risk_class") or ("read_context" if item.get("read_only") else "unknown"),
                    "approval_default": item.get("approval_default"),
                }
            )
        )
    return KodaSkillPackage(
        package_dir=package_dir.resolve(),
        manifest_path=manifest_path.resolve(),
        manifest_kind="legacy_plugin",
        id=package_id,
        name=_text(raw.get("name") or package_id),
        version=_text(raw.get("version") or "0.0.0"),
        description=_text(raw.get("description")),
        author=_text(raw.get("author") or "unknown"),
        source=_text(raw.get("source") or str(package_dir)),
        permissions=_safe_dict(raw.get("permissions")),
        docs=_safe_dict(raw.get("docs")),
        tools=tuple(tools),
        raw_manifest=dict(raw),
    )


def _normalize_manifest_skill(item: Any, package_dir: Path) -> dict[str, Any]:
    raw = _safe_dict(item)
    content_path = _text(raw.get("content_path"))
    content = _text(raw.get("content"))
    if content_path:
        resolved = _safe_child_path(package_dir, content_path)
        if resolved and resolved.is_file():
            content = resolved.read_text(encoding="utf-8")
    return {
        "id": _text(raw.get("id") or raw.get("name")),
        "name": _text(raw.get("name") or raw.get("id")),
        "instruction": _text(raw.get("instruction")),
        "content": content,
        "content_path": content_path,
        "aliases": _string_list(raw.get("aliases")),
        "tags": _string_list(raw.get("tags")),
        "triggers": _string_list(raw.get("triggers")),
        "requires": _string_list(raw.get("requires")),
        "conflicts": _string_list(raw.get("conflicts")),
        "output_format_enforcement": _text(raw.get("output_format_enforcement")),
        "max_token_budget": int(raw.get("max_token_budget") or 2500),
        "enabled": True,
        "source": "skill_package",
    }


def _normalize_manifest_tool(item: Any) -> dict[str, Any]:
    raw = _safe_dict(item)
    tool_id = _text(raw.get("id"))
    access_level = _text(raw.get("access_level") or "write").lower() or "write"
    risk_class = _text(raw.get("risk_class") or ("read_context" if access_level == "read" else "unknown")).lower()
    approval_default = _text(raw.get("approval_default"))
    if not approval_default:
        approval_default = "allow" if access_level == "read" and risk_class == "read_context" else "require_approval"
    return {
        "id": tool_id,
        "title": _text(raw.get("title") or tool_id),
        "category": _text(raw.get("category") or "skill_package"),
        "description": _text(raw.get("description")),
        "handler": _text(raw.get("handler") or raw.get("handler_path")),
        "access_level": access_level,
        "effect_tags": _string_list(raw.get("effect_tags")),
        "idempotency": _text(raw.get("idempotency") or ("read_only" if access_level == "read" else "unknown")),
        "risk_class": risk_class,
        "approval_default": approval_default,
        "timeout_seconds": int(raw.get("timeout_seconds") or 30),
        "args_schema": _safe_dict(raw.get("args_schema") or raw.get("params") or {"type": "object", "properties": {}}),
    }


def _hash_package(package_dir: Path, findings: list[SkillScanFinding]) -> tuple[str, dict[str, str]]:
    files = _iter_package_files(package_dir, findings)
    package_hasher = hashlib.sha256()
    file_hashes: dict[str, str] = {}
    total_bytes = 0
    for file_path in files:
        rel = _rel(package_dir, file_path)
        try:
            content = file_path.read_bytes()
        except OSError as exc:
            findings.append(_finding("file.unreadable", "error", "filesystem", str(exc), file_path))
            continue
        total_bytes += len(content)
        if len(content) > _MAX_FILE_BYTES:
            findings.append(
                _finding(
                    "file.too_large",
                    "error",
                    "filesystem",
                    f"File exceeds {_MAX_FILE_BYTES} byte budget.",
                    file_path,
                )
            )
        digest = hashlib.sha256(content).hexdigest()
        file_hashes[rel] = digest
        package_hasher.update(rel.encode("utf-8"))
        package_hasher.update(digest.encode("ascii"))
    if total_bytes > _MAX_PACKAGE_BYTES:
        findings.append(
            _finding(
                "package.too_large",
                "error",
                "filesystem",
                f"Package exceeds {_MAX_PACKAGE_BYTES} byte budget.",
                package_dir,
            )
        )
    return package_hasher.hexdigest(), file_hashes


def _iter_package_files(package_dir: Path, findings: list[SkillScanFinding]) -> list[Path]:
    root = package_dir.resolve()
    files: list[Path] = []
    for item in sorted(package_dir.rglob("*")):
        try:
            resolved = item.resolve()
        except OSError:
            findings.append(_finding("path.unresolved", "error", "filesystem", "Path cannot be resolved.", item))
            continue
        if not _is_relative_to(resolved, root):
            findings.append(_finding("path.escape", "critical", "filesystem", "Path escapes package root.", item))
            continue
        if item.is_symlink() and not _is_relative_to(resolved, root):
            findings.append(
                _finding("path.symlink_escape", "critical", "filesystem", "Symlink escapes package root.", item)
            )
            continue
        if item.is_file():
            files.append(item)
    if len(files) > _MAX_PACKAGE_FILES:
        findings.append(
            _finding(
                "package.too_many_files",
                "error",
                "filesystem",
                f"Package has {len(files)} files, above {_MAX_PACKAGE_FILES}.",
                package_dir,
            )
        )
    return files[: _MAX_PACKAGE_FILES + 1]


def _scan_permissions(package: KodaSkillPackage, findings: list[SkillScanFinding], risk_classes: set[str]) -> None:
    for key, value in package.permissions.items():
        normalized = str(key).strip().lower()
        if normalized not in _ALLOWED_PERMISSION_KEYS:
            risk_classes.add("unknown")
            findings.append(
                _finding(
                    "permission.unknown",
                    "error",
                    "permissions",
                    f"Unknown permission key: {key}",
                    package.manifest_path,
                )
            )
            continue
        if normalized in {"secrets", "shell", "packages"} and value:
            risk_classes.add("secret_access" if normalized == "secrets" else "code_execution")
            findings.append(
                _finding(
                    f"permission.{normalized}",
                    "error",
                    "permissions",
                    f"Permission '{normalized}' requires a stricter review path than Phase 4 allows.",
                    package.manifest_path,
                )
            )
        if normalized == "network" and value:
            risk_classes.add("network_write")
            findings.append(
                _finding(
                    "permission.network",
                    "warning",
                    "permissions",
                    "Network permission requires operator review.",
                    package.manifest_path,
                )
            )


def _scan_skills(package: KodaSkillPackage, findings: list[SkillScanFinding]) -> None:
    for skill in package.skills:
        if not skill.get("id") or not skill.get("name"):
            findings.append(_finding("skill.missing_id", "error", "manifest", "Skill must define id and name."))
        if not str(skill.get("content") or "").strip():
            findings.append(_finding("skill.empty_content", "error", "manifest", "Skill content is empty."))
        content_path = _text(skill.get("content_path"))
        if content_path and not _safe_child_path(package.package_dir, content_path):
            findings.append(
                _finding("skill.path_escape", "critical", "filesystem", "Skill content_path escapes package.")
            )


def _scan_tools(
    package: KodaSkillPackage,
    findings: list[SkillScanFinding],
    risk_classes: set[str],
    *,
    agent_id: str | None,
    installed_tool_ids: set[str] | None,
) -> None:
    existing_ids = set(CORE_TOOL_CATALOG)
    existing_ids.update(installed_tool_ids or _installed_tool_ids(agent_id, exclude_package_id=package.id))
    seen: set[str] = set()
    for tool in package.tools:
        tool_id = _text(tool.get("id"))
        risk_class = _text(tool.get("risk_class") or "unknown").lower()
        if risk_class:
            risk_classes.add(risk_class)
        if not _VALID_TOOL_ID.match(tool_id):
            findings.append(_finding("tool.invalid_id", "error", "manifest", f"Invalid tool id: {tool_id}"))
        if tool_id in seen:
            findings.append(_finding("tool.duplicate_id", "error", "manifest", f"Duplicate tool id: {tool_id}"))
        seen.add(tool_id)
        if tool_id in existing_ids:
            findings.append(_finding("tool.id_conflict", "error", "manifest", f"Tool id already exists: {tool_id}"))
        try:
            validate_json_schema_object(_safe_dict(tool.get("args_schema")))
        except ToolSchemaError as exc:
            findings.append(_finding("tool.schema_invalid", "error", "manifest", str(exc)))
        handler = _text(tool.get("handler"))
        if not _handler_file(package.package_dir, handler):
            findings.append(
                _finding(
                    "tool.handler_missing",
                    "error",
                    "manifest",
                    f"Handler not found for tool {tool_id}: {handler}",
                )
            )
        if risk_class in _HIGH_RISK_CLASSES:
            findings.append(
                _finding(
                    f"tool.risk.{risk_class}",
                    "error",
                    "risk",
                    f"Tool {tool_id} declares high or unknown risk class {risk_class}.",
                )
            )
        elif risk_class in _REVIEW_RISK_CLASSES and tool.get("access_level") != "read":
            findings.append(
                _finding("tool.review_required", "warning", "risk", f"Tool {tool_id} requires operator review.")
            )


def _scan_files(
    package: KodaSkillPackage,
    findings: list[SkillScanFinding],
    risk_classes: set[str],
    redactions: set[str],
) -> None:
    for file_path in _iter_package_files(package.package_dir, findings):
        if file_path.name in {"setup.py", "install.sh", "postinstall.sh"}:
            risk_classes.add("code_execution")
            findings.append(
                _finding("file.install_script", "error", "supply_chain", "Install scripts are not allowed.", file_path)
            )
        try:
            text = file_path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        except OSError:
            continue
        if _SECRET_RE.search(text):
            risk_classes.add("secret_access")
            redactions.add(_rel(package.package_dir, file_path))
            findings.append(
                _finding("file.secret_literal", "error", "secrets", "Secret-looking content found.", file_path)
            )
        if file_path.suffix == ".py":
            _scan_python_file(file_path, text, findings, risk_classes)
        if file_path.name == "package.json" and '"scripts"' in text:
            risk_classes.add("code_execution")
            findings.append(
                _finding(
                    "file.package_scripts",
                    "error",
                    "supply_chain",
                    "package.json scripts are not allowed.",
                    file_path,
                )
            )


def _scan_python_file(
    file_path: Path,
    text: str,
    findings: list[SkillScanFinding],
    risk_classes: set[str],
) -> None:
    try:
        tree = ast.parse(text)
    except SyntaxError as exc:
        findings.append(_finding("python.syntax", "error", "code", f"Python syntax error: {exc}", file_path))
        return
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                root = alias.name.split(".", 1)[0]
                _classify_import(root, findings, risk_classes, file_path)
        elif isinstance(node, ast.ImportFrom):
            root = str(node.module or "").split(".", 1)[0]
            _classify_import(root, findings, risk_classes, file_path)
        elif isinstance(node, ast.Call):
            dotted = _call_name(node.func)
            if dotted in {"eval", "exec", "os.system"} or dotted.startswith("subprocess."):
                risk_classes.add("code_execution")
                findings.append(
                    _finding(
                        "python.dangerous_call",
                        "error",
                        "code",
                        f"Dangerous call is not allowed: {dotted}",
                        file_path,
                    )
                )


def _classify_import(
    root: str,
    findings: list[SkillScanFinding],
    risk_classes: set[str],
    file_path: Path,
) -> None:
    if root in _DANGEROUS_IMPORTS:
        risk_classes.add("code_execution")
        findings.append(
            _finding("python.dangerous_import", "error", "code", f"Dangerous import is not allowed: {root}", file_path)
        )
    elif root in _NETWORK_IMPORTS:
        risk_classes.add("network_write")
        findings.append(
            _finding(
                "python.network_import",
                "warning",
                "code",
                f"Network-capable import requires review: {root}",
                file_path,
            )
        )


def _build_lock(
    scan: SkillScanResult,
    agent_id: str,
    *,
    previous_lock: dict[str, Any] | None,
) -> dict[str, Any]:
    package = scan.package
    return {
        "schema_version": SKILL_LOCK_VERSION,
        "package_id": package.id,
        "name": package.name,
        "version": package.version,
        "description": package.description,
        "author": package.author,
        "source": package.source,
        "package_path": str(package.package_dir),
        "manifest_path": str(package.manifest_path),
        "package_hash": scan.package_hash,
        "manifest": package.to_dict(),
        "agent_id": agent_id,
        "installed_skills": [
            {
                **dict(skill),
                "source_package_id": package.id,
                "version": package.version,
                "source_path": str(package.package_dir),
            }
            for skill in package.skills
        ],
        "installed_tools": [
            {
                **dict(tool),
                "source_package_id": package.id,
                "version": package.version,
                "source_path": str(package.package_dir),
            }
            for tool in package.tools
        ],
        "scan_summary": {
            "schema_version": SKILL_SCAN_VERSION,
            "decision": scan.decision,
            "severity": scan.severity,
            "findings": [finding.to_dict() for finding in scan.findings],
            "risk_classes": list(scan.risk_classes),
            "package_hash": scan.package_hash,
            "scanner_version": scan.scanner_version,
        },
        "installed_at": _now_iso(),
        "previous_revision": previous_lock,
        "rollback_ref": previous_lock.get("package_hash") if previous_lock else None,
    }


def _tool_definition_from_package_tool(raw_tool: dict[str, Any], *, package_id: str) -> ToolDefinition:
    return ToolDefinition(
        id=str(raw_tool.get("id") or ""),
        title=str(raw_tool.get("title") or raw_tool.get("id") or ""),
        category=str(raw_tool.get("category") or "skill_package"),
        description=str(raw_tool.get("description") or ""),
        args_schema=_safe_dict(raw_tool.get("args_schema")) or {"type": "object", "properties": {}},
        handler_ref=f"skill_package:{package_id}:{raw_tool.get('handler') or ''}",
        access_level=str(raw_tool.get("access_level") or "write"),
        effect_tags=tuple(_string_list(raw_tool.get("effect_tags"))),
        idempotency=str(raw_tool.get("idempotency") or "unknown"),
        risk_class=str(raw_tool.get("risk_class") or "unknown"),
        approval_default=str(raw_tool.get("approval_default") or "require_approval"),
        timeout_seconds=int(raw_tool.get("timeout_seconds") or 30),
        ui_metadata={"source_package_id": package_id, "installed": True},
        docs_metadata={"contract": KODA_SKILL_SCHEMA_VERSION, "source_package_id": package_id},
        source="skill_package",
    )


def _persist_skill_package_lock(agent_id: str, lock: dict[str, Any]) -> None:
    _upsert_db_lock(agent_id, lock)
    locks = [item for item in _fallback_locks(agent_id) if item.get("package_id") != lock.get("package_id")]
    locks.append(lock)
    _write_fallback_locks(agent_id, locks)


def _delete_skill_package_lock(agent_id: str, package_id: str) -> None:
    _delete_db_lock(agent_id, package_id)
    locks = [item for item in _fallback_locks(agent_id) if item.get("package_id") != package_id]
    _write_fallback_locks(agent_id, locks)


def _upsert_db_lock(agent_id: str, lock: dict[str, Any]) -> None:
    backend = _primary_backend(agent_id)
    if backend is None:
        return
    try:
        from koda.state.primary import run_coro_sync

        run_coro_sync(backend.upsert_skill_package_lock(agent_id, lock))
    except Exception:
        log.debug("skill_package_db_upsert_skipped", exc_info=True)


def _list_db_locks(agent_id: str) -> list[dict[str, Any]] | None:
    backend = _primary_backend(agent_id)
    if backend is None:
        return None
    try:
        from koda.state.primary import run_coro_sync

        return list(run_coro_sync(backend.list_skill_package_locks(agent_id)))
    except Exception:
        log.debug("skill_package_db_list_skipped", exc_info=True)
        return None


def _get_db_lock(agent_id: str, package_id: str) -> dict[str, Any] | None:
    backend = _primary_backend(agent_id)
    if backend is None:
        return None
    try:
        from koda.state.primary import run_coro_sync

        result = run_coro_sync(backend.get_skill_package_lock(agent_id, package_id))
        return dict(result) if isinstance(result, dict) else None
    except Exception:
        log.debug("skill_package_db_get_skipped", exc_info=True)
        return None


def _delete_db_lock(agent_id: str, package_id: str) -> None:
    backend = _primary_backend(agent_id)
    if backend is None:
        return
    try:
        from koda.state.primary import run_coro_sync

        run_coro_sync(backend.delete_skill_package_lock(agent_id, package_id))
    except Exception:
        log.debug("skill_package_db_delete_skipped", exc_info=True)


def _append_db_event(agent_id: str, package_id: str, event_type: str, payload: dict[str, Any]) -> None:
    backend = _primary_backend(agent_id)
    if backend is None:
        return
    try:
        from koda.state.primary import run_coro_sync

        run_coro_sync(backend.append_skill_package_event(agent_id, package_id, event_type, payload))
    except Exception:
        log.debug("skill_package_db_event_skipped", exc_info=True)


def _primary_backend(agent_id: str) -> Any | None:
    try:
        from koda.state.primary import get_primary_state_backend

        return get_primary_state_backend(agent_id=agent_id)
    except Exception:
        return None


def _fallback_locks(agent_id: str) -> list[dict[str, Any]]:
    path = _fallback_lock_path(agent_id)
    if not path.exists():
        return []
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return []
    locks = payload.get("locks") if isinstance(payload, dict) else payload
    return [dict(item) for item in locks if isinstance(item, dict)] if isinstance(locks, list) else []


def _write_fallback_locks(agent_id: str, locks: list[dict[str, Any]]) -> None:
    path = _fallback_lock_path(agent_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"schema_version": SKILL_LOCK_VERSION, "locks": locks}, indent=2), encoding="utf-8")


def _fallback_lock_path(agent_id: str) -> Path:
    return STATE_ROOT_DIR / "skill_packages" / _normalize_agent_id(agent_id).lower() / "locks.json"


def _emit_package_audit(event_type: str, agent_id: str, details: dict[str, Any]) -> None:
    package_id = str(details.get("package_id") or details.get("lock", {}).get("package_id") or "")
    _append_db_event(agent_id, package_id, event_type, details)
    try:
        from koda.services.audit import AuditEvent, emit

        emit(AuditEvent(event_type=event_type, details={"agent_id": agent_id, **details}))
    except Exception:
        log.debug("skill_package_audit_skipped", exc_info=True)


def _clear_tool_registry_cache() -> None:
    try:
        from koda.services import tool_registry

        tool_registry._DEFAULT_REGISTRY_CACHE.clear()
    except Exception:
        pass


def _unregister_plugin_if_present(package_id: str) -> None:
    if not PLUGIN_SYSTEM_ENABLED:
        return
    try:
        from koda.plugins import get_registry

        get_registry().unregister(package_id)
    except Exception:
        pass


def _installed_tool_ids(agent_id: str | None, *, exclude_package_id: str = "") -> set[str]:
    ids: set[str] = set()
    for lock in list_skill_package_locks(agent_id):
        if exclude_package_id and str(lock.get("package_id") or "") == exclude_package_id:
            continue
        for tool in lock.get("installed_tools") or []:
            if isinstance(tool, dict) and tool.get("id"):
                ids.add(str(tool["id"]))
    return ids


def _safe_child_path(root: Path, value: str) -> Path | None:
    try:
        candidate = (root / value).resolve()
        return candidate if _is_relative_to(candidate, root.resolve()) else None
    except Exception:
        return None


def _handler_file(root: Path, handler: str) -> Path | None:
    parts = handler.rsplit(".", 1)
    if len(parts) != 2:
        return None
    module_path, func_name = parts
    if not module_path or not func_name:
        return None
    candidate = _safe_child_path(root, f"{module_path.replace('.', '/')}.py")
    return candidate if candidate and candidate.is_file() else None


def _call_name(func: ast.AST) -> str:
    if isinstance(func, ast.Name):
        return func.id
    if isinstance(func, ast.Attribute):
        owner = _call_name(func.value)
        return f"{owner}.{func.attr}" if owner else func.attr
    return ""


def _finding(
    finding_id: str,
    severity: str,
    category: str,
    message: str,
    path: str | Path = "",
    user_action: str = "Fix the package and scan again.",
) -> SkillScanFinding:
    return SkillScanFinding(finding_id, severity, category, message, str(path), user_action)


def _highest_severity(values: list[str]) -> str:
    order = {"info": 0, "warning": 1, "error": 2, "critical": 3}
    if not values:
        return "info"
    return max(values, key=lambda value: order.get(value, 0))


def _safe_dict(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, dict) else {}


def _safe_list(value: Any) -> list[Any]:
    return list(value) if isinstance(value, list) else []


def _string_list(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value] if value.strip() else []
    if not isinstance(value, list | tuple | set):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def _text(value: Any) -> str:
    return str(value or "").strip()


def _normalize_agent_id(agent_id: str | None) -> str:
    return str(agent_id or AGENT_ID or "default").strip() or "default"


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _rel(root: Path, path: Path) -> str:
    try:
        return str(path.resolve().relative_to(root.resolve()))
    except Exception:
        return str(path)


def _is_relative_to(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def _lock_summary(lock: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": lock.get("schema_version"),
        "package_id": lock.get("package_id"),
        "version": lock.get("version"),
        "agent_id": lock.get("agent_id"),
        "package_hash": lock.get("package_hash"),
        "installed_skills": [item.get("id") for item in lock.get("installed_skills") or [] if isinstance(item, dict)],
        "installed_tools": [item.get("id") for item in lock.get("installed_tools") or [] if isinstance(item, dict)],
    }
