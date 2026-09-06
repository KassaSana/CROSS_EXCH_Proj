from __future__ import annotations

import asyncio

from arb.persistence import OpportunityStore


async def wait_for_rows(
    store: OpportunityStore, expected: int, timeout_seconds: float = 5.0
) -> None:
    """Block until `expected` opportunities are readable from the store.

    The writer flushes on its own interval and aiosqlite commits on a worker
    thread, so a fixed sleep races the flush: it passes locally and fails on a
    loaded CI runner. Poll for the condition the test actually depends on.
    """
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout_seconds
    while True:
        rows = await store.recent(limit=expected + 1)
        if len(rows) >= expected:
            return
        if loop.time() >= deadline:
            raise AssertionError(
                f"{len(rows)} of {expected} opportunities persisted within {timeout_seconds}s"
            )
        await asyncio.sleep(0.01)
