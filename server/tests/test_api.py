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
from conftest import wait_for_rows
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
    assert response.json()[0]["timestamp_ns"] == "1"


def test_healthz_is_alive() -> None:
    client = TestClient(
        create_app(OpportunityStore(":memory:"), OrderBookManager(), LiveBroadcaster())
    )
    response = client.get("/healthz")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


@pytest.mark.parametrize("limit", [0, 501])
def test_recent_endpoint_rejects_out_of_range_limits(limit: int) -> None:
    client = TestClient(
        create_app(OpportunityStore(":memory:"), OrderBookManager(), LiveBroadcaster())
    )

    assert client.get(f"/api/opportunities/recent?limit={limit}").status_code == 422


@pytest.mark.parametrize(
    "path",
    [
        "/api/stats?window=forever",
        "/api/system/stats?window=forever",
        "/api/system/timeseries?window=forever",
        "/api/system/timeseries?bucket_seconds=0",
        "/api/system/timeseries?bucket_seconds=86401",
    ],
)
def test_statistics_endpoints_reject_invalid_query_values(path: str) -> None:
    client = TestClient(
        create_app(OpportunityStore(":memory:"), OrderBookManager(), LiveBroadcaster())
    )

    assert client.get(path).status_code == 422


def test_metrics_endpoint_exposes_prometheus_payload() -> None:
    client = TestClient(
        create_app(OpportunityStore(":memory:"), OrderBookManager(), LiveBroadcaster())
    )
    response = client.get("/metrics")
    assert response.status_code == 200
    assert "arb_ws_clients" in response.text


def test_adapter_status_returns_runtime_fields() -> None:
    adapter = StubAdapter(["BTC-USD"])
    adapter.connected = True
    adapter.last_message_ns = time.time_ns()
    adapter.reconnect_count = 2
    adapter.last_error = "socket reset"

    client = TestClient(
        create_app(
            OpportunityStore(":memory:"), OrderBookManager(), LiveBroadcaster(), adapters=[adapter]
        )
    )
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
    assert body["stale_pairs"] == [
        {
            "exchange": "stub",
            "pair": "BTC-USD",
            "initialized": False,
            "continuous": False,
            "connected": True,
            "age_ms": None,
            "max_age_ms": 30_000,
            "eligible": False,
            "reason": "missing",
        }
    ]


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
        "background_task_failures": [],
    }


def test_readyz_reports_background_task_failures() -> None:
    client = TestClient(
        create_app(
            OpportunityStore(":memory:"),
            OrderBookManager(),
            LiveBroadcaster(),
            background_failures=lambda: [
                {"task": "adapter:gemini", "error": "RuntimeError('boom')"}
            ],
        )
    )

    response = client.get("/readyz")

    assert response.status_code == 503
    assert response.json()["background_task_failures"] == [
        {"task": "adapter:gemini", "error": "RuntimeError('boom')"}
    ]


def test_book_status_uses_canonical_eligibility_payload() -> None:
    manager = OrderBookManager(max_age_seconds=12.5, clock=lambda: 1_000)
    manager.apply(
        MarketEvent(
            exchange="stub",
            pair="BTC-USD",
            kind=EventKind.SNAPSHOT,
            sequence=1,
            timestamp_ns=1,
            bids=(PriceLevel(price=Decimal("100"), size=Decimal("1")),),
            asks=(PriceLevel(price=Decimal("101"), size=Decimal("1")),),
        ),
        received_monotonic_ns=1_000,
    )
    client = TestClient(
        create_app(
            OpportunityStore(":memory:"),
            manager,
            LiveBroadcaster(),
            expected_pairs=[("stub", "BTC-USD")],
        )
    )

    assert client.get("/api/book-status").json() == [
        {
            "exchange": "stub",
            "pair": "BTC-USD",
            "initialized": True,
            "continuous": True,
            "connected": True,
            "age_ms": 0,
            "max_age_ms": 12_500,
            "eligible": True,
            "reason": None,
        }
    ]


def test_window_to_ns_known_and_unknown_values() -> None:
    from arb.api import window_to_ns

    assert window_to_ns("1h") == 3_600_000_000_000
    assert window_to_ns("4h") == 14_400_000_000_000
    assert window_to_ns("24h") == 86_400_000_000_000
    assert window_to_ns("1d") == 86_400_000_000_000
    assert window_to_ns("72h") == 259_200_000_000_000
    assert window_to_ns("1w") == 604_800_000_000_000
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
        self.closed = False
        self.sent: list[dict[str, object]] = []

    async def accept(self) -> None:
        self.accepted = True

    async def send_json(self, payload: dict[str, object]) -> None:
        if self.fail_on_send:
            raise RuntimeError("client dead")
        self.sent.append(payload)

    async def close(self, code: int = 1000, reason: str | None = None) -> None:
        self.closed = True


@pytest.mark.asyncio
async def test_broadcaster_sends_to_all_clients() -> None:
    broadcaster = LiveBroadcaster()
    a, b = FakeWebSocket(), FakeWebSocket()
    await broadcaster.connect(a)  # type: ignore[arg-type]
    await broadcaster.connect(b)  # type: ignore[arg-type]
    await broadcaster.broadcast(LiveMessage(type="opportunity", payload={"pair": "BTC-USD"}))
    await asyncio.sleep(0)
    assert a.sent == [
        {
            "type": "opportunity",
            "payload": {"pair": "BTC-USD"},
            "stream_sequence": 1,
        }
    ]
    assert b.sent == a.sent


@pytest.mark.asyncio
async def test_broadcaster_drops_dead_clients() -> None:
    broadcaster = LiveBroadcaster()
    healthy, dead = FakeWebSocket(), FakeWebSocket(fail_on_send=True)
    await broadcaster.connect(healthy)  # type: ignore[arg-type]
    await broadcaster.connect(dead)  # type: ignore[arg-type]
    await broadcaster.broadcast(LiveMessage(type="top_of_book", payload={"x": 1}))
    await asyncio.sleep(0)
    # Dead client must be removed from the pool.
    assert dead not in broadcaster._clients
    assert healthy in broadcaster._clients
    # A second broadcast does not raise even though dead is gone.
    await broadcaster.broadcast(LiveMessage(type="top_of_book", payload={"x": 2}))
    await asyncio.sleep(0)
    assert len(healthy.sent) == 2


@pytest.mark.asyncio
async def test_broadcaster_with_no_clients_is_noop() -> None:
    broadcaster = LiveBroadcaster()
    # Must not raise.
    await broadcaster.broadcast(LiveMessage(type="opportunity", payload={}))


def test_websocket_route_accepts_connection() -> None:
    client = TestClient(
        create_app(OpportunityStore(":memory:"), OrderBookManager(), LiveBroadcaster())
    )
    with client.websocket_connect("/ws/live") as ws:
        snapshot = ws.receive_json()
        assert snapshot["type"] == "state_snapshot"
        assert snapshot["payload"] == {"books": [], "statuses": []}
        assert snapshot["stream_sequence"] == 1
        ws.send_text("ping")


def test_websocket_connection_restores_only_current_eligible_books() -> None:
    manager = OrderBookManager(clock=lambda: 1_000)
    manager.apply(
        MarketEvent(
            exchange="stub",
            pair="BTC-USD",
            kind=EventKind.SNAPSHOT,
            sequence=4,
            timestamp_ns=99,
            bids=(PriceLevel(price=Decimal("100"), size=Decimal("1")),),
            asks=(PriceLevel(price=Decimal("101"), size=Decimal("2")),),
        ),
        received_monotonic_ns=1_000,
    )
    app = create_app(
        OpportunityStore(":memory:"),
        manager,
        LiveBroadcaster(),
        expected_pairs=[("stub", "BTC-USD"), ("stub", "ETH-USD")],
    )

    with TestClient(app).websocket_connect("/ws/live") as ws:
        snapshot = ws.receive_json()

    assert snapshot["type"] == "state_snapshot"
    assert snapshot["payload"]["books"] == [
        {
            "exchange": "stub",
            "pair": "BTC-USD",
            "best_bid_price": "100",
            "best_bid_size": "1",
            "best_ask_price": "101",
            "best_ask_size": "2",
            "sequence": 4,
            "timestamp_ns": "99",
        }
    ]
    assert [status["eligible"] for status in snapshot["payload"]["statuses"]] == [True, False]


@pytest.mark.asyncio
async def test_initial_state_is_ordered_before_live_updates() -> None:
    broadcaster = LiveBroadcaster()
    websocket = FakeWebSocket()
    await broadcaster.connect(
        websocket,  # type: ignore[arg-type]
        lambda: LiveMessage(type="state_snapshot", payload={"books": []}),
    )
    await broadcaster.broadcast(LiveMessage(type="top_of_book", payload={"sequence": 2}))
    await asyncio.sleep(0)

    assert [message["type"] for message in websocket.sent] == [
        "state_snapshot",
        "top_of_book",
    ]
    assert [message["stream_sequence"] for message in websocket.sent] == [1, 2]


@pytest.mark.asyncio
async def test_slow_client_queue_overflow_does_not_block_broadcast() -> None:
    release_send = asyncio.Event()

    class SlowWebSocket(FakeWebSocket):
        async def send_json(self, payload: dict[str, object]) -> None:
            await release_send.wait()
            await super().send_json(payload)

    broadcaster = LiveBroadcaster(queue_maxsize=1)
    slow = SlowWebSocket()
    await broadcaster.connect(slow)  # type: ignore[arg-type]
    await broadcaster.broadcast(LiveMessage(type="top_of_book", payload={"sequence": 1}))
    await asyncio.sleep(0)
    await broadcaster.broadcast(LiveMessage(type="top_of_book", payload={"sequence": 2}))

    await asyncio.wait_for(
        broadcaster.broadcast(LiveMessage(type="top_of_book", payload={"sequence": 3})),
        timeout=0.1,
    )
    await asyncio.sleep(0)

    assert slow not in broadcaster._clients
    assert slow.closed is True
    release_send.set()


def _seed_opp(store: OpportunityStore, **kwargs: Any) -> ArbitrageOpportunity:
    defaults: dict[str, Any] = dict(
        timestamp_ns=time.time_ns(),
        pair="BTC-USD",
        buy_exchange="gemini",
        sell_exchange="coinbase",
        buy_price=Decimal("100"),
        sell_price=Decimal("103"),
        spread_pct=Decimal("3"),
        max_size=Decimal("1"),
        theoretical_profit_usd=Decimal("3"),
    )
    defaults.update(kwargs)
    return ArbitrageOpportunity(**defaults)


@pytest.mark.asyncio
async def test_system_overview_reports_uptime_and_started_at(tmp_path: Path) -> None:
    store = OpportunityStore(str(tmp_path / "ov.sqlite3"))
    await store.initialize()
    started_at_holder = [time.time_ns() - 5_000_000_000]  # started 5s ago
    client = TestClient(
        create_app(
            store, OrderBookManager(), LiveBroadcaster(), started_at_holder=started_at_holder
        )
    )
    response = client.get("/api/system/overview")
    assert response.status_code == 200
    body = response.json()
    assert body["started_at_ns"] == str(started_at_holder[0])
    assert body["uptime_seconds"] >= 5
    assert body["all_time_count"] == 0
    assert body["all_time_peak_minute"] is None


@pytest.mark.asyncio
async def test_system_stats_endpoint_returns_extended_aggregates(tmp_path: Path) -> None:
    store = OpportunityStore(
        str(tmp_path / "sys.sqlite3"), batch_size=10, flush_interval_seconds=0.05
    )
    await store.initialize()
    runner = asyncio.create_task(store.run())
    now = time.time_ns()
    await store.enqueue(_seed_opp(store, timestamp_ns=now, spread_pct=Decimal("2"), pair="BTC-USD"))
    await store.enqueue(
        _seed_opp(store, timestamp_ns=now - 1, spread_pct=Decimal("4"), pair="BTC-USD")
    )
    await store.enqueue(
        _seed_opp(store, timestamp_ns=now - 2, spread_pct=Decimal("1"), pair="ETH-USD")
    )
    await wait_for_rows(store, 3)
    await store.close()
    runner.cancel()

    client = TestClient(create_app(store, OrderBookManager(), LiveBroadcaster()))
    response = client.get("/api/system/stats?window=1h")
    assert response.status_code == 200
    body = response.json()
    assert body["window"] == "1h"
    assert body["count"] == 3
    assert Decimal(body["max_spread_pct"]) == Decimal("4")
    assert body["top_pair"] == "BTC-USD"
    assert body["peak_minute"] is not None


@pytest.mark.asyncio
async def test_system_timeseries_endpoint_returns_buckets(tmp_path: Path) -> None:
    store = OpportunityStore(
        str(tmp_path / "ts.sqlite3"), batch_size=10, flush_interval_seconds=0.05
    )
    await store.initialize()
    runner = asyncio.create_task(store.run())
    bucket_ns = 60 * 1_000_000_000
    base = (time.time_ns() // bucket_ns) * bucket_ns
    await store.enqueue(_seed_opp(store, timestamp_ns=base))
    await store.enqueue(_seed_opp(store, timestamp_ns=base + bucket_ns))
    await wait_for_rows(store, 2)
    await store.close()
    runner.cancel()

    client = TestClient(create_app(store, OrderBookManager(), LiveBroadcaster()))
    response = client.get("/api/system/timeseries?window=1h&bucket_seconds=60")
    assert response.status_code == 200
    body = response.json()
    assert body["window"] == "1h"
    assert body["bucket_seconds"] == 60
    assert len(body["points"]) >= 1
    assert isinstance(body["points"][0]["bucket_start_ns"], str)


@pytest.mark.asyncio
async def test_system_reset_zeros_uptime_without_clearing_history(tmp_path: Path) -> None:
    store = OpportunityStore(str(tmp_path / "reset.sqlite3"))
    await store.initialize()
    started_at_holder = [time.time_ns() - 60_000_000_000]  # started 60s ago
    client = TestClient(
        create_app(
            store, OrderBookManager(), LiveBroadcaster(), started_at_holder=started_at_holder
        )
    )
    before = client.get("/api/system/overview").json()
    assert before["uptime_seconds"] >= 60

    reset = client.post("/api/system/reset")
    assert reset.status_code == 200
    assert reset.json()["uptime_seconds"] == 0

    after = client.get("/api/system/overview").json()
    assert after["uptime_seconds"] < 5
    assert after["started_at_ns"] > before["started_at_ns"]
    # Holder is mutated so subsequent endpoints see the new start.
    assert str(started_at_holder[0]) == after["started_at_ns"]


@pytest.mark.asyncio
async def test_system_endpoints_handle_empty_store(tmp_path: Path) -> None:
    store = OpportunityStore(str(tmp_path / "empty.sqlite3"))
    await store.initialize()
    client = TestClient(create_app(store, OrderBookManager(), LiveBroadcaster()))

    overview = client.get("/api/system/overview").json()
    assert overview["all_time_count"] == 0
    assert overview["all_time_peak_minute"] is None

    stats = client.get("/api/system/stats?window=1w").json()
    assert stats["count"] == 0
    assert stats["top_pair"] is None
    assert stats["peak_minute"] is None

    ts = client.get("/api/system/timeseries?window=1h&bucket_seconds=60").json()
    assert ts["points"] == []
