---
module: order-books
path: 03-Order Books
keywords: l2, sorted-levels, sequence, stale, top-of-book
---

# Order Book State

#module-order-books #pattern-state-machine #test-order-books

## Purpose

`OrderBookManager` maintains an independent L2 book for every `(exchange, pair)` key. It applies snapshots and contiguous deltas, exposes best prices, and marks a book stale whenever continuity or validity is uncertain.

Detection uses `eligibility()`, `eligible_top_of_book()`, and `eligible_books()` rather than raw book access. Eligibility requires initialization, continuity, connection, a recent monotonic receipt time, and a complete uncrossed top-of-book. `set_exchange_connected(False)` clears affected state immediately.

## Key Files

| File | Role |
|---|---|
| `server/arb/orderbook.py` | `SortedLevels`, `OrderBook`, and manager |
| `server/arb/types.py` | events, top-of-book, update result |
| `server/tests/test_orderbook.py` | behavior tests |
| `server/tests/test_orderbook_properties.py` | invariant/property tests |

## Public Interface

`apply(event)`, `set_exchange_connected`, `eligibility`, `eligible_top_of_book`, `eligible_books`, `best_bid`, `best_ask`, `top_of_book`, `snapshot`, `known_pairs`, and `level_snapshot`.

## State Rules

```text
stale/empty --SNAPSHOT--> valid
valid --next sequence--> valid
valid --old sequence--> unchanged
valid --gap--> stale/cleared
valid --crossed book--> stale/cleared
```

Prices are kept in an ascending list plus a price-to-size map. Bids select the last price; asks select the first. A size of zero removes a price level.

## Dependencies

The manager uses only shared types and is called by `main.py`, reconciliation tests, and the API. The detector depends on the manager indirectly through `TopOfBook` values.

## Configuration

No direct configuration. Readiness uses the manager's `TopOfBook.timestamp_ns` and a 30-second window in `api.py`.

## Testing

Run `python -m pytest server/tests/test_orderbook.py server/tests/test_orderbook_properties.py -q`. Important guarantees include snapshot initialization, zero-size removal, isolation by key, rejection of old/gapped deltas, and crossed-book recovery.

## Related Notes

- [[Exchange Adapters]]
- [[Arbitrage Detection]]
- [[Request Flow]]
