"""SQLite read-only manager for agent tools."""

from __future__ import annotations

import os
import re

from koda.logging_config import get_logger

log = get_logger(__name__)

# ---------------------------------------------------------------------------
# Query validation
# ---------------------------------------------------------------------------

_WRITE_RE = re.compile(
    r"\b(INSERT|UPDATE|DELETE|DROP|ALTER|CREATE|TRUNCATE)\b",
    re.IGNORECASE,
)
_ALLOWED_RE = re.compile(r"^\s*(SELECT|PRAGMA)\b", re.IGNORECASE)
_COMMENT_RE = re.compile(r"(--|/\*)")
_MULTI_STMT_RE = re.compile(r";\s*\S")
_BACKSLASH_RE = re.compile(r"\\")


def _validate_query(sql: str) -> str:
    """Validate SQL is read-only. Returns error message or empty string if valid."""
    stripped = sql.strip()
    if not stripped:
        return "Empty SQL."
    if _BACKSLASH_RE.search(stripped):
        return "Backslash meta-commands are not allowed."
    if _COMMENT_RE.search(stripped):
        return "SQL comments not allowed."
    if _MULTI_STMT_RE.search(stripped):
        return "Multi-statement queries are not allowed."
    if _WRITE_RE.search(stripped):
        return "Write operations not allowed. Only SELECT, PRAGMA."
    if not _ALLOWED_RE.match(stripped):
        return "Only SELECT and PRAGMA queries allowed."
    return ""


def _validate_db_path(db_path: str) -> str | None:
    """Validate the database file path. Returns error message or None if valid."""
    from koda.config import SQLITE_ALLOWED_PATHS

    if not db_path:
        return "Missing db_path."
    resolved = os.path.realpath(os.path.expanduser(db_path))
    if not os.path.isfile(resolved):
        return f"Database file not found: {db_path}"
    if SQLITE_ALLOWED_PATHS:
        for allowed in SQLITE_ALLOWED_PATHS:
            if resolved.startswith(os.path.realpath(allowed)):
                return None
        return "Path not in allowed paths."
    return None


# ---------------------------------------------------------------------------
# Manager
# ---------------------------------------------------------------------------


class SQLiteManager:
    """Async SQLite manager with read-only enforcement and path sandboxing."""

    def __init__(self) -> None:
        self._available: bool = False

    async def start(self) -> None:
        """Check whether aiosqlite is importable."""
        try:
            import aiosqlite  # noqa: F401

            self._available = True
            log.info("sqlite_manager_available")
        except ImportError:
            self._available = False
            log.warning("sqlite_manager_unavailable", msg="aiosqlite not installed")

    async def stop(self) -> None:
        """No persistent resources to release."""

    @property
    def is_available(self) -> bool:
        return self._available

    async def query(self, sql: str, db_path: str, max_rows: int = 100) -> str:
        """Execute a read-only query against a SQLite file and return formatted results."""
        err = _validate_query(sql)
        if err:
            return f"Error: {err}"
        path_err = _validate_db_path(db_path)
        if path_err:
            return f"Error: {path_err}"
        try:
            import aiosqlite

            resolved = os.path.realpath(os.path.expanduser(db_path))
            async with aiosqlite.connect(resolved, uri=False) as db:
                db.row_factory = None  # type: ignore[assignment]
                cursor = await db.execute(sql)
                if cursor.description:
                    columns = [d[0] for d in cursor.description]
                    rows = await cursor.fetchmany(max_rows)
                    header = " | ".join(columns)
                    lines = [header, "-" * len(header)]
                    for row in rows:
                        lines.append(" | ".join(str(v) for v in row))
                    lines.append(f"\n({len(rows)} rows)")
                    return "\n".join(lines)
                return "Query executed."
        except Exception as e:
            return f"Error: {e}"

    async def get_schema(self, db_path: str, table: str | None = None) -> str:
        """List tables or show columns for a specific table."""
        path_err = _validate_db_path(db_path)
        if path_err:
            return f"Error: {path_err}"
        try:
            import aiosqlite

            resolved = os.path.realpath(os.path.expanduser(db_path))
            async with aiosqlite.connect(resolved) as db:
                if table:
                    cursor = await db.execute(f"PRAGMA table_info('{table}')")
                    rows = await cursor.fetchall()
                    if not rows:
                        return f"Table '{table}' not found or has no columns."
                    lines = [f"Table: {table}"]
                    for row in rows:
                        nullable = "NULL" if not row[3] else "NOT NULL"
                        default = f" DEFAULT {row[4]}" if row[4] else ""
                        lines.append(f"  {row[1]}: {row[2]} {nullable}{default}")
                    return "\n".join(lines)
                else:
                    cursor = await db.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
                    tables = [row[0] for row in await cursor.fetchall()]
                    return f"Tables ({len(tables)}):\n" + "\n".join(f"  {t}" for t in tables)
        except Exception as e:
            return f"Error: {e}"


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------

_manager: SQLiteManager | None = None


def get_sqlite_manager() -> SQLiteManager:
    """Return the module-level SQLiteManager singleton."""
    global _manager  # noqa: PLW0603
    if _manager is None:
        _manager = SQLiteManager()
    return _manager
