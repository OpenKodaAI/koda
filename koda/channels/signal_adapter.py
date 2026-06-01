"""Signal adapter using the signal-cli REST API.

Transport: Polling — the adapter spawns a background task that periodically
polls the signal-cli REST API for new messages.  ``is_official = False``
because signal-cli is an unofficial community client.
"""

from __future__ import annotations

import asyncio
import contextlib
import time
from typing import Any

from koda.channels.base import ChannelAdapter
from koda.channels.types import ChannelIdentity, IncomingMessage, OutgoingMessage
from koda.logging_config import get_logger

log = get_logger(__name__)

_POLL_INTERVAL_SECONDS = 2.0


class SignalAdapter(ChannelAdapter):
    """Bridges Signal via the signal-cli REST API into the Koda channel layer."""

    channel_type: str = "signal"
    is_official: bool = False

    def __init__(self) -> None:
        self._agent_id: str = ""
        self._phone_number: str = ""
        self._cli_url: str = ""
        self._task: asyncio.Task[None] | None = None
        self._running: bool = False
        self._session: Any = None

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def initialize(self, agent_id: str, secrets: dict[str, str]) -> None:
        self._agent_id = agent_id
        self._phone_number = secrets["SIGNAL_PHONE_NUMBER"]
        self._cli_url = secrets["SIGNAL_CLI_URL"].rstrip("/")
        log.info(
            "signal.initialized: agent=%s phone=%s url=%s",
            agent_id,
            self._phone_number,
            self._cli_url,
        )

    async def start(self) -> None:
        import aiohttp as aio

        self._session = aio.ClientSession()
        self._running = True
        self._task = asyncio.create_task(self._poll_loop())
        log.info("signal.started: agent=%s", self._agent_id)

    async def stop(self) -> None:
        self._running = False
        if self._task is not None:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task
            self._task = None
        if self._session:
            await self._session.close()
            self._session = None
        log.info("signal.stopped: agent=%s", self._agent_id)

    # ------------------------------------------------------------------
    # Polling
    # ------------------------------------------------------------------

    async def _poll_loop(self) -> None:
        while self._running:
            try:
                url = f"{self._cli_url}/v1/receive/{self._phone_number}"
                async with self._session.get(url) as resp:
                    if resp.status == 200:
                        messages: list[dict[str, Any]] = await resp.json()
                        for msg in messages:
                            await self._process_message(msg)
            except asyncio.CancelledError:
                break
            except Exception:
                log.exception("signal.poll_error: agent=%s", self._agent_id)

            await asyncio.sleep(_POLL_INTERVAL_SECONDS)

    async def _process_message(self, msg: dict[str, Any]) -> None:
        envelope = msg.get("envelope", {})
        data_message = envelope.get("dataMessage")
        if data_message is None:
            return

        source = envelope.get("source", "")
        source_name = envelope.get("sourceName", source)
        text = data_message.get("message", "")
        timestamp_ms = data_message.get("timestamp", 0)

        # Group context.
        group_info = data_message.get("groupInfo")
        is_group = group_info is not None
        channel_id = group_info.get("groupId", source) if group_info else source

        channel = ChannelIdentity(
            channel_type="signal",
            channel_id=channel_id,
            user_id=source,
            user_display_name=source_name,
            is_group=is_group,
        )

        incoming = IncomingMessage(
            id=str(timestamp_ms),
            channel=channel,
            text=text or "",
            timestamp=time.time(),
            reply_to_id=None,
            raw_platform_data=msg,
        )
        await self._dispatch_inbound(incoming)

    # ------------------------------------------------------------------
    # Outbound
    # ------------------------------------------------------------------

    async def send_text(self, channel: ChannelIdentity, msg: OutgoingMessage) -> str:
        url = f"{self._cli_url}/v2/send"
        payload: dict[str, Any] = {
            "message": msg.text,
            "number": self._phone_number,
            "recipients": [channel.channel_id],
        }

        async with self._session.post(url, json=payload) as resp:
            data = await resp.json()
            return str(data.get("timestamp", ""))

    async def send_typing(self, channel: ChannelIdentity) -> None:
        # signal-cli does not expose a typing indicator endpoint.
        pass

    async def send_voice(self, channel: ChannelIdentity, path: str, caption: str = "") -> None:
        await self._send_with_attachment(channel, path, caption)

    async def send_document(self, channel: ChannelIdentity, path: str, filename: str, caption: str = "") -> None:
        await self._send_with_attachment(channel, path, caption)

    async def send_image(self, channel: ChannelIdentity, path: str, caption: str = "") -> None:
        await self._send_with_attachment(channel, path, caption)

    async def _send_with_attachment(self, channel: ChannelIdentity, path: str, caption: str = "") -> None:
        import base64

        with open(path, "rb") as f:
            file_data = base64.b64encode(f.read()).decode()

        url = f"{self._cli_url}/v2/send"
        payload: dict[str, Any] = {
            "message": caption,
            "number": self._phone_number,
            "recipients": [channel.channel_id],
            "base64_attachments": [file_data],
        }

        await self._session.post(url, json=payload)

    # ------------------------------------------------------------------
    # Health
    # ------------------------------------------------------------------

    def health(self) -> dict[str, Any]:
        return {
            "channel_type": self.channel_type,
            "is_official": self.is_official,
            "status": "running" if self._running else "stopped",
            "signal_cli_url": self._cli_url,
        }
