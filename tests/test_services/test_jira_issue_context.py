"""Tests for proactive Jira issue dossier discovery."""

from __future__ import annotations

from unittest.mock import ANY, AsyncMock, MagicMock, call, patch

import pytest

from koda.services.artifact_ingestion import ArtifactKind, ArtifactRef, ArtifactStatus, ExtractedArtifact
from koda.services.jira_issue_context import (
    IssueContextDossier,
    _extract_linked_url,
    build_issue_context_dossier,
    extract_issue_keys,
)


def _artifact(label: str, *, kind: ArtifactKind, status: ArtifactStatus = ArtifactStatus.COMPLETE) -> ExtractedArtifact:
    return ExtractedArtifact(
        ref=ArtifactRef(
            artifact_id=label,
            kind=kind,
            label=label,
            source_type="test",
            critical_for_action=(status != ArtifactStatus.COMPLETE),
        ),
        status=status,
        summary=f"summary for {label}",
        critical_for_action=(status != ArtifactStatus.COMPLETE),
    )


class TestIssueKeyExtraction:
    def test_extract_issue_keys_deduplicates_text_and_browse_urls(self):
        text = "Analisar SIM-410 e depois abrir https://example.atlassian.net/browse/SIM-410 junto com SIM-512"

        assert extract_issue_keys(text) == ["SIM-410", "SIM-512"]


class TestIssueContextDossier:
    @pytest.mark.asyncio
    async def test_build_issue_context_dossier_prioritizes_media_referenced_attachments(self):
        jira_client = MagicMock()
        jira_client.issue.return_value = {
            "key": "SIM-410",
            "fields": {
                "summary": "Checkout failure",
                "description": {
                    "type": "doc",
                    "version": 1,
                    "content": [
                        {
                            "type": "mediaSingle",
                            "content": [
                                {
                                    "type": "media",
                                    "attrs": {"id": "200", "type": "file"},
                                }
                            ],
                        },
                        {
                            "type": "paragraph",
                            "content": [
                                {"type": "text", "text": "Ver documentação"},
                                {
                                    "type": "text",
                                    "text": " aqui",
                                    "marks": [{"type": "link", "attrs": {"href": "https://example.com/spec"}}],
                                },
                            ],
                        },
                    ],
                },
                "attachment": [
                    {
                        "id": "100",
                        "filename": "notes.pdf",
                        "mimeType": "application/pdf",
                        "size": 1024,
                        "content": "https://test.atlassian.net/100",
                        "created": "2026-03-17T12:00:00.000+0000",
                    },
                    {
                        "id": "200",
                        "filename": "screen.png",
                        "mimeType": "image/png",
                        "size": 1024,
                        "content": "https://test.atlassian.net/200",
                        "created": "2026-03-17T12:00:00.000+0000",
                    },
                ],
                "issuelinks": [],
            },
        }
        jira_client.issue_get_comments.return_value = {
            "comments": [
                {
                    "id": "300",
                    "body": {
                        "type": "doc",
                        "version": 1,
                        "content": [
                            {
                                "type": "paragraph",
                                "content": [
                                    {"type": "text", "text": "Relacionado a "},
                                    {
                                        "type": "text",
                                        "text": "SIM-500",
                                        "marks": [
                                            {
                                                "type": "link",
                                                "attrs": {"href": "https://example.atlassian.net/browse/SIM-500"},
                                            }
                                        ],
                                    },
                                ],
                            }
                        ],
                    },
                }
            ]
        }
        jira_client.get_issue_remote_links.return_value = [
            {"object": {"url": "https://docs.google.com/document/d/abc123/edit"}}
        ]

        extract_attachment = AsyncMock(
            side_effect=[
                _artifact("screen.png", kind=ArtifactKind.IMAGE),
                _artifact("notes.pdf", kind=ArtifactKind.PDF),
            ]
        )
        extract_url = AsyncMock(
            side_effect=[
                _artifact("https://example.com/spec", kind=ArtifactKind.URL),
                _artifact("SIM-500", kind=ArtifactKind.URL),
                _artifact(
                    "https://docs.google.com/document/d/abc123/edit",
                    kind=ArtifactKind.URL,
                    status=ArtifactStatus.UNRESOLVED,
                ),
            ]
        )

        with (
            patch("koda.services.jira_issue_context._extract_attachment", extract_attachment),
            patch("koda.services.jira_issue_context._extract_linked_url", extract_url),
        ):
            dossier = await build_issue_context_dossier(
                issue_key="SIM-410",
                jira_client=jira_client,
                jira_session=MagicMock(),
                query="Analise o card SIM-410 por completo",
            )

        assert isinstance(dossier, IssueContextDossier)
        assert dossier.dossier.subject_id == "SIM-410"
        assert dossier.media_refs[0]["id"] == "200"
        assert dossier.discovered_urls == [
            "https://example.com/spec",
            "https://example.atlassian.net/browse/SIM-500",
            "https://docs.google.com/document/d/abc123/edit",
        ]
        assert extract_attachment.await_args_list == [
            call(
                issue_key="SIM-410",
                attachment=jira_client.issue.return_value["fields"]["attachment"][1],
                jira_session=ANY,
                media_refs=dossier.media_refs,
            ),
            call(
                issue_key="SIM-410",
                attachment=jira_client.issue.return_value["fields"]["attachment"][0],
                jira_session=ANY,
                media_refs=dossier.media_refs,
            ),
        ]
        assert len(dossier.dossier.artifacts) == 5
        assert "complete=4" in dossier.dossier.summary
        assert "unresolved=1" in dossier.dossier.summary

    @pytest.mark.asyncio
    async def test_extract_linked_url_marks_google_workspace_as_unresolved(self):
        extracted = await _extract_linked_url(
            issue_key="SIM-410",
            url="https://docs.google.com/document/d/abc123/edit",
            jira_client=MagicMock(),
            confluence_client=None,
        )

        assert extracted is not None
        assert extracted.status == ArtifactStatus.UNRESOLVED
        assert "Google Workspace URL" in extracted.summary
