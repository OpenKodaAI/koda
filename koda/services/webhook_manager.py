"""Webhook registration and event notification for agent tools."""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import os
import re
import time
from dataclasses import dataclass, field
from typing import Any

from koda.logging_config import get_logger

log = get_logger(__name__)

_NAME_RE = re.compile(r"^[a-zA-Z0-9_-]{1,64}$")


@dataclass
class WebhookRegistration:
    name: str
    path: str
    secret: str | None = None
    created_at: float = field(default_factory=time.time)
    call_count: int = 0
    last_called_at: float | None = None


@dataclass
class WebhookEvent:
    webhook_name: str
    payload: dict[str, Any]
    headers: dict[str, str]
    received_at: float = field(default_factory=time.time)
    verified: bool = False


class WebhookManager:
    """In-memory webhook registration and event notification."""

    def __init__(self) -> None:
        self._registrations: dict[str, WebhookRegistration] = {}  # name -> registration
        self._events: list[WebhookEvent] = []  # bounded event log
        self._waiters: dict[str, list[asyncio.Event]] = {}  # event_type -> list of waiters
        self._max_events: int = 100
        self._max_registrations: int = 10
        self._persistence_path: str | None = None

    def set_persistence_path(self, path: str) -> None:
        self._persistence_path = path
        self._load_from_disk()

    def _load_from_disk(self) -> None:
        if not self._persistence_path or not os.path.isfile(self._persistence_path):
            return
        try:
            with open(self._persistence_path) as f:
                data = json.load(f)
            for name, rd in data.get("registrations", {}).items():
                self._registrations[name] = WebhookRegistration(
                    name=rd["name"],
                    path=rd["path"],
                    secret=rd.get("secret"),
                    created_at=rd.get("created_at", time.time()),
                    call_count=rd.get("call_count", 0),
                )
            log.info("webhooks_loaded", count=len(self._registrations))
        except Exception as e:
            log.warning("webhooks_load_failed", error=str(e))

    def _save_to_disk(self) -> None:
        if not self._persistence_path:
            return
        try:
            data = {
                "registrations": {
                    n: {
                        "name": r.name,
                        "path": r.path,
                        "secret": r.secret,
                        "created_at": r.created_at,
                        "call_count": r.call_count,
                    }
                    for n, r in self._registrations.items()
                }
            }
            os.makedirs(os.path.dirname(self._persistence_path) or ".", exist_ok=True)
            with open(self._persistence_path, "w") as f:
                json.dump(data, f, default=str)
        except Exception as e:
            log.warning("webhooks_save_failed", error=str(e))

    def register(self, name: str, path: str, secret: str | None = None) -> str | None:
        """Register a webhook. Returns error string or None."""
        if not _NAME_RE.match(name):
            return "Invalid name. Use alphanumeric, hyphens, underscores (1-64 chars)."
        if name in self._registrations:
            return f"Webhook '{name}' already exists."
        if len(self._registrations) >= self._max_registrations:
            return f"Maximum {self._max_registrations} webhooks reached."
        if not path.startswith("/"):
            path = f"/{path}"
        self._registrations[name] = WebhookRegistration(name=name, path=path, secret=secret)
        log.info("webhook_registered", name=name, path=path)
        self._save_to_disk()
        return None

    def unregister(self, name: str) -> str | None:
        """Unregister a webhook. Returns error string or None."""
        if name not in self._registrations:
            return f"Webhook '{name}' not found."
        del self._registrations[name]
        log.info("webhook_unregistered", name=name)
        self._save_to_disk()
        return None

    def list_webhooks(self) -> list[dict[str, Any]]:
        """List all registered webhooks."""
        return [
            {
                "name": reg.name,
                "path": reg.path,
                "has_secret": reg.secret is not None,
                "call_count": reg.call_count,
                "last_called_at": reg.last_called_at,
                "created_at": reg.created_at,
            }
            for reg in self._registrations.values()
        ]

    def verify_signature(self, name: str, payload_bytes: bytes, signature: str) -> bool:
        """Verify HMAC-SHA256 signature for a webhook."""
        reg = self._registrations.get(name)
        if not reg or not reg.secret:
            return True  # No secret = no verification needed
        expected = hmac.new(reg.secret.encode(), payload_bytes, hashlib.sha256).hexdigest()
        return hmac.compare_digest(f"sha256={expected}", signature)

    def receive_event(self, name: str, payload: dict[str, Any], headers: dict[str, str] | None = None) -> str | None:
        """Process an incoming webhook event. Returns error or None."""
        reg = self._registrations.get(name)
        if not reg:
            return f"Webhook '{name}' not found."

        reg.call_count += 1
        reg.last_called_at = time.time()

        event = WebhookEvent(
            webhook_name=name,
            payload=payload,
            headers=headers or {},
            verified=True,
        )
        self._events.append(event)
        if len(self._events) > self._max_events:
            self._events = self._events[-self._max_events :]

        # Notify waiters
        event_type = f"webhook.{name}"
        waiters = self._waiters.get(event_type, [])
        for waiter in waiters:
            waiter.set()

        log.info("webhook_event_received", name=name, payload_size=len(json.dumps(payload)))
        return None

    async def wait_for_event(self, event_type: str, timeout: float = 60) -> WebhookEvent | None:
        """Wait for a specific event type. Returns event or None on timeout."""
        timeout = min(timeout, 300)  # hard cap at 5 minutes

        event = asyncio.Event()
        if event_type not in self._waiters:
            self._waiters[event_type] = []
        self._waiters[event_type].append(event)

        try:
            await asyncio.wait_for(event.wait(), timeout=timeout)
            # Find the most recent matching event
            for e in reversed(self._events):
                if f"webhook.{e.webhook_name}" == event_type:
                    return e
            return None
        except TimeoutError:
            return None
        finally:
            waiter_list = self._waiters.get(event_type, [])
            if event in waiter_list:
                waiter_list.remove(event)

    def get_recent_events(self, name: str | None = None, limit: int = 20) -> list[dict[str, Any]]:
        """Get recent webhook events."""
        events = self._events
        if name:
            events = [e for e in events if e.webhook_name == name]
        events = events[-limit:]
        return [
            {
                "webhook_name": e.webhook_name,
                "payload": e.payload,
                "received_at": e.received_at,
                "verified": e.verified,
            }
            for e in events
        ]


# Singleton
webhook_manager = WebhookManager()
