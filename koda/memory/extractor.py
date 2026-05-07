"""Memory extraction from conversations using the configured LLM runtime."""

from __future__ import annotations

import json
import re
from datetime import datetime, timedelta

from koda.logging_config import get_logger
from koda.memory.config import MEMORY_EXTRACTION_MODEL, MEMORY_EXTRACTION_PROVIDER, MEMORY_MAX_EXTRACTION_ITEMS
from koda.memory.profile import MemoryProfile
from koda.memory.prompts import get_extraction_prompt
from koda.memory.types import Memory, MemoryStatus, MemoryType, build_conflict_key
from koda.services.llm_runner import get_provider_fallback_chain, resolve_provider_model, run_llm

log = get_logger(__name__)

_CONTINUATION_PREFIXES = re.compile(
    r"^(continua|e sobre|e o|prossiga|go on|continue|and the|what about)\b",
    re.IGNORECASE,
)
_STACKTRACE_LINE = re.compile(
    r"(Traceback \(most recent call last\)"
    r"|File .+, line \d+"
    r"|at .+[(:]\d+[):]"
    r"|raise \w+"
    r"|\w*(Error|Exception)\b)"
)
_EXTRACTION_SYSTEM_PROMPT = (
    "You are a read-only memory extractor. "
    "Do not call tools, execute commands, browse, or read/write files. "
    "Return only the requested JSON array."
)


def _should_skip_extraction(query: str, response: str) -> bool:
    """Return True if the conversation is too trivial to warrant extraction."""
    if len(query) < 15 and len(response) < 100:
        return True
    if _CONTINUATION_PREFIXES.match(query.strip()):
        return True
    lines = response.strip().splitlines()
    if len(lines) > 5:
        trace_lines = sum(1 for ln in lines if _STACKTRACE_LINE.match(ln.strip()) or not ln.strip())
        if trace_lines / len(lines) >= 0.7:
            return True
    return False


def _looks_trivial(content: str, query: str, response: str) -> bool:
    normalized = " ".join(content.lower().split())
    if len(normalized) < 3:
        return True
    if normalized in {"ok", "certo", "thanks", "thank you", "entendido", "understood"}:
        return True
    if normalized in query.lower() and len(normalized) < 48:
        return True
    return normalized in response.lower() and len(normalized) < 48


def _estimate_quality(content: str, importance: float, confidence: float) -> float:
    detail_bonus = min(0.15, len(content.split()) / 80)
    punctuation_bonus = 0.05 if any(token in content for token in ("/", "#", ":", ".")) else 0.0
    return max(0.0, min(1.0, (importance * 0.45) + (confidence * 0.35) + detail_bonus + punctuation_bonus))


def _normalize_evidence_refs(value: object) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip()[:180] for item in value if str(item).strip()]
    if isinstance(value, str) and value.strip():
        return [value.strip()[:180]]
    return []


def _parse_valid_until(value: object) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is not None:
        parsed = parsed.astimezone().replace(tzinfo=None)
    return parsed


def _infer_claim_kind(item: dict[str, object], memory_type: MemoryType) -> str:
    claim_kind = str(item.get("claim_kind", "")).strip().lower()
    if claim_kind:
        return claim_kind
    return memory_type.value


def _infer_subject(item: dict[str, object], content: str) -> str:
    subject = str(item.get("subject", "")).strip()
    if subject:
        return subject[:120]
    return " ".join(content.split()[:8]).strip()[:120]


def _infer_decision_source(item: dict[str, object], origin_kind: str) -> str:
    decision_source = str(item.get("decision_source", "")).strip().lower()
    if decision_source:
        return decision_source[:80]
    return "runtime_observation" if origin_kind != "conversation" else "conversation"


def _is_structurally_weak(
    *,
    content: str,
    subject: str,
    evidence_refs: list[str],
    retention_reason: str,
    importance: float,
    confidence: float,
) -> bool:
    if len(subject) < 3:
        return True
    # Keep parser behavior permissive for short but valid factual memories.
    # Evidence and retention hints help quality, but their absence alone should
    # not discard a structurally valid extraction.
    _ = (evidence_refs, retention_reason, importance, confidence)
    return len(content.strip()) < 3


def _focus_bonus(content: str, profile: MemoryProfile | None) -> float:
    if profile is None or not profile.focus_domains:
        return 0.0
    lowered = content.lower()
    return 0.08 if any(domain.lower() in lowered for domain in profile.focus_domains) else 0.0


def _enforce_profile_limits(memories: list[Memory], profile: MemoryProfile) -> list[Memory]:
    if not memories:
        return []

    selected: list[Memory] = []
    counts_by_type: dict[str, int] = {}
    for memory in sorted(memories, key=lambda item: (item.importance, item.quality_score), reverse=True):
        type_key = memory.memory_type.value
        if counts_by_type.get(type_key, 0) >= profile.max_items_for(memory.memory_type):
            continue
        selected.append(memory)
        counts_by_type[type_key] = counts_by_type.get(type_key, 0) + 1
        if len(selected) >= profile.max_items_per_turn:
            break
    return selected


async def extract(
    query: str,
    response: str,
    user_id: int,
    session_id: str | None = None,
    *,
    agent_id: str | None = None,
    source_query_id: int | None = None,
    source_task_id: int | None = None,
    source_episode_id: int | None = None,
    project_key: str = "",
    environment: str = "",
    team: str = "",
    origin_kind: str = "conversation",
    profile: MemoryProfile | None = None,
) -> list[Memory]:
    """Extract memories from a query-response pair."""
    if _should_skip_extraction(query, response):
        return []

    max_items = min(
        MEMORY_MAX_EXTRACTION_ITEMS,
        profile.max_items_per_turn if profile else MEMORY_MAX_EXTRACTION_ITEMS,
    )
    prompt = get_extraction_prompt().format(
        query=query[:8000],
        response=response[:16000],
        max_items=max_items,
    )

    try:
        result: dict | None = None
        for provider in get_provider_fallback_chain(MEMORY_EXTRACTION_PROVIDER):
            candidate = await run_llm(
                provider=provider,
                query=prompt,
                work_dir="/tmp",
                model=resolve_provider_model(provider, preferred_model=MEMORY_EXTRACTION_MODEL, query=prompt),
                max_turns=1,
                max_budget=0.02,
                system_prompt=_EXTRACTION_SYSTEM_PROMPT,
                permission_mode="plan",
                dry_run=True,
            )
            if candidate.get("_tool_uses") or candidate.get("_native_items"):
                log.warning("memory_extraction_tool_use_blocked", provider=provider)
                continue
            if not candidate.get("error"):
                result = candidate
                break
            log.warning("memory_extraction_provider_error", provider=provider, error=candidate.get("result", ""))

        if not result:
            return []

        raw = result.get("result", "").strip()
        return _parse_extraction_result(
            raw,
            user_id,
            session_id,
            source_query_preview=query[:200],
            agent_id=agent_id,
            source_query_id=source_query_id,
            source_task_id=source_task_id,
            source_episode_id=source_episode_id,
            project_key=project_key,
            environment=environment,
            team=team,
            origin_kind=origin_kind,
            query=query,
            response=response,
            profile=profile,
        )

    except Exception:
        log.exception("memory_extraction_failed")
        return []


def _parse_extraction_result(
    raw: str,
    user_id: int,
    session_id: str | None,
    *,
    source_query_preview: str = "",
    agent_id: str | None = None,
    source_query_id: int | None = None,
    source_task_id: int | None = None,
    source_episode_id: int | None = None,
    project_key: str = "",
    environment: str = "",
    team: str = "",
    origin_kind: str = "conversation",
    query: str = "",
    response: str = "",
    profile: MemoryProfile | None = None,
) -> list[Memory]:
    """Parse the JSON array returned by the extraction model."""
    text = raw.strip()
    if text.startswith("```"):
        lines = [line for line in text.split("\n") if not line.strip().startswith("```")]
        text = "\n".join(lines).strip()

    try:
        items = json.loads(text)
    except json.JSONDecodeError:
        start = text.find("[")
        end = text.rfind("]")
        if start == -1 or end == -1:
            log.warning("memory_extraction_no_json", raw=text[:200])
            return []
        try:
            items = json.loads(text[start : end + 1])
        except json.JSONDecodeError:
            log.warning("memory_extraction_invalid_json", raw=text[:200])
            return []

    if not isinstance(items, list):
        return []

    resolved_profile = profile or MemoryProfile(agent_id=agent_id or "default")
    memories: list[Memory] = []
    now = datetime.now()

    for item in items[:MEMORY_MAX_EXTRACTION_ITEMS]:
        if not isinstance(item, dict):
            continue

        content = str(item.get("content", "")).strip()
        if not content or _looks_trivial(content, query, response):
            continue
        if resolved_profile.should_ignore(content):
            continue

        type_str = str(item.get("type", "fact")).lower()
        try:
            memory_type = MemoryType(type_str)
        except ValueError:
            memory_type = MemoryType.FACT

        importance = item.get("importance", 0.5)
        if not isinstance(importance, (int, float)):
            importance = 0.5
        importance = max(0.0, min(1.0, float(importance)))
        if importance < resolved_profile.min_importance_for(memory_type):
            continue

        confidence = item.get("confidence", importance)
        if not isinstance(confidence, (int, float)):
            confidence = importance
        confidence = max(0.0, min(1.0, float(confidence)))

        ttl_days = resolved_profile.ttl_days_for(memory_type)
        expires_at = now + timedelta(days=ttl_days)
        claim_kind = _infer_claim_kind(item, memory_type)
        subject = _infer_subject(item, content)
        decision_source = _infer_decision_source(item, origin_kind)
        evidence_refs = _normalize_evidence_refs(item.get("evidence_refs"))
        retention_reason = str(item.get("retention_reason", "")).strip()[:220]
        valid_until = _parse_valid_until(item.get("valid_until"))
        conflict_key = str(item.get("conflict_key", "")).strip()[:120] or build_conflict_key(
            memory_type,
            subject=subject,
            project_key=project_key,
            environment=environment,
            team=team,
        )
        if _is_structurally_weak(
            content=content,
            subject=subject,
            evidence_refs=evidence_refs,
            retention_reason=retention_reason,
            importance=importance,
            confidence=confidence,
        ):
            continue
        quality_score = min(
            1.0, _estimate_quality(content, importance, confidence) + _focus_bonus(content, resolved_profile)
        )

        metadata: dict[str, object] = {"origin": origin_kind}
        if source_query_preview:
            metadata["source_query_preview"] = source_query_preview
        if resolved_profile.focus_domains:
            metadata["focus_domains"] = list(resolved_profile.focus_domains)
        if retention_reason:
            metadata["retention_reason"] = retention_reason

        memories.append(
            Memory(
                user_id=user_id,
                memory_type=memory_type,
                content=content,
                importance=importance,
                source_query_id=source_query_id,
                session_id=session_id,
                agent_id=agent_id,
                origin_kind=origin_kind,
                source_task_id=source_task_id,
                source_episode_id=source_episode_id,
                project_key=project_key,
                environment=environment,
                team=team,
                quality_score=quality_score,
                extraction_confidence=confidence,
                embedding_status="pending",
                claim_kind=claim_kind,
                subject=subject,
                decision_source=decision_source,
                evidence_refs=evidence_refs,
                applicability_scope={
                    "project_key": project_key,
                    "environment": environment,
                    "team": team,
                    "origin_kind": origin_kind,
                },
                valid_until=valid_until,
                conflict_key=conflict_key,
                memory_status=MemoryStatus.ACTIVE.value,
                retention_reason=retention_reason,
                created_at=now,
                expires_at=expires_at,
                metadata=metadata,
            )
        )

    return _enforce_profile_limits(memories, resolved_profile)
