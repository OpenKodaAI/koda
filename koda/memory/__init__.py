"""Vector memory system for persistent cross-session memory."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from koda.memory.manager import MemoryManager

_manager: MemoryManager | None = None


def get_memory_manager() -> MemoryManager:
    """Get or create the singleton MemoryManager."""
    global _manager
    if _manager is None:
        from koda.config import AGENT_ID
        from koda.memory.manager import MemoryManager

        _manager = MemoryManager(AGENT_ID)
    return _manager


__all__ = ["MemoryManager", "get_memory_manager"]
