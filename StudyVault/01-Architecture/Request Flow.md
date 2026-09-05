---
module: architecture
path: 01-Architecture
keywords: request-flow, event-flow, websocket, lifecycle
---

# Request and Event Flow

#arch-request-flow #pattern-event-driven

## Startup Flow

```text
arb.main
  -> load_config()
  -> create OrderBookManager, Detector, Store, Adapters, Broadcaster
  -> create FastAPI app
  -> initialize SQLite
  -> start persistence and reconciliation tasks
  -> start one consumer task per adapter
  -> serve HTTP/WebSocket API
```

## Market Event Flow

1. An adapter connects, resets connection-local sequence state, and subscribes.
2. A raw message is parsed into one or more `MarketEvent` objects.
3. The adapter emits an initial snapshot or fetches one when sequence state is unsafe.
4. `main.consume_adapter` applies the event to the matching `(exchange, pair)` book and records local monotonic receipt time.
5. Rejected events stop at the book boundary; accepted events produce a `TopOfBook` broadcast.
6. `OrderBookManager.eligible_books` filters for initialized, continuous, connected, recent, complete books; only those are passed to `detect_for_pair`.
7. Each qualifying opportunity is queued for SQLite and broadcast to clients.

## HTTP/WebSocket Flow

The browser loads historical data through `dashboard/src/api/client.ts`. It then opens `/ws/live`; each JSON message has a `type` and `payload`. The hook merges `top_of_book` messages into live book state and prepends opportunity messages to the feed.

## Recovery Flow

```text
sequence gap
  -> adapter increments gap counter
  -> adapter fetches REST snapshot
  -> synthetic SNAPSHOT event
  -> OrderBookManager replaces book
  -> future deltas resume
```

## Related Notes

- [[System Architecture]]
- [[Exchange Adapters]]
- [[API and Observability]]
