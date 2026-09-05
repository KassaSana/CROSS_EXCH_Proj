---
module: architecture
path: 01-Architecture
keywords: pipeline, asyncio, event-driven, data-flow
---

# System Architecture

#arch-pipeline #pattern-event-driven

## Purpose

ArbSync is a single-process, single-event-loop system. Exchange adapters turn venue-specific public market data into common events. The runtime applies those events to in-memory books, detects theoretical arbitrage, writes opportunities asynchronously, and broadcasts live state.

## Architecture

```text
Gemini / Coinbase / Binance WebSockets
                |
                v
       ExchangeAdapter.connect()
                |
                v
        normalized MarketEvent
                |
                v
       OrderBookManager.apply()
                |
                v
       TopOfBook for affected pair
          /                 \
         v                   v
  ArbitrageDetector     LiveBroadcaster
         |                   |
         v                   v
 OpportunityStore       React dashboard
         |
         v
       SQLite
```

## Boundaries

- Adapters own exchange protocol details and sequence recovery.
- `types.py` defines the language shared between adapters and downstream consumers.
- `OrderBookManager` owns mutable book state and rejects unsafe deltas.
- The detector is pure calculation over `TopOfBook` values.
- Persistence owns queueing, batching, schema, and historical queries.
- FastAPI exposes state; it does not perform market processing.

## Key Tradeoffs

- SQLite keeps deployment simple for one process.
- Async tasks fit I/O-heavy feeds and avoid blocking the event loop.
- Adapter-driven snapshot resync is simpler than buffering uncertain deltas.
- Decimal values preserve price arithmetic and are serialized as strings.

## Related Notes

- [[Request Flow]]
- [[Exchange Adapters]]
- [[Order Book State]]
