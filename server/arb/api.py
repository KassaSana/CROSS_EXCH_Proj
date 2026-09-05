from __future__ import annotations

import asyncio
import time
from collections.abc import Callable, Iterable
from dataclasses import dataclass

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.responses import Response

from arb.adapters.base import ExchangeAdapter
from arb.metrics import (
    book_eligible,
    book_staleness_seconds,
    render_metrics,
    ws_client_queue_overflows_total,
    ws_clients,
)
from arb.orderbook import OrderBookManager
from arb.persistence import OpportunityStore
from arb.types import LiveMessage


def window_to_ns(window: str) -> int:
    values = {
        "1h": 3_600_000_000_000,
        "4h": 14_400_000_000_000,
        "24h": 86_400_000_000_000,
        "1d": 86_400_000_000_000,
        "72h": 259_200_000_000_000,
        "1w": 604_800_000_000_000,
    }
    return values.get(window, values["1h"])


READINESS_WINDOW_NS = 30_000_000_000


@dataclass
class _ClientConnection:
    queue: asyncio.Queue[dict[str, object]]
    sender_task: asyncio.Task[None] | None = None


class LiveBroadcaster:
    def __init__(self, queue_maxsize: int = 256) -> None:
        if queue_maxsize <= 0:
            raise ValueError("queue_maxsize must be positive")
        self._clients: dict[WebSocket, _ClientConnection] = {}
        self._queue_maxsize = queue_maxsize
        self._lock = asyncio.Lock()
        self._stream_sequence = 0

    async def connect(
        self,
        websocket: WebSocket,
        initial_state: Callable[[], LiveMessage] | None = None,
    ) -> None:
        await websocket.accept()
        async with self._lock:
            connection = _ClientConnection(asyncio.Queue(maxsize=self._queue_maxsize))
            if initial_state is not None:
                connection.queue.put_nowait(self._envelope(initial_state()))
            self._clients[websocket] = connection
            connection.sender_task = asyncio.create_task(
                self._send_messages(websocket, connection)
            )
            ws_clients.set(len(self._clients))

    async def disconnect(self, websocket: WebSocket) -> None:
        async with self._lock:
            connection = self._clients.pop(websocket, None)
            ws_clients.set(len(self._clients))
        if connection is not None and connection.sender_task is not None:
            connection.sender_task.cancel()
            await asyncio.gather(connection.sender_task, return_exceptions=True)

    async def broadcast(self, message: LiveMessage) -> None:
        dropped: list[tuple[WebSocket, _ClientConnection]] = []
        async with self._lock:
            if not self._clients:
                return
            payload = self._envelope(message)
            for client, connection in list(self._clients.items()):
                try:
                    connection.queue.put_nowait(payload)
                except asyncio.QueueFull:
                    dropped.append((client, connection))
                    del self._clients[client]
                    ws_client_queue_overflows_total.inc()
            if dropped:
                ws_clients.set(len(self._clients))
        for client, connection in dropped:
            if connection.sender_task is not None:
                connection.sender_task.cancel()
            asyncio.create_task(self._close_slow_client(client))

    async def _send_messages(
        self, websocket: WebSocket, connection: _ClientConnection
    ) -> None:
        try:
            while True:
                await websocket.send_json(await connection.queue.get())
        except Exception:
            pass
        finally:
            async with self._lock:
                if self._clients.get(websocket) is connection:
                    del self._clients[websocket]
                    ws_clients.set(len(self._clients))

    @staticmethod
    async def _close_slow_client(websocket: WebSocket) -> None:
        try:
            await websocket.close(code=1013, reason="outgoing queue full")
        except Exception:
            pass

    def _envelope(self, message: LiveMessage) -> dict[str, object]:
        self._stream_sequence += 1
        return {
            "type": message.type,
            "payload": message.payload,
            "stream_sequence": self._stream_sequence,
        }


def create_app(
    store: OpportunityStore,
    book_manager: OrderBookManager,
    broadcaster: LiveBroadcaster,
    adapters: Iterable[ExchangeAdapter] = (),
    expected_pairs: Iterable[tuple[str, str]] = (),
    started_at_holder: list[int] | None = None,
) -> FastAPI:
    app = FastAPI(title="Cross-Exchange Arbitrage Detector")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )
    adapter_list = list(adapters)
    tracked_pairs = list(expected_pairs)
    started_at: list[int] = started_at_holder if started_at_holder is not None else [time.time_ns()]

    @app.get("/api/opportunities/recent")
    async def recent_opportunities(limit: int = 100) -> list[dict[str, str | int]]:
        return await store.recent(limit=limit)

    @app.get("/api/stats")
    async def stats(window: str = "1h") -> dict[str, str | int]:
        return await store.stats(window_to_ns(window))

    @app.get("/api/system/overview")
    async def system_overview() -> dict[str, object]:
        all_time = await store.extended_stats(window_ns=None)
        return {
            "started_at_ns": started_at[0],
            "uptime_seconds": max(0, (time.time_ns() - started_at[0]) // 1_000_000_000),
            "all_time_count": all_time["count"],
            "all_time_max_spread_pct": all_time["max_spread_pct"],
            "all_time_peak_minute": await store.peak_minute(window_ns=None),
        }

    @app.get("/api/system/stats")
    async def system_stats(window: str = "1h") -> dict[str, object]:
        window_ns = window_to_ns(window)
        extended = await store.extended_stats(window_ns=window_ns)
        peak = await store.peak_minute(window_ns=window_ns)
        return {"window": window, **extended, "peak_minute": peak}

    @app.get("/api/system/timeseries")
    async def system_timeseries(window: str = "1h", bucket_seconds: int = 60) -> dict[str, object]:
        window_ns = window_to_ns(window)
        if bucket_seconds <= 0:
            bucket_seconds = 60
        points = await store.timeseries(window_ns=window_ns, bucket_seconds=bucket_seconds)
        return {"window": window, "bucket_seconds": bucket_seconds, "points": points}

    @app.post("/api/system/reset")
    async def system_reset() -> dict[str, int]:
        started_at[0] = time.time_ns()
        return {"started_at_ns": started_at[0], "uptime_seconds": 0}

    @app.get("/api/pairs")
    async def pairs() -> list[dict[str, str]]:
        return [{"exchange": exchange, "pair": pair} for exchange, pair in book_manager.known_pairs()]

    @app.get("/api/book-status")
    async def book_status() -> list[dict[str, object]]:
        return [status.as_payload() for status in book_manager.eligibility_for(tracked_pairs)]

    @app.get("/api/adapters")
    async def adapter_status() -> list[dict[str, str | int | bool | None]]:
        now_ns = time.time_ns()
        return [adapter.status_snapshot(now_ns).as_payload() for adapter in adapter_list]

    @app.get("/healthz")
    async def healthz() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/readyz")
    async def readyz() -> JSONResponse:
        disconnected = [adapter.name for adapter in adapter_list if not adapter.connected]
        stale_pairs: list[dict[str, object]] = []
        for status in book_manager.eligibility_for(tracked_pairs):
            if not status.eligible:
                stale_pairs.append(status.as_payload())

        ready = not disconnected and not stale_pairs
        payload: dict[str, object] = {
            "status": "ready" if ready else "not_ready",
            "disconnected_adapters": disconnected,
            "stale_pairs": stale_pairs,
        }
        return JSONResponse(payload, status_code=200 if ready else 503)

    @app.get("/metrics")
    async def metrics() -> Response:
        for status in book_manager.eligibility_for(tracked_pairs):
            book_eligible.labels(exchange=status.exchange, pair=status.pair).set(
                1 if status.eligible else 0
            )
            if status.age_ns is not None:
                book_staleness_seconds.labels(
                    exchange=status.exchange, pair=status.pair
                ).set(status.age_ns / 1_000_000_000)
        payload, content_type = render_metrics()
        return Response(content=payload, media_type=content_type)

    @app.websocket("/ws/live")
    async def live_updates(websocket: WebSocket) -> None:
        def current_state() -> LiveMessage:
            statuses = book_manager.eligibility_for(tracked_pairs)
            books = [
                top.as_payload()
                for status in statuses
                if status.eligible
                if (top := book_manager.top_of_book(status.exchange, status.pair)) is not None
            ]
            return LiveMessage(
                type="state_snapshot",
                payload={
                    "books": books,
                    "statuses": [status.as_payload() for status in statuses],
                },
            )

        await broadcaster.connect(websocket, current_state)
        try:
            while True:
                await websocket.receive_text()
        except WebSocketDisconnect:
            await broadcaster.disconnect(websocket)

    return app
