"""Tests for whisper_manager: GGML model download, catalog, idempotency."""

from __future__ import annotations

import io
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest


@pytest.fixture
def whisper_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Isolated whisper models directory for each test."""
    models_dir = tmp_path / "whisper-models"
    monkeypatch.setattr("koda.services.whisper_manager.WHISPER_ASSET_ROOT", str(models_dir))
    monkeypatch.setattr("koda.services.whisper_manager.WHISPER_MODEL", str(models_dir / "ggml-large-v3-turbo-q5_0.bin"))
    return models_dir


def _fake_response(body: bytes, content_length: int | None = None) -> Any:
    """Mimic urllib.request.urlopen's context-manager response."""

    class _Resp:
        def __init__(self) -> None:
            self.headers = {"Content-Length": str(content_length if content_length is not None else len(body))}
            self._stream = io.BytesIO(body)

        def __enter__(self) -> _Resp:
            return self

        def __exit__(self, *_: object) -> None:
            return None

        def read(self, n: int = -1) -> bytes:
            return self._stream.read(n)

    return _Resp()


def _patched_urlopen(monkeypatch: pytest.MonkeyPatch, body: bytes) -> list[str]:
    """Patch urllib.request.urlopen and capture the URL each call hits."""
    captured: list[str] = []

    def _fake_urlopen(request: Any, timeout: int = 60) -> Any:
        url = request.full_url if hasattr(request, "full_url") else str(request)
        captured.append(url)
        return _fake_response(body)

    monkeypatch.setattr("urllib.request.urlopen", _fake_urlopen)
    return captured


def test_whisper_catalog_lists_known_variants_with_download_state(whisper_dir: Path) -> None:
    from koda.services import whisper_manager

    catalog = whisper_manager.whisper_catalog_payload()
    variant_ids = {item["variant_id"] for item in catalog["items"]}
    assert "large-v3-turbo-q5_0" in variant_ids
    assert catalog["default_variant"] == "large-v3-turbo-q5_0"
    assert all(item["downloaded"] is False for item in catalog["items"])
    assert catalog["models_dir"] == str(whisper_dir)


def test_ensure_whisper_model_downloads_and_writes_atomically(
    whisper_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from koda.services import whisper_manager

    body = b"x" * (3 * 1024 * 1024)  # 3 MiB → exercises the chunk loop
    urls = _patched_urlopen(monkeypatch, body)
    progress: list[tuple[int, int]] = []

    result = whisper_manager.ensure_whisper_model_downloaded(
        "large-v3-turbo-q5_0",
        progress_callback=lambda d, t: progress.append((d, t)),
    )

    assert urls == [whisper_manager.KNOWN_WHISPER_VARIANTS["large-v3-turbo-q5_0"]["url"]]
    target = whisper_dir / "ggml-large-v3-turbo-q5_0.bin"
    assert target.exists()
    assert target.stat().st_size == len(body)
    assert result["bytes"] == len(body)
    assert result["downloaded"] is True
    # Progress must be monotonic and end exactly at total.
    assert progress[-1] == (len(body), len(body))
    assert all(progress[i][0] <= progress[i + 1][0] for i in range(len(progress) - 1))


def test_ensure_whisper_short_circuits_when_already_downloaded(
    whisper_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from koda.services import whisper_manager

    target = whisper_dir / "ggml-large-v3-turbo-q5_0.bin"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(b"already-here")

    def _should_not_be_called(*_: object, **__: object) -> Any:
        raise AssertionError("urlopen must not be called when the file is already on disk")

    monkeypatch.setattr("urllib.request.urlopen", _should_not_be_called)
    progress: list[tuple[int, int]] = []
    result = whisper_manager.ensure_whisper_model_downloaded(
        "large-v3-turbo-q5_0",
        progress_callback=lambda d, t: progress.append((d, t)),
    )
    assert result["downloaded"] is True
    assert result["bytes"] == len(b"already-here")
    # Progress should still fire once so the toast immediately shows 100%.
    assert progress == [(len(b"already-here"), len(b"already-here"))]


def test_ensure_whisper_unknown_variant_raises(whisper_dir: Path) -> None:
    from koda.services import whisper_manager

    with pytest.raises(KeyError, match="unknown whisper variant"):
        whisper_manager.ensure_whisper_model_downloaded("definitely-not-a-real-variant")


def test_ensure_whisper_failed_download_cleans_up_tmp(whisper_dir: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from koda.services import whisper_manager

    class _BrokenStream:
        def __init__(self) -> None:
            self.headers = {"Content-Length": "1024"}
            self._chunks: Iterator[bytes] = iter([b"x" * 256, b"x" * 256])
            self._yielded = False

        def __enter__(self) -> _BrokenStream:
            return self

        def __exit__(self, *_: object) -> None:
            return None

        def read(self, _n: int = -1) -> bytes:
            try:
                return next(self._chunks)
            except StopIteration:
                # Simulate a connection drop in the middle of the stream.
                raise ConnectionError("network dropped mid-stream") from None

    monkeypatch.setattr("urllib.request.urlopen", lambda *_a, **_kw: _BrokenStream())

    with pytest.raises(ConnectionError):
        whisper_manager.ensure_whisper_model_downloaded("large-v3-turbo-q5_0")

    target = whisper_dir / "ggml-large-v3-turbo-q5_0.bin"
    tmp = target.with_suffix(target.suffix + ".tmp")
    assert not target.exists(), "target must NOT be created when the download fails"
    assert not tmp.exists(), ".tmp must be cleaned up on failure"


def test_downloaded_whisper_variants_reflects_disk_state(
    whisper_dir: Path,
) -> None:
    from koda.services import whisper_manager

    assert whisper_manager.downloaded_whisper_variants() == set()

    whisper_dir.mkdir(parents=True, exist_ok=True)
    (whisper_dir / "ggml-large-v3-turbo-q5_0.bin").write_bytes(b"abc")
    assert whisper_manager.downloaded_whisper_variants() == {"large-v3-turbo-q5_0"}

    # Empty file does NOT count as downloaded.
    (whisper_dir / "ggml-medium-q5_0.bin").write_bytes(b"")
    assert "medium-q5_0" not in whisper_manager.downloaded_whisper_variants()


def test_delete_whisper_model_removes_file_and_reports_size(whisper_dir: Path) -> None:
    from koda.services import whisper_manager

    whisper_dir.mkdir(parents=True, exist_ok=True)
    target = whisper_dir / "ggml-large-v3-turbo-q5_0.bin"
    target.write_bytes(b"x" * 1024)

    result = whisper_manager.delete_whisper_model("large-v3-turbo-q5_0")

    assert result["removed"] is True
    assert result["bytes_freed"] == 1024
    assert not target.exists()
    # Idempotent: a second delete reports `removed=False` but does not raise.
    second = whisper_manager.delete_whisper_model("large-v3-turbo-q5_0")
    assert second["removed"] is False
    assert second["bytes_freed"] == 0


def test_delete_whisper_unknown_variant_raises(whisper_dir: Path) -> None:
    from koda.services import whisper_manager

    with pytest.raises(KeyError, match="unknown whisper variant"):
        whisper_manager.delete_whisper_model("definitely-not-a-real-variant")


def test_whisper_default_variant_tracks_configured_filename(whisper_dir: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from koda.services import whisper_manager

    monkeypatch.setattr(
        "koda.services.whisper_manager.WHISPER_MODEL",
        str(whisper_dir / "ggml-medium-q5_0.bin"),
    )
    assert whisper_manager.whisper_default_variant_id() == "medium-q5_0"

    # Falls back to the catalog default when the configured filename is unknown.
    monkeypatch.setattr(
        "koda.services.whisper_manager.WHISPER_MODEL",
        str(whisper_dir / "ggml-totally-unknown.bin"),
    )
    assert whisper_manager.whisper_default_variant_id() == whisper_manager.WHISPER_DEFAULT_VARIANT
