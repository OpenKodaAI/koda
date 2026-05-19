"""Capability summaries — derived view of an AgentSpec for routing and prompt injection.

A ``CapabilitySummary`` is the concise "who handles what" signal a squad member
exposes to peers and to capability-based routers. It's *derived* from the
AgentSpec (source of truth) and *cached* in ``squad_member_capabilities`` for
fast lookup. Regenerate when an AgentSpec changes.
"""

from __future__ import annotations

import json
import re
import uuid as _uuid_module
from contextlib import suppress
from dataclasses import dataclass, field
from typing import Any

from koda.logging_config import get_logger

log = get_logger(__name__)

_SCHEMA_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_DELEGATE_WHEN_MAX = 300
_DO_NOT_DELEGATE_MAX = 300
_DOMAINS_MAX = 8
_OUTCOMES_MAX = 3
_TOOL_CATEGORIES_MAX = 6
_ALLOWED_TOOL_IDS_MAX = 32
_INTEGRATION_IDS_MAX = 16

_TOOL_PREFIX_CATEGORY: dict[str, str] = {
    "mcp_": "mcp",
    "file_": "fileops",
    "db_": "db",
    "browser_": "browser",
    "image_": "image",
    "job_": "ops",
    "shell_": "shell",
    "git_": "git",
    "plugin_": "plugin",
    "workflow_": "workflow",
    "snapshot_": "snapshots",
    "agent_": "agent_comm",
    "squad_": "agent_comm",
    "webhook_": "webhook",
}


def _infer_tool_category(tool: str) -> str:
    for prefix, label in _TOOL_PREFIX_CATEGORY.items():
        if tool.startswith(prefix):
            return label
    return "tool"


@dataclass
class CapabilitySummary:
    agent_id: str
    display_name: str
    role: str
    domains: list[str] = field(default_factory=list)
    primary_outcomes: list[str] = field(default_factory=list)
    tool_categories: list[str] = field(default_factory=list)
    delegate_when: str = ""
    do_not_delegate: str = ""
    is_coordinator: bool = False
    allowed_tool_ids: list[str] = field(default_factory=list)
    integration_ids: list[str] = field(default_factory=list)
    preferred_provider: str = ""
    preferred_model: str = ""
    cost_weight: float = 1.0
    load_score: float = 0.0
    quality_score: float = 0.5
    recent_success_rate: float | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "agent_id": self.agent_id,
            "display_name": self.display_name,
            "role": self.role,
            "domains": list(self.domains),
            "primary_outcomes": list(self.primary_outcomes),
            "tool_categories": list(self.tool_categories),
            "delegate_when": self.delegate_when,
            "do_not_delegate": self.do_not_delegate,
            "is_coordinator": self.is_coordinator,
            "allowed_tool_ids": list(self.allowed_tool_ids),
            "integration_ids": list(self.integration_ids),
            "preferred_provider": self.preferred_provider,
            "preferred_model": self.preferred_model,
            "cost_weight": self.cost_weight,
            "load_score": self.load_score,
            "quality_score": self.quality_score,
            "recent_success_rate": self.recent_success_rate,
            "metadata": dict(self.metadata),
        }


def _coerce_list(value: Any, *, cap: int | None = None) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        items = [value]
    elif isinstance(value, (list, tuple, set)):
        items = list(value)
    else:
        return []
    out = [str(x).strip() for x in items if x is not None and str(x).strip()]
    if cap is not None:
        out = out[:cap]
    return out


def _coerce_text(value: Any, *, cap: int) -> str:
    if not value:
        return ""
    text = str(value).strip()
    return text[:cap]


def build_capability_summary(
    agent_spec: dict[str, Any],
    *,
    agent_id: str | None = None,
    display_name: str | None = None,
    is_coordinator: bool = False,
) -> CapabilitySummary:
    """Derive a CapabilitySummary from an AgentSpec payload (normalized or raw)."""
    mission = agent_spec.get("mission_profile") or {}
    tool_policy = agent_spec.get("tool_policy") or {}
    model_policy = agent_spec.get("model_policy") or {}
    integration_policy = agent_spec.get("integration_policy") or agent_spec.get("integrations") or {}
    if not isinstance(mission, dict):
        mission = {}
    if not isinstance(tool_policy, dict):
        tool_policy = {}
    if not isinstance(model_policy, dict):
        model_policy = {}
    if not isinstance(integration_policy, dict):
        integration_policy = {}

    raw_aid = agent_id or agent_spec.get("agent_id") or ""
    aid = str(raw_aid).strip().upper()
    name = (display_name or "").strip() or aid

    role = _coerce_text(mission.get("role"), cap=120)
    domains = _coerce_list(mission.get("domains"), cap=_DOMAINS_MAX)
    primary_outcomes = _coerce_list(mission.get("primary_outcomes"), cap=_OUTCOMES_MAX)
    delegate_when = _coerce_text(mission.get("delegate_when"), cap=_DELEGATE_WHEN_MAX)
    do_not_delegate = _coerce_text(mission.get("do_not_delegate"), cap=_DO_NOT_DELEGATE_MAX)

    allowed_tool_ids = _coerce_list(tool_policy.get("allowed_tool_ids"), cap=_ALLOWED_TOOL_IDS_MAX)
    categories = sorted({_infer_tool_category(t) for t in allowed_tool_ids if isinstance(t, str) and t})[
        :_TOOL_CATEGORIES_MAX
    ]
    preferred_provider, preferred_model = _resolve_preferred_model(model_policy)
    integration_ids = _extract_integration_ids(integration_policy)
    ops = agent_spec.get("routing_profile") or agent_spec.get("delivery_profile") or {}
    if not isinstance(ops, dict):
        ops = {}

    return CapabilitySummary(
        agent_id=aid,
        display_name=name,
        role=role,
        domains=domains,
        primary_outcomes=primary_outcomes,
        tool_categories=categories,
        delegate_when=delegate_when,
        do_not_delegate=do_not_delegate,
        is_coordinator=bool(is_coordinator),
        allowed_tool_ids=allowed_tool_ids,
        integration_ids=integration_ids,
        preferred_provider=preferred_provider,
        preferred_model=preferred_model,
        cost_weight=_coerce_float(ops.get("cost_weight"), default=1.0, low=0.1, high=10.0),
        load_score=_coerce_float(ops.get("load_score"), default=0.0, low=0.0, high=1.0),
        quality_score=_coerce_float(ops.get("quality_score"), default=0.5, low=0.0, high=1.0),
        recent_success_rate=_coerce_optional_float(ops.get("recent_success_rate"), low=0.0, high=1.0),
        metadata={key: value for key, value in ops.items() if key in {"notes", "quality_source", "load_source"}},
    )


def _coerce_float(value: Any, *, default: float, low: float, high: float) -> float:
    try:
        parsed = float(value if value is not None else default)
    except (TypeError, ValueError):
        parsed = default
    return max(low, min(high, parsed))


def _coerce_optional_float(value: Any, *, low: float, high: float) -> float | None:
    if value is None:
        return None
    return _coerce_float(value, default=low, low=low, high=high)


def _resolve_preferred_model(model_policy: dict[str, Any]) -> tuple[str, str]:
    allowed = _coerce_list(model_policy.get("allowed_providers"))
    provider = str(model_policy.get("default_provider") or "").strip().lower()
    if not provider and allowed:
        provider = allowed[0].lower()
    default_models = model_policy.get("default_models") or {}
    if not isinstance(default_models, dict):
        default_models = {}
    model = str(default_models.get(provider) or "").strip() if provider else ""
    functional_defaults = model_policy.get("functional_defaults") or {}
    if not model and isinstance(functional_defaults, dict):
        general = functional_defaults.get("general") or {}
        if isinstance(general, dict):
            provider = provider or str(general.get("provider_id") or "").strip().lower()
            model = str(general.get("model_id") or "").strip()
    return provider, model


def _extract_integration_ids(integration_policy: dict[str, Any]) -> list[str]:
    candidates: list[str] = []
    for key in ("allowed_integration_ids", "integration_ids", "enabled_integrations"):
        candidates.extend(_coerce_list(integration_policy.get(key)))
    grants = integration_policy.get("grants") or integration_policy.get("permissions") or {}
    if isinstance(grants, dict):
        candidates.extend(str(key) for key in grants if key)
    return _coerce_list(candidates, cap=_INTEGRATION_IDS_MAX)


def format_capability_block(
    summaries: list[CapabilitySummary],
    *,
    exclude_agent_id: str | None = None,
) -> str:
    """Render the ``<squad_members>`` markdown block for prompt injection."""
    excl = (exclude_agent_id or "").strip().upper()
    lines = ["<squad_members>"]
    for cs in summaries:
        if excl and cs.agent_id == excl:
            continue
        flag = " (coordinator)" if cs.is_coordinator else ""
        lines.append(f"- {cs.display_name} [{cs.agent_id}]{flag}")
        if cs.role:
            lines.append(f"  role: {cs.role}")
        if cs.domains:
            lines.append(f"  domains: {', '.join(cs.domains)}")
        if cs.primary_outcomes:
            lines.append(f"  outcomes: {'; '.join(cs.primary_outcomes)}")
        if cs.delegate_when:
            lines.append(f"  delegate_when: {cs.delegate_when}")
        if cs.do_not_delegate:
            lines.append(f"  do_not_delegate: {cs.do_not_delegate}")
        if cs.tool_categories:
            lines.append(f"  tools: {', '.join(cs.tool_categories)}")
        if cs.preferred_provider or cs.preferred_model:
            model_label = "/".join(part for part in [cs.preferred_provider, cs.preferred_model] if part)
            lines.append(f"  model: {model_label}")
    lines.append("</squad_members>")
    return "\n".join(lines)


def _row_to_summary(row: Any) -> CapabilitySummary:
    def _decode(value: Any) -> Any:
        if isinstance(value, str):
            try:
                return json.loads(value)
            except (json.JSONDecodeError, ValueError):
                return None
        return value

    domains = _decode(row["domains"]) or []
    outcomes = _decode(row["primary_outcomes"]) or []
    tool_categories = _decode(row["tool_categories"]) or []
    return CapabilitySummary(
        agent_id=row["agent_id"],
        display_name=row["display_name"] or row["agent_id"],
        role=row["role_label"] or "",
        domains=[str(x) for x in domains if x is not None],
        primary_outcomes=[str(x) for x in outcomes if x is not None],
        tool_categories=[str(x) for x in tool_categories if x is not None],
        delegate_when=row["delegate_when"] or "",
        do_not_delegate=row["do_not_delegate"] or "",
        is_coordinator=bool(row["is_coordinator"]),
    )


class SquadMemberCapabilityCache:
    def __init__(
        self,
        *,
        dsn: str,
        schema: str = "knowledge_v2",
        pool_min_size: int = 1,
        pool_max_size: int = 4,
    ) -> None:
        if not _SCHEMA_RE.match(schema):
            raise ValueError(f"invalid postgres schema name: {schema!r}")
        self._dsn = dsn
        self._schema = schema
        self._pool_min_size = max(1, int(pool_min_size))
        self._pool_max_size = max(self._pool_min_size, int(pool_max_size))
        self._pool: Any | None = None

    async def _ensure_pool(self) -> Any:
        if self._pool is None:
            import asyncpg  # type: ignore[import-not-found]

            self._pool = await asyncpg.create_pool(
                self._dsn,
                min_size=self._pool_min_size,
                max_size=self._pool_max_size,
            )
        return self._pool

    async def close(self) -> None:
        if self._pool is not None:
            with suppress(Exception):
                await self._pool.close()
            self._pool = None

    async def upsert(
        self,
        *,
        squad_id: str,
        summary: CapabilitySummary,
        ttl_seconds: int | None = 3600,
        spec_version: int = 0,
    ) -> None:
        if not squad_id:
            raise ValueError("squad_id is required")
        if not summary.agent_id:
            raise ValueError("summary.agent_id is required")
        ttl_clause = "NOW() + ($12 || ' seconds')::interval" if ttl_seconds else "NULL"
        params: list[Any] = [
            squad_id,
            summary.agent_id,
            summary.display_name,
            summary.role,
            json.dumps(summary.domains),
            json.dumps(summary.primary_outcomes),
            json.dumps(summary.tool_categories),
            summary.delegate_when,
            summary.do_not_delegate,
            bool(summary.is_coordinator),
            int(spec_version),
        ]
        if ttl_seconds:
            params.append(str(int(ttl_seconds)))
        sql = f"""
            INSERT INTO "{self._schema}"."squad_member_capabilities"
                (squad_id, agent_id, display_name, role_label, domains,
                 primary_outcomes, tool_categories, delegate_when, do_not_delegate,
                 is_coordinator, spec_version, expires_at)
            VALUES ($1, $2, $3, $4, $5::jsonb, $6::jsonb, $7::jsonb,
                    $8, $9, $10, $11, {ttl_clause})
            ON CONFLICT (squad_id, agent_id) DO UPDATE SET
                display_name = EXCLUDED.display_name,
                role_label = EXCLUDED.role_label,
                domains = EXCLUDED.domains,
                primary_outcomes = EXCLUDED.primary_outcomes,
                tool_categories = EXCLUDED.tool_categories,
                delegate_when = EXCLUDED.delegate_when,
                do_not_delegate = EXCLUDED.do_not_delegate,
                is_coordinator = EXCLUDED.is_coordinator,
                spec_version = EXCLUDED.spec_version,
                expires_at = EXCLUDED.expires_at,
                updated_at = NOW()
        """
        pool = await self._ensure_pool()
        async with pool.acquire() as conn:
            await conn.execute(sql, *params)

    async def get(
        self,
        *,
        squad_id: str,
        agent_id: str,
        include_expired: bool = False,
    ) -> CapabilitySummary | None:
        clauses = ["squad_id = $1", "agent_id = $2"]
        if not include_expired:
            clauses.append("(expires_at IS NULL OR expires_at > NOW())")
        sql = f'SELECT * FROM "{self._schema}"."squad_member_capabilities" WHERE {" AND ".join(clauses)}'
        pool = await self._ensure_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(sql, squad_id, agent_id)
        return _row_to_summary(row) if row is not None else None

    async def list_for_squad(
        self,
        *,
        squad_id: str,
        include_expired: bool = False,
    ) -> list[CapabilitySummary]:
        clauses = ["squad_id = $1"]
        if not include_expired:
            clauses.append("(expires_at IS NULL OR expires_at > NOW())")
        sql = (
            f'SELECT * FROM "{self._schema}"."squad_member_capabilities" '
            f"WHERE {' AND '.join(clauses)} "
            f"ORDER BY is_coordinator DESC, display_name ASC"
        )
        pool = await self._ensure_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch(sql, squad_id)
        return [_row_to_summary(r) for r in rows]

    async def invalidate(self, *, squad_id: str, agent_id: str | None = None) -> int:
        clauses = ["squad_id = $1"]
        params: list[Any] = [squad_id]
        if agent_id:
            params.append(agent_id)
            clauses.append(f"agent_id = ${len(params)}")
        sql = f'DELETE FROM "{self._schema}"."squad_member_capabilities" WHERE {" AND ".join(clauses)}'
        pool = await self._ensure_pool()
        async with pool.acquire() as conn:
            result = await conn.execute(sql, *params)
        if isinstance(result, str):
            parts = result.split()
            with suppress(ValueError):
                return int(parts[-1])
        return 0


# Avoid an unused-import warning while keeping uuid available for future
# helpers (capability ids, opaque tokens) — the module is intentionally tight.
_UUID_NS = _uuid_module.NAMESPACE_DNS


_cache: SquadMemberCapabilityCache | None = None


def _build_cache() -> SquadMemberCapabilityCache | None:
    from koda.config import POSTGRES_URL
    from koda.knowledge.config import KNOWLEDGE_V2_POSTGRES_SCHEMA

    if not POSTGRES_URL:
        return None
    schema = (KNOWLEDGE_V2_POSTGRES_SCHEMA or "knowledge_v2").strip() or "knowledge_v2"
    return SquadMemberCapabilityCache(dsn=POSTGRES_URL, schema=schema)


def get_capability_cache() -> SquadMemberCapabilityCache | None:
    """Return the singleton capability cache, or None if no Postgres DSN is configured."""
    global _cache  # noqa: PLW0603
    if _cache is None:
        _cache = _build_cache()
    return _cache
