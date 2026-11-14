"""Every Koda call site that decodes user-supplied images, run on real image files.

The call sites (M1-E7-T2 batch P3; docs/engineering/SUPPLY_CHAIN_TRIAGE.md §3.1):

- ``save_operator_profile_photo`` (koda/control_plane/operator_profile_photos.py)
- ``save_room_photo`` (koda/squads/room_photos.py)
- ``_extract_image`` and its OCR backend (koda/services/artifact_ingestion.py),
  which Telegram photos and image documents reach

Each fixture is encoded by Pillow in the named container format, so the decoder
Koda runs in production parses real bytes (EXIF orientation, alpha, palettes,
animation, truncation), not a mock.
"""

from __future__ import annotations

import importlib.util
import io
from collections.abc import Callable
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest
from PIL import Image, ImageDraw, ImageFont

from koda.control_plane import operator_profile_photos
from koda.services import artifact_ingestion
from koda.services.artifact_ingestion import ArtifactKind, ArtifactRef, ArtifactStatus, extract_artifact
from koda.squads import room_photos

RED = (220, 30, 30)
BLUE = (30, 30, 220)
_ORIENTATION_TAG = 0x0112
_MAKE_TAG = 0x010F


def _split(size: tuple[int, int] = (80, 40)) -> Image.Image:
    """An image whose left half is red and right half is blue."""
    image = Image.new("RGB", size, BLUE)
    image.paste(RED, (0, 0, size[0] // 2, size[1]))
    return image


def _encode(image: Image.Image, fmt: str, **params: Any) -> bytes:
    buffer = io.BytesIO()
    image.save(buffer, format=fmt, **params)
    return buffer.getvalue()


def _animated_gif() -> bytes:
    frames = [_split().convert("P", palette=Image.Palette.ADAPTIVE, colors=4), Image.new("P", (80, 40), 0)]
    return _encode(frames[0], "GIF", save_all=True, append_images=frames[1:], duration=100, loop=0)


def _jpeg_with_exif(orientation: int) -> bytes:
    exif = Image.Exif()
    exif[_ORIENTATION_TAG] = orientation
    exif[_MAKE_TAG] = "KodaCam"
    return _encode(_split(), "JPEG", exif=exif, quality=95)


# format -> encoded 80x40 split image
FORMATS: dict[str, Callable[[], bytes]] = {
    "jpeg": lambda: _encode(_split(), "JPEG", quality=95),
    "jpeg_progressive": lambda: _encode(_split(), "JPEG", quality=95, progressive=True),
    "png_rgb": lambda: _encode(_split(), "PNG"),
    "png_rgba": lambda: _encode(_split().convert("RGBA"), "PNG"),
    "png_palette": lambda: _encode(_split().convert("P", palette=Image.Palette.ADAPTIVE, colors=4), "PNG"),
    "webp_lossless": lambda: _encode(_split(), "WEBP", lossless=True),
    "gif_animated": _animated_gif,
    "bmp": lambda: _encode(_split(), "BMP"),
    "tiff": lambda: _encode(_split(), "TIFF"),
}


def _close(pixel: tuple[int, ...], colour: tuple[int, int, int], tolerance: int = 40) -> bool:
    return all(abs(int(a) - b) <= tolerance for a, b in zip(pixel[:3], colour, strict=True))


# saver name -> (module whose STATE_ROOT_DIR to redirect, save function, decode error)
SAVERS: dict[str, tuple[Any, Callable[[bytes], Any], type[Exception], type[Exception]]] = {
    "operator_profile_photo": (
        operator_profile_photos,
        lambda raw: operator_profile_photos.save_operator_profile_photo("usr_test", raw),
        operator_profile_photos.InvalidProfilePhotoError,
        operator_profile_photos.ProfilePhotoTooLargeError,
    ),
    "room_photo": (
        room_photos,
        lambda raw: room_photos.save_room_photo("thread_test", raw),
        room_photos.InvalidPhotoError,
        room_photos.PhotoTooLargeError,
    ),
}


@pytest.fixture(params=sorted(SAVERS))
def saver(request: pytest.FixtureRequest, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    module, save, decode_error, too_large_error = SAVERS[request.param]
    monkeypatch.setattr(module, "STATE_ROOT_DIR", tmp_path)
    return save, decode_error, too_large_error, module


@pytest.mark.parametrize("fmt", sorted(FORMATS))
def test_photo_savers_store_every_format_as_a_square_rgb_jpeg(saver, fmt: str) -> None:
    save, _decode_error, _too_large, _module = saver

    stored = save(FORMATS[fmt]())

    with Image.open(stored.path) as out:
        assert out.format == "JPEG"
        assert out.mode == "RGB"
        assert out.size == (40, 40)
        assert _close(out.getpixel((5, 20)), RED), out.getpixel((5, 20))
        assert _close(out.getpixel((34, 20)), BLUE), out.getpixel((34, 20))
    assert stored.byte_size == stored.path.stat().st_size


# EXIF orientation -> (pixel, expected colour) after Koda auto-orients the 80x40 split image
_ORIENTED = {
    1: [((5, 20), RED), ((34, 20), BLUE)],
    3: [((5, 20), BLUE), ((34, 20), RED)],  # rotated 180 degrees
    6: [((20, 5), RED), ((20, 34), BLUE)],  # rotated 90 degrees clockwise: left edge on top
    8: [((20, 5), BLUE), ((20, 34), RED)],  # rotated 90 degrees counter-clockwise
}


@pytest.mark.parametrize("orientation", sorted(_ORIENTED))
def test_photo_savers_apply_exif_orientation_and_strip_metadata(saver, orientation: int) -> None:
    save, _decode_error, _too_large, _module = saver

    stored = save(_jpeg_with_exif(orientation))

    with Image.open(stored.path) as out:
        assert out.size == (40, 40)
        for point, colour in _ORIENTED[orientation]:
            assert _close(out.getpixel(point), colour), (point, out.getpixel(point))
        assert dict(out.getexif()) == {}
        assert "exif" not in out.info


def test_photo_savers_downscale_large_images_to_the_maximum_dimension(saver) -> None:
    save, _decode_error, _too_large, module = saver

    stored = save(_encode(_split((1200, 900)), "JPEG", quality=90))

    with Image.open(stored.path) as out:
        assert out.size == (module.MAX_DIMENSION, module.MAX_DIMENSION)
        assert _close(out.getpixel((10, 256)), RED)
        assert _close(out.getpixel((500, 256)), BLUE)


@pytest.mark.parametrize(
    "payload",
    [
        pytest.param(b"definitely not an image", id="not_an_image"),
        pytest.param(FORMATS["jpeg"]()[:300], id="truncated_jpeg"),
        pytest.param(FORMATS["png_rgb"]()[:60], id="truncated_png"),
        pytest.param(b"\x89PNG\r\n\x1a\n" + b"\x00" * 64, id="png_signature_only"),
    ],
)
def test_photo_savers_reject_undecodable_payloads(saver, payload: bytes) -> None:
    save, decode_error, _too_large, _module = saver

    with pytest.raises(decode_error):
        save(payload)


def test_photo_savers_reject_payloads_over_the_size_cap(saver) -> None:
    save, _decode_error, too_large_error, module = saver

    with pytest.raises(too_large_error):
        save(b"x" * (module.MAX_INPUT_BYTES + 1))


@pytest.fixture
def artifact_cache_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    cache_dir = tmp_path / "artifact_cache"
    monkeypatch.setattr("koda.services.artifact_ingestion.ARTIFACT_CACHE_DIR", cache_dir)
    return cache_dir


def _image_ref(path: Path) -> ArtifactRef:
    return ArtifactRef(
        artifact_id=f"artifact-{path.stem}",
        kind=ArtifactKind.IMAGE,
        label=path.name,
        source_type="test",
        mime_type="image/*",
        path=str(path),
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("fmt", sorted(FORMATS))
async def test_extract_image_reads_dimensions_of_every_format(tmp_path, artifact_cache_dir, fmt: str) -> None:
    path = tmp_path / f"upload-{fmt}.img"
    path.write_bytes(FORMATS[fmt]())

    with patch("koda.services.artifact_ingestion._ocr_image_path", return_value=""):
        extracted = await extract_artifact(_image_ref(path))

    assert extracted.status == ArtifactStatus.COMPLETE
    assert extracted.metadata["dimensions"] == {"width": 80, "height": 40}
    assert extracted.summary.startswith(f"Image {path.name} (80x40).")
    assert extracted.visual_paths == [str(path)]


@pytest.mark.asyncio
async def test_extract_image_keeps_an_undecodable_file_for_visual_inspection(tmp_path, artifact_cache_dir) -> None:
    path = tmp_path / "broken.png"
    path.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 64)

    extracted = await extract_artifact(_image_ref(path))

    assert extracted.status == ArtifactStatus.COMPLETE
    assert extracted.visual_paths == [str(path)]
    assert any(warning.startswith("image metadata unavailable") for warning in extracted.warnings)
    assert "dimensions" not in extracted.metadata


# --- OCR backend (rapidocr-onnxruntime, Python < 3.13) on Pillow-decoded input ---

_HAS_OCR = importlib.util.find_spec("rapidocr_onnxruntime") is not None
_ocr = pytest.mark.skipif(not _HAS_OCR, reason="rapidocr-onnxruntime is only installed on Python < 3.13")


def _text_image(mode: str) -> Image.Image:
    image = Image.new("RGB", (640, 160), "white")
    ImageDraw.Draw(image).text((24, 36), "KODA 2026", fill="black", font=ImageFont.load_default(size=72))
    return image.convert(mode)


# Every branch of rapidocr's loader: bilevel ("1" is converted to L), greyscale, RGB and RGBA.
_OCR_INPUTS = {
    "png_rgb": lambda: _encode(_text_image("RGB"), "PNG"),
    "jpeg": lambda: _encode(_text_image("RGB"), "JPEG", quality=92),
    "png_rgba": lambda: _encode(_text_image("RGBA"), "PNG"),
    "png_greyscale": lambda: _encode(_text_image("L"), "PNG"),
    "png_bilevel": lambda: _encode(_text_image("1"), "PNG"),
    "webp": lambda: _encode(_text_image("RGB"), "WEBP", lossless=True),
}


@_ocr
@pytest.mark.parametrize("fmt", sorted(_OCR_INPUTS))
def test_ocr_backend_reads_text_from_pillow_decoded_images(fmt: str) -> None:
    text = artifact_ingestion._ocr_image_bytes(_OCR_INPUTS[fmt]())

    assert "KODA" in text.upper().replace(" ", ""), text
    assert "2026" in text, text


@_ocr
@pytest.mark.asyncio
async def test_extract_image_runs_real_ocr_end_to_end(tmp_path, artifact_cache_dir) -> None:
    path = tmp_path / "screenshot.png"
    path.write_bytes(_OCR_INPUTS["png_rgb"]())

    extracted = await extract_artifact(_image_ref(path))

    assert extracted.status == ArtifactStatus.COMPLETE
    assert "OCR text was extracted" in extracted.summary
    assert "KODA" in extracted.text_content.upper().replace(" ", "")
    assert extracted.metadata["dimensions"] == {"width": 640, "height": 160}
