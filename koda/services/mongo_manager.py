"""MongoDB read-only manager for agent tools."""

from __future__ import annotations

import json
from typing import Any

from koda.logging_config import get_logger

log = get_logger(__name__)


class MongoManager:
    """Async MongoDB manager with read-only query support and multi-environment clients."""

    def __init__(self) -> None:
        self._clients: dict[str, Any] = {}
        self._available: bool = False

    async def start(self) -> None:
        try:
            import motor.motor_asyncio  # noqa: F401

            self._available = True
        except ImportError:
            self._available = False

    async def stop(self) -> None:
        for client in self._clients.values():
            client.close()
        self._clients.clear()

    @property
    def is_available(self) -> bool:
        return self._available

    async def _get_client(self, env: str | None = None) -> Any:
        import motor.motor_asyncio

        from koda.config import _env as get_env

        env = env or "default"
        if env in self._clients:
            return self._clients[env]
        suffix = f"_{env.upper()}" if env != "default" else ""
        url = get_env(f"MONGO_URL{suffix}", get_env("MONGO_URL", ""))
        if not url:
            raise ValueError(f"MONGO_URL{suffix} not configured.")
        client = motor.motor_asyncio.AsyncIOMotorClient(url)
        self._clients[env] = client
        return client

    async def query(
        self,
        database: str,
        collection: str,
        filter_doc: dict[str, Any] | None = None,
        limit: int = 100,
        env: str | None = None,
    ) -> str:
        """Run a read-only find query and return formatted results."""
        try:
            client = await self._get_client(env)
            db = client[database]
            coll = db[collection]
            cursor = coll.find(filter_doc or {}).limit(min(limit, 1000))
            docs: list[dict[str, Any]] = []
            async for doc in cursor:
                # Convert ObjectId fields to strings for JSON serialisation
                for k, v in list(doc.items()):
                    if type(v).__name__ == "ObjectId":
                        doc[k] = str(v)
                docs.append(doc)
            if not docs:
                return f"No documents found in {database}.{collection}."
            lines = [f"Results from {database}.{collection} ({len(docs)} docs):"]
            for doc in docs:
                lines.append(json.dumps(doc, default=str, ensure_ascii=False)[:500])
            return "\n".join(lines)
        except Exception as e:
            return f"Error: {e}"


_manager: MongoManager | None = None


def get_mongo_manager() -> MongoManager:
    """Return the singleton MongoManager instance."""
    global _manager  # noqa: PLW0603
    if _manager is None:
        _manager = MongoManager()
    return _manager
