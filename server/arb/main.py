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
from arb.types import LiveMessage

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


async def run_pipeline() -> None:
    configure_logging()
    config = load_config()
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
    broadcaster = LiveBroadcaster()
    expected_pairs = [
        *(("gemini", normalize_gemini_symbol(symbol)) for symbol in config.exchanges.get("gemini", [])),
        *(("coinbase", normalize_coinbase_symbol(symbol)) for symbol in config.exchanges.get("coinbase", [])),
        *(("binance", normalize_binance_symbol(symbol)) for symbol in config.exchanges.get("binance", [])),
    ]
    app = create_app(store, book_manager, broadcaster, adapters=adapters, expected_pairs=expected_pairs)

    await store.initialize()
    persistence_task = asyncio.create_task(store.run())
    reconcile_task = asyncio.create_task(SnapshotReconciler(adapters, book_manager, expected_pairs).run())

    async def consume_adapter(adapter: ExchangeAdapter) -> None:
        async for event in adapter.connect():
            events_ingested_total.labels(exchange=event.exchange).inc()
            result = book_manager.apply(event)
            if not result.accepted or result.top_of_book is None:
                continue

            book_updates_total.labels(exchange=event.exchange, pair=event.pair).inc()
            book_staleness_seconds.labels(exchange=event.exchange, pair=event.pair).set(0)
            await broadcaster.broadcast(LiveMessage(type="top_of_book", payload=result.top_of_book.as_payload()))
            pair_books = [
                top
                for exchange in ("gemini", "coinbase", "binance")
                if (top := book_manager.top_of_book(exchange, event.pair)) is not None
            ]
            detect_started = time.perf_counter()
            opportunities = detector.detect_for_pair(event.pair, pair_books, time.time_ns())
            detection_latency_seconds.observe(time.perf_counter() - detect_started)
            for opportunity in opportunities:
                opportunities_total.labels(pair=opportunity.pair).inc()
                await store.enqueue(opportunity)
                await broadcaster.broadcast(LiveMessage(type="opportunity", payload=opportunity.as_payload()))

    adapter_tasks = [asyncio.create_task(consume_adapter(adapter)) for adapter in adapters]

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
