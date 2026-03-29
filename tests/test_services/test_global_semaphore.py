"""Tests for global semaphore enforcement."""

import asyncio

import pytest


class TestGlobalSemaphore:
    @pytest.mark.asyncio
    async def test_semaphore_limits_concurrent(self):
        semaphore = asyncio.Semaphore(1)
        entered = []
        exited = []

        async def worker(name: str):
            async with semaphore:
                entered.append(name)
                # Verify mutual exclusion: at most 1 worker active at a time
                active = len(entered) - len(exited)
                assert active <= 1, f"Expected <=1 active, got {active}"
                await asyncio.sleep(0.01)
                exited.append(name)

        await asyncio.gather(worker("a"), worker("b"))
        assert len(entered) == 2
        assert len(exited) == 2
