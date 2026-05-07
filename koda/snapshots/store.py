"""Snapshot persistence."""

from __future__ import annotations

import json
import os
import re
import time
from typing import Any

from koda.logging_config import get_logger

log = get_logger(__name__)

_NAME_RE = re.compile(r"^[a-zA-Z0-9_-]{1,64}$")


class SnapshotStore:
    def __init__(self) -> None:
        self._base_dir: str = ""

    def _get_dir(self, scope_id: int) -> str:
        from koda.config import IMAGE_TEMP_DIR

        base = self._base_dir or str(IMAGE_TEMP_DIR)
        d = os.path.join(base, "snapshots", str(scope_id))
        os.makedirs(d, mode=0o700, exist_ok=True)
        return d

    async def save(self, scope_id: int, name: str, snapshot_data: dict[str, Any]) -> str | None:
        """Save snapshot to disk. Returns error or None."""
        if not _NAME_RE.match(name):
            return "Invalid name. Use alphanumeric, hyphens, underscores (1-64 chars)."
        d = self._get_dir(scope_id)
        path = os.path.join(d, f"{name}.json")
        try:
            with open(path, "w") as f:
                json.dump(snapshot_data, f, default=str, indent=2)
            os.chmod(path, 0o600)
            log.info("snapshot_saved", name=name, scope_id=scope_id)
            return None
        except Exception as e:
            return f"Error saving snapshot: {e}"

    def load(self, scope_id: int, name: str) -> dict[str, Any] | str:
        """Load snapshot from disk. Returns data dict or error string."""
        if not _NAME_RE.match(name):
            return "Invalid snapshot name."
        d = self._get_dir(scope_id)
        path = os.path.join(d, f"{name}.json")
        if not os.path.isfile(path):
            return f"Snapshot '{name}' not found."
        try:
            with open(path) as f:
                data: dict[str, Any] = json.load(f)
                return data
        except Exception as e:
            return f"Error loading snapshot: {e}"

    def list_snapshots(self, scope_id: int) -> list[dict[str, Any]]:
        """List saved snapshots."""
        d = self._get_dir(scope_id)
        results = []
        for fname in sorted(os.listdir(d)):
            if not fname.endswith(".json"):
                continue
            name = fname[:-5]
            path = os.path.join(d, fname)
            stat = os.stat(path)
            results.append(
                {
                    "name": name,
                    "size": stat.st_size,
                    "modified": stat.st_mtime,
                    "age_hours": round((time.time() - stat.st_mtime) / 3600, 1),
                }
            )
        return results

    def delete(self, scope_id: int, name: str) -> str | None:
        """Delete a snapshot. Returns error or None."""
        if not _NAME_RE.match(name):
            return "Invalid name."
        d = self._get_dir(scope_id)
        path = os.path.join(d, f"{name}.json")
        if not os.path.isfile(path):
            return f"Snapshot '{name}' not found."
        os.remove(path)
        return None

    def diff(self, scope_id: int, name_a: str, name_b: str) -> dict[str, Any] | str:
        """Compare two snapshots. Returns diff dict or error."""
        a = self.load(scope_id, name_a)
        if isinstance(a, str):
            return a
        b = self.load(scope_id, name_b)
        if isinstance(b, str):
            return b

        diff_result: dict[str, Any] = {"from": name_a, "to": name_b, "changes": {}}
        a_subs = a.get("subsystems", {})
        b_subs = b.get("subsystems", {})
        all_keys = set(a_subs) | set(b_subs)
        for key in sorted(all_keys):
            if key not in a_subs:
                diff_result["changes"][key] = {"status": "added"}
            elif key not in b_subs:
                diff_result["changes"][key] = {"status": "removed"}
            elif a_subs[key] != b_subs[key]:
                diff_result["changes"][key] = {"status": "changed"}
            # unchanged: skip
        return diff_result


_store: SnapshotStore | None = None


def get_snapshot_store() -> SnapshotStore:
    global _store
    if _store is None:
        _store = SnapshotStore()
    return _store
