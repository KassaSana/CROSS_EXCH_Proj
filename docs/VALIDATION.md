# Validation status

This page records what has been verified and what evidence is still missing. It is
not an implementation checklist; completed design decisions belong in the code,
tests, and focused documents such as [`RESYNC.md`](RESYNC.md).

## Automated verification

Current baseline: 150 backend tests passing as of 2026-09-06.

The suite covers:

- snapshot and delta application
- duplicate, overlapping, out-of-order, and missing exchange updates
- exchange-specific snapshot recovery
- disconnect invalidation and cold-start delta rejection
- stale, incomplete, and crossed-book exclusion
- detection using only eligible venues
- fixture replay for Gemini, Coinbase, and Binance.US
- bounded persistence and WebSocket queues
- WebSocket reconnection and state restoration
- REST, readiness, metrics, persistence, and statistics behavior

CI also runs strict mypy, Ruff, frontend type checking, ESLint, the production
dashboard build, and coverage checks for the order-book and detector modules.

## Synthetic performance

The committed detector and ingest-to-detection measurements are documented in
[`../BENCHMARKS.md`](../BENCHMARKS.md), with raw values in
[`../benchmarks/results.json`](../benchmarks/results.json).

These measurements are local and synthetic. They do not include internet latency or
prove sustained behavior against live exchanges.

## Live observations

Two short live runs validate the observer and the current 60-second book-age limit:

- [`soak_smoke_5m_2026-09-05.md`](../benchmarks/soak_smoke_5m_2026-09-05.md)
- [`soak_validation_60s_window.md`](../benchmarks/soak_validation_60s_window.md)

The five-minute run observed 29,001 Coinbase events, 2,042 Gemini events, and 1,760
Binance.US events with no adapter reconnects or detected sequence gaps. A subsequent
90-second run kept all 27 configured books eligible for every successful sample.

These are smoke tests, not long-duration reliability evidence.

## Remaining validation gap

A documented 24-hour live soak is still required. It should capture:

- memory usage and start-to-end drift
- reconnect and sequence-gap counts per exchange
- book eligibility and maximum update age
- recovery duration after disconnects
- persistence queue drops and WebSocket client overflows
- background-task and observer HTTP failures
- process crashes or restarts

Run the observer as described in [`../BENCHMARKS.md`](../BENCHMARKS.md) and commit the
generated report only after the full run completes.
