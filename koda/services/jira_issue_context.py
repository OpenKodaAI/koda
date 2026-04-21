"""Deep Jira issue dossier discovery and artifact ingestion."""

from __future__ import annotations

import asyncio
import hashlib
import mimetypes
import os
import re
from contextlib import suppress
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

from koda.config import AGENT_ID, CONFLUENCE_URL, IMAGE_TEMP_DIR, JIRA_URL
from koda.logging_config import get_logger
from koda.services.artifact_ingestion import (
    ArtifactDossier,
    ArtifactKind,
    ArtifactRef,
    ArtifactStatus,
    EvidenceRef,
    ExtractedArtifact,
    extract_artifact,
)
from koda.utils.adf_renderer import classify_url, extract_media_refs_from_adf, extract_urls_from_adf

log = get_logger(__name__)

_ISSUE_KEY_RE = re.compile(r"\b([A-Z][A-Z0-9]{1,15}-\d+)\b")
_BROWSE_RE = re.compile(r"/browse/([A-Z][A-Z0-9]{1,15}-\d+)", re.IGNORECASE)
_CONFLUENCE_PAGE_RE = re.compile(r"/pages/(\d+)")
_MAX_URLS = 12


def _resolved_atlassian_base_urls() -> tuple[str, str]:
    jira_url = JIRA_URL
    confluence_url = CONFLUENCE_URL
    current_agent = str(os.environ.get("AGENT_ID") or AGENT_ID or "").strip().upper()
    if current_agent:
        with suppress(Exception):
            from koda.services.core_connection_broker import get_core_connection_broker

            urls = get_core_connection_broker().atlassian_base_urls(agent_id=current_agent)
            jira_url = str(urls.get("jira") or jira_url or "").strip()
            confluence_url = str(urls.get("confluence") or confluence_url or "").strip()
    return jira_url, confluence_url


@dataclass(slots=True)
class IssueContextDossier:
    """Resolved issue plus proactive artifact dossier."""

    issue: dict[str, Any]
    comments: list[dict[str, Any]]
    remote_links: list[dict[str, Any]]
    dossier: ArtifactDossier
    discovered_urls: list[str] = field(default_factory=list)
    media_refs: list[dict[str, str]] = field(default_factory=list)


def extract_issue_keys(text: str) -> list[str]:
    """Extract unique Jira issue keys from free-form text or Jira URLs."""
    seen: set[str] = set()
    results: list[str] = []
    for match in _ISSUE_KEY_RE.findall(text or ""):
        normalized = match.upper()
        if normalized not in seen:
            seen.add(normalized)
            results.append(normalized)
    for match in _BROWSE_RE.findall(text or ""):
        normalized = match.upper()
        if normalized not in seen:
            seen.add(normalized)
            results.append(normalized)
    return results


async def build_issue_context_dossier(
    *,
    issue_key: str,
    jira_client: Any,
    jira_session: Any,
    query: str = "",
    confluence_client: Any | None = None,
) -> IssueContextDossier:
    """Build a deep issue dossier with proactive artifact discovery."""
    issue = await asyncio.to_thread(jira_client.issue, issue_key)
    comments_raw = await asyncio.to_thread(jira_client.issue_get_comments, issue_key)
    try:
        remote_links = await asyncio.to_thread(jira_client.get_issue_remote_links, issue_key)
    except Exception:
        remote_links = []

    comments = _normalize_comments(comments_raw)
    attachments = list(issue.get("fields", {}).get("attachment", []) or [])
    media_refs = _collect_media_refs(issue, comments)
    discovered_urls = _collect_urls(issue, comments, remote_links)
    prioritized_attachments = _prioritize_attachments(attachments, media_refs)

    extracted_artifacts: list[ExtractedArtifact] = []
    warnings: list[str] = []
    for attachment in prioritized_attachments:
        extracted = await _extract_attachment(
            issue_key=issue_key,
            attachment=attachment,
            jira_session=jira_session,
            media_refs=media_refs,
        )
        extracted_artifacts.append(extracted)
        warnings.extend(extracted.warnings)

    for url in discovered_urls[:_MAX_URLS]:
        linked_artifact = await _extract_linked_url(
            issue_key=issue_key,
            url=url,
            jira_client=jira_client,
            confluence_client=confluence_client,
        )
        if linked_artifact is None:
            continue
        extracted_artifacts.append(linked_artifact)
        warnings.extend(linked_artifact.warnings)

    issue_summary = issue.get("fields", {}).get("summary", "") or issue_key
    dossier = ArtifactDossier(
        subject_id=issue_key,
        subject_label=f"Jira issue {issue_key}: {issue_summary}",
        summary=_build_issue_summary(issue_key, issue_summary, extracted_artifacts, query=query),
        artifacts=extracted_artifacts,
        warnings=list(dict.fromkeys(warnings)),
        metadata={
            "issue_key": issue_key,
            "url_count": len(discovered_urls),
            "attachment_count": len(attachments),
        },
    )
    return IssueContextDossier(
        issue=issue,
        comments=comments,
        remote_links=list(remote_links or []),
        dossier=dossier,
        discovered_urls=discovered_urls,
        media_refs=media_refs,
    )


def _normalize_comments(comments_raw: object) -> list[dict[str, Any]]:
    if isinstance(comments_raw, dict):
        comments = comments_raw.get("comments", [])
        return [item for item in comments if isinstance(item, dict)]
    if isinstance(comments_raw, list):
        return [item for item in comments_raw if isinstance(item, dict)]
    return []


def _collect_media_refs(issue: dict[str, Any], comments: list[dict[str, Any]]) -> list[dict[str, str]]:
    refs: list[dict[str, str]] = []
    description = issue.get("fields", {}).get("description")
    if isinstance(description, dict):
        refs.extend(extract_media_refs_from_adf(description))
    for comment in comments:
        body = comment.get("body")
        if isinstance(body, dict):
            refs.extend(extract_media_refs_from_adf(body))
    return refs


def _collect_urls(
    issue: dict[str, Any],
    comments: list[dict[str, Any]],
    remote_links: list[dict[str, Any]],
) -> list[str]:
    urls: list[str] = []
    description = issue.get("fields", {}).get("description")
    if isinstance(description, dict):
        urls.extend(extract_urls_from_adf(description))
    for comment in comments:
        body = comment.get("body")
        if isinstance(body, dict):
            urls.extend(extract_urls_from_adf(body))
    for link in remote_links:
        if isinstance(link, dict):
            obj = link.get("object")
            if isinstance(obj, dict) and isinstance(obj.get("url"), str):
                urls.append(str(obj["url"]))
    seen: set[str] = set()
    ordered: list[str] = []
    for url in urls:
        if url and url not in seen:
            seen.add(url)
            ordered.append(url)
    return ordered


def _prioritize_attachments(
    attachments: list[dict[str, Any]],
    media_refs: list[dict[str, str]],
) -> list[dict[str, Any]]:
    referenced_ids = {str(ref.get("id", "")) for ref in media_refs if ref.get("id")}

    def _sort_key(attachment: dict[str, Any]) -> tuple[int, str]:
        attachment_id = str(attachment.get("id", ""))
        filename = str(attachment.get("filename", ""))
        referenced_rank = 0 if attachment_id in referenced_ids else 1
        return (referenced_rank, filename.lower())

    return sorted(attachments, key=_sort_key)


async def _extract_attachment(
    *,
    issue_key: str,
    attachment: dict[str, Any],
    jira_session: Any,
    media_refs: list[dict[str, str]],
) -> ExtractedArtifact:
    attachment_id = str(attachment.get("id", "") or "")
    filename = str(attachment.get("filename", "attachment"))
    mime_type = str(attachment.get("mimeType", "") or mimetypes.guess_type(filename)[0] or "")
    size = int(attachment.get("size") or 0)
    content_url = str(attachment.get("content", "") or "")
    kind = _detect_attachment_kind(filename, mime_type)
    referenced_ids = {str(ref.get("id", "")) for ref in media_refs if ref.get("id")}
    critical = attachment_id in referenced_ids or kind not in {ArtifactKind.URL, ArtifactKind.UNKNOWN}
    updated_at = str(attachment.get("created", "") or "")

    if not content_url:
        return ExtractedArtifact(
            ref=ArtifactRef(
                artifact_id=f"{issue_key}:{attachment_id}",
                kind=kind,
                label=filename,
                source_type="jira_attachment",
                mime_type=mime_type,
                issue_key=issue_key,
                size_bytes=size,
                updated_at=updated_at,
                critical_for_action=critical,
                metadata={"attachment_id": attachment_id},
            ),
            status=ArtifactStatus.UNRESOLVED,
            summary=f"Attachment {filename} has no download URL.",
            warnings=["attachment content URL missing"],
            critical_for_action=critical,
        )

    limit = _artifact_size_limit(kind)
    if limit and size > limit:
        return ExtractedArtifact(
            ref=ArtifactRef(
                artifact_id=f"{issue_key}:{attachment_id}",
                kind=kind,
                label=filename,
                source_type="jira_attachment",
                mime_type=mime_type,
                issue_key=issue_key,
                size_bytes=size,
                updated_at=updated_at,
                critical_for_action=critical,
                metadata={"attachment_id": attachment_id},
            ),
            status=ArtifactStatus.PARTIAL,
            summary=f"Attachment {filename} exceeds the proactive extraction limit.",
            warnings=[f"attachment too large for proactive extraction ({size} bytes)"],
            critical_for_action=critical,
        )

    temp_path = await asyncio.to_thread(
        _download_attachment_to_temp,
        jira_session,
        issue_key,
        attachment_id,
        filename,
        content_url,
    )
    ref = ArtifactRef(
        artifact_id=f"{issue_key}:{attachment_id}",
        kind=kind,
        label=filename,
        source_type="jira_attachment",
        mime_type=mime_type,
        path=temp_path,
        issue_key=issue_key,
        size_bytes=size,
        updated_at=updated_at,
        critical_for_action=critical,
        metadata={"attachment_id": attachment_id, "referenced_in_adf": attachment_id in referenced_ids},
    )
    extracted = await extract_artifact(ref)
    return extracted


async def _extract_linked_url(
    *,
    issue_key: str,
    url: str,
    jira_client: Any,
    confluence_client: Any | None,
) -> ExtractedArtifact | None:
    jira_url, confluence_url = _resolved_atlassian_base_urls()
    category = classify_url(url, jira_url, confluence_url)
    artifact_id = hashlib.sha256(f"{issue_key}:{url}".encode(), usedforsecurity=False).hexdigest()[:16]
    base_ref = ArtifactRef(
        artifact_id=artifact_id,
        kind=ArtifactKind.URL,
        label=url,
        source_type="jira_url",
        url=url,
        issue_key=issue_key,
        critical_for_action=False,
        metadata={"category": category},
    )

    if category == "jira":
        linked_key = _extract_issue_key_from_url(url)
        if linked_key and linked_key != issue_key:
            linked_issue = await asyncio.to_thread(jira_client.issue, linked_key)
            summary = linked_issue.get("fields", {}).get("summary", "") or linked_key
            text = f"Linked Jira issue {linked_key}: {summary}"
            return ExtractedArtifact(
                ref=base_ref,
                status=ArtifactStatus.COMPLETE,
                summary=text,
                evidence_chunks=[EvidenceRef(citation=linked_key, excerpt=text)],
                citations=[linked_key],
                text_content=text,
                critical_for_action=False,
            )
        return None

    if category == "confluence" and confluence_client is not None:
        page_id = _extract_confluence_page_id(url)
        if page_id:
            page = await asyncio.to_thread(confluence_client.get_page_by_id, page_id, expand="body.storage")
            title = str(page.get("title", f"Confluence page {page_id}"))
            body = page.get("body")
            body_value = page.get("body", {}).get("storage", {}).get("value", "") if isinstance(body, dict) else ""
            text = _html_to_text(body_value)
            excerpt = f"{title}\n{text}".strip()
            evidence = [EvidenceRef(citation=f"confluence:{page_id}", excerpt=excerpt[:700])] if excerpt else []
            return ExtractedArtifact(
                ref=base_ref,
                status=ArtifactStatus.COMPLETE if excerpt else ArtifactStatus.PARTIAL,
                summary=excerpt[:1000] + ("..." if len(excerpt) > 1000 else ""),
                evidence_chunks=evidence,
                citations=[f"confluence:{page_id}"] if excerpt else [],
                text_content=excerpt[:4000],
                critical_for_action=False,
            )

    parsed = urlparse(url)
    if parsed.netloc.endswith("docs.google.com") or parsed.netloc.endswith("drive.google.com"):
        return ExtractedArtifact(
            ref=base_ref,
            status=ArtifactStatus.UNRESOLVED,
            summary=f"Linked Google Workspace URL could not be resolved automatically: {url}",
            warnings=["google workspace URL requires a dedicated integration path"],
            critical_for_action=False,
        )

    return await extract_artifact(base_ref)


def _build_issue_summary(
    issue_key: str,
    issue_summary: str,
    artifacts: list[ExtractedArtifact],
    *,
    query: str,
) -> str:
    complete = sum(1 for artifact in artifacts if artifact.status == ArtifactStatus.COMPLETE)
    partial = sum(1 for artifact in artifacts if artifact.status == ArtifactStatus.PARTIAL)
    unresolved = sum(1 for artifact in artifacts if artifact.status == ArtifactStatus.UNRESOLVED)
    unsupported = sum(1 for artifact in artifacts if artifact.status == ArtifactStatus.UNSUPPORTED)
    detail = (
        f"{issue_key}: {issue_summary}. "
        "Artifacts extracted: "
        f"complete={complete}, partial={partial}, unresolved={unresolved}, unsupported={unsupported}."
    )
    if query:
        detail += f" Query focus: {query[:280]}."
    return detail


def _download_attachment_to_temp(
    jira_session: Any,
    issue_key: str,
    attachment_id: str,
    filename: str,
    content_url: str,
) -> str:
    response = jira_session.get(content_url)
    response.raise_for_status()
    IMAGE_TEMP_DIR.mkdir(parents=True, exist_ok=True)
    ext = Path(filename).suffix or _extension_for_download(filename)
    path = IMAGE_TEMP_DIR / f"jira_artifact_{issue_key}_{attachment_id}{ext}"
    path.write_bytes(response.content)
    return str(path)


def _extension_for_download(filename: str) -> str:
    guessed = Path(filename).suffix
    return guessed if guessed else ".bin"


def _artifact_size_limit(kind: ArtifactKind) -> int:
    from koda.services.atlassian_client import MAX_AUDIO_SIZE, MAX_IMAGE_SIZE
    from koda.utils.video import MAX_VIDEO_SIZE

    if kind == ArtifactKind.IMAGE:
        return MAX_IMAGE_SIZE
    if kind == ArtifactKind.AUDIO:
        return MAX_AUDIO_SIZE
    if kind == ArtifactKind.VIDEO:
        return MAX_VIDEO_SIZE
    return 50 * 1024 * 1024


def _detect_attachment_kind(filename: str, mime_type: str) -> ArtifactKind:
    from koda.services.artifact_ingestion import detect_artifact_kind

    return detect_artifact_kind(path=filename, mime_type=mime_type)


def _extract_issue_key_from_url(url: str) -> str | None:
    match = _BROWSE_RE.search(url)
    if not match:
        return None
    return match.group(1).upper()


def _extract_confluence_page_id(url: str) -> str | None:
    match = _CONFLUENCE_PAGE_RE.search(url)
    if match:
        return match.group(1)
    parsed = urlparse(url)
    query = parse_qs(parsed.query)
    page_ids = query.get("pageId")
    if page_ids:
        return page_ids[0]
    return None


def _html_to_text(html: str) -> str:
    try:
        from bs4 import BeautifulSoup
    except ImportError:
        return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", html or "")).strip()
    soup = BeautifulSoup(html or "", "html.parser")
    return re.sub(r"\s+", " ", soup.get_text("\n")).strip()
