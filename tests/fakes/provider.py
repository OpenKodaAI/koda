"""Scripted provider adapter for end-to-end agent-turn tests.

``StubProvider`` replaces one provider's entry in
``koda.services.llm_runner._HTTP_PROVIDER_RUNNERS``: the dispatch table that
``get_provider_capabilities``, ``run_llm`` and ``run_llm_streaming`` consult
before any real adapter. The entry has the same shape as the real HTTP
adapters (``run``, ``stream``, ``capabilities``, ``first_chunk_timeout``) and
reports results through the same ``metadata_collector`` keys, so provider
fallback, the agent tool loop, retries and delivery above it run unchanged.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Callable, Sequence
from dataclasses import dataclass
from typing import Any

import pytest

from koda.services import llm_runner
from koda.services.provider_runtime import ProviderCapabilities, TurnMode


@dataclass
class ProviderTurn:
    """One scripted provider answer.

    ``error`` makes the turn fail with that message, classified by
    ``error_kind`` and ``retryable`` the way the real adapters classify
    transport errors. ``hold`` keeps the turn open after its first chunk until
    the event is set, which lets a test act while the provider is running.
    """

    text: str = ""
    cost_usd: float = 0.0
    session_id: str | None = None
    stop_reason: str = "end_turn"
    error: str | None = None
    error_kind: str = "transient"
    retryable: bool = False
    hold: asyncio.Event | None = None


@dataclass
class ProviderCall:
    """What the runtime sent to the provider for one turn."""

    query: str
    model: str
    session_id: str | None
    turn_mode: str
    system_prompt: str | None
    streaming: bool


Script = Sequence[ProviderTurn] | Callable[[ProviderCall], ProviderTurn]


class StubProvider:
    """Answers provider turns from a script instead of calling a model.

    ``script`` is either a sequence of turns, consumed in order (the last one
    repeats when the script runs out), or a callable that picks the turn for
    each call. Every call is recorded in ``calls``; ``holding`` is set once a
    turn with ``hold`` is waiting, and ``cancelled_turns`` counts streaming
    turns that were cancelled.
    """

    def __init__(self, script: Script, *, provider: str = "claude") -> None:
        self.provider = provider
        self._script = script
        self.calls: list[ProviderCall] = []
        self.holding = asyncio.Event()
        self.cancelled_turns = 0

    def install(self, monkeypatch: pytest.MonkeyPatch) -> StubProvider:
        """Register this stub as the adapter for ``self.provider`` for one test."""
        monkeypatch.setitem(
            llm_runner._HTTP_PROVIDER_RUNNERS,
            self.provider,
            {
                "run": self.run,
                "stream": self.stream,
                "capabilities": self.capabilities,
                "first_chunk_timeout": 5.0,
            },
        )
        return self

    def _next_turn(self, call: ProviderCall) -> ProviderTurn:
        self.calls.append(call)
        if callable(self._script):
            return self._script(call)
        index = min(len(self.calls), len(self._script)) - 1
        return self._script[index]

    async def capabilities(self, turn_mode: TurnMode) -> ProviderCapabilities:
        return ProviderCapabilities(
            provider=self.provider,
            turn_mode=turn_mode,
            status="ready",
            can_execute=True,
            supports_native_resume=True,
            checked_via="stub",
        )

    async def stream(
        self,
        *,
        query: str,
        model: str,
        session_id: str | None = None,
        system_prompt: str | None = None,
        process_holder: dict[str, Any] | None = None,
        metadata_collector: dict[str, Any] | None = None,
        turn_mode: TurnMode = "new_turn",
        **_kwargs: Any,
    ) -> AsyncIterator[str]:
        turn = self._next_turn(
            ProviderCall(
                query=query,
                model=model,
                session_id=session_id,
                turn_mode=turn_mode,
                system_prompt=system_prompt,
                streaming=True,
            )
        )
        collector = metadata_collector if metadata_collector is not None else {}
        if process_holder is not None:
            # Same registration as the real HTTP adapters: no subprocess, only the task.
            process_holder["task"] = asyncio.current_task()
        try:
            if turn.text:
                yield turn.text
            if turn.hold is not None:
                self.holding.set()
                await turn.hold.wait()
        except asyncio.CancelledError:
            self.cancelled_turns += 1
            raise
        finally:
            if process_holder is not None:
                process_holder.pop("task", None)
        if turn.error is not None:
            collector.update(
                error=True,
                error_message=turn.error,
                error_kind=turn.error_kind,
                retryable=turn.retryable,
            )
            return
        collector.update(
            session_id=turn.session_id,
            usage={"input_tokens": 10, "output_tokens": 5},
            cost_usd=turn.cost_usd,
            stop_reason=turn.stop_reason,
        )

    async def run(
        self,
        *,
        query: str,
        model: str,
        session_id: str | None = None,
        system_prompt: str | None = None,
        turn_mode: TurnMode = "new_turn",
        **_kwargs: Any,
    ) -> dict[str, Any]:
        turn = self._next_turn(
            ProviderCall(
                query=query,
                model=model,
                session_id=session_id,
                turn_mode=turn_mode,
                system_prompt=system_prompt,
                streaming=False,
            )
        )
        if turn.hold is not None:
            self.holding.set()
            await turn.hold.wait()
        if turn.error is not None:
            return {
                "result": turn.error,
                "session_id": session_id,
                "cost_usd": 0.0,
                "usage": {},
                "error": True,
                "_error_kind": turn.error_kind,
                "_retryable": turn.retryable,
            }
        return {
            "result": turn.text,
            "session_id": turn.session_id,
            "cost_usd": turn.cost_usd,
            "usage": {"input_tokens": 10, "output_tokens": 5},
            "error": False,
            "_stop_reason": turn.stop_reason,
        }
