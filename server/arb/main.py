from __future__ import annotations

import asyncio
import logging
import os
import time
from decimal import Decimal

import structlog
import uvicorn

from arb.adapters.base import ExchangeAdapter
from arb.adapters.binance import BinanceAdapter, normalize_binance_symbol
from arb.adapters.coinbase import CoinbaseAdapter, normalize_coinbase_symbol
from arb.adapters.gemini import GeminiAdapter, normalize_gemini_symbol
from arb.api import LiveBroadcaster, create_app
from arb.config import load_config
from arb.detector import ArbitrageDetector
from arb.metrics import (
    book_staleness_seconds,
    book_updates_total,
    detection_latency_seconds,
    events_ingested_total,
    opportunities_total,
)
from arb.orderbook import OrderBookManager
from arb.persistence import OpportunityStore
from arb.reconcile import SnapshotReconciler
from arb.types import LiveMessage, MarketEvent

logger = structlog.get_logger(__name__)


def configure_logging() -> None:
    level_name = os.getenv("ARB_LOG_LEVEL", "INFO").upper()
    level = getattr(logging, level_name, logging.INFO)
    logging.basicConfig(level=level, format="%(message)s")
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.stdlib.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(level),
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )


async def process_market_event(
    event: MarketEvent,
    *,
    book_manager: OrderBookManager,
    detector: ArbitrageDetector,
    store: OpportunityStore,
    broadcaster: LiveBroadcaster,
) -> None:
    """Apply one event, publish its book, then detect and deliver opportunities."""
    received_monotonic_ns = time.monotonic_ns()
    events_ingested_total.labels(exchange=event.exchange).inc()
    result = book_manager.apply(event, received_monotonic_ns=received_monotonic_ns)
    if not result.accepted or result.top_of_book is None:
        return

    book_updates_total.labels(exchange=event.exchange, pair=event.pair).inc()
    book_staleness_seconds.labels(exchange=event.exchange, pair=event.pair).set(0)
    await broadcaster.broadcast(LiveMessage(type="top_of_book", payload=result.top_of_book.as_payload()))
    pair_books = book_manager.eligible_books(
        event.pair, ("gemini", "coinbase", "binance"), received_monotonic_ns
    )
    detect_started = time.perf_counter()
    opportunities = detector.detect_for_pair(event.pair, pair_books, time.time_ns())
    detection_latency_seconds.observe(time.perf_counter() - detect_started)
    for opportunity in opportunities:
        opportunities_total.labels(pair=opportunity.pair).inc()
        await store.enqueue(opportunity)
        await broadcaster.broadcast(LiveMessage(type="opportunity", payload=opportunity.as_payload()))


async def consume_adapter(
    adapter: ExchangeAdapter,
    *,
    book_manager: OrderBookManager,
    detector: ArbitrageDetector,
    store: OpportunityStore,
    broadcaster: LiveBroadcaster,
) -> None:
    """Process each normalized event from an adapter in sequence."""
    async for event in adapter.connect():
        await process_market_event(
            event,
            book_manager=book_manager,
            detector=detector,
            store=store,
            broadcaster=broadcaster,
        )


async def run_pipeline() -> None:
    configure_logging()
    config = load_config()
    started_at_holder: list[int] = [time.time_ns()]
    book_manager = OrderBookManager()
    detector = ArbitrageDetector(threshold_pct=Decimal(str(config.detector.threshold_pct)))
    store = OpportunityStore(
        config.server.database_path,
        batch_size=config.persistence.batch_size,
        flush_interval_seconds=config.persistence.flush_interval_seconds,
        queue_maxsize=config.persistence.queue_maxsize,
    )
    adapters = [
        GeminiAdapter(config.exchanges.get("gemini", [])),
        CoinbaseAdapter(config.exchanges.get("coinbase", [])),
        BinanceAdapter(config.exchanges.get("binance", [])),
    ]
    for adapter in adapters:
        adapter.set_connection_state_callback(book_manager.set_exchange_connected)
    broadcaster = LiveBroadcaster()
    expected_pairs = [
        *(("gemini", normalize_gemini_symbol(symbol)) for symbol in config.exchanges.get("gemini", [])),
        *(("coinbase", normalize_coinbase_symbol(symbol)) for symbol in config.exchanges.get("coinbase", [])),
        *(("binance", normalize_binance_symbol(symbol)) for symbol in config.exchanges.get("binance", [])),
    ]
    app = create_app(
        store,
        book_manager,
        broadcaster,
        adapters=adapters,
        expected_pairs=expected_pairs,
        started_at_holder=started_at_holder,
    )

    await store.initialize()
    persistence_task = asyncio.create_task(store.run())
    reconcile_task = asyncio.create_task(SnapshotReconciler(adapters, book_manager, expected_pairs).run())

    adapter_tasks = [
        asyncio.create_task(
            consume_adapter(
                adapter,
                book_manager=book_manager,
                detector=detector,
                store=store,
                broadcaster=broadcaster,
            )
        )
        for adapter in adapters
    ]

    config_uvicorn = uvicorn.Config(app=app, host=config.server.host, port=config.server.port, log_level="info")
    server = uvicorn.Server(config_uvicorn)
    try:
        await server.serve()
    finally:
        for task in adapter_tasks:
            task.cancel()
        reconcile_task.cancel()
        await store.close()
        persistence_task.cancel()


if __name__ == "__main__":
    asyncio.run(run_pipeline())
