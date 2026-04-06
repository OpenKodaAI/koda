"""Atlassian (Jira + Confluence) service layer wrapping atlassian-python-api."""

import asyncio
import inspect
import json
import os
import shlex
from collections.abc import Callable
from contextlib import suppress
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

from koda.config import (
    AGENT_ID,
    CONFLUENCE_API_TOKEN,
    CONFLUENCE_CLOUD,
    CONFLUENCE_TIMEOUT,
    CONFLUENCE_URL,
    CONFLUENCE_USERNAME,
    IMAGE_TEMP_DIR,
    JIRA_API_TOKEN,
    JIRA_CLOUD,
    JIRA_DEEP_CONTEXT_ENABLED,
    JIRA_TIMEOUT,
    JIRA_URL,
    JIRA_USERNAME,
)
from koda.logging_config import get_logger
from koda.services.artifact_ingestion import ArtifactDossier, ArtifactKind, ExtractedArtifact
from koda.services.jira_issue_context import IssueContextDossier, build_issue_context_dossier
from koda.utils.adf_renderer import classify_url, extract_urls_from_adf, render_adf

log = get_logger(__name__)

MAX_OUTPUT = 8000
MAX_ANALYZE_OUTPUT = 16000
COMMENT_META_PROPERTY_KEY = "koda.comment_meta"
MAX_COMMENT_EXCERPT = 280
COMMENT_META_STATUS_PRESENT = "present"
COMMENT_META_STATUS_MISSING = "missing"
COMMENT_META_STATUS_ERROR = "error"

# ---------------------------------------------------------------------------
# Media type helpers
# ---------------------------------------------------------------------------

SUPPORTED_IMAGE_MIMES = frozenset(
    {
        "image/jpeg",
        "image/png",
        "image/gif",
        "image/webp",
        "image/bmp",
        "image/tiff",
    }
)
SUPPORTED_AUDIO_MIMES = frozenset(
    {
        "audio/mpeg",
        "audio/mp3",
        "audio/wav",
        "audio/ogg",
        "audio/x-wav",
        "audio/aac",
        "audio/flac",
        "audio/mp4",
        "audio/x-m4a",
    }
)
MAX_IMAGE_SIZE = 20 * 1024 * 1024  # 20 MB
MAX_AUDIO_SIZE = 25 * 1024 * 1024  # 25 MB

# Auto-processing limits for issues analyze
MAX_AUTO_IMAGES = 5
MAX_AUTO_AUDIO = 2
MAX_AUTO_IMAGE_SIZE = 10 * 1024 * 1024
MAX_AUTO_AUDIO_SIZE = 15 * 1024 * 1024
MAX_TRANSCRIPTION_CHARS = 2000


def _current_agent_id() -> str:
    return str(os.environ.get("AGENT_ID") or AGENT_ID or "").strip().upper()


def _resolved_atlassian_base_urls() -> tuple[str, str]:
    jira_url = JIRA_URL
    confluence_url = CONFLUENCE_URL
    current_agent = _current_agent_id()
    if current_agent:
        with suppress(Exception):
            from koda.services.core_connection_broker import get_core_connection_broker

            urls = get_core_connection_broker().atlassian_base_urls(agent_id=current_agent)
            jira_url = str(urls.get("jira") or jira_url or "").strip()
            confluence_url = str(urls.get("confluence") or confluence_url or "").strip()
    return jira_url, confluence_url


def _resolve_atlassian_client_kwargs(integration_id: str) -> dict[str, Any]:
    normalized = integration_id.strip().lower()
    if normalized == "jira":
        legacy_kwargs = {
            "url": JIRA_URL,
            "username": JIRA_USERNAME,
            "password": JIRA_API_TOKEN,
            "cloud": JIRA_CLOUD,
        }
    elif normalized == "confluence":
        legacy_kwargs = {
            "url": CONFLUENCE_URL,
            "username": CONFLUENCE_USERNAME,
            "password": CONFLUENCE_API_TOKEN,
            "cloud": CONFLUENCE_CLOUD,
        }
    else:
        raise KeyError(normalized)

    current_agent = _current_agent_id()
    if current_agent:
        with suppress(Exception):
            from koda.services.core_connection_broker import get_core_connection_broker

            resolved_kwargs = get_core_connection_broker().atlassian_client_kwargs(
                normalized,
                agent_id=current_agent,
            )
            if resolved_kwargs:
                return {**legacy_kwargs, **resolved_kwargs}
    return legacy_kwargs


def is_image_mime(mime_type: str) -> bool:
    return mime_type.lower() in SUPPORTED_IMAGE_MIMES


def is_audio_mime(mime_type: str) -> bool:
    return mime_type.lower() in SUPPORTED_AUDIO_MIMES


def _download_attachment(session: object, content_url: str) -> bytes:
    """Download attachment content from Jira. Raises on failure."""
    response = session.get(content_url)  # type: ignore[attr-defined]
    response.raise_for_status()
    return response.content  # type: ignore[no-any-return]


@dataclass
class MediaContext:
    image_paths: list[str] = field(default_factory=list)
    transcriptions: dict[str, str] = field(default_factory=dict)
    video_hints: list[str] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)


def parse_atlassian_args(raw: str) -> tuple[str, str, dict[str, str]]:
    """Parse '<resource> <action> [--key value ...]' into (resource, action, params_dict).

    Raises ValueError if resource or action is missing.
    """
    tokens = shlex.split(raw)
    if len(tokens) < 2:
        raise ValueError("Expected: <resource> <action> [--key value ...]")

    resource = tokens[0].lower()
    action = tokens[1].lower()
    params: dict[str, str] = {}

    i = 2
    while i < len(tokens):
        token = tokens[i]
        if token.startswith("--") and i + 1 < len(tokens):
            key = token[2:]  # strip --
            params[key] = tokens[i + 1]
            i += 2
        else:
            # Positional value — skip
            i += 1

    return resource, action, params


def _require(params: dict[str, str], *keys: str) -> None:
    """Validate that all required keys are present in params."""
    for k in keys:
        if k not in params:
            raise ValueError(f"Missing required parameter: --{k}")


def _truncate(text: str, limit: int = MAX_OUTPUT) -> str:
    if len(text) > limit:
        return text[:limit] + "\n\u2026 (truncated)"
    return text


def _format_result(data: object) -> str:
    """Format API result as 'Exit 0:\\n<json>'."""
    try:
        body = json.dumps(data, indent=2, ensure_ascii=False, default=str)
    except (TypeError, ValueError):
        body = str(data)
    return _truncate(f"Exit 0:\n{body}")


def _format_error(err: Exception) -> str:
    return _truncate(f"Exit 1:\n{err}")


def _comment_body_to_text(body: object) -> str:
    if isinstance(body, dict):
        return render_adf(body).strip()
    if body is None:
        return ""
    return str(body).strip()


def _comment_excerpt(body: object, limit: int = MAX_COMMENT_EXCERPT) -> str:
    text = " ".join(_comment_body_to_text(body).split())
    if not text:
        return "(no readable content)"
    if len(text) <= limit:
        return text
    return text[: max(limit - 1, 0)].rstrip() + "…"


def _looks_like_comment_metadata(value: object) -> bool:
    if not isinstance(value, dict):
        return False
    known_keys = {"agent_id", "mode", "issue_key", "reply_to_comment_id", "created_at", "updated_at"}
    return any(key in value for key in known_keys)


def _normalize_comment_metadata_payload(payload: object) -> dict[str, Any] | None:
    current = payload
    for _ in range(3):
        if not isinstance(current, dict):
            return None
        if _looks_like_comment_metadata(current):
            return cast(dict[str, Any], current)
        nested = current.get("value")
        if isinstance(nested, dict):
            current = nested
            continue
        return None
    return None


_SEARCH_FIELDS = ["summary", "status", "assignee", "priority", "issuetype", "created", "updated"]


def _extract_name(obj: object, key: str = "name") -> str:
    if isinstance(obj, dict):
        return obj.get(key, "") or obj.get("name", "") or ""
    return str(obj) if obj else ""


def _slim_search_results(data: object) -> object:
    if not isinstance(data, dict) or "issues" not in data:
        return data
    issues = []
    for issue in data.get("issues", []):
        fields = issue.get("fields", {})
        issues.append(
            {
                "key": issue.get("key", ""),
                "summary": fields.get("summary", ""),
                "status": _extract_name(fields.get("status")),
                "assignee": _extract_name(fields.get("assignee"), key="displayName"),
                "priority": _extract_name(fields.get("priority")),
                "type": _extract_name(fields.get("issuetype")),
                "created": fields.get("created", ""),
                "updated": fields.get("updated", ""),
            }
        )
    return {"total": data.get("total", len(issues)), "issues": issues}


def _format_size(size: int) -> str:
    """Format byte size to human-readable string."""
    if size < 1024:
        return f"{size} B"
    if size < 1024 * 1024:
        return f"{size / 1024:.0f} KB"
    return f"{size / (1024 * 1024):.1f} MB"


def _format_links(issue_links: list, remote_links: list) -> list[dict]:
    """Format issue links and remote links into a unified list."""
    result: list[dict] = []
    for link in issue_links:
        link_type = link.get("type", {}).get("name", "")
        if "outwardIssue" in link:
            target = link["outwardIssue"]
            direction = link.get("type", {}).get("outward", link_type)
            result.append(
                {
                    "direction": "outward",
                    "type": direction,
                    "key": target.get("key", ""),
                    "summary": target.get("fields", {}).get("summary", ""),
                    "status": _extract_name(target.get("fields", {}).get("status")),
                }
            )
        if "inwardIssue" in link:
            target = link["inwardIssue"]
            direction = link.get("type", {}).get("inward", link_type)
            result.append(
                {
                    "direction": "inward",
                    "type": direction,
                    "key": target.get("key", ""),
                    "summary": target.get("fields", {}).get("summary", ""),
                    "status": _extract_name(target.get("fields", {}).get("status")),
                }
            )
    for rlink in remote_links:
        obj = rlink.get("object", {})
        result.append(
            {
                "direction": "remote",
                "type": "remote link",
                "url": obj.get("url", ""),
                "title": obj.get("title", ""),
            }
        )
    return result


def _format_issue_analysis(
    issue: dict,
    comments: object,
    remote_links: list,
    media_context: MediaContext | None = None,
    artifact_dossier: ArtifactDossier | None = None,
) -> str:
    """Build structured text analysis of a Jira issue."""
    fields = issue.get("fields", {})
    key = issue.get("key", "?")
    summary = fields.get("summary", "")
    artifact_by_attachment_id: dict[str, ExtractedArtifact] = {}
    if artifact_dossier:
        for artifact in artifact_dossier.artifacts:
            attachment_id = str(artifact.ref.metadata.get("attachment_id", "") or "")
            if attachment_id:
                artifact_by_attachment_id[attachment_id] = artifact

    lines: list[str] = []
    lines.append(f"## {key}: {summary}")

    # Metadata
    status = _extract_name(fields.get("status"))
    issuetype = _extract_name(fields.get("issuetype"))
    priority = _extract_name(fields.get("priority"))
    assignee = _extract_name(fields.get("assignee"), key="displayName")
    reporter = _extract_name(fields.get("reporter"), key="displayName")
    created = (fields.get("created") or "")[:10]
    updated = (fields.get("updated") or "")[:10]

    meta_parts = []
    if status:
        meta_parts.append(f"**Status:** {status}")
    if issuetype:
        meta_parts.append(f"**Type:** {issuetype}")
    if priority:
        meta_parts.append(f"**Priority:** {priority}")
    if meta_parts:
        lines.append(" | ".join(meta_parts))

    people_parts = []
    if assignee:
        people_parts.append(f"**Assignee:** {assignee}")
    if reporter:
        people_parts.append(f"**Reporter:** {reporter}")
    if people_parts:
        lines.append(" | ".join(people_parts))

    date_parts = []
    if created:
        date_parts.append(f"**Created:** {created}")
    if updated:
        date_parts.append(f"**Updated:** {updated}")
    if date_parts:
        lines.append(" | ".join(date_parts))

    # Labels, components, fix versions, sprint, story points, parent
    labels = fields.get("labels")
    if labels:
        lines.append(f"**Labels:** {', '.join(labels)}")

    components = fields.get("components")
    if components:
        comp_names = [_extract_name(c) for c in components]
        lines.append(f"**Components:** {', '.join(comp_names)}")

    fix_versions = fields.get("fixVersions")
    if fix_versions:
        fv_names = [_extract_name(v) for v in fix_versions]
        lines.append(f"**Fix Versions:** {', '.join(fv_names)}")

    # Sprint (custom field — often customfield_10020)
    sprint = fields.get("sprint")
    if sprint:
        lines.append(f"**Sprint:** {_extract_name(sprint)}")

    # Story points (often customfield_10028)
    story_points = fields.get("story_points") or fields.get("customfield_10028")
    if story_points:
        lines.append(f"**Story Points:** {story_points}")

    parent = fields.get("parent")
    if parent:
        parent_key = parent.get("key", "")
        parent_summary = parent.get("fields", {}).get("summary", "")
        lines.append(f"**Parent:** {parent_key}" + (f' "{parent_summary}"' if parent_summary else ""))

    # Description
    description = fields.get("description")
    all_urls: list[str] = []
    lines.append("")
    lines.append("### Description")
    if description:
        rendered = render_adf(description) if isinstance(description, dict) else str(description)
        lines.append(rendered)
        if isinstance(description, dict):
            all_urls.extend(extract_urls_from_adf(description))
    else:
        lines.append("(no description)")

    # Comments
    comment_list = []
    if isinstance(comments, dict):
        comment_list = comments.get("comments", [])
    elif isinstance(comments, list):
        comment_list = comments

    lines.append("")
    lines.append(f"### Comments ({len(comment_list)})")
    for c in comment_list:
        author = _extract_name(c.get("author"), key="displayName")
        created_at = (c.get("created") or "")[:10]
        lines.append(f"**{author}** ({created_at}):")
        body = c.get("body")
        if body:
            rendered = render_adf(body) if isinstance(body, dict) else str(body)
            lines.append(rendered)
            if isinstance(body, dict):
                all_urls.extend(extract_urls_from_adf(body))
        lines.append("")

    # Attachments
    attachments = fields.get("attachment", [])
    if attachments:
        lines.append(f"### Attachments ({len(attachments)})")
        for att in attachments:
            fname = att.get("filename", "?")
            size = _format_size(att.get("size", 0))
            mime = att.get("mimeType", "")
            att_id = str(att.get("id", ""))
            att_author = _extract_name(att.get("author"), key="displayName")
            att_date = (att.get("created") or "")[:10]
            lines.append(f"- {fname} ({size}, {mime}, id={att_id}) — by {att_author}, {att_date}")
            if media_context:
                if any(att_id in p for p in media_context.image_paths):
                    lines.append("  [image downloaded for visual analysis]")
                elif att_id in media_context.transcriptions:
                    transcription = media_context.transcriptions[att_id]
                    lines.append(f"  [audio transcription]: {transcription}")
                elif fname in media_context.video_hints:
                    lines.append(f"  [use view_video --attachment-id {att_id} to analyze]")
            elif artifact_dossier:
                attachment_artifact = artifact_by_attachment_id.get(att_id)
                if (
                    attachment_artifact
                    and attachment_artifact.ref.kind == ArtifactKind.IMAGE
                    and attachment_artifact.visual_paths
                ):
                    lines.append("  [image downloaded for visual analysis]")
                elif (
                    attachment_artifact
                    and attachment_artifact.ref.kind == ArtifactKind.AUDIO
                    and attachment_artifact.text_content
                ):
                    excerpt = attachment_artifact.text_content[:240].replace("\n", " ")
                    lines.append(f"  [audio transcription]: {excerpt}")
                elif attachment_artifact and attachment_artifact.ref.kind == ArtifactKind.VIDEO:
                    lines.append(f"  [use view_video --attachment-id {att_id} to analyze]")
        lines.append("")

    # Issue links
    issue_links = fields.get("issuelinks", [])
    formatted_links = _format_links(issue_links, remote_links)
    if formatted_links:
        lines.append(f"### Issue Links ({len(formatted_links)})")
        for fl in formatted_links:
            if fl.get("direction") == "remote":
                lines.append(f"- [remote] {fl.get('title', '')} — {fl.get('url', '')}")
            else:
                arrow = "→" if fl.get("direction") == "outward" else "←"
                lines.append(
                    f"- {fl.get('type', '')} {arrow} {fl.get('key', '')} "
                    f'"{fl.get("summary", "")}" ({fl.get("status", "")})'
                )
        lines.append("")

    # URLs found
    if all_urls:
        # Deduplicate preserving order
        seen: set[str] = set()
        unique_urls: list[str] = []
        for u in all_urls:
            if u not in seen:
                seen.add(u)
                unique_urls.append(u)
        lines.append(f"### URLs Found ({len(unique_urls)})")
        for u in unique_urls:
            jira_url, confluence_url = _resolved_atlassian_base_urls()
            cat = classify_url(u, jira_url, confluence_url)
            lines.append(f"- [{cat}] {u}")

    # Image paths for queue_manager regex detection
    if media_context and media_context.image_paths:
        lines.append("")
        lines.append("### Downloaded Images")
        for img_path in media_context.image_paths:
            lines.append(f"- {img_path}")
    elif artifact_dossier and artifact_dossier.visual_paths:
        lines.append("")
        lines.append("### Downloaded Images")
        for img_path in artifact_dossier.visual_paths:
            lines.append(f"- {img_path}")

    if artifact_dossier:
        lines.append("")
        lines.append("### Artifact Dossier")
        lines.append(artifact_dossier.summary)
        if artifact_dossier.warnings:
            lines.append("Warnings:")
            for warning in artifact_dossier.warnings[:10]:
                lines.append(f"- {warning}")
        if artifact_dossier.has_blocking_gaps:
            lines.append("Critical extraction gaps:")
            for artifact in artifact_dossier.critical_pending[:8]:
                lines.append(f"- {artifact.ref.label}: {artifact.status.value}")
        if artifact_dossier.artifacts:
            lines.append("Artifacts:")
            for artifact in artifact_dossier.artifacts[:12]:
                lines.append(f"- {artifact.ref.label} [{artifact.ref.kind.value}] status={artifact.status.value}")
                if artifact.summary:
                    lines.append(f"  {artifact.summary}")
                for evidence in artifact.evidence_chunks[:2]:
                    lines.append(f"  {evidence.citation}: {evidence.excerpt}")

    return "\n".join(lines)


def _process_media_attachments(
    session: object,
    attachments: list[dict],
    key: str,
) -> MediaContext:
    """Auto-process image and audio attachments for issue analysis."""
    ctx = MediaContext()
    images_processed = 0
    audio_processed = 0

    IMAGE_TEMP_DIR.mkdir(parents=True, exist_ok=True)

    for att in attachments:
        mime = att.get("mimeType", "").lower()
        size = att.get("size", 0)
        att_id = str(att.get("id", ""))
        filename = att.get("filename", "file")
        content_url = att.get("content", "")

        if not content_url:
            continue

        # Images
        if is_image_mime(mime) and images_processed < MAX_AUTO_IMAGES:
            if size > MAX_AUTO_IMAGE_SIZE:
                ctx.skipped.append(f"{filename}: image too large ({_format_size(size)})")
                continue
            try:
                data = _download_attachment(session, content_url)
                ext = Path(filename).suffix or ".jpg"
                img_path = str(IMAGE_TEMP_DIR / f"jira_img_{att_id}{ext}")
                Path(img_path).write_bytes(data)
                ctx.image_paths.append(img_path)
                images_processed += 1
            except Exception as e:
                log.warning("auto_image_download_failed", attachment_id=att_id, error=str(e))
                ctx.skipped.append(f"{filename}: download failed")
            continue

        # Audio
        if is_audio_mime(mime) and audio_processed < MAX_AUTO_AUDIO:
            if size > MAX_AUTO_AUDIO_SIZE:
                ctx.skipped.append(f"{filename}: audio too large ({_format_size(size)})")
                continue
            try:
                from koda.utils.audio import is_ffmpeg_available, transcribe_audio_sync

                if not is_ffmpeg_available():
                    ctx.skipped.append(f"{filename}: ffmpeg unavailable")
                    continue
                data = _download_attachment(session, content_url)
                ext = Path(filename).suffix or ".mp3"
                audio_path = str(IMAGE_TEMP_DIR / f"jira_audio_{att_id}{ext}")
                Path(audio_path).write_bytes(data)
                try:
                    transcription = transcribe_audio_sync(audio_path)
                    if transcription:
                        if len(transcription) > MAX_TRANSCRIPTION_CHARS:
                            transcription = transcription[:MAX_TRANSCRIPTION_CHARS] + "..."
                        ctx.transcriptions[att_id] = transcription
                    else:
                        ctx.skipped.append(f"{filename}: transcription returned empty")
                finally:
                    Path(audio_path).unlink(missing_ok=True)
                audio_processed += 1
            except Exception as e:
                log.warning("auto_audio_process_failed", attachment_id=att_id, error=str(e))
                ctx.skipped.append(f"{filename}: processing failed")
            continue

        # Videos — hint only
        if mime.startswith("video/"):
            ctx.video_hints.append(filename)

    return ctx


class JiraService:
    """Async wrapper around atlassian-python-api Jira client."""

    def __init__(self, client_kwargs: dict[str, Any] | None = None) -> None:
        from atlassian import Jira

        kwargs = dict(client_kwargs or _resolve_atlassian_client_kwargs("jira"))
        self._client = Jira(api_version="3", **kwargs)
        self._jira_identity: dict[str, Any] | None = None
        self._jira_identity_loaded = False

    # Handlers that return pre-formatted text (not JSON) with a higher output limit
    _TEXT_HANDLERS: frozenset[str] = frozenset(
        {
            "issues_analyze",
            "issues_view_video",
            "issues_view_image",
            "issues_view_audio",
        }
    )

    async def execute(self, resource: str, action: str, params: dict[str, str]) -> str:
        """Dispatch to the correct Jira API method."""
        from koda.utils.approval import check_execution_approved

        if not check_execution_approved():
            return "Exit 1:\nCommand execution not approved."
        handler_key = f"{resource}_{action}"
        handler = self._handlers.get(handler_key)
        if not handler:
            return (
                f"Exit 1:\nUnknown command: {resource} {action}. Available: {', '.join(sorted(self._handlers.keys()))}"
            )
        try:
            typed_handler = cast(Callable[[JiraService, dict[str, str]], Any], handler)
            if inspect.iscoroutinefunction(typed_handler):
                result = await asyncio.wait_for(typed_handler(self, params), timeout=JIRA_TIMEOUT)
            else:
                result = await asyncio.wait_for(
                    asyncio.to_thread(typed_handler, self, params),
                    timeout=JIRA_TIMEOUT,
                )
            if handler_key in self._TEXT_HANDLERS:
                return _truncate(f"Exit 0:\n{result}", limit=MAX_ANALYZE_OUTPUT)
            return _format_result(result)
        except TimeoutError:
            return f"Timeout after {JIRA_TIMEOUT}s for {resource} {action}."
        except PermissionError as e:
            return f"Exit 1:\n{e}"
        except ValueError as e:
            return f"Exit 1:\n{e}"
        except Exception as e:
            log.exception("jira_error", resource=resource, action=action)
            return _format_error(e)

    # --- Issue handlers ---

    def _get_current_jira_identity(self) -> dict[str, Any]:
        if not self._jira_identity_loaded:
            try:
                identity = self._client.myself()
            except Exception:
                log.warning("jira_myself_lookup_failed")
                identity = {}
            self._jira_identity = cast(dict[str, Any], identity or {})
            self._jira_identity_loaded = True
        return self._jira_identity or {}

    def _get_current_jira_account_id(self) -> str | None:
        identity = self._get_current_jira_identity()
        account_id = identity.get("accountId") if isinstance(identity, dict) else None
        if not isinstance(account_id, str):
            return None
        normalized = account_id.strip()
        return normalized or None

    def verify_identity(self) -> dict[str, Any]:
        """Run a lightweight authenticated probe and return the current identity."""
        identity = self._client.myself()
        if not isinstance(identity, dict):
            raise ValueError("Jira identity probe returned an unexpected payload.")
        return cast(dict[str, Any], identity)

    def _get_issue_comment(self, issue_key: str, comment_id: str) -> dict[str, Any]:
        comment = self._client.issue_get_comment(issue_key, comment_id)
        if not isinstance(comment, dict):
            raise ValueError(f"Comment {comment_id} was not found on {issue_key}.")
        return cast(dict[str, Any], comment)

    def _get_comment_property_value(self, comment_id: str) -> tuple[dict[str, Any] | None, str]:
        try:
            payload = self._client.get_comment_property(comment_id, COMMENT_META_PROPERTY_KEY)
        except Exception as exc:
            status_code = getattr(getattr(exc, "response", None), "status_code", None)
            if status_code == 404:
                return None, COMMENT_META_STATUS_MISSING
            log.warning(
                "jira_comment_property_read_failed", comment_id=comment_id, status_code=status_code, error=str(exc)
            )
            return None, COMMENT_META_STATUS_ERROR

        metadata = _normalize_comment_metadata_payload(payload)
        if metadata is None:
            if payload is None:
                return None, COMMENT_META_STATUS_MISSING
            log.warning("jira_comment_property_invalid_shape", comment_id=comment_id)
            return None, COMMENT_META_STATUS_ERROR
        return metadata, COMMENT_META_STATUS_PRESENT

    def _set_comment_property_value(self, comment_id: str, metadata: dict[str, Any]) -> bool:
        try:
            comment_base = self._client.resource_url("comment")
            self._client.put(f"{comment_base}/{comment_id}/properties/{COMMENT_META_PROPERTY_KEY}", data=metadata)
        except Exception as exc:
            log.warning("jira_comment_property_set_failed", comment_id=comment_id, error=str(exc))
            return False
        return True

    def _build_comment_metadata(
        self,
        *,
        issue_key: str,
        mode: str,
        reply_to_comment_id: str | None = None,
        created_at: str | None = None,
        updated_at: str | None = None,
    ) -> dict[str, Any]:
        metadata: dict[str, Any] = {
            "agent_id": AGENT_ID or "default",
            "mode": mode,
            "issue_key": issue_key,
            "created_at": created_at or datetime.now(UTC).isoformat(),
        }
        if reply_to_comment_id:
            metadata["reply_to_comment_id"] = reply_to_comment_id
        if updated_at:
            metadata["updated_at"] = updated_at
        return metadata

    def _format_comment(self, issue_key: str, comment: dict[str, Any]) -> dict[str, Any]:
        author = comment.get("author")
        author_dict = cast(dict[str, Any], author if isinstance(author, dict) else {})
        comment_meta, comment_meta_status = self._get_comment_property_value(str(comment.get("id", "")))
        return {
            "issue_key": issue_key,
            "id": str(comment.get("id", "")),
            "author": _extract_name(author_dict, key="displayName"),
            "author_account_id": author_dict.get("accountId", ""),
            "created": comment.get("created", ""),
            "updated": comment.get("updated", ""),
            "body_text": _comment_body_to_text(comment.get("body")),
            "body": comment.get("body"),
            "visibility": comment.get("visibility"),
            "comment_meta": comment_meta,
            "comment_meta_status": comment_meta_status,
        }

    def _audit_comment_blocked(
        self,
        *,
        action: str,
        issue_key: str,
        comment_id: str,
        reason: str,
    ) -> None:
        from koda.services.audit import emit_security

        emit_security(
            "security.jira_comment_blocked",
            action=action,
            issue_key=issue_key,
            comment_id=comment_id,
            reason=reason,
        )

    def _ensure_owned_comment(self, issue_key: str, comment_id: str, *, action: str) -> dict[str, Any]:
        comment = self._get_issue_comment(issue_key, comment_id)
        author = cast(dict[str, Any], comment.get("author") if isinstance(comment.get("author"), dict) else {})
        author_account_id = author.get("accountId")
        current_account_id = self._get_current_jira_account_id()
        if not isinstance(author_account_id, str) or not author_account_id.strip() or not current_account_id:
            self._audit_comment_blocked(
                action=action,
                issue_key=issue_key,
                comment_id=comment_id,
                reason="missing_comment_or_agent_identity",
            )
            raise PermissionError(
                "Blocked: this action is only allowed for comments authored by the configured Jira service account."
            )
        if author_account_id != current_account_id:
            self._audit_comment_blocked(
                action=action,
                issue_key=issue_key,
                comment_id=comment_id,
                reason="comment_not_owned_by_service_account",
            )
            raise PermissionError(
                "Blocked: this action is only allowed for comments authored by the configured Jira service account."
            )
        return comment

    def _persist_comment_metadata(
        self,
        *,
        issue_key: str,
        comment: object,
        mode: str,
        reply_to_comment_id: str | None = None,
        existing_metadata: dict[str, Any] | None = None,
    ) -> tuple[dict[str, Any] | None, bool]:
        if not isinstance(comment, dict):
            return None, False
        comment_id = str(comment.get("id", "")).strip()
        if not comment_id:
            return None, False
        current = existing_metadata or {}
        metadata = self._build_comment_metadata(
            issue_key=issue_key,
            mode=str(current.get("mode") or mode),
            reply_to_comment_id=cast(str | None, current.get("reply_to_comment_id")) or reply_to_comment_id,
            created_at=cast(str | None, current.get("created_at")),
            updated_at=datetime.now(UTC).isoformat() if existing_metadata is not None else None,
        )
        return metadata, self._set_comment_property_value(comment_id, metadata)

    def _delete_issue_comment(self, issue_key: str, comment_id: str) -> None:
        issue_base = self._client.resource_url("issue")
        self._client.delete(f"{issue_base}/{issue_key}/comment/{comment_id}")

    def _rollback_created_comment(self, issue_key: str, comment: object) -> bool:
        if not isinstance(comment, dict):
            return False
        comment_id = str(comment.get("id", "")).strip()
        if not comment_id:
            return False
        try:
            self._delete_issue_comment(issue_key, comment_id)
        except Exception as exc:
            log.warning("jira_comment_rollback_failed", issue_key=issue_key, comment_id=comment_id, error=str(exc))
            return False
        return True

    def _build_linked_reply_body(self, target_comment: dict[str, Any], *, reply_body: str) -> dict[str, Any]:
        from koda.utils.adf_builder import text_to_adf

        comment_id = str(target_comment.get("id", ""))
        raw_author = target_comment.get("author")
        author = cast(dict[str, Any], raw_author if isinstance(raw_author, dict) else {})
        author_label = _extract_name(author, key="displayName") or author.get("accountId", "unknown author")
        excerpt = _comment_excerpt(target_comment.get("body"))
        linked_reply_text = (
            f"Replying to comment #{comment_id} by {author_label}\n\nOriginal excerpt:\n{excerpt}\n\n{reply_body}"
        )
        return text_to_adf(linked_reply_text)

    def _issues_search(self, params: dict[str, str]) -> object:
        jql = params.get("jql", "")
        limit = int(params.get("limit", "20"))
        raw = self._client.jql(jql, limit=limit, fields=_SEARCH_FIELDS)
        return _slim_search_results(raw)

    def _issues_get(self, params: dict[str, str]) -> object:
        _require(params, "key")
        return self._client.issue(params["key"])

    def _issues_create(self, params: dict[str, str]) -> object:
        _require(params, "project", "summary")
        fields: dict[str, object] = {
            "project": {"key": params["project"]},
            "summary": params["summary"],
            "issuetype": {"name": params.get("type", "Task")},
        }
        if "description" in params:
            from koda.utils.adf_builder import text_to_adf

            fields["description"] = text_to_adf(params["description"])
        if "assignee" in params:
            fields["assignee"] = {"accountId": params["assignee"]}
        if "priority" in params:
            fields["priority"] = {"name": params["priority"]}
        if "labels" in params:
            fields["labels"] = [label.strip() for label in params["labels"].split(",")]
        return self._client.issue_create(fields=fields)

    def _issues_update(self, params: dict[str, str]) -> object:
        _require(params, "key")
        key = params["key"]
        fields = {k: v for k, v in params.items() if k != "key"}
        return self._client.issue_update(key, fields=fields)

    def _issues_delete(self, params: dict[str, str]) -> object:
        _require(params, "key")
        self._client.issue_delete(params["key"])
        return {
            "deleted": True,
            "issue_key": params["key"],
        }

    def _issues_transition(self, params: dict[str, str]) -> object:
        _require(params, "key", "status")
        key, status = params["key"], params["status"]
        transitions = self._client.get_issue_transitions(key)
        tid: str | None = None
        matched_transition: dict[str, Any] | None = None
        # Support numeric transition ID directly
        if status.isdigit():
            for transition in transitions:
                if str(transition.get("id")) == status:
                    tid = status
                    matched_transition = cast(dict[str, Any], transition)
                    break
        else:
            status_lower = status.lower()
            for transition in transitions:
                to_raw = transition.get("to", {})
                to_name = (to_raw.get("name", "") if isinstance(to_raw, dict) else str(to_raw)).lower()
                t_name = str(transition.get("name", "")).lower()
                if status_lower in (to_name, t_name):
                    tid = str(transition["id"])
                    matched_transition = cast(dict[str, Any], transition)
                    break
        if tid is None:
            available = []
            for t in transitions:
                to_raw = t.get("to", {})
                to_label = to_raw.get("name", "?") if isinstance(to_raw, dict) else str(to_raw or "?")
                available.append(f"{t.get('name', '?')} (id={t.get('id')}, to={to_label})")
            raise ValueError(
                f"No transition matching '{status}' for {key}. Available: {', '.join(available) or 'none'}"
            )
        self._client.set_issue_status_by_transition_id(key, tid)
        transition_name = str((matched_transition or {}).get("name", "") or "")
        to_raw = (matched_transition or {}).get("to", {})
        to_status = to_raw.get("name", "") if isinstance(to_raw, dict) else str(to_raw or "")
        return {
            "transitioned": True,
            "issue_key": key,
            "requested_status": status,
            "transition_id": tid,
            "transition_name": transition_name,
            "to_status": to_status,
        }

    def _issues_comment(self, params: dict[str, str]) -> object:
        _require(params, "key", "body")
        from koda.utils.adf_builder import text_to_adf

        adf_body = text_to_adf(params["body"])
        comment = self._client.issue_add_comment(params["key"], adf_body)
        metadata, attached = self._persist_comment_metadata(
            issue_key=params["key"],
            comment=comment,
            mode="comment",
        )
        if not attached:
            rolled_back = self._rollback_created_comment(params["key"], comment)
            if rolled_back:
                raise ValueError("Failed to attach Jira comment metadata; the new comment was rolled back for safety.")
            raise ValueError(
                "Failed to attach Jira comment metadata; the comment may require manual cleanup before retrying."
            )
        result = self._format_comment(params["key"], comment) if isinstance(comment, dict) else {"comment": comment}
        result["comment_meta"] = metadata
        result["comment_meta_attached"] = attached
        return result

    def _issues_comment_get(self, params: dict[str, str]) -> object:
        _require(params, "key", "comment-id")
        comment = self._get_issue_comment(params["key"], params["comment-id"])
        return self._format_comment(params["key"], comment)

    def _issues_comment_edit(self, params: dict[str, str]) -> object:
        _require(params, "key", "comment-id", "body")
        from koda.utils.adf_builder import text_to_adf

        existing = self._ensure_owned_comment(params["key"], params["comment-id"], action="comment_edit")
        previous_meta, previous_meta_status = self._get_comment_property_value(params["comment-id"])
        if previous_meta_status == COMMENT_META_STATUS_ERROR:
            raise ValueError("Blocked: unable to safely verify the existing Jira comment metadata before editing.")
        updated = self._client.issue_edit_comment(params["key"], params["comment-id"], text_to_adf(params["body"]))
        metadata, attached = self._persist_comment_metadata(
            issue_key=params["key"],
            comment=updated if isinstance(updated, dict) else existing,
            mode="comment",
            existing_metadata=previous_meta,
        )
        if not attached:
            rollback_body = existing.get("body")
            try:
                self._client.issue_edit_comment(params["key"], params["comment-id"], rollback_body)
            except Exception as exc:
                log.warning(
                    "jira_comment_edit_rollback_failed",
                    issue_key=params["key"],
                    comment_id=params["comment-id"],
                    error=str(exc),
                )
                raise ValueError(
                    "Failed to attach Jira comment metadata after editing; manual review is required before retrying."
                ) from exc
            raise ValueError("Failed to attach Jira comment metadata; the edit was rolled back for safety.")
        comment_payload = updated if isinstance(updated, dict) else existing
        result = self._format_comment(params["key"], cast(dict[str, Any], comment_payload))
        result["comment_meta"] = metadata
        result["comment_meta_attached"] = attached
        return result

    def _issues_comment_delete(self, params: dict[str, str]) -> object:
        _require(params, "key", "comment-id")
        self._ensure_owned_comment(params["key"], params["comment-id"], action="comment_delete")
        self._delete_issue_comment(params["key"], params["comment-id"])
        return {
            "deleted": True,
            "issue_key": params["key"],
            "comment_id": params["comment-id"],
        }

    def _issues_comment_reply(self, params: dict[str, str]) -> object:
        _require(params, "key", "comment-id", "body")
        target_comment = self._get_issue_comment(params["key"], params["comment-id"])
        reply_comment = self._client.issue_add_comment(
            params["key"],
            self._build_linked_reply_body(target_comment, reply_body=params["body"]),
        )
        metadata, attached = self._persist_comment_metadata(
            issue_key=params["key"],
            comment=reply_comment,
            mode="reply_linked",
            reply_to_comment_id=params["comment-id"],
        )
        if not attached:
            rolled_back = self._rollback_created_comment(params["key"], reply_comment)
            if rolled_back:
                raise ValueError("Failed to attach Jira reply metadata; the linked reply was rolled back for safety.")
            raise ValueError(
                "Failed to attach Jira reply metadata; the new reply may require manual cleanup before retrying."
            )
        result = (
            self._format_comment(params["key"], reply_comment)
            if isinstance(reply_comment, dict)
            else {"comment": reply_comment}
        )
        result["reply_to_comment_id"] = params["comment-id"]
        result["target_comment_excerpt"] = _comment_excerpt(target_comment.get("body"))
        result["comment_meta"] = metadata
        result["comment_meta_attached"] = attached
        return result

    def _issues_transitions(self, params: dict[str, str]) -> object:
        _require(params, "key")
        return self._client.get_issue_transitions(params["key"])

    def _issues_assign(self, params: dict[str, str]) -> object:
        _require(params, "key", "account-id")
        self._client.assign_issue(params["key"], params["account-id"])
        return {
            "assigned": True,
            "issue_key": params["key"],
            "account_id": params["account-id"],
        }

    def _issues_comments(self, params: dict[str, str]) -> object:
        _require(params, "key")
        return self._client.issue_get_comments(params["key"])

    async def build_issue_dossier(self, issue_key: str, *, query: str = "") -> IssueContextDossier:
        """Build the proactive issue dossier used by tooling and runtime prefetch."""
        confluence_client = None
        _jira_url, confluence_url = _resolved_atlassian_base_urls()
        if confluence_url:
            try:
                confluence_client = get_confluence_service()._client
            except Exception:
                log.warning("confluence_client_unavailable_for_issue_dossier", issue_key=issue_key)
        return await build_issue_context_dossier(
            issue_key=issue_key,
            jira_client=self._client,
            jira_session=self._client._session,
            query=query,
            confluence_client=confluence_client,
        )

    def _issues_link(self, params: dict[str, str]) -> object:
        _require(params, "type", "inward", "outward")
        data = {
            "type": {"name": params["type"]},
            "inwardIssue": {"key": params["inward"]},
            "outwardIssue": {"key": params["outward"]},
        }
        self._client.create_issue_link(data)
        return {
            "linked": True,
            "link_type": params["type"],
            "inward_issue_key": params["inward"],
            "outward_issue_key": params["outward"],
        }

    async def _issues_analyze(self, params: dict[str, str]) -> object:
        _require(params, "key")
        key = params["key"]
        if JIRA_DEEP_CONTEXT_ENABLED:
            try:
                context_dossier = await self.build_issue_dossier(key, query=f"Analyze Jira issue {key}")
                return _format_issue_analysis(
                    context_dossier.issue,
                    context_dossier.comments,
                    context_dossier.remote_links,
                    artifact_dossier=context_dossier.dossier,
                )
            except Exception:
                log.exception("jira_deep_context_failed", key=key)

        issue = await asyncio.to_thread(self._client.issue, key)
        comments = await asyncio.to_thread(self._client.issue_get_comments, key)
        try:
            remote_links = await asyncio.to_thread(self._client.get_issue_remote_links, key)
        except Exception:
            remote_links = []

        attachments = issue.get("fields", {}).get("attachment", [])
        media_ctx: MediaContext | None = None
        if attachments:
            try:
                media_ctx = await asyncio.to_thread(
                    _process_media_attachments,
                    self._client._session,
                    attachments,
                    key,
                )
            except Exception:
                log.warning("media_processing_failed", key=key)

        return _format_issue_analysis(issue, comments, remote_links, media_ctx)

    def _issues_attachments(self, params: dict[str, str]) -> object:
        _require(params, "key")
        issue = self._client.issue(params["key"])
        attachments = issue.get("fields", {}).get("attachment", [])
        result: list[dict] = []
        for att in attachments:
            result.append(
                {
                    "filename": att.get("filename", ""),
                    "size": att.get("size", 0),
                    "mimeType": att.get("mimeType", ""),
                    "author": _extract_name(att.get("author"), key="displayName"),
                    "created": att.get("created", ""),
                    "id": att.get("id", ""),
                }
            )
        return result

    def _issues_links(self, params: dict[str, str]) -> object:
        _require(params, "key")
        key = params["key"]
        issue = self._client.issue(key)
        issue_links = issue.get("fields", {}).get("issuelinks", [])
        try:
            remote_links = self._client.get_issue_remote_links(key)
        except Exception:
            remote_links = []
        return _format_links(issue_links, remote_links)

    def _issues_view_image(self, params: dict[str, str]) -> object:
        _require(params, "key", "attachment-id")
        key, attachment_id = params["key"], params["attachment-id"]

        issue = self._client.issue(key)
        attachments = issue.get("fields", {}).get("attachment", [])
        attachment = next(
            (a for a in attachments if str(a.get("id", "")) == str(attachment_id)),
            None,
        )
        if not attachment:
            return f"Error: Attachment {attachment_id} not found on {key}"

        mime = attachment.get("mimeType", "")
        filename = attachment.get("filename", "image")
        size = attachment.get("size", 0)

        if not is_image_mime(mime):
            return f"Error: Attachment '{filename}' is not an image (mimeType: {mime})"
        if size > MAX_IMAGE_SIZE:
            return f"Error: Image too large ({_format_size(size)}). Max: {_format_size(MAX_IMAGE_SIZE)}"

        content_url = attachment.get("content", "")
        if not content_url:
            return f"Error: No content URL for attachment {attachment_id}"

        try:
            content = _download_attachment(self._client._session, content_url)
        except Exception as e:
            return f"Error: Failed to download image attachment: {e}"

        IMAGE_TEMP_DIR.mkdir(parents=True, exist_ok=True)
        ext = Path(filename).suffix or ".jpg"
        # Convert TIFF/BMP to JPEG for Claude compatibility
        needs_convert = ext.lower() in (".tiff", ".tif", ".bmp")
        img_path = str(IMAGE_TEMP_DIR / f"jira_img_{attachment_id}{ext}")
        Path(img_path).write_bytes(content)

        if needs_convert:
            import subprocess

            jpeg_path = str(IMAGE_TEMP_DIR / f"jira_img_{attachment_id}.jpg")
            try:
                subprocess.run(
                    ["ffmpeg", "-i", img_path, "-y", jpeg_path],
                    capture_output=True,
                    timeout=30,
                )
                Path(img_path).unlink(missing_ok=True)
                img_path = jpeg_path
            except Exception:
                log.warning("image_convert_failed", attachment_id=attachment_id)

        return (
            f"## Image: {filename} ({key})\n\n"
            f"Downloaded image attachment for visual analysis.\n\n"
            f"Image file:\n- {img_path}"
        )

    def _issues_view_audio(self, params: dict[str, str]) -> object:
        _require(params, "key", "attachment-id")
        key, attachment_id = params["key"], params["attachment-id"]

        from koda.utils.audio import is_ffmpeg_available, transcribe_audio_sync

        if not is_ffmpeg_available():
            return "Error: FFmpeg is not available. Required for audio processing."

        issue = self._client.issue(key)
        attachments = issue.get("fields", {}).get("attachment", [])
        attachment = next(
            (a for a in attachments if str(a.get("id", "")) == str(attachment_id)),
            None,
        )
        if not attachment:
            return f"Error: Attachment {attachment_id} not found on {key}"

        mime = attachment.get("mimeType", "")
        filename = attachment.get("filename", "audio")
        size = attachment.get("size", 0)

        if not is_audio_mime(mime):
            return f"Error: Attachment '{filename}' is not audio (mimeType: {mime})"
        if size > MAX_AUDIO_SIZE:
            return f"Error: Audio too large ({_format_size(size)}). Max: {_format_size(MAX_AUDIO_SIZE)}"

        content_url = attachment.get("content", "")
        if not content_url:
            return f"Error: No content URL for attachment {attachment_id}"

        try:
            content = _download_attachment(self._client._session, content_url)
        except Exception as e:
            return f"Error: Failed to download audio attachment: {e}"

        IMAGE_TEMP_DIR.mkdir(parents=True, exist_ok=True)
        ext = Path(filename).suffix or ".mp3"
        audio_path = str(IMAGE_TEMP_DIR / f"jira_audio_{attachment_id}{ext}")
        Path(audio_path).write_bytes(content)

        try:
            transcription = transcribe_audio_sync(audio_path)
            if not transcription:
                return (
                    f"## Audio: {filename} ({key})\n\n"
                    "Transcription returned empty — audio may be silent or unrecognizable."
                )
            return f"## Audio: {filename} ({key})\n\n### Transcription:\n{transcription}"
        except Exception as e:
            return f"Error: Transcription failed for '{filename}': {e}"
        finally:
            Path(audio_path).unlink(missing_ok=True)

    def _issues_view_video(self, params: dict[str, str]) -> object:
        _require(params, "key", "attachment-id")
        key, attachment_id = params["key"], params["attachment-id"]

        issue = self._client.issue(key)
        attachments = issue.get("fields", {}).get("attachment", [])
        attachment = next(
            (a for a in attachments if str(a.get("id", "")) == str(attachment_id)),
            None,
        )
        if not attachment:
            return f"Error: Attachment {attachment_id} not found on {key}"

        mime = attachment.get("mimeType", "")
        filename = attachment.get("filename", "video")
        size = attachment.get("size", 0)

        from koda.utils.video import MAX_VIDEO_SIZE, is_video_mime

        if not is_video_mime(mime):
            return f"Error: Attachment '{filename}' is not a video (mimeType: {mime})"
        if size > MAX_VIDEO_SIZE:
            return f"Error: Video too large ({_format_size(size)}). Max: {_format_size(MAX_VIDEO_SIZE)}"

        content_url = attachment.get("content", "")
        if not content_url:
            return f"Error: No content URL for attachment {attachment_id}"
        try:
            content = _download_attachment(self._client._session, content_url)
        except Exception as e:
            return f"Error: Failed to download video attachment: {e}"

        from koda.utils.video import process_video_attachment

        frame_paths, summary = process_video_attachment(content, filename, attachment_id)
        return f"## Video Analysis: {filename} ({key})\n\n{summary}"

    # --- Project handlers ---

    def _projects_list(self, params: dict[str, str]) -> object:
        return self._client.projects()

    def _projects_get(self, params: dict[str, str]) -> object:
        _require(params, "key")
        return self._client.project(params["key"])

    # --- Board handlers ---

    def _boards_list(self, params: dict[str, str]) -> object:
        name = params.get("name")
        if name:
            return self._client.get_all_agile_boards(board_name=name)
        return self._client.get_all_agile_boards()

    def _boards_get(self, params: dict[str, str]) -> object:
        _require(params, "id")
        return self._client.get_agile_board(params["id"])

    # --- Sprint handlers ---

    def _sprints_list(self, params: dict[str, str]) -> object:
        _require(params, "board-id")
        return self._client.get_all_sprints_from_board(params["board-id"])

    def _sprints_get(self, params: dict[str, str]) -> object:
        _require(params, "id")
        return self._client.get_sprint(params["id"])

    def _sprints_issues(self, params: dict[str, str]) -> object:
        _require(params, "id")
        sprint_id = params["id"]
        jql = params.get("jql", "")
        if jql:
            raw = self._client.get_sprint_issues(sprint_id, jql=jql)
        else:
            raw = self._client.get_sprint_issues(sprint_id)
        return _slim_search_results(raw)

    # --- User handlers ---

    def _users_search(self, params: dict[str, str]) -> object:
        _require(params, "query")
        return self._client.user_find_by_user_string(query=params["query"])

    # --- Component/version/metadata handlers ---

    def _components_list(self, params: dict[str, str]) -> object:
        _require(params, "project")
        return self._client.get_project_components(params["project"])

    def _versions_list(self, params: dict[str, str]) -> object:
        _require(params, "project")
        return self._client.get_project_versions(params["project"])

    def _statuses_list(self, params: dict[str, str]) -> object:
        return self._client.get_all_statuses()

    def _priorities_list(self, params: dict[str, str]) -> object:
        return self._client.get_all_priorities()

    def _fields_list(self, params: dict[str, str]) -> object:
        return self._client.get_all_fields()

    _handlers: dict[str, object] = {
        "issues_search": _issues_search,
        "issues_get": _issues_get,
        "issues_create": _issues_create,
        "issues_update": _issues_update,
        "issues_delete": _issues_delete,
        "issues_transition": _issues_transition,
        "issues_transitions": _issues_transitions,
        "issues_comment": _issues_comment,
        "issues_comment_get": _issues_comment_get,
        "issues_comment_edit": _issues_comment_edit,
        "issues_comment_delete": _issues_comment_delete,
        "issues_comment_reply": _issues_comment_reply,
        "issues_assign": _issues_assign,
        "issues_comments": _issues_comments,
        "issues_link": _issues_link,
        "issues_analyze": _issues_analyze,
        "issues_attachments": _issues_attachments,
        "issues_links": _issues_links,
        "issues_view_video": _issues_view_video,
        "issues_view_image": _issues_view_image,
        "issues_view_audio": _issues_view_audio,
        "projects_list": _projects_list,
        "projects_get": _projects_get,
        "boards_list": _boards_list,
        "boards_get": _boards_get,
        "sprints_list": _sprints_list,
        "sprints_get": _sprints_get,
        "sprints_issues": _sprints_issues,
        "users_search": _users_search,
        "components_list": _components_list,
        "versions_list": _versions_list,
        "statuses_list": _statuses_list,
        "priorities_list": _priorities_list,
        "fields_list": _fields_list,
    }


class ConfluenceService:
    """Async wrapper around atlassian-python-api Confluence client."""

    def __init__(self, client_kwargs: dict[str, Any] | None = None) -> None:
        from atlassian import Confluence

        kwargs = dict(client_kwargs or _resolve_atlassian_client_kwargs("confluence"))
        self._client = Confluence(**kwargs)

    async def execute(self, resource: str, action: str, params: dict[str, str]) -> str:
        """Dispatch to the correct Confluence API method."""
        from koda.utils.approval import check_execution_approved

        if not check_execution_approved():
            return "Exit 1:\nCommand execution not approved."
        handler_key = f"{resource}_{action}"
        handler = self._handlers.get(handler_key)
        if not handler:
            return (
                f"Exit 1:\nUnknown command: {resource} {action}. Available: {', '.join(sorted(self._handlers.keys()))}"
            )
        try:
            typed_handler = cast(Callable[[ConfluenceService, dict[str, str]], Any], handler)
            result: Any = await asyncio.wait_for(
                asyncio.to_thread(typed_handler, self, params),
                timeout=CONFLUENCE_TIMEOUT,
            )
            return _format_result(result)
        except TimeoutError:
            return f"Timeout after {CONFLUENCE_TIMEOUT}s for {resource} {action}."
        except ValueError as e:
            return f"Exit 1:\n{e}"
        except Exception as e:
            log.exception("confluence_error", resource=resource, action=action)
            return _format_error(e)

    # --- Page handlers ---

    def _pages_get(self, params: dict[str, str]) -> object:
        if "id" in params:
            return self._client.get_page_by_id(params["id"])
        _require(params, "space", "title")
        return self._client.get_page_by_title(params["space"], params["title"])

    def _pages_create(self, params: dict[str, str]) -> object:
        _require(params, "space", "title", "body")
        kwargs: dict[str, object] = {
            "space": params["space"],
            "title": params["title"],
            "body": params["body"],
        }
        if "parent-id" in params:
            kwargs["parent_id"] = params["parent-id"]
        return self._client.create_page(**kwargs)

    def _pages_update(self, params: dict[str, str]) -> object:
        _require(params, "id", "title", "body")
        return self._client.update_page(
            page_id=params["id"],
            title=params["title"],
            body=params["body"],
        )

    def _pages_delete(self, params: dict[str, str]) -> object:
        _require(params, "id")
        return self._client.remove_page(params["id"])

    def _pages_search(self, params: dict[str, str]) -> object:
        cql = params.get("cql", "")
        limit = int(params.get("limit", "25"))
        return self._client.cql(cql, limit=limit)

    def _pages_children(self, params: dict[str, str]) -> object:
        _require(params, "id")
        return self._client.get_page_child_by_type(params["id"])

    # --- Space handlers ---

    def _spaces_list(self, params: dict[str, str]) -> object:
        return self._client.get_all_spaces()

    def _spaces_get(self, params: dict[str, str]) -> object:
        _require(params, "key")
        return self._client.get_space(params["key"])

    def verify_read_access(self) -> dict[str, Any]:
        """Run a lightweight authenticated read probe and return a compact summary."""
        probe = self._client.get_all_spaces(start=0, limit=1)
        if isinstance(probe, dict):
            results = probe.get("results")
            if isinstance(results, list):
                first = cast(dict[str, Any], results[0]) if results else {}
                return {
                    "space_count": len(results),
                    "first_space_key": str(first.get("key") or ""),
                    "first_space_name": str(first.get("name") or ""),
                }
        raise ValueError("Confluence read probe returned an unexpected payload.")

    _handlers: dict[str, object] = {
        "pages_get": _pages_get,
        "pages_create": _pages_create,
        "pages_update": _pages_update,
        "pages_delete": _pages_delete,
        "pages_search": _pages_search,
        "pages_children": _pages_children,
        "spaces_list": _spaces_list,
        "spaces_get": _spaces_get,
    }


# --- Lazy singletons ---


def get_jira_service() -> JiraService:
    """Create a Jira service bound to the current agent connection."""
    return JiraService()


def get_confluence_service() -> ConfluenceService:
    """Create a Confluence service bound to the current agent connection."""
    return ConfluenceService()
