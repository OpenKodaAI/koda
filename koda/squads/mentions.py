"""Channel-aware mention resolution for squad routing.

Mentions are structural routing signals, but their shape is channel-specific:
Telegram users mention bot usernames, Web users usually mention agent ids or
display names, and future adapters can pass their own extracted entities. This
module resolves those channel mentions to active squad participant ids without
using role or intent heuristics.
"""

from __future__ import annotations

import asyncio
import re
import unicodedata
from dataclasses import dataclass, field
from typing import Any

from koda.logging_config import get_logger
from koda.squads.capabilities import CapabilitySummary

log = get_logger(__name__)

_STRUCTURAL_MENTION_RE = re.compile(r"(?<![A-Za-z0-9_])@([A-Za-z][A-Za-z0-9_.-]*)")
_BOT_USERNAME_CACHE: dict[str, str] = {}


@dataclass(frozen=True)
class ChannelMentionToken:
    raw: str
    normalized: str
    source: str
    user_id: str | None = None
    username: str | None = None


@dataclass(frozen=True)
class MentionResolution:
    channel: str
    resolved_agent_ids: list[str] = field(default_factory=list)
    unresolved: list[str] = field(default_factory=list)
    ambiguous: dict[str, list[str]] = field(default_factory=dict)
    tokens: list[ChannelMentionToken] = field(default_factory=list)

    @property
    def has_mentions(self) -> bool:
        return bool(self.tokens)

    @property
    def has_resolved_mentions(self) -> bool:
        return bool(self.resolved_agent_ids)

    def to_dict(self) -> dict[str, Any]:
        return {
            "channel": self.channel,
            "resolved_agent_ids": list(self.resolved_agent_ids),
            "unresolved": list(self.unresolved),
            "ambiguous": {key: list(value) for key, value in self.ambiguous.items()},
            "tokens": [
                {
                    "raw": token.raw,
                    "normalized": token.normalized,
                    "source": token.source,
                    "user_id": token.user_id,
                    "username": token.username,
                }
                for token in self.tokens
            ],
        }


def _participant_agent_id(participant: Any) -> str:
    if isinstance(participant, str):
        return participant.strip()
    return str(getattr(participant, "agent_id", "") or "").strip()


def _is_active_participant(participant: Any) -> bool:
    if isinstance(participant, str):
        return bool(participant.strip())
    return bool(_participant_agent_id(participant)) and getattr(participant, "left_at", None) is None


def _norm(value: str) -> str:
    text = unicodedata.normalize("NFKD", str(value or ""))
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = text.strip().lstrip("@").lower()
    text = re.sub(r"[^a-z0-9]+", "-", text)
    return text.strip("-")


def _alias_variants(value: str) -> set[str]:
    normalized = _norm(value)
    if not normalized:
        return set()
    compact = normalized.replace("-", "")
    underscored = normalized.replace("-", "_")
    dotted = normalized.replace("-", ".")
    variants = {normalized, compact, underscored, dotted}
    return {variant for variant in variants if variant}


def _json_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item or "").strip()]
    if isinstance(value, tuple):
        return [str(item).strip() for item in value if str(item or "").strip()]
    if isinstance(value, str) and value.strip():
        return [value.strip()]
    return []


def _agent_metadata_from_manager(agent_ids: set[str]) -> dict[str, dict[str, Any]]:
    if not agent_ids:
        return {}
    try:
        from koda.control_plane.manager import get_control_plane_manager

        manager = get_control_plane_manager()
        out: dict[str, dict[str, Any]] = {}
        for agent in manager.list_agents():
            agent_id = str(agent.get("id") or agent.get("agent_id") or "").strip()
            if agent_id in agent_ids:
                metadata = agent.get("metadata")
                out[agent_id] = metadata if isinstance(metadata, dict) else {}
        return out
    except Exception:
        log.debug("squad_mention_agent_metadata_unavailable", exc_info=True)
        return {}


async def _bot_username_for_agent(agent_id: str) -> str | None:
    if agent_id in _BOT_USERNAME_CACHE:
        return _BOT_USERNAME_CACHE[agent_id]
    try:
        from koda.control_plane.manager import get_control_plane_manager
        from koda.squads.telegram_outbound import get_outbound_bot

        token = get_control_plane_manager().get_decrypted_secret_value(agent_id, "AGENT_TOKEN")
        if not token:
            return None
        bot = get_outbound_bot(token)
        me = await bot.get_me()
        username = str(getattr(me, "username", "") or "").strip().lstrip("@")
        if username:
            _BOT_USERNAME_CACHE[agent_id] = username
            return username
    except Exception:
        log.debug("squad_mention_bot_username_lookup_failed", agent_id=agent_id, exc_info=True)
    return None


def _metadata_alias_values(metadata: dict[str, Any]) -> list[str]:
    values: list[str] = []
    for key in (
        "aliases",
        "mention_aliases",
        "telegram_aliases",
        "telegram_username",
        "telegram_bot_username",
        "bot_username",
        "username",
    ):
        values.extend(_json_list(metadata.get(key)))
    channel_aliases = metadata.get("channel_aliases")
    if isinstance(channel_aliases, dict):
        values.extend(_json_list(channel_aliases.get("telegram")))
        values.extend(_json_list(channel_aliases.get("web")))
    return values


async def _alias_map(
    participants: list[Any],
    *,
    capability_summaries: list[CapabilitySummary] | None = None,
    include_bot_usernames: bool = False,
) -> tuple[dict[str, set[str]], dict[str, str]]:
    active_ids = [
        _participant_agent_id(participant) for participant in participants if _is_active_participant(participant)
    ]
    active_set = {agent_id for agent_id in active_ids if agent_id}
    metadata_by_agent = _agent_metadata_from_manager(active_set)
    summary_by_agent = {summary.agent_id: summary for summary in capability_summaries or []}
    alias_to_agents: dict[str, set[str]] = {}
    user_id_to_agent: dict[str, str] = {}

    def add_alias(agent_id: str, value: str) -> None:
        for variant in _alias_variants(value):
            alias_to_agents.setdefault(variant, set()).add(agent_id)

    for agent_id in active_ids:
        if not agent_id:
            continue
        add_alias(agent_id, agent_id)
        summary = summary_by_agent.get(agent_id)
        if summary is not None:
            add_alias(agent_id, summary.display_name)
            add_alias(agent_id, summary.role)
        metadata = metadata_by_agent.get(agent_id, {})
        for alias in _metadata_alias_values(metadata):
            add_alias(agent_id, alias)
        for key in ("telegram_user_id", "bot_user_id"):
            value = metadata.get(key)
            if value is not None and str(value).strip():
                user_id_to_agent[str(value).strip()] = agent_id

    if include_bot_usernames:
        usernames = await asyncio.gather(
            *[_bot_username_for_agent(agent_id) for agent_id in active_ids if agent_id],
            return_exceptions=True,
        )
        for agent_id, username in zip([aid for aid in active_ids if aid], usernames, strict=True):
            if isinstance(username, str) and username.strip():
                add_alias(agent_id, username)
    return alias_to_agents, user_id_to_agent


def _slice_entity_text(text: str, entity: Any) -> str:
    # Telegram offsets are UTF-16 code units. For ASCII mentions, Python slicing
    # matches; for non-ASCII display text, prefer Message.parse_entity in the
    # caller path when available.
    offset = int(getattr(entity, "offset", 0) or 0)
    length = int(getattr(entity, "length", 0) or 0)
    if length <= 0:
        return ""
    return text[offset : offset + length]


def _entity_text(message: Any, text: str, entity: Any) -> str:
    parser = getattr(message, "parse_entity", None)
    if callable(parser):
        try:
            parsed = parser(entity)
            if parsed:
                return str(parsed)
        except Exception:
            pass
    return _slice_entity_text(text, entity)


def _telegram_tokens(text: str, channel_context: dict[str, Any]) -> list[ChannelMentionToken]:
    message = channel_context.get("message")
    tokens: list[ChannelMentionToken] = []
    entities = list(getattr(message, "entities", None) or getattr(message, "caption_entities", None) or [])
    for entity in entities:
        entity_type = str(getattr(entity, "type", "") or "").lower()
        if entity_type not in {"mention", "text_mention"}:
            continue
        raw = _entity_text(message, text, entity).strip()
        user = getattr(entity, "user", None)
        username = str(getattr(user, "username", "") or "").strip().lstrip("@") or None
        user_id = str(getattr(user, "id", "") or "").strip() or None
        token_raw = username or raw
        normalized = _norm(token_raw)
        if normalized:
            tokens.append(
                ChannelMentionToken(
                    raw=raw or token_raw,
                    normalized=normalized,
                    source=f"telegram_{entity_type}",
                    user_id=user_id,
                    username=username,
                )
            )

    seen = {token.normalized for token in tokens}
    for match in _STRUCTURAL_MENTION_RE.finditer(text or ""):
        raw = match.group(0)
        normalized = _norm(match.group(1))
        if normalized and normalized not in seen:
            tokens.append(ChannelMentionToken(raw=raw, normalized=normalized, source="telegram_text"))
            seen.add(normalized)
    return tokens


def _web_tokens(text: str) -> list[ChannelMentionToken]:
    return [
        ChannelMentionToken(raw=match.group(0), normalized=_norm(match.group(1)), source="web_text")
        for match in _STRUCTURAL_MENTION_RE.finditer(text or "")
        if _norm(match.group(1))
    ]


class SquadMentionResolver:
    async def resolve(
        self,
        text: str,
        *,
        participants: list[Any],
        channel: str,
        channel_context: dict[str, Any] | None = None,
        capability_summaries: list[CapabilitySummary] | None = None,
    ) -> MentionResolution:
        resolved_channel = (channel or "generic").strip().lower()
        context = dict(channel_context or {})
        tokens = (
            _telegram_tokens(text, context)
            if resolved_channel == "telegram"
            else _web_tokens(text)
            if resolved_channel == "web"
            else _web_tokens(text)
        )
        if not tokens:
            return MentionResolution(channel=resolved_channel)

        alias_to_agents, user_id_to_agent = await _alias_map(
            participants,
            capability_summaries=capability_summaries,
            include_bot_usernames=resolved_channel == "telegram",
        )
        resolved: list[str] = []
        unresolved: list[str] = []
        ambiguous: dict[str, list[str]] = {}
        seen: set[str] = set()
        for token in tokens:
            candidates: set[str] = set()
            if token.user_id and token.user_id in user_id_to_agent:
                candidates.add(user_id_to_agent[token.user_id])
            candidates.update(alias_to_agents.get(token.normalized, set()))
            if not candidates:
                unresolved.append(token.raw)
                continue
            if len(candidates) > 1:
                ambiguous[token.raw] = sorted(candidates)
                continue
            agent_id = next(iter(candidates))
            if agent_id not in seen:
                resolved.append(agent_id)
                seen.add(agent_id)
        return MentionResolution(
            channel=resolved_channel,
            resolved_agent_ids=resolved,
            unresolved=unresolved,
            ambiguous=ambiguous,
            tokens=tokens,
        )


_default_resolver: SquadMentionResolver | None = None


def get_squad_mention_resolver() -> SquadMentionResolver:
    global _default_resolver
    if _default_resolver is None:
        _default_resolver = SquadMentionResolver()
    return _default_resolver
