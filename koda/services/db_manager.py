"""PostgreSQL database manager with read-only query support and multi-environment pools."""

from __future__ import annotations

import re
import ssl
import time
from dataclasses import dataclass
from inspect import isawaitable
from typing import TYPE_CHECKING, Any
from urllib.parse import urlparse, urlunparse

from koda.logging_config import get_logger

if TYPE_CHECKING:
    from koda.config import PostgresEnvConfig

log = get_logger(__name__)
_SSH_TUNNEL_LOCAL_HOST = "127.0.0.1"

# Statements that are allowed as the leading keyword
_ALLOWED_LEADING = re.compile(
    r"^\s*(SELECT|WITH|SHOW|EXPLAIN)\b",
    re.IGNORECASE,
)

# Dangerous keywords that must never appear
_BLOCKED_KEYWORDS = re.compile(
    r"\b(INSERT|UPDATE|DELETE|DROP|ALTER|CREATE|TRUNCATE|GRANT|REVOKE|COPY)\b",
    re.IGNORECASE,
)

# Block SQL comments (anti-injection)
_COMMENT_RE = re.compile(r"(--|/\*)")

# Block multi-statement: semicolon followed by more SQL
_MULTI_STMT_RE = re.compile(r";\s*\S")

# Block backslash meta-commands (psql)
_BACKSLASH_RE = re.compile(r"\\")


@dataclass
class _EnvPool:
    pool: Any = None
    ssh_conn: Any = None
    ssh_listener: Any = None


async def _maybe_await_close(target: Any) -> None:
    close = getattr(target, "close", None)
    if close is None:
        return
    result = close()
    if isawaitable(result):
        await result


class DBManager:
    """Async PostgreSQL manager with per-environment connection pools and read-only enforcement."""

    def __init__(self) -> None:
        self._envs: dict[str, _EnvPool] = {}

    @staticmethod
    def _build_ssl_context(config: PostgresEnvConfig) -> ssl.SSLContext | None:
        if config.ssl_mode == "disable":
            return None

        _valid_modes = ("require", "verify-ca", "verify-full")
        if config.ssl_mode not in _valid_modes:
            raise ValueError(
                f"Unsupported ssl_mode: {config.ssl_mode!r}. Supported: disable, {', '.join(_valid_modes)}"
            )

        ctx = ssl.create_default_context()

        if config.ssl_mode == "require":
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE
        elif config.ssl_mode == "verify-ca":
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_REQUIRED
        elif config.ssl_mode == "verify-full":
            ctx.check_hostname = True
            ctx.verify_mode = ssl.CERT_REQUIRED

        if config.ssl_ca_cert:
            ctx.load_verify_locations(config.ssl_ca_cert)
        if config.ssl_client_cert and config.ssl_client_key:
            ctx.load_cert_chain(config.ssl_client_cert, config.ssl_client_key)

        return ctx

    @staticmethod
    def _read_ssh_key(path: str) -> str:
        """Read an SSH private key, stripping any trailing public key lines.

        Some key files (e.g. Terraform-generated) append the public key after
        the ``-----END ... PRIVATE KEY-----`` marker.  asyncssh treats these
        extra lines as an invalid certificate and refuses to load the key.
        """
        with open(path) as fh:
            lines: list[str] = []
            for line in fh:
                lines.append(line)
                if "PRIVATE KEY-----" in line and line.strip().startswith("-----END"):
                    break
        return "".join(lines)

    @staticmethod
    async def _start_ssh_tunnel(config: PostgresEnvConfig, pg_host: str, pg_port: int) -> tuple[Any, Any, int]:
        import asyncssh

        connect_kwargs: dict[str, Any] = {
            "host": config.ssh_host,
            "port": config.ssh_port,
            "username": config.ssh_user,
            "known_hosts": None,
        }
        if config.ssh_key_file:
            key_data = DBManager._read_ssh_key(config.ssh_key_file)
            connect_kwargs["client_keys"] = [asyncssh.import_private_key(key_data)]
        if config.ssh_password:
            connect_kwargs["password"] = config.ssh_password

        ssh_conn = await asyncssh.connect(**connect_kwargs)
        ssh_listener = await ssh_conn.forward_local_port(
            _SSH_TUNNEL_LOCAL_HOST,
            0,
            pg_host,
            pg_port,
        )
        local_port: int = ssh_listener.get_port()
        log.info(
            "ssh_tunnel_established",
            ssh_host=config.ssh_host,
            local_host=_SSH_TUNNEL_LOCAL_HOST,
            local_port=local_port,
            remote_host=pg_host,
            remote_port=pg_port,
        )
        return ssh_conn, ssh_listener, local_port

    async def _create_env_pool(self, env_name: str, config: PostgresEnvConfig) -> None:
        dsn = config.url
        ssh_conn = None
        ssh_listener = None

        try:
            if config.ssh_enabled:
                parsed = urlparse(dsn)
                pg_host = parsed.hostname or "localhost"
                pg_port = parsed.port or 5432
                ssh_conn, ssh_listener, local_port = await self._start_ssh_tunnel(config, pg_host, pg_port)
                if parsed.username:
                    netloc = parsed.username
                    if parsed.password:
                        netloc += f":{parsed.password}"
                    netloc += "@"
                else:
                    netloc = ""
                netloc += f"{_SSH_TUNNEL_LOCAL_HOST}:{local_port}"
                dsn = urlunparse(parsed._replace(netloc=netloc))

            ssl_ctx = self._build_ssl_context(config)

            import asyncpg

            pool_kwargs: dict[str, Any] = {"min_size": 1, "max_size": 5}
            if ssl_ctx is not None:
                pool_kwargs["ssl"] = ssl_ctx

            pool = await asyncpg.create_pool(dsn, **pool_kwargs)
            self._envs[env_name] = _EnvPool(pool=pool, ssh_conn=ssh_conn, ssh_listener=ssh_listener)
            log.info("db_pool_created", env=env_name)
        except Exception:
            log.exception("db_pool_creation_failed", env=env_name)
            if ssh_listener:
                ssh_listener.close()
            if ssh_conn:
                await _maybe_await_close(ssh_conn)
                await ssh_conn.wait_closed()

    async def start(self) -> None:
        """Create connection pools for all configured environments."""
        from koda.config import POSTGRES_ENV_CONFIGS

        for env_name, config in POSTGRES_ENV_CONFIGS.items():
            await self._create_env_pool(env_name, config)

        if not self._envs:
            log.warning("postgres_no_pools", msg="No database pools were created")

    async def stop(self) -> None:
        """Close all connection pools and SSH tunnels."""
        for env_name, ep in list(self._envs.items()):
            if ep.pool:
                await ep.pool.close()
                log.info("db_pool_closed", env=env_name)
            if ep.ssh_listener:
                ep.ssh_listener.close()
            if ep.ssh_conn:
                await _maybe_await_close(ep.ssh_conn)
                await ep.ssh_conn.wait_closed()
                log.info("ssh_tunnel_closed", env=env_name)
        self._envs.clear()

    @property
    def is_available(self) -> bool:
        return bool(self._envs)

    @property
    def available_envs(self) -> list[str]:
        return list(self._envs.keys())

    def is_env_available(self, env: str) -> bool:
        return env in self._envs

    def _get_pool(self, env: str | None = None) -> tuple[str, Any]:
        """Resolve environment and return (env_name, pool).

        - If env is specified, use that env.
        - If only one env exists, use it.
        - If multiple exist, default to "prod".
        """
        if not self._envs:
            raise ValueError("No database pools available.")

        if env is not None:
            ep = self._envs.get(env)
            if not ep:
                raise ValueError(f"Unknown env '{env}'. Available: {', '.join(self._envs)}")
            return env, ep.pool

        if len(self._envs) == 1:
            env_name = next(iter(self._envs))
            return env_name, self._envs[env_name].pool

        # Multiple envs: default to prod
        if "prod" in self._envs:
            return "prod", self._envs["prod"].pool

        # Fallback to first available
        env_name = next(iter(self._envs))
        return env_name, self._envs[env_name].pool

    def _validate_query(self, sql: str) -> str | None:
        """Validate SQL is read-only. Returns error message or None if valid."""
        stripped = sql.strip()

        if not stripped:
            return "Empty query."

        if _BACKSLASH_RE.search(stripped):
            return "Backslash meta-commands are not allowed."

        if _COMMENT_RE.search(stripped):
            return "SQL comments (-- or /* */) are not allowed."

        if _MULTI_STMT_RE.search(stripped):
            return "Multi-statement queries are not allowed."

        if not _ALLOWED_LEADING.match(stripped):
            return "Only SELECT, WITH, SHOW, and EXPLAIN queries are allowed."

        if _BLOCKED_KEYWORDS.search(stripped):
            return (
                "Query contains a blocked keyword "
                "(INSERT, UPDATE, DELETE, DROP, ALTER, CREATE, TRUNCATE, GRANT, REVOKE, COPY)."
            )

        return None

    async def query(
        self, sql: str, timeout: int | None = None, max_rows: int | None = None, env: str | None = None
    ) -> str:
        """Execute a read-only query and return formatted results."""
        from koda.config import POSTGRES_MAX_ROWS, POSTGRES_QUERY_TIMEOUT

        if timeout is None:
            timeout = POSTGRES_QUERY_TIMEOUT
        if max_rows is None:
            max_rows = POSTGRES_MAX_ROWS

        try:
            env_name, pool = self._get_pool(env)
        except ValueError as e:
            return f"Error: {e}"

        err = self._validate_query(sql)
        if err:
            return f"Error: {err}"

        start = time.monotonic()
        try:
            async with pool.acquire() as conn:
                rows = await conn.fetch(sql, timeout=timeout)
        except Exception as e:
            return f"Error: {e}"
        elapsed = time.monotonic() - start

        env_label = f"[{env_name}] " if len(self._envs) > 1 else ""

        if not rows:
            return f"{env_label}Query: {sql}\nRows: 0 ({elapsed:.3f}s)\n\nNo results."

        columns = list(rows[0].keys())
        truncated = len(rows) > max_rows
        display_rows = rows[:max_rows]

        # Calculate column widths
        col_widths = {col: len(str(col)) for col in columns}
        for row in display_rows:
            for col in columns:
                col_widths[col] = max(col_widths[col], len(str(row[col])))

        # Build table
        header = "| " + " | ".join(str(col).ljust(col_widths[col]) for col in columns) + " |"
        separator = "|-" + "-|-".join("-" * col_widths[col] for col in columns) + "-|"

        lines = [
            f"{env_label}Query: {sql}",
            f"Rows: {len(rows)}{' (truncated)' if truncated else ''} ({elapsed:.3f}s)",
            "",
            header,
            separator,
        ]

        for row in display_rows:
            line = "| " + " | ".join(str(row[col]).ljust(col_widths[col]) for col in columns) + " |"
            lines.append(line)

        if truncated:
            lines.append(f"\n... {len(rows) - max_rows} more rows not shown (limit: {max_rows}).")

        return "\n".join(lines)

    async def get_schema(self, table: str | None = None, env: str | None = None) -> str:
        """List tables or show columns for a specific table."""
        try:
            env_name, pool = self._get_pool(env)
        except ValueError as e:
            return f"Error: {e}"

        env_label = f"[{env_name}] " if len(self._envs) > 1 else ""

        try:
            async with pool.acquire() as conn:
                if table is None:
                    rows = await conn.fetch(
                        "SELECT table_name, table_type "
                        "FROM information_schema.tables "
                        "WHERE table_schema = 'public' "
                        "ORDER BY table_name",
                        timeout=10,
                    )
                    if not rows:
                        return f"{env_label}No tables found in public schema."

                    lines = [f"{env_label}Tables in public schema:", ""]
                    for row in rows:
                        lines.append(f"  {row['table_name']} ({row['table_type']})")
                    return "\n".join(lines)
                else:
                    rows = await conn.fetch(
                        "SELECT column_name, data_type, is_nullable, column_default "
                        "FROM information_schema.columns "
                        "WHERE table_schema = 'public' AND table_name = $1 "
                        "ORDER BY ordinal_position",
                        table,
                        timeout=10,
                    )
                    if not rows:
                        return f"{env_label}Table '{table}' not found or has no columns."

                    lines = [f"{env_label}Columns of {table}:", ""]
                    for row in rows:
                        nullable = "NULL" if row["is_nullable"] == "YES" else "NOT NULL"
                        default = f" DEFAULT {row['column_default']}" if row["column_default"] else ""
                        lines.append(f"  {row['column_name']}: {row['data_type']} {nullable}{default}")
                    return "\n".join(lines)
        except Exception as e:
            return f"Error: {e}"

    async def explain(self, sql: str, analyze: bool = False, env: str | None = None) -> str:
        """Run EXPLAIN on a query and return the plan."""
        try:
            env_name, pool = self._get_pool(env)
        except ValueError as e:
            return f"Error: {e}"

        # Reuse full validation to block writable CTEs etc.
        err = self._validate_query(sql)
        if err:
            return f"Error: {err}"

        # Extra check: only SELECT/WITH allowed for EXPLAIN
        stripped = sql.strip()
        leading = re.match(r"^\s*(\w+)", stripped)
        if not leading or leading.group(1).upper() not in ("SELECT", "WITH"):
            return "Error: EXPLAIN only supports SELECT queries."

        prefix = "EXPLAIN ANALYZE" if analyze else "EXPLAIN"
        explain_sql = f"{prefix} {sql}"

        env_label = f"[{env_name}] " if len(self._envs) > 1 else ""

        try:
            async with pool.acquire() as conn:
                rows = await conn.fetch(explain_sql, timeout=30)
                plan_lines = [str(row[0]) for row in rows]
                header = "EXPLAIN ANALYZE" if analyze else "EXPLAIN"
                return f"{env_label}{header}:\n" + "\n".join(plan_lines)
        except Exception as e:
            return f"Error: {e}"


db_manager = DBManager()
