from __future__ import annotations

import time
from collections.abc import Iterable

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.responses import Response

from arb.adapters.base import ExchangeAdapter
from arb.metrics import book_staleness_seconds, render_metrics, ws_clients
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


class LiveBroadcaster:
    def __init__(self) -> None:
        self._clients: set[WebSocket] = set()

    async def connect(self, websocket: WebSocket) -> None:
        await websocket.accept()
        self._clients.add(websocket)
        ws_clients.set(len(self._clients))

    async def disconnect(self, websocket: WebSocket) -> None:
        self._clients.discard(websocket)
        ws_clients.set(len(self._clients))

    async def broadcast(self, message: LiveMessage) -> None:
        if not self._clients:
            return
        dead: list[WebSocket] = []
        for client in self._clients:
            try:
                await client.send_json({"type": message.type, "payload": message.payload})
            except RuntimeError:
                dead.append(client)
        for client in dead:
            self._clients.discard(client)
        if dead:
            ws_clients.set(len(self._clients))


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

    @app.get("/api/adapters")
    async def adapter_status() -> list[dict[str, str | int | bool | None]]:
        now_ns = time.time_ns()
        return [adapter.status_snapshot(now_ns).as_payload() for adapter in adapter_list]

    @app.get("/healthz")
    async def healthz() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/readyz")
    async def readyz() -> JSONResponse:
        now_ns = time.time_ns()
        disconnected = [adapter.name for adapter in adapter_list if not adapter.connected]
        stale_pairs: list[dict[str, object]] = []
        for exchange, pair in tracked_pairs:
            status = book_manager.eligibility(exchange, pair)
            if not status.eligible:
                stale_pairs.append({"exchange": exchange, "pair": pair})

        ready = not disconnected and not stale_pairs
        payload: dict[str, object] = {
            "status": "ready" if ready else "not_ready",
            "disconnected_adapters": disconnected,
            "stale_pairs": stale_pairs,
        }
        return JSONResponse(payload, status_code=200 if ready else 503)

    @app.get("/metrics")
    async def metrics() -> Response:
        now_ns = time.time_ns()
        for exchange, pair in tracked_pairs:
            top = book_manager.eligible_top_of_book(exchange, pair)
            if top is None:
                continue
            book_staleness_seconds.labels(exchange=exchange, pair=pair).set(max(0, (now_ns - top.timestamp_ns) / 1_000_000_000))
        payload, content_type = render_metrics()
        return Response(content=payload, media_type=content_type)

    @app.websocket("/ws/live")
    async def live_updates(websocket: WebSocket) -> None:
        await broadcaster.connect(websocket)
        try:
            while True:
                await websocket.receive_text()
        except WebSocketDisconnect:
            await broadcaster.disconnect(websocket)

    return app
