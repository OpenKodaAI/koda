"""MySQL read-only manager for agent tools."""

from __future__ import annotations

import re
from typing import Any
from urllib.parse import urlparse

from koda.logging_config import get_logger

log = get_logger(__name__)

_WRITE_RE = re.compile(
    r"\b(INSERT|UPDATE|DELETE|DROP|ALTER|CREATE|TRUNCATE|GRANT|REVOKE)\b",
    re.IGNORECASE,
)
_ALLOWED_RE = re.compile(
    r"^\s*(SELECT|SHOW|DESCRIBE|EXPLAIN)\b",
    re.IGNORECASE,
)
_COMMENT_RE = re.compile(r"(--|/\*)")
_MULTI_STMT_RE = re.compile(r";\s*\S")


def _validate_query(sql: str) -> str:
    """Validate SQL is read-only. Returns error message or empty string if valid."""
    stripped = sql.strip()
    if not stripped:
        return "Empty SQL."
    if _COMMENT_RE.search(stripped):
        return "SQL comments are not allowed."
    if _MULTI_STMT_RE.search(stripped):
        return "Multi-statement execution is not allowed."
    if _WRITE_RE.search(stripped):
        return "Write operations are not allowed. Only SELECT, SHOW, DESCRIBE, EXPLAIN."
    if not _ALLOWED_RE.match(stripped):
        return "Only SELECT, SHOW, DESCRIBE, EXPLAIN queries are allowed."
    return ""


class MySQLManager:
    """Async MySQL manager with per-environment connection pools and read-only enforcement."""

    def __init__(self) -> None:
        self._pools: dict[str, Any] = {}
        self._available = False

    async def start(self) -> None:
        """Check if aiomysql is installed and mark availability."""
        try:
            import aiomysql  # noqa: F401

            self._available = True
        except ImportError:
            log.warning("aiomysql_not_installed")
            self._available = False

    async def stop(self) -> None:
        """Close all connection pools."""
        for pool in self._pools.values():
            pool.close()
            await pool.wait_closed()
        self._pools.clear()

    @property
    def is_available(self) -> bool:
        return self._available

    async def _get_pool(self, env: str | None = None) -> Any:
        import aiomysql

        from koda.config import _env

        env = env or "default"
        if env in self._pools:
            return self._pools[env]

        suffix = f"_{env.upper()}" if env != "default" else ""
        url = _env(f"MYSQL_URL{suffix}", _env("MYSQL_URL", ""))
        if not url:
            raise ValueError(f"MYSQL_URL{suffix} not configured.")

        parsed = urlparse(url)
        pool = await aiomysql.create_pool(
            host=parsed.hostname or "localhost",
            port=parsed.port or 3306,
            user=parsed.username or "root",
            password=parsed.password or "",
            db=parsed.path.lstrip("/") if parsed.path else "",
            minsize=1,
            maxsize=5,
            autocommit=True,
        )
        self._pools[env] = pool
        return pool

    async def query(
        self,
        sql: str,
        env: str | None = None,
        max_rows: int = 100,
        timeout: int = 30,
    ) -> str:
        """Execute a read-only query and return formatted results."""
        err = _validate_query(sql)
        if err:
            return f"Error: {err}"
        try:
            pool = await self._get_pool(env)
            async with pool.acquire() as conn, conn.cursor() as cur:
                await cur.execute(sql)
                if cur.description:
                    columns = [d[0] for d in cur.description]
                    rows = await cur.fetchmany(max_rows)
                    header = " | ".join(columns)
                    sep = "-" * len(header)
                    lines = [header, sep]
                    for row in rows:
                        lines.append(" | ".join(str(v) for v in row))
                    total = cur.rowcount if cur.rowcount >= 0 else len(rows)
                    lines.append(f"\n({total} rows, showing {len(rows)})")
                    return "\n".join(lines)
                return f"Query executed. Rows affected: {cur.rowcount}"
        except Exception as e:
            return f"Error: {e}"

    async def get_schema(self, table: str | None = None, env: str | None = None) -> str:
        """List tables or show columns for a specific table."""
        try:
            pool = await self._get_pool(env)
            async with pool.acquire() as conn, conn.cursor() as cur:
                if table:
                    await cur.execute(f"DESCRIBE `{table}`")
                    rows = await cur.fetchall()
                    lines = [f"Table: {table}"]
                    for row in rows:
                        nullable = "NOT NULL" if row[2] == "NO" else "NULL"
                        default = f" DEFAULT {row[4]}" if row[4] else ""
                        lines.append(f"  {row[0]}: {row[1]} {nullable}{default}")
                    return "\n".join(lines)
                else:
                    await cur.execute("SHOW TABLES")
                    tables = [row[0] for row in await cur.fetchall()]
                    return f"Tables ({len(tables)}):\n" + "\n".join(f"  {t}" for t in tables)
        except Exception as e:
            return f"Error: {e}"


_manager: MySQLManager | None = None


def get_mysql_manager() -> MySQLManager:
    """Return the singleton MySQLManager instance."""
    global _manager  # noqa: PLW0603
    if _manager is None:
        _manager = MySQLManager()
    return _manager
