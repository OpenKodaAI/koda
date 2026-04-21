"""Observability stubs for image/video/music generation.

The Models section of the dashboard lets the operator pick a default
provider+model for six functional slots: ``general``, ``image``, ``video``,
``audio``, ``transcription`` and ``music``. The first three (``general``,
``audio``, ``transcription``) flow into real runtime behavior through
``koda.config``. The remaining three (``image``, ``video``, ``music``) had
no runtime consumer — the operator could configure them but nothing read
the choice back.

This module closes that observability gap without shipping provider
integrations. It exposes:

* ``resolve_{image,video,music}_generation_default()`` — returns the
  operator's configured selection (or ``None`` when unset), backed by the
  public ``koda.config.resolve_functional_default`` API. Anything that wants
  to adopt these defaults later (e.g. a future image-generation service)
  pulls from here.
* ``invoke_{image,video,music}_generation()`` — explicitly raises
  :class:`GenerationServiceNotImplemented` with a structured message. The
  error surfaces the configured selection so the UI / logs can report
  accurately: *"configurado como openai/gpt-image-1 mas geração não
  implementada"*. This replaces the previous silent absence with a
  fail-closed contract that future implementations can satisfy.

Keeping the configuration wired to observable surface area makes the UI
choice meaningful today (operators can confirm their selection persists
and resolves) and gives future implementations a single source of truth.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from koda.config import resolve_functional_default

FunctionalSlot = Literal["image", "video", "music"]


@dataclass(frozen=True, slots=True)
class FunctionalDefaultSelection:
    """Operator-selected default provider+model for a functional slot."""

    provider_id: str
    model_id: str

    @property
    def present(self) -> bool:
        return bool(self.provider_id) and bool(self.model_id)


class GenerationServiceNotImplemented(NotImplementedError):
    """Raised when a stub service is invoked before its real runtime exists.

    The message includes the operator's configured selection (if any) to aid
    debugging: the operator can confirm the configuration reached the runtime
    even though execution is not wired yet.
    """

    def __init__(self, slot: FunctionalSlot, selection: FunctionalDefaultSelection) -> None:
        self.slot = slot
        self.selection = selection
        if selection.present:
            detail = (
                f"Geração de {slot} configurada como "
                f"{selection.provider_id}/{selection.model_id} — runtime ainda não implementado."
            )
        else:
            detail = (
                f"Geração de {slot} não implementada e sem provider padrão configurado. "
                "Defina um default em /control-plane/system/models."
            )
        super().__init__(detail)


def _resolve(slot: FunctionalSlot) -> FunctionalDefaultSelection | None:
    provider, model = resolve_functional_default(slot)
    if not provider or not model:
        return None
    return FunctionalDefaultSelection(provider_id=provider, model_id=model)


def resolve_image_generation_default() -> FunctionalDefaultSelection | None:
    """Return the image-generation default selection, or ``None`` when unset."""
    return _resolve("image")


def resolve_video_generation_default() -> FunctionalDefaultSelection | None:
    """Return the video-generation default selection, or ``None`` when unset."""
    return _resolve("video")


def resolve_music_generation_default() -> FunctionalDefaultSelection | None:
    """Return the music-generation default selection, or ``None`` when unset."""
    return _resolve("music")


def _invoke(slot: FunctionalSlot) -> None:
    selection = _resolve(slot) or FunctionalDefaultSelection(provider_id="", model_id="")
    raise GenerationServiceNotImplemented(slot, selection)


def invoke_image_generation(_prompt: str) -> None:
    """Stub entry point for image generation. Always raises."""
    _invoke("image")


def invoke_video_generation(_prompt: str) -> None:
    """Stub entry point for video generation. Always raises."""
    _invoke("video")


def invoke_music_generation(_prompt: str) -> None:
    """Stub entry point for music generation. Always raises."""
    _invoke("music")
