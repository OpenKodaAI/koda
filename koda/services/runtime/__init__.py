"""Observable isolated runtime control plane."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .controller import RuntimeController, get_runtime_controller

__all__ = ["RuntimeController", "get_runtime_controller"]


def __getattr__(name: str) -> Any:
    if name in {"RuntimeController", "get_runtime_controller"}:
        from .controller import RuntimeController, get_runtime_controller

        return {
            "RuntimeController": RuntimeController,
            "get_runtime_controller": get_runtime_controller,
        }[name]
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
