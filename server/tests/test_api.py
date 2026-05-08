import asyncio
import time
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest
from arb.adapters.base import ExchangeAdapter
from arb.api import LiveBroadcaster, create_app
from arb.orderbook import OrderBookManager
from arb.persistence import OpportunityStore
from arb.types import ArbitrageOpportunity, EventKind, LiveMessage, MarketEvent, PriceLevel
from fastapi.testclient import TestClient


class StubAdapter(ExchangeAdapter):
    name = "stub"
    ws_url = "wss://example.test"
    snapshot_url = "https://example.test/snapshot"

    async def subscribe(self, websocket: Any) -> None:
        return None

    async def parse_message(self, message: str) -> list[MarketEvent]:
        return []

    async def fetch_snapshot(self, pair: str, trigger_sequence: int) -> MarketEvent:
        return MarketEvent(
            exchange=self.name,
            pair=pair,
            kind=EventKind.SNAPSHOT,
            sequence=trigger_sequence,
            timestamp_ns=trigger_sequence,
            bids=(PriceLevel(price=Decimal("100"), size=Decimal("1")),),
            asks=(PriceLevel(price=Decimal("101"), size=Decimal("1")),),
        )


@pytest.mark.asyncio
async def test_recent_endpoint_returns_saved_rows(tmp_path: Path) -> None:
    db_path = tmp_path / "test.sqlite3"
    store = OpportunityStore(str(db_path), batch_size=1, flush_interval_seconds=0.01)
    await store.initialize()
    await store.enqueue(
        ArbitrageOpportunity(
            timestamp_ns=1,
            pair="BTC-USD",
            buy_exchange="gemini",
            sell_exchange="coinbase",
            buy_price=Decimal("100"),
            sell_price=Decimal("101"),
            spread_pct=Decimal("1"),
            max_size=Decimal("0.5"),
            theoretical_profit_usd=Decimal("0.5"),
        )
    )
    task = asyncio.create_task(store.run())
    await asyncio.sleep(0.05)
    await store.close()
    task.cancel()

    client = TestClient(create_app(store, OrderBookManager(), LiveBroadcaster()))
    response = client.get("/api/opportunities/recent?limit=10")
    assert response.status_code == 200
    assert response.json()[0]["pair"] == "BTC-USD"


def test_healthz_is_alive() -> None:
    client = TestClient(create_app(OpportunityStore(":memory:"), OrderBookManager(), LiveBroadcaster()))
    response = client.get("/healthz")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_metrics_endpoint_exposes_prometheus_payload() -> None:
    client = TestClient(create_app(OpportunityStore(":memory:"), OrderBookManager(), LiveBroadcaster()))
    response = client.get("/metrics")
    assert response.status_code == 200
    assert "arb_ws_clients" in response.text


def test_adapter_status_returns_runtime_fields() -> None:
    adapter = StubAdapter(["BTC-USD"])
    adapter.connected = True
    adapter.last_message_ns = time.time_ns()
    adapter.reconnect_count = 2
    adapter.last_error = "socket reset"

    client = TestClient(create_app(OpportunityStore(":memory:"), OrderBookManager(), LiveBroadcaster(), adapters=[adapter]))
    response = client.get("/api/adapters")

    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    assert body[0]["exchange"] == "stub"
    assert body[0]["connected"] is True
    assert isinstance(body[0]["last_message_age_ms"], int)
    assert body[0]["last_message_age_ms"] >= 0
    assert body[0]["gap_count"] == 0
    assert body[0]["reconnect_count"] == 2
    assert body[0]["last_error"] == "socket reset"


def test_readyz_returns_not_ready_for_missing_updates() -> None:
    adapter = StubAdapter(["BTC-USD"])
    adapter.connected = True
    client = TestClient(
        create_app(
            OpportunityStore(":memory:"),
            OrderBookManager(),
            LiveBroadcaster(),
            adapters=[adapter],
            expected_pairs=[("stub", "BTC-USD")],
        )
    )

    response = client.get("/readyz")

    assert response.status_code == 503
    body = response.json()
    assert body["status"] == "not_ready"
    assert body["disconnected_adapters"] == []
    assert body["stale_pairs"] == [{"exchange": "stub", "pair": "BTC-USD"}]


def test_readyz_returns_ready_for_fresh_books() -> None:
    adapter = StubAdapter(["BTC-USD"])
    adapter.connected = True
    manager = OrderBookManager()
    manager.apply(
        MarketEvent(
            exchange="stub",
            pair="BTC-USD",
            kind=EventKind.SNAPSHOT,
            sequence=1,
            timestamp_ns=time.time_ns(),
            bids=(PriceLevel(price=Decimal("100"), size=Decimal("1")),),
            asks=(PriceLevel(price=Decimal("101"), size=Decimal("1")),),
        )
    )

    client = TestClient(
        create_app(
            OpportunityStore(":memory:"),
            manager,
            LiveBroadcaster(),
            adapters=[adapter],
            expected_pairs=[("stub", "BTC-USD")],
        )
    )

    response = client.get("/readyz")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ready",
        "disconnected_adapters": [],
        "stale_pairs": [],
    }


def test_window_to_ns_known_and_unknown_values() -> None:
    from arb.api import window_to_ns

    assert window_to_ns("1h") == 3_600_000_000_000
    assert window_to_ns("24h") == 86_400_000_000_000
    assert window_to_ns("72h") == 259_200_000_000_000
    # Unknown windows must default to 1h, never raise.
    assert window_to_ns("nonsense") == 3_600_000_000_000


def test_pairs_endpoint_lists_known_books() -> None:
    manager = OrderBookManager()
    manager.apply(
        MarketEvent(
            exchange="gemini",
            pair="BTC-USD",
            kind=EventKind.SNAPSHOT,
            sequence=1,
            timestamp_ns=time.time_ns(),
            bids=(PriceLevel(price=Decimal("100"), size=Decimal("1")),),
            asks=(PriceLevel(price=Decimal("101"), size=Decimal("1")),),
        )
    )
    client = TestClient(create_app(OpportunityStore(":memory:"), manager, LiveBroadcaster()))
    response = client.get("/api/pairs")
    assert response.status_code == 200
    assert response.json() == [{"exchange": "gemini", "pair": "BTC-USD"}]


@pytest.mark.asyncio
async def test_stats_endpoint_returns_aggregates(tmp_path: Path) -> None:
    db_path = tmp_path / "stats.sqlite3"
    store = OpportunityStore(str(db_path), batch_size=1, flush_interval_seconds=0.01)
    await store.initialize()
    now_ns = time.time_ns()
    await store.enqueue(
        ArbitrageOpportunity(
            timestamp_ns=now_ns,
            pair="BTC-USD",
            buy_exchange="gemini",
            sell_exchange="coinbase",
            buy_price=Decimal("100"),
            sell_price=Decimal("103"),
            spread_pct=Decimal("3"),
            max_size=Decimal("1"),
            theoretical_profit_usd=Decimal("3"),
        )
    )
    runner = asyncio.create_task(store.run())
    await asyncio.sleep(0.1)
    await store.close()
    runner.cancel()

    client = TestClient(create_app(store, OrderBookManager(), LiveBroadcaster()))
    response = client.get("/api/stats?window=1h")
    assert response.status_code == 200
    body = response.json()
    assert body["count"] == 1
    assert Decimal(body["max_spread_pct"]) == Decimal("3")
    assert Decimal(body["total_theoretical_profit_usd"]) == Decimal("3")


class FakeWebSocket:
    def __init__(self, *, fail_on_send: bool = False) -> None:
        self.fail_on_send = fail_on_send
        self.accepted = False
        self.sent: list[dict[str, object]] = []

    async def accept(self) -> None:
        self.accepted = True

    async def send_json(self, payload: dict[str, object]) -> None:
        if self.fail_on_send:
            raise RuntimeError("client dead")
        self.sent.append(payload)


@pytest.mark.asyncio
async def test_broadcaster_sends_to_all_clients() -> None:
    broadcaster = LiveBroadcaster()
    a, b = FakeWebSocket(), FakeWebSocket()
    await broadcaster.connect(a)  # type: ignore[arg-type]
    await broadcaster.connect(b)  # type: ignore[arg-type]
    await broadcaster.broadcast(LiveMessage(type="opportunity", payload={"pair": "BTC-USD"}))
    assert a.sent == [{"type": "opportunity", "payload": {"pair": "BTC-USD"}}]
    assert b.sent == a.sent


@pytest.mark.asyncio
async def test_broadcaster_drops_dead_clients() -> None:
    broadcaster = LiveBroadcaster()
    healthy, dead = FakeWebSocket(), FakeWebSocket(fail_on_send=True)
    await broadcaster.connect(healthy)  # type: ignore[arg-type]
    await broadcaster.connect(dead)  # type: ignore[arg-type]
    await broadcaster.broadcast(LiveMessage(type="top_of_book", payload={"x": 1}))
    # Dead client must be removed from the pool.
    assert dead not in broadcaster._clients
    assert healthy in broadcaster._clients
    # A second broadcast does not raise even though dead is gone.
    await broadcaster.broadcast(LiveMessage(type="top_of_book", payload={"x": 2}))
    assert len(healthy.sent) == 2


@pytest.mark.asyncio
async def test_broadcaster_with_no_clients_is_noop() -> None:
    broadcaster = LiveBroadcaster()
    # Must not raise.
    await broadcaster.broadcast(LiveMessage(type="opportunity", payload={}))


def test_websocket_route_accepts_connection() -> None:
    client = TestClient(create_app(OpportunityStore(":memory:"), OrderBookManager(), LiveBroadcaster()))
    with client.websocket_connect("/ws/live") as ws:
        # Connection accepted; sending text is allowed by the keepalive loop.
        ws.send_text("ping")
