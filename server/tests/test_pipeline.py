import asyncio
from decimal import Decimal
from unittest.mock import AsyncMock, Mock

import pytest
from arb import main
from arb.detector import ArbitrageDetector
from arb.orderbook import OrderBookManager
from arb.types import EventKind, LiveMessage, MarketEvent, PriceLevel


def snapshot(exchange: str, bid: str = "100", ask: str = "101") -> MarketEvent:
    return MarketEvent(
        exchange=exchange,
        pair="BTC-USD",
        kind=EventKind.SNAPSHOT,
        sequence=1,
        timestamp_ns=1,
        bids=(PriceLevel(Decimal(bid), Decimal("1")),),
        asks=(PriceLevel(Decimal(ask), Decimal("1")),),
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("enqueue_accepted", [True, False])
async def test_processing_order_and_payloads(monkeypatch, enqueue_accepted) -> None:
    manager = OrderBookManager()
    manager.apply(snapshot("coinbase", "103", "104"))
    manager.apply(snapshot("binance", "105", "106"))
    event = snapshot("gemini")
    detector = ArbitrageDetector(Decimal("0.1"))
    books = Mock(wraps=manager)
    detection = Mock(wraps=detector)
    store = Mock(enqueue=AsyncMock(return_value=enqueue_accepted))
    broadcaster = Mock(broadcast=AsyncMock())
    for name in (
        "book_eligible",
        "events_ingested_total",
        "book_updates_total",
        "book_staleness_seconds",
        "detection_latency_seconds",
        "opportunities_total",
    ):
        metric = Mock()
        monkeypatch.setattr(main, name, metric)
    clock = Mock()
    clock.perf_counter.side_effect = [10.0, 10.25]
    clock.time_ns.return_value = 123
    clock.monotonic_ns.side_effect = [123, 123]
    monkeypatch.setattr(main, "time", clock)

    await main.process_market_event(
        event,
        book_manager=books,
        detector=detection,
        store=store,
        broadcaster=broadcaster,
    )

    pair_books = [
        manager.top_of_book(exchange, event.pair) for exchange in ("gemini", "coinbase", "binance")
    ]
    opportunities = detector.detect_for_pair(event.pair, pair_books, 123)
    assert len(opportunities) == 3
    books.apply.assert_called_once_with(event, received_monotonic_ns=123)
    detection.detect_for_pair.assert_called_once_with("BTC-USD", pair_books, 123)
    assert store.enqueue.await_count == 3
    assert broadcaster.broadcast.await_count == 5
    assert broadcaster.broadcast.await_args_list[0].args == (
        LiveMessage("top_of_book", pair_books[0].as_payload()),
    )
    assert broadcaster.broadcast.await_args_list[1].args[0].type == "book_status"


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", [EventKind.DELTA, EventKind.SNAPSHOT])
async def test_rejected_or_incomplete_event_stops_before_delivery(kind) -> None:
    event = MarketEvent("gemini", "BTC-USD", kind, 1, 1)
    detector = Mock()
    store = Mock(enqueue=AsyncMock())
    broadcaster = Mock(broadcast=AsyncMock())

    await main.process_market_event(
        event,
        book_manager=OrderBookManager(),
        detector=detector,
        store=store,
        broadcaster=broadcaster,
    )

    detector.detect_for_pair.assert_not_called()
    store.enqueue.assert_not_awaited()
    broadcaster.broadcast.assert_awaited_once()
    status_message = broadcaster.broadcast.await_args.args[0]
    assert status_message.type == "book_status"
    assert status_message.payload["eligible"] is False


@pytest.mark.asyncio
@pytest.mark.parametrize("second_exchange", [False, True])
async def test_no_opportunity_still_broadcasts_book(second_exchange) -> None:
    manager = OrderBookManager()
    if second_exchange:
        manager.apply(snapshot("coinbase"))
    store = Mock(enqueue=AsyncMock())
    broadcaster = Mock(broadcast=AsyncMock())

    await main.process_market_event(
        snapshot("gemini"),
        book_manager=manager,
        detector=ArbitrageDetector(Decimal("0.1")),
        store=store,
        broadcaster=broadcaster,
    )

    store.enqueue.assert_not_awaited()
    broadcaster.broadcast.assert_any_await(
        LiveMessage("top_of_book", manager.top_of_book("gemini", "BTC-USD").as_payload())
    )
    assert broadcaster.broadcast.await_count == 2


@pytest.mark.asyncio
async def test_slow_browser_does_not_block_detection() -> None:
    release_send = asyncio.Event()

    class SlowWebSocket:
        async def accept(self) -> None:
            return None

        async def send_json(self, payload: dict[str, object]) -> None:
            await release_send.wait()

        async def close(self, code: int = 1000, reason: str | None = None) -> None:
            return None

    manager = OrderBookManager()
    manager.apply(snapshot("coinbase", "103", "104"))
    manager.apply(snapshot("binance", "105", "106"))
    store = Mock(enqueue=AsyncMock())
    broadcaster = main.LiveBroadcaster(queue_maxsize=1)
    await broadcaster.connect(SlowWebSocket())  # type: ignore[arg-type]

    await asyncio.wait_for(
        main.process_market_event(
            snapshot("gemini"),
            book_manager=manager,
            detector=ArbitrageDetector(Decimal("0.1")),
            store=store,
            broadcaster=broadcaster,
        ),
        timeout=0.1,
    )

    assert store.enqueue.await_count == 3
    release_send.set()


@pytest.mark.asyncio
async def test_consumer_continues_after_rejected_event() -> None:
    rejected = MarketEvent("gemini", "BTC-USD", EventKind.DELTA, 1, 1)
    accepted = snapshot("gemini")

    async def events():
        yield rejected
        yield accepted

    adapter = Mock()
    adapter.connect.return_value = events()
    broadcaster = Mock(broadcast=AsyncMock())
    manager = OrderBookManager()
    await main.consume_adapter(
        adapter,
        book_manager=manager,
        detector=ArbitrageDetector(Decimal("0.1")),
        store=Mock(enqueue=AsyncMock()),
        broadcaster=broadcaster,
    )

    broadcaster.broadcast.assert_any_await(
        LiveMessage("top_of_book", manager.top_of_book("gemini", "BTC-USD").as_payload())
    )
    assert broadcaster.broadcast.await_count == 3


@pytest.mark.asyncio
async def test_event_receipt_time_drives_freshness(monkeypatch) -> None:
    event = MarketEvent(
        **{
            **snapshot("gemini").__dict__,
            "received_monotonic_ns": 1_000,
        }
    )
    clock = Mock()
    clock.monotonic_ns.return_value = 9_000
    clock.perf_counter.side_effect = [1.0, 1.1]
    clock.time_ns.return_value = 123
    monkeypatch.setattr(main, "time", clock)
    for name in (
        "book_eligible",
        "events_ingested_total",
        "book_updates_total",
        "book_staleness_seconds",
        "detection_latency_seconds",
        "opportunities_total",
    ):
        monkeypatch.setattr(main, name, Mock())
    manager = OrderBookManager(clock=lambda: 9_000)

    await main.process_market_event(
        event,
        book_manager=manager,
        detector=ArbitrageDetector(Decimal("0.1")),
        store=Mock(enqueue=AsyncMock()),
        broadcaster=Mock(broadcast=AsyncMock()),
    )

    assert manager.eligibility("gemini", "BTC-USD", 9_000).age_ns == 8_000
    clock.monotonic_ns.assert_called_once_with()


@pytest.mark.asyncio
async def test_processing_delay_can_make_received_event_ineligible(monkeypatch) -> None:
    event = MarketEvent(
        **{
            **snapshot("gemini").__dict__,
            "received_monotonic_ns": 1_000,
        }
    )
    clock = Mock()
    clock.monotonic_ns.return_value = 2_001
    monkeypatch.setattr(main, "time", clock)
    for name in (
        "book_eligible",
        "events_ingested_total",
        "book_updates_total",
        "book_staleness_seconds",
        "detection_latency_seconds",
        "opportunities_total",
    ):
        monkeypatch.setattr(main, name, Mock())
    broadcaster = Mock(broadcast=AsyncMock())
    detector = Mock()

    await main.process_market_event(
        event,
        book_manager=OrderBookManager(max_age_seconds=0.000001),
        detector=detector,
        store=Mock(enqueue=AsyncMock()),
        broadcaster=broadcaster,
    )

    detector.detect_for_pair.assert_not_called()
    broadcaster.broadcast.assert_awaited_once()
    message = broadcaster.broadcast.await_args.args[0]
    assert message.type == "book_status"
    assert message.payload["reason"] == "too_old"


@pytest.mark.asyncio
async def test_background_task_supervisor_records_unexpected_failure(monkeypatch) -> None:
    logged = Mock()
    metric = Mock()
    monkeypatch.setattr(main, "logger", Mock(error=logged))
    monkeypatch.setattr(main, "background_task_failures_total", metric)
    supervisor = main.BackgroundTaskSupervisor()

    async def fail() -> object:
        raise RuntimeError("boom")

    task = supervisor.create("adapter:gemini", fail())
    await asyncio.gather(task, return_exceptions=True)
    await asyncio.sleep(0)

    assert supervisor.failures() == [{"task": "adapter:gemini", "error": "RuntimeError('boom')"}]
    metric.labels.assert_called_once_with(task="adapter:gemini")
    metric.labels.return_value.inc.assert_called_once_with()
    logged.assert_called_once_with(
        "background_task_failed",
        task="adapter:gemini",
        error="RuntimeError('boom')",
    )


@pytest.mark.asyncio
async def test_background_task_supervisor_ignores_shutdown_cancellation() -> None:
    supervisor = main.BackgroundTaskSupervisor()

    async def wait_forever() -> object:
        await asyncio.Event().wait()
        return None

    task = supervisor.create("persistence", wait_forever())
    supervisor.stop()
    task.cancel()
    await asyncio.gather(task, return_exceptions=True)
    await asyncio.sleep(0)

    assert supervisor.failures() == []
