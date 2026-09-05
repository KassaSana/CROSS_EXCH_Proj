---
module: exercises
path: 09-Exercises
keywords: practice, onboarding, code-reading, debugging
---

# ArbSync — Onboarding Exercises

#practice #onboarding

These exercises are for active recall. Try answering before opening each answer.

## Adapters

1. Trace one Gemini WebSocket message from `parse_message` to `main.consume_adapter`.
> [!answer]- View Answer
> `GeminiAdapter.parse_message` builds or emits a `MarketEvent`; `connect` yields it; `consume_adapter` applies it to `OrderBookManager`.

2. Why does Binance assign a local per-pair sequence?
> [!answer]- View Answer
> Binance depth messages carry update ranges whose IDs can jump, so treating each `u` as a contiguous per-event sequence creates false gaps.

3. What happens after a generic adapter sequence gap?
> [!answer]- View Answer
> The adapter increments its gap counter, fetches a REST snapshot, records its sequence, and emits the snapshot so the book gets a clean boundary.

4. Where would you inspect a reconnect loop that never recovers?
> [!answer]- View Answer
> Start in `base.py:connect`, then check `last_error`, adapter status, WebSocket URL, subscription payload, and snapshot endpoint.

5. How would you add a fourth exchange?
> [!answer]- View Answer
> Add an adapter subclass, normalization/parser/snapshot tests, instantiate it in `main.py`, add symbols to `config.toml`, and include replay coverage.

## Order Books

6. Why is a delta rejected when the book is stale?
> [!answer]- View Answer
> Without a trusted sequence chain, applying the delta could create an incorrect book; a fresh snapshot must establish state first.

7. How are best bid and best ask selected?
> [!answer]- View Answer
> Prices are stored ascending; bids use the last price and asks use the first price.

8. What does size zero mean?
> [!answer]- View Answer
> It removes that price level from the side.

9. Why does a crossed book clear itself?
> [!answer]- View Answer
> A bid at or above the ask violates expected book validity, so the manager discards potentially corrupt state and waits for a snapshot.

10. What test proves exchange and pair state is isolated?
> [!answer]- View Answer
> `test_multiple_pairs_and_exchanges_are_isolated` applies snapshots to different keys and checks unrelated lookups remain empty.

## Detection

11. Which prices are used for an opportunity?
> [!answer]- View Answer
> Buy at the source book's best ask and sell at the destination book's best bid.

12. Why are permutations used?
> [!answer]- View Answer
> Arbitrage is directional; buying on A and selling on B differs from buying on B and selling on A.

13. How is maximum tradable size calculated?
> [!answer]- View Answer
> It is the smaller of the buy ask size and sell bid size.

14. What does `threshold_pct = 0.1` mean?
> [!answer]- View Answer
> The price difference must be at least 0.1 percent after comparing sell bid to buy ask.

15. What important real-world costs are absent?
> [!answer]- View Answer
> Fees, slippage, withdrawal/transfer costs, latency, inventory limits, and execution risk.

## Persistence

16. Why is writing queued instead of done inline?
> [!answer]- View Answer
> SQLite I/O could delay market-event processing; batching keeps the hot detection path responsive.

17. What happens when the persistence queue is full?
> [!answer]- View Answer
> `enqueue` returns false, drops the opportunity, and increments `persistence_queue_drops_total`.

18. Why are Decimal fields stored as text?
> [!answer]- View Answer
> Text preserves exact decimal representation and avoids binary float drift at storage boundaries.

19. When does `store.run` flush a batch?
> [!answer]- View Answer
> When the batch reaches `batch_size` or when the flush interval timeout fires.

20. What is a common SQLite test trap here?
> [!answer]- View Answer
> Separate `:memory:` connections do not share state, so tests should use a file path such as pytest `tmp_path`.

## API and Dashboard

21. What makes `/readyz` different from `/healthz`?
> [!answer]- View Answer
> Health only says the process responds; readiness requires connected adapters and fresh top-of-book data for tracked pairs.

22. What two message types does the live stream send?
> [!answer]- View Answer
> `top_of_book` and `opportunity`.

23. Why does the browser load REST data before WebSocket data?
> [!answer]- View Answer
> REST provides an initial historical/current view; WebSocket then supplies incremental live updates.

24. Where would you debug a dashboard with stale cards but a healthy backend?
> [!answer]- View Answer
> Inspect `useWebSocket.ts`, the message type/payload shape, client state updates, and browser network/WebSocket logs.

25. How does the API remove dead WebSocket clients?
> [!answer]- View Answer
> Broadcast catches a `RuntimeError`, collects that socket, removes it from the client set, and updates the client gauge.

## Runtime and Architecture

26. Which function is the composition root?
> [!answer]- View Answer
> `server/arb/main.py:run_pipeline` constructs and wires the major components and background tasks.

27. Why does the detector run only for the affected pair?
> [!answer]- View Answer
> A market event changes one exchange/pair, so checking that pair avoids unnecessary comparisons for unrelated symbols.

28. What happens during shutdown?
> [!answer]- View Answer
> Adapter tasks and reconciliation are cancelled, the store is closed, and the persistence task is cancelled after its lifecycle is ended.

29. Where is periodic snapshot reconciliation implemented?
> [!answer]- View Answer
> `SnapshotReconciler` cycles through configured targets, compares the top ten live levels with a REST snapshot, and records large mismatches.

30. What is the end-to-end invariant you care about most?
> [!answer]- View Answer
> Only contiguous, valid market state should produce a top-of-book; only qualifying comparisons should produce opportunities; persistence and UI should observe those results without blocking ingestion.

## Related Notes

- [[System Architecture]]
- [[Request Flow]]
- [[Exchange Adapters]]
- [[Order Book State]]
- [[Arbitrage Detection]]
- [[Persistence]]
- [[API and Observability]]
- [[React Dashboard]]
