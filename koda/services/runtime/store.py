"""Runtime persistence with a Postgres-only primary path."""

from __future__ import annotations

from typing import Any

from koda.services.runtime.postgres_store import PostgresRuntimeStore
from koda.state_primary import get_primary_state_backend, postgres_primary_mode


class RuntimeStore:
    """Public runtime store entrypoint backed by the primary Postgres implementation."""

    def __init__(self) -> None:
        if not postgres_primary_mode():
            raise RuntimeError("runtime_primary_mode_required")
        if get_primary_state_backend() is None:
            raise RuntimeError("runtime_primary_backend_unavailable")
        self._impl = PostgresRuntimeStore()

    def __getattr__(self, name: str) -> Any:
        return getattr(self._impl, name)
