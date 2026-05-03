"""Pure-logic tests for koda.services.artifact_ingestion.

Pins:
  detect_artifact_kind        — MIME-first, extension fallback, URL last resort
  ArtifactRef.cache_identity  — cache-scope keys are required to avoid leakage

These functions decide where an artifact ends up in cache and what extractor
runs over it. Drift here causes silent cross-context leakage (the highest-risk
gap in the explore report).
"""

from __future__ import annotations

from typing import Any

import pytest

from koda.services.artifact_ingestion import (
    ArtifactKind,
    ArtifactRef,
    detect_artifact_kind,
)

# ---------------------------------------------------------------------------
# detect_artifact_kind — MIME wins
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "mime,expected",
    [
        ("image/png", ArtifactKind.IMAGE),
        ("image/jpeg", ArtifactKind.IMAGE),
        ("image/webp", ArtifactKind.IMAGE),
        ("image/svg+xml", ArtifactKind.IMAGE),
        ("audio/mpeg", ArtifactKind.AUDIO),
        ("audio/ogg", ArtifactKind.AUDIO),
        ("audio/x-wav", ArtifactKind.AUDIO),
        ("video/mp4", ArtifactKind.VIDEO),
        ("video/webm", ArtifactKind.VIDEO),
        ("application/pdf", ArtifactKind.PDF),
        ("application/vnd.openxmlformats-officedocument.wordprocessingml.document", ArtifactKind.DOCX),
        ("application/msword", ArtifactKind.DOCX),
        ("application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", ArtifactKind.SPREADSHEET),
        ("application/vnd.ms-excel", ArtifactKind.SPREADSHEET),
        ("text/html", ArtifactKind.HTML),
        ("application/json", ArtifactKind.JSON),
        ("application/x-yaml", ArtifactKind.YAML),
        ("text/yaml", ArtifactKind.YAML),
        ("application/xml", ArtifactKind.XML),
        ("text/xml", ArtifactKind.XML),
        ("text/csv", ArtifactKind.CSV),
        ("text/tab-separated-values", ArtifactKind.TSV),
        ("text/plain", ArtifactKind.TEXT),
        ("text/markdown", ArtifactKind.TEXT),
    ],
)
def test_detect_kind_by_mime(mime: str, expected: ArtifactKind) -> None:
    assert detect_artifact_kind(mime_type=mime) == expected


# ---------------------------------------------------------------------------
# detect_artifact_kind — extension fallback when MIME missing
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "path,expected",
    [
        ("/tmp/image.png", ArtifactKind.IMAGE),
        ("/tmp/image.JPG", ArtifactKind.IMAGE),
        ("/tmp/photo.jpeg", ArtifactKind.IMAGE),
        ("/tmp/anim.gif", ArtifactKind.IMAGE),
        ("/tmp/icon.bmp", ArtifactKind.IMAGE),
        ("/tmp/song.mp3", ArtifactKind.AUDIO),
        ("/tmp/note.m4a", ArtifactKind.AUDIO),
        ("/tmp/clip.flac", ArtifactKind.AUDIO),
        ("/tmp/movie.mp4", ArtifactKind.VIDEO),
        ("/tmp/clip.mov", ArtifactKind.VIDEO),
        ("/tmp/clip.webm", ArtifactKind.VIDEO),
        ("/tmp/contract.pdf", ArtifactKind.PDF),
        ("/tmp/report.docx", ArtifactKind.DOCX),
        ("/tmp/data.xlsx", ArtifactKind.SPREADSHEET),
        ("/tmp/data.csv", ArtifactKind.CSV),
        ("/tmp/data.tsv", ArtifactKind.TSV),
        ("/tmp/data.json", ArtifactKind.JSON),
        ("/tmp/cfg.yaml", ArtifactKind.YAML),
        ("/tmp/cfg.YML", ArtifactKind.YAML),
        ("/tmp/dom.xml", ArtifactKind.XML),
        ("/tmp/page.html", ArtifactKind.HTML),
        ("/tmp/notes.md", ArtifactKind.TEXT),
        ("/tmp/log.log", ArtifactKind.TEXT),
        ("/tmp/snippet.py", ArtifactKind.TEXT),
    ],
)
def test_detect_kind_by_extension_fallback(path: str, expected: ArtifactKind) -> None:
    """Extension fallback runs only when MIME is empty/unknown."""
    assert detect_artifact_kind(path=path, mime_type="") == expected


# ---------------------------------------------------------------------------
# detect_artifact_kind — URL when nothing else available
# ---------------------------------------------------------------------------


def test_detect_kind_url_only_returns_url() -> None:
    assert detect_artifact_kind(url="https://example.com/page") == ArtifactKind.URL


def test_detect_kind_url_with_path_prefers_extension() -> None:
    """When path is provided alongside URL, extension wins (URL is last resort)."""
    assert detect_artifact_kind(path="/tmp/file.pdf", url="https://x") == ArtifactKind.PDF


# ---------------------------------------------------------------------------
# detect_artifact_kind — unknown / pathless / mimeless
# ---------------------------------------------------------------------------


def test_detect_kind_unknown_returns_unknown() -> None:
    assert detect_artifact_kind() == ArtifactKind.UNKNOWN


def test_detect_kind_unknown_extension_returns_unknown() -> None:
    assert detect_artifact_kind(path="/tmp/file.xyz123") == ArtifactKind.UNKNOWN


def test_detect_kind_mime_wins_over_extension() -> None:
    """A `.pdf` file with `image/png` MIME is classified as IMAGE."""
    assert detect_artifact_kind(path="/tmp/spoof.pdf", mime_type="image/png") == ArtifactKind.IMAGE


def test_detect_kind_html_mime_overrides_pdf_extension() -> None:
    """An HTML payload disguised as `.pdf` is classified by MIME."""
    assert detect_artifact_kind(path="/tmp/disguised.pdf", mime_type="text/html") == ArtifactKind.HTML


# ---------------------------------------------------------------------------
# ArtifactRef.cache_identity — scope-leak prevention
# ---------------------------------------------------------------------------


def _ref(**overrides: Any) -> ArtifactRef:
    base: dict[str, Any] = {
        "artifact_id": "abc123",
        "kind": ArtifactKind.PDF,
        "label": "doc.pdf",
        "source_type": "test",
        "metadata": {},
    }
    base.update(overrides)
    return ArtifactRef(**base)


def test_cache_identity_includes_extractor_version() -> None:
    ident = _ref().cache_identity()
    assert "extractor_version" in ident


def test_cache_identity_isolates_by_agent_id() -> None:
    a = _ref(metadata={"agent_id": "AGENT_A"}).cache_identity()
    b = _ref(metadata={"agent_id": "AGENT_B"}).cache_identity()
    assert a != b
    assert a["cache_scope"]["agent_id"] == "AGENT_A"
    assert b["cache_scope"]["agent_id"] == "AGENT_B"


def test_cache_identity_isolates_by_user_id() -> None:
    a = _ref(metadata={"user_id": 111}).cache_identity()
    b = _ref(metadata={"user_id": 222}).cache_identity()
    assert a != b


def test_cache_identity_isolates_by_task_id() -> None:
    a = _ref(metadata={"task_id": 1}).cache_identity()
    b = _ref(metadata={"task_id": 2}).cache_identity()
    assert a != b


def test_cache_identity_isolates_by_workspace_root() -> None:
    a = _ref(metadata={"workspace_root": "/work/a"}).cache_identity()
    b = _ref(metadata={"workspace_root": "/work/b"}).cache_identity()
    assert a != b


def test_cache_identity_isolates_by_workspace_scope() -> None:
    a = _ref(metadata={"workspace_scope": "scope-a"}).cache_identity()
    b = _ref(metadata={"workspace_scope": "scope-b"}).cache_identity()
    assert a != b


def test_cache_identity_isolates_by_source_scope() -> None:
    a = _ref(metadata={"source_scope": "telegram"}).cache_identity()
    b = _ref(metadata={"source_scope": "web_upload"}).cache_identity()
    assert a != b


def test_cache_identity_isolates_by_project_key() -> None:
    a = _ref(metadata={"project_key": "alpha"}).cache_identity()
    b = _ref(metadata={"project_key": "beta"}).cache_identity()
    assert a != b


def test_cache_identity_full_scope_round_trip() -> None:
    """All seven scope keys must surface in cache_scope verbatim."""
    md = {
        "agent_id": "A",
        "user_id": 1,
        "task_id": 7,
        "workspace_root": "/w",
        "workspace_scope": "ws",
        "source_scope": "tg",
        "project_key": "p",
    }
    ident = _ref(metadata=md).cache_identity()
    assert ident["cache_scope"] == md


def test_cache_identity_omits_scope_keys_with_falsy_values() -> None:
    """Falsy values (None, "", [], ()) are not surfaced — keep cache scopes terse."""
    md = {
        "agent_id": "A",
        "user_id": None,
        "task_id": "",
        "workspace_root": [],
        "workspace_scope": (),
        "source_scope": "tg",
    }
    ident = _ref(metadata=md).cache_identity()
    cs = ident["cache_scope"]
    assert cs == {"agent_id": "A", "source_scope": "tg"}


def test_cache_identity_ignores_non_scope_metadata() -> None:
    """Random metadata fields are not surfaced into cache_scope."""
    ident = _ref(metadata={"agent_id": "A", "foo": "bar", "trace_id": "x"}).cache_identity()
    assert "foo" not in ident["cache_scope"]
    assert "trace_id" not in ident["cache_scope"]


def test_cache_identity_pathless_ref_has_no_size() -> None:
    """Without a path, size_bytes is None unless explicitly provided."""
    ident = _ref(path=None, size_bytes=None).cache_identity()
    assert ident["path"] is None
    assert ident["size_bytes"] is None


def test_cache_identity_changes_when_explicit_size_changes() -> None:
    """Size and updated_at are part of the cache identity to invalidate stale runs."""
    a = _ref(path=None, size_bytes=1024, updated_at="2026-01-01T00:00:00Z").cache_identity()
    b = _ref(path=None, size_bytes=2048, updated_at="2026-01-01T00:00:00Z").cache_identity()
    assert a != b


def test_cache_identity_distinguishes_kinds() -> None:
    a = _ref(kind=ArtifactKind.PDF).cache_identity()
    b = _ref(kind=ArtifactKind.IMAGE).cache_identity()
    assert a != b
    assert a["kind"] == "pdf"
    assert b["kind"] == "image"
