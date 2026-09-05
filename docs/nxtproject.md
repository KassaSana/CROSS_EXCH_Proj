# Order book trust and recovery

**The rule:** a book is eligible for detection only when we know how it was
initialized, that its updates are continuous, and that its data is recent
enough.

Reconnecting is only part of recovery. The system must stop using questionable
data immediately and rebuild trusted state before resuming.

Protocol details stay inside the adapters; their consumers share one eligibility
rule.

## Status at a glance

| Item | State | Where |
| --- | --- | --- |
| 1a. Binance.US snapshot-and-buffer | DONE | `server/arb/adapters/binance.py` |
| 1b. Coinbase sequencing | DONE | `server/arb/adapters/coinbase.py` |
| 1c. Gemini migration | DONE | `server/arb/adapters/gemini.py` |
| 2. Explicit book eligibility | DONE | `server/arb/orderbook.py`, `server/arb/main.py` |
| 3a. Dashboard reconnect | NOT STARTED | `dashboard/src/hooks/useWebSocket.ts` |
| 3b. Backend state restore on connect | NOT STARTED | `server/arb/api.py` |
| 4a. Bounded per-client queues | NOT STARTED | `server/arb/api.py` |
| 4b. Background task visibility | NOT STARTED | `server/arb/main.py` |
| Proof: fixture-driven failure cases | MOSTLY DONE | `server/tests/` |
| Proof: live soak | NOT STARTED | - |

Baseline: 127 tests passing as of 2026-09-05.

## 1. Correct sequence handling inside each adapter

Exchange update IDs validate the exchange's protocol inside the adapter. A local
event sequence is what `OrderBookManager` checks on the normalized stream. Local
numbering is fine only after exchange continuity has been established.

### 1a. Binance.US - DONE (commits 55fdf35, 510a58e)

`server/arb/adapters/binance.py` follows the documented procedure: it buffers
depth updates while the REST snapshot is in flight (`_buffers`), aligns the
snapshot's `lastUpdateId` against the buffered `U/u` ranges, discards updates
already covered, applies the rest in order, and restarts synchronization when an
update starts beyond the next expected ID.

The buffer is bounded at `max_buffered_updates = 1_000`. Overflow, snapshot
failure, and a snapshot that never catches up all abort synchronization and
reconnect rather than silently declaring the book synchronized.

13 dedicated tests in `server/tests/test_adapters/test_adapters.py`.

### 1b. Coinbase - DONE (commits f54e084, f6a3d15)

`server/arb/adapters/coinbase.py`:

- The confirmed parsing bug is fixed - `sequence_num` is read from the outer
  envelope and preserved while processing nested `events`.
- Books initialize from the Level 2 stream's own snapshot; a delta for an
  uninitialized product is refused and triggers a reconnect.
- Envelope sequence continuity is validated at connection scope
  (`_accept_envelope_sequence`), with events grouped per `product_id` and
  combined into one `MarketEvent` per product per envelope.
- On a gap or lost continuity the adapter resubscribes and waits for a fresh
  stream snapshot. REST Exchange sequence numbers are never substituted for
  Advanced Trade WebSocket sequence numbers.
- `heartbeats` is now subscribed alongside `level2`.

Supporting work: `server/scripts/_capture_coinbase_shape.py` (the multi-product
envelope capture used to verify real behaviour before committing to a strict gap
rule), a regenerated `server/tests/fixtures/recorded/coinbase_btcusd_5min.jsonl`,
and 10 tests covering multiple products and multiple events in one envelope.

Left deliberately open: the "Coinbase receives very few events in production"
quirk in `CLAUDE.md` predates this fix and has not been re-measured against a
live run. Check it during the soak.

### 1c. Gemini - DONE

`server/arb/adapters/gemini.py` now uses the current `wss://ws.gemini.com`
differential depth stream with `snapshot=-1`. The first `depthUpdate` for each
pair is emitted as the full snapshot; subsequent frames validate Gemini's
`U/u` exchange update ranges before being assigned consecutive local sequences.
Duplicate or covered frames are ignored, while a skipped range invalidates the
pair and requests a reconnect so a new stream snapshot rebuilds it.

The REST book endpoint remains only for `SnapshotReconciler` comparisons. It is
no longer part of stream initialization or recovery. Protocol-shaped Gemini
fixtures and adapter tests cover subscription shape, initial snapshot, overlap,
duplicates, gaps, and resnapshot after reconnect.

## 2. Make book eligibility explicit - DONE (commits 71efe94, e52c6bf)

| Condition | Eligible for detection? |
| --- | --- |
| Connected, initialized, continuous, sufficiently recent | Yes |
| Waiting for initial snapshot | No |
| Sequence gap or disconnected feed | No, immediately |
| Otherwise valid book exceeds the age limit | No |
| Reconnected but still rebuilding | No |

Implemented in `OrderBookManager.eligibility()` (`server/arb/orderbook.py:180`),
which returns a `BookEligibility` with an explicit reason: `missing`,
`disconnected`, `uninitialized`, `discontinuous`, `too_old`, `incomplete`, or
`crossed`.

Responsibilities landed as designed:

- **Adapter** reports loss of continuity (`request_reconnect`) and connection
  state (`set_connection_state_callback`, `server/arb/adapters/base.py`).
- **`OrderBookManager.set_exchange_connected()`** clears affected books
  immediately and rejects deltas until a new snapshot arrives - invalidation
  reaches the manager on the disconnect itself, not on the next market event, so
  a reconnect cannot make an old book eligible again.
- **`process_market_event()`** (`server/arb/main.py:61-92`) stamps receipt time
  before processing delays, evaluates eligibility once, and passes only eligible
  books to the detector.
- **Detector** is unchanged; it computes spreads from what it is handed.

Freshness: `MarketEvent.received_monotonic_ns` is stamped in
`ExchangeAdapter.stream_events()` before parsing; ages use `time.monotonic_ns`;
`max_age_seconds` is configurable (`config.toml:20`, currently 30.0, matching the
existing readiness threshold). `eligible_books()` requires at least two eligible
exchange books before returning any.

The same decision is reused by detection, `/book-status`, `/readyz`, and the
`book_eligible` / `book_staleness_seconds` metrics via `eligibility_for()`
(`server/arb/api.py:125`).

Still open as a tuning task: measure how often the age cutoff excludes a quiet
but valid market, then tune it explicitly rather than by inheritance.

## 3. Reconnect the dashboard and restore its state

### 3a. Dashboard reconnect - NOT STARTED

`dashboard/src/hooks/useWebSocket.ts` is still 19 lines: it opens one socket and
never retries. Extend that same hook with:

- Connection status: connecting, connected, reconnecting.
- Exponential retry delays with jitter, capped at 30 seconds.
- One active socket and one retry timer.
- Cleanup that prevents retries after unmount.
- Protection against callbacks from an old socket updating current state.
- Retry-counter reset after a stable connection.

### 3b. Backend state restore on connect - NOT STARTED

`/ws/live` (`server/arb/api.py:166`) accepts the socket and loops on
`receive_text`. It sends no current state.

On disconnection the dashboard should mark cached books unavailable. On
reconnection the backend should send current eligible books before subsequent
live updates, with explicit ordering so an older snapshot cannot overwrite newer
data.

Note this is partially masked today: `dashboard/src/pages/Dashboard.tsx` polls
`/book-status` every 2 seconds and drops cached books that are no longer
eligible, so the UI self-corrects within a couple of seconds. That is a
workaround, not the ordering guarantee.

Historical opportunities and statistics can be refreshed over HTTP. The
initial-history request must not overwrite opportunities received while that
request was pending. This restores the current view; it does not recover every
missed live opportunity.

## 4. Keep dashboard problems from damaging ingestion

### 4a. Bounded per-client queues - NOT STARTED

`LiveBroadcaster.broadcast` (`server/arb/api.py:46`) awaits `client.send_json`
inline for each client, so a slow browser back-pressures exchange ingestion.

Give each dashboard client a bounded outgoing queue and a sender task. A slow
client gets disconnected and resynchronizes; it cannot hold up processing. This
is a concrete reason for a queue without introducing a broker.

Note: `test_broadcast_failure_propagates_before_detection` currently asserts the
existing inline coupling and will need to change with this work.

### 4b. Background task visibility - NOT STARTED

`server/arb/main.py:167-171` creates the persistence, reconcile, and adapter
tasks with no `add_done_callback`. A crashed task fails silently. Failures should
surface immediately through logs and readiness status.

## How we prove it works

Covered today by recorded protocol-shaped messages and controlled failures:

- Missing, duplicate, overlapping, and out-of-order exchange updates.
- Snapshot retrieval while new updates arrive (Binance buffering tests).
- Disconnect followed by deltas before a replacement snapshot
  (`test_disconnect_invalidates_book_until_new_snapshot`,
  `test_cold_start_delta_is_rejected_until_snapshot`).
- A stale venue offering the best apparent price contributing no opportunity
  (`test_book_becomes_ineligible_when_age_limit_is_exceeded`,
  `test_processing_delay_can_make_received_event_ineligible`).
- Healthy remaining venues continuing detection
  (`test_consumer_continues_after_rejected_event`).
- Replay fixtures for all three exchanges (`server/tests/test_replay.py`).

Not yet covered:

- Dashboard disconnect/reconnect without duplicate sockets or stale-state
  overwrite (blocked on 3a).
- A slow browser leaving exchange ingestion unaffected (blocked on 4a).
- A live soak test tracking resyncs, excluded books, update age, task failures,
  and recovery duration.

## Next up

**Start here: dashboard reconnect (3a) plus backend state restore (3b).** Do
these together so reconnecting cannot leave the UI showing stale state.

1. **Dashboard reconnect (3a) plus backend state restore (3b)** - do these
   together; a reconnect without a state refresh just shows stale books.
2. **Broadcaster queues (4a) and task supervision (4b)** - note 4a requires
   rewriting `test_broadcast_failure_propagates_before_detection`, which
   currently pins the inline coupling.
3. **Live soak run and threshold tuning** - includes re-measuring the Coinbase
   event-volume quirk and the 30s age cutoff's exclusion rate.

### Picking this up in a fresh session

- Read this file first; it is the state of record for the plan.
- `git log --oneline -8` shows the work already landed.
- Verify the baseline before changing anything, from the repo root:
  `.venv/Scripts/python.exe -m pytest -q server/tests` (127 passing),
  `.venv/Scripts/python.exe -m mypy --strict server/arb`,
  `.venv/Scripts/python.exe -m ruff check server`.
- Update the status table and the section tag in this file as part of the same
  commit as the code change, so the tracker never drifts from the tree.

## Notes

- `SnapshotReconciler` (`server/arb/reconcile.py`) calls
  `adapter.fetch_snapshot()` but only compares top levels and logs a mismatch
  metric - it never applies the snapshot to a book. So REST Exchange sequence
  numbers are not leaking into book state, and the section 1 warning about
  mixing sequence spaces is satisfied on that path.
- `server/tests/test_replay.py` resolves fixture paths relative to the repo
  root. Run pytest from the repo root, not from `server/`:
  `.venv/Scripts/python.exe -m pytest -q server/tests`. Running it from
  `server/` produces 3 spurious `FileNotFoundError` failures.
