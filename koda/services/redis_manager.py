"""Redis read-only manager for agent tools."""

from __future__ import annotations

from typing import Any

from koda.logging_config import get_logger

log = get_logger(__name__)

READ_ONLY_COMMANDS = frozenset(
    {
        "GET",
        "MGET",
        "HGET",
        "HGETALL",
        "HMGET",
        "HKEYS",
        "HVALS",
        "HLEN",
        "LRANGE",
        "LLEN",
        "LINDEX",
        "SMEMBERS",
        "SCARD",
        "SISMEMBER",
        "ZRANGE",
        "ZRANGEBYSCORE",
        "ZCARD",
        "ZSCORE",
        "KEYS",
        "EXISTS",
        "TYPE",
        "TTL",
        "PTTL",
        "DBSIZE",
        "INFO",
        "STRLEN",
        "SCAN",
        "HSCAN",
        "SSCAN",
        "ZSCAN",
    }
)


class RedisManager:
    """Manages read-only Redis connections for agent tool execution."""

    def __init__(self) -> None:
        self._connections: dict[str, Any] = {}
        self._available = False

    async def start(self) -> None:
        try:
            import redis.asyncio  # noqa: F401

            self._available = True
        except ImportError:
            self._available = False

    async def stop(self) -> None:
        for conn in self._connections.values():
            await conn.close()
        self._connections.clear()

    @property
    def is_available(self) -> bool:
        return self._available

    async def _get_connection(self, env: str | None = None) -> Any:
        env = env or "default"
        if env in self._connections:
            return self._connections[env]

        import redis.asyncio as aioredis

        from koda.config import _env as get_env

        suffix = f"_{env.upper()}" if env != "default" else ""
        url = get_env(f"REDIS_URL{suffix}", get_env("REDIS_URL", ""))
        if not url:
            raise ValueError(f"REDIS_URL{suffix} not configured.")
        conn = aioredis.from_url(url, decode_responses=True)
        self._connections[env] = conn
        return conn

    async def execute(self, command: str, args: list[str] | None = None, env: str | None = None) -> str:
        """Execute a read-only Redis command and return a formatted string result."""
        cmd = command.strip().upper()
        if cmd not in READ_ONLY_COMMANDS:
            return (
                f"Error: command '{command}' is not allowed. "
                f"Only read-only commands: {', '.join(sorted(READ_ONLY_COMMANDS))}"
            )
        try:
            conn = await self._get_connection(env)
            result = await conn.execute_command(cmd, *(args or []))
            if isinstance(result, (list, tuple)):
                if len(result) > 200:
                    result = list(result[:200])
                lines = [f"Result ({len(result)} items):"]
                for i, item in enumerate(result):
                    lines.append(f"  [{i}] {item}")
                return "\n".join(lines)
            elif isinstance(result, dict):
                lines = [f"Result ({len(result)} keys):"]
                for k, v in list(result.items())[:200]:
                    lines.append(f"  {k}: {v}")
                return "\n".join(lines)
            elif isinstance(result, bytes):
                return result.decode(errors="replace")
            return str(result) if result is not None else "(nil)"
        except Exception as e:
            return f"Error: {e}"


_manager: RedisManager | None = None


def get_redis_manager() -> RedisManager:
    """Return the singleton RedisManager instance."""
    global _manager  # noqa: PLW0603
    if _manager is None:
        _manager = RedisManager()
    return _manager
