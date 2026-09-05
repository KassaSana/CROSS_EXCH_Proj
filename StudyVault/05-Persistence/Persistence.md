---
module: persistence
path: 05-Persistence
keywords: sqlite, asyncio, batching, queue, statistics
---

# Persistence

#module-persistence #pattern-batched-writes

## Purpose

`OpportunityStore` persists detected opportunities without blocking the detection path. Producers enqueue immutable records; a background task flushes them by batch size or time interval and serves historical aggregate queries.

## Key File

| File | Role |
|---|---|
| `server/arb/persistence.py` | SQLite schema, queue, flush, reports |
| `server/tests/test_persistence.py` | database and batching tests |

## Internal Flow

```text
detector output -> enqueue() -> bounded asyncio.Queue
                               |
                     store.run() timeout/batch
                               v
                         SQLite WAL write
```

The queue is bounded. If it fills, the opportunity is dropped and a Prometheus counter records the loss. Decimal fields are stored as text on insert; report queries cast numeric fields to SQLite `REAL` for aggregation.

## Public Interface

`initialize`, `enqueue`, `run`, `close`, `recent`, `stats`, `extended_stats`, `peak_minute`, and `timeseries`.

## Dependencies

Uses `aiosqlite`, shared opportunity types, and persistence metrics. The API calls the query methods; `main.py` owns the background task lifecycle.

## Configuration

`batch_size`, `flush_interval_seconds`, `queue_maxsize`, and `database_path` are under `[persistence]` and `[server]` in `config.toml`.

## Testing

Run `python -m pytest server/tests/test_persistence.py -q`. Tests should use a file under pytest `tmp_path`; separate `:memory:` connections do not share the same SQLite database.

## Related Notes

- [[Arbitrage Detection]]
- [[API and Observability]]
- [[System Architecture]]
