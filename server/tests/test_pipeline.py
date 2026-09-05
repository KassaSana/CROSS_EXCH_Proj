from decimal import Decimal
from unittest.mock import AsyncMock, Mock, call

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
    trace = Mock()
    books = Mock(wraps=manager)
    detection = Mock(wraps=detector)
    store = Mock(enqueue=AsyncMock(return_value=enqueue_accepted))
    broadcaster = Mock(broadcast=AsyncMock())
    trace.attach_mock(books, "books")
    trace.attach_mock(detection, "detector")
    trace.attach_mock(store, "store")
    trace.attach_mock(broadcaster, "broadcaster")
    for name in (
        "events_ingested_total",
        "book_updates_total",
        "book_staleness_seconds",
        "detection_latency_seconds",
        "opportunities_total",
    ):
        metric = Mock()
        monkeypatch.setattr(main, name, metric)
        trace.attach_mock(metric, name)
    clock = Mock()
    clock.perf_counter.side_effect = [10.0, 10.25]
    clock.time_ns.return_value = 123
    monkeypatch.setattr(main, "time", clock)
    trace.attach_mock(clock, "clock")

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
    expected = [
        call.events_ingested_total.labels(exchange="gemini"),
        call.events_ingested_total.labels().inc(),
        call.books.apply(event),
        call.book_updates_total.labels(exchange="gemini", pair="BTC-USD"),
        call.book_updates_total.labels().inc(),
        call.book_staleness_seconds.labels(exchange="gemini", pair="BTC-USD"),
        call.book_staleness_seconds.labels().set(0),
        call.broadcaster.broadcast(LiveMessage("top_of_book", pair_books[0].as_payload())),
        call.books.top_of_book("gemini", "BTC-USD"),
        call.books.top_of_book("coinbase", "BTC-USD"),
        call.books.top_of_book("binance", "BTC-USD"),
        call.clock.perf_counter(),
        call.clock.time_ns(),
        call.detector.detect_for_pair("BTC-USD", pair_books, 123),
        call.clock.perf_counter(),
        call.detection_latency_seconds.observe(0.25),
    ]
    for opportunity in opportunities:
        expected.extend(
            [
                call.opportunities_total.labels(pair="BTC-USD"),
                call.opportunities_total.labels().inc(),
                call.store.enqueue(opportunity),
                call.broadcaster.broadcast(LiveMessage("opportunity", opportunity.as_payload())),
            ]
        )
    assert trace.mock_calls == expected
    assert store.enqueue.await_count == 3
    assert broadcaster.broadcast.await_count == 4


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
    broadcaster.broadcast.assert_not_awaited()


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
    broadcaster.broadcast.assert_awaited_once_with(
        LiveMessage("top_of_book", manager.top_of_book("gemini", "BTC-USD").as_payload())
    )


@pytest.mark.asyncio
async def test_broadcast_failure_propagates_before_detection() -> None:
    detector = Mock()
    store = Mock(enqueue=AsyncMock())
    broadcaster = Mock(broadcast=AsyncMock(side_effect=ValueError("send failed")))

    with pytest.raises(ValueError, match="send failed"):
        await main.process_market_event(
            snapshot("gemini"),
            book_manager=OrderBookManager(),
            detector=detector,
            store=store,
            broadcaster=broadcaster,
        )

    detector.detect_for_pair.assert_not_called()
    store.enqueue.assert_not_awaited()


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

    broadcaster.broadcast.assert_awaited_once_with(
        LiveMessage("top_of_book", manager.top_of_book("gemini", "BTC-USD").as_payload())
    )
