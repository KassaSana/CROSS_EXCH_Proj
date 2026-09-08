# Connected-dashboard performance investigation — 2026-09-08

This investigation measures ArbSync's Python event-processing path with a real
headless Chrome browser displaying its production-built React dashboard. It uses
modeled local exchange traffic, not a captured production workload or an internet
latency measurement. The baseline's receive-to-detection timing alone concealed
substantial backlog and dropped output at larger burst sizes.

## Baseline

Two 20-second runs at each average rate, on Windows 11 / Python 3.12.10 / Chrome
152.0.7977.77, with 16 logical CPUs and 15.65 GiB RAM. CPU percentages use **one
logical core as 100%**, not the whole machine. Each row shows the range across
the two runs; percentiles are calculated independently per run.

| Average events/s | Backend mean CPU | Peak backend RSS | Receive→detect p95 | Receive→detect p99 | Send→detect p99 | Persistence drops/run | Dashboard queue overflows/run |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 110 | 4.6–5.6% | 71.7–72.6 MiB | 0.44 ms | 0.72–0.73 ms | 27–29 ms | 0 | 0 |
| 1,100 | 29.9–30.1% | 81.5–81.6 MiB | 0.41 ms | 0.71–0.79 ms | 986–1,024 ms | 0 | 4 |
| 5,500 | 79.3–83.0% | 115.4–128.4 MiB | 0.34–0.37 ms | 0.66–0.81 ms | 22,062–22,933 ms | 9,062–9,104 | 5 |

All sent events eventually reached the handler in these runs. Persistence drops
mean opportunities were detected but could not be queued for storage. Dashboard
overflows close the affected connection; they do not stop the detector.

No >50 ms browser long tasks were recorded in the baseline. This does **not** mean
the overloaded dashboard was healthy: at 5,500/s it received only 24 and 342
messages in the two runs because its connections were repeatedly dropped. At
110/s it received 4,890 messages/run; browser process-tree mean CPU was 31.9–36.4%
of one core. Frame intervals were around 7 ms on this host, with p99 around
13.6 ms. Headless frame timing is a scheduling proxy, not proof of physical paint
latency on another user's display.

Sources: [baseline measurements](baseline-perf-20260908T095921Z.json),
[baseline profiler run](baseline-profile-20260908T100355Z.json),
[Python profile](baseline-python-profile.txt).

## What the profiler found

The separate 10-second, 1,100/s Python profile recorded 11,000 events:

- `top_of_book`: 88,270 calls, 0.609 seconds cumulative.
- `eligible_books`: 0.675 seconds cumulative, including nested book reads.
- `detect_for_pair`: 0.043 seconds cumulative in the production detector.
- Recursive opportunity serialization (`_asdict_inner`): 0.122 seconds cumulative.

These overlapping cumulative times must not be added together. The Windows
completion-port wait dominating total elapsed time is primarily waiting, not
evidence of a CPU-intensive function to rewrite in C++. cProfile observes the
main Python thread; it does not attribute SQLite's background-thread work.
Ordinary production runs, rather than profiler runs, supply the comparison
latencies and process CPU measurements.

## Results after the changes

Three changes were measured, each with two 20-second runs per rate on the same
host and harness as the baseline.

**Coalescing.** Per-book display updates are collected and flushed at 20 Hz,
newest per book, instead of publishing on every accepted event. Opportunities
and book invalidations stay immediate.

**Dashboard batching.** The browser buffers incoming quotes, statuses and
opportunities and applies them on a 50 ms timer, instead of setting state per
message. Sections are memoized and list keys no longer contain the venue
sequence number.

**Suppression.** A book update whose displayed content matches the last one
sent for that book is dropped rather than queued. Status is compared on
`initialized`, `continuous`, `connected`, `eligible` and `reason`; quotes on
the four best bid/ask price and size fields.

| Average events/s | Stage | Backend mean CPU | Receive→detect p99 | Send→detect p99 | Persistence drops/run | Dashboard overflows/run | Browser mean CPU |
| ---: | :--- | ---: | ---: | ---: | ---: | ---: | ---: |
| 110 | baseline | 4.6–5.6% | 0.72–0.73 ms | 27–29 ms | 0 | 0 | 31.9–36.4% |
| 110 | coalescing | 3.8–4.2% | 0.92–1.48 ms | 29–40 ms | 0 | 0 | 16.4–16.5% |
| 110 | + batching | 4.2–4.3% | 0.37–1.54 ms | 17–36 ms | 0 | 0 | 15.5–18.2% |
| 110 | + suppression | 2.6–3.4% | 0.27–0.56 ms | 17–21 ms | 0 | 0 | 9.9–13.0% |
| 1,100 | baseline | 29.9–30.1% | 0.71–0.79 ms | 986–1,024 ms | 0 | 4 | 40.3–41.9% |
| 1,100 | coalescing | 33.2–34.0% | 0.49–0.62 ms | 520–528 ms | 0 | 0 | 41.9–47.3% |
| 1,100 | + batching | 16.4–26.0% | 0.27–0.62 ms | 76–648 ms | 0 | 0 | 28.2–38.2% |
| 1,100 | + suppression | 15.4–15.8% | 0.24–0.25 ms | 71–88 ms | 0 | 0 | 18.8–20.7% |
| 5,500 | baseline | 79.3–83.0% | 0.66–0.81 ms | 22,062–22,933 ms | 9,062–9,104 | 5 | 16.3–17.7% |
| 5,500 | coalescing | 85.0–87.1% | 0.46–0.47 ms | 8,821–9,156 ms | 0 | 0 | 73.8–76.0% |
| 5,500 | + batching | 64.1–66.1% | 0.28–0.32 ms | 1,979–2,587 ms | 0 | 0 | 49.6–56.5% |
| 5,500 | + suppression | 61.8–61.9% | 0.22 ms | 1,899–1,912 ms | 0 | 0 | 39.3–43.2% |

Each stage is cumulative. Baseline browser CPU at 5,500/s is low only because
the dashboard had been disconnected and was receiving almost nothing.

### What each stage did

Coalescing removed the data loss, not the cost. Persistence drops and dashboard
evictions went to zero and stored rows at 5,500/s rose from 15,467–15,509 to
24,571, but backend CPU rose, because the backend began completing delivery and
persistence work the baseline had been discarding.

Dashboard batching produced the largest single improvement in both backend CPU
and send-to-detect latency. Two effects are mixed here and this workload cannot
separate them: the browser does less work per message, and it also drains its
socket faster, which relieves the backend. Browser and backend share this host,
so some of the backend CPU change reflects reduced contention rather than
reduced backend work.

Suppression roughly halved delivered message volume again (12,570 to 6,873 per
run at 1,100/s) and browser CPU with it. Its additional backend CPU gain is
smaller than batching's, and at 1,100/s its clearest effect is on consistency:
the batching stage ranged 16.4–26.0% CPU and 76–648 ms send-to-detect across
its two runs, which suppression narrowed to 15.4–15.8% and 71–88 ms.

Suppression's other purpose is not visible in this table. After a sequence gap
the book is cleared and every subsequent delta is refused until a snapshot
arrives; publishing an invalidation per refused event reintroduces the flood
that coalescing removed. That path is covered by a test rather than by this
workload, which does not generate sustained gap storms.

### What these runs do not establish

- Only the last two reports carry source fingerprints, which the harness added
  partway through this investigation. The baseline and coalescing runs cannot
  be shown to have measured an unchanged tree, and the coalescing run predates
  the dashboard batching work. Treat the first two rows of each rate as
  indicative and the fingerprinted pair as the controlled comparison.
- Delivered message counts fall by design (4,890/run to 931/run at 110/s). This
  is only correct because a suppressed repeat carries no new displayed content
  and the dashboard separately re-polls authoritative book status every two
  seconds. Removing that poll would change what suppression costs.
- Suppression compares displayed content, deliberately excluding `age_ms`,
  which changes on every event. A suppressed repeat can leave a stale age
  reading in the browser until the next real change or REST poll.
- Send→detect p99 remains 1.9 s at 5,500/s with backend CPU near 62% of one
  core. Socket backlog under sustained overload is reduced, not eliminated; the
  single event loop is still the throughput limit.
- These are the same modeled bursts as the baseline, not live exchange traffic,
  and the 5,500/s case remains an explicit stress assumption.

Sources: [coalescing](optimized-perf-20260908T101202Z.json),
[coalescing plus batching](verified-optimized-perf-20260908T101715Z.json),
[plus suppression](dedupe-perf-20260908T102410Z.json).

## Repeat the measurements

From the repository root, with Node and an installed Chrome browser:

```powershell
uv sync --locked --extra dev --extra perf
uv run python server/scripts/profile_pipeline.py --label baseline --repeats 2
# Run after the change to compare against the baseline. The committed reports
# use the labels `optimized` (coalescing) and `dedupe` (plus suppression):
uv run python server/scripts/profile_pipeline.py --label dedupe --repeats 2
# Separate diagnostic run, not a capacity benchmark:
uv run python server/scripts/profile_pipeline.py --label dedupe --rates 1100 --seconds 10 --profile
uv run python server/scripts/check_dashboard.py
```

The runner builds into `dashboard/dist-perf`, starts a private localhost backend,
launches an isolated headless Chrome context, and creates a new SQLite database
per scenario under `raw/`. It never opens the normal `arb.sqlite3` history.
Chrome can be replaced with installed Edge using `--channel msedge`. The runner
cleans up its child backend, feed server, and browser. Do not run performance
scenarios concurrently or edit source while a run is active. Reports include
source fingerprints and flag changes during a run.

Use `--rates`, `--seconds` (positive multiples of five), `--depth`, and
`--burst-ms` to vary the workload. The default is:

- 27 books, nine assets across three exchange parsers.
- 500 initial levels on each side. Updates replace sizes and insert/delete levels.
- Approximately 88% Coinbase, 6% Gemini, 6% Binance messages, modeled on the
  venue mix and ~109 events/s average in the committed five-minute smoke run.
- 80% deeper-book updates and 20% updates to the best sizes. One cross-venue
  pair remains profitable to exercise opportunity delivery and persistence.
  This is deliberately more opportunity-heavy than the zero-opportunity live soak.
- Every five seconds: four seconds at 0.25× the named rate, then one second at
  4×, sent in 100 ms microbursts. The 5,500/s case therefore offers 22,000/s
  during its peak second. This burst shape is an explicit stress assumption,
  not an empirically measured live p99 traffic distribution.
- Five seconds of warmup, a quiet drain, the measured feed, then a bounded drain
  and writer/browser settling period. Reported CPU includes that drain period.

## Metric definitions and limits

- **Receive→detection:** timestamp when the adapter takes a message from its
  WebSocket iterator through completion of detection, including JSON parsing,
  normalization, eligibility, and the handler's pre-detection work. It includes
  evaluations that produce no opportunity. It excludes time already spent in
  socket/library queues and excludes subsequent opportunity delivery.
- **Send→detection:** local generator timestamp just before sending through
  completion of detection, joined by exchange/pair/sequence. This exposes
  socket backlog and scheduling delays hidden by receive-only timing. It is
  not an exchange-to-host internet latency measurement.
- **Receive→handler complete:** also includes opportunity enqueueing and
  dashboard publication, plus the explicit scheduling yield after processing.
  It does not claim that SQLite committed or Chrome painted the event.
- **Clocks:** the benchmark worker substitutes `perf_counter_ns` consistently
  for receipt/freshness timestamps. Python 3.12's Windows `monotonic_ns` was too
  coarse for this measurement. This is isolated benchmark instrumentation;
  normal application clock behavior is unchanged.
- **CPU/RSS:** external `psutil` sampling every 250 ms, using the worker's actual
  PID (the Windows virtualenv launcher can have a different PID). Browser RSS
  sums the benchmark browser's processes and can count shared pages more than
  once. Neither RSS figure is equivalent to private heap allocation.
- **Memory overhead:** exact event records and browser timing samples are kept
  for each finite run. RSS therefore includes measurement overhead that grows
  with event count. These short runs cannot establish a memory leak or replace
  the planned 24-hour live soak.
- **Queues:** drop counters are exact; queue depth and event-loop lag are sampled
  every 50 ms and may miss transient peaks. `valid` in the JSON means event
  completeness and adapter correctness, **not** absence of queue drops or
  uninterrupted browser connectivity; check those fields separately.
- **Browser:** Long Tasks API, animation-frame intervals, Chrome DevTools
  Protocol task/script/layout/style durations and heap metrics. Opt-in React
  production profiling records actual render durations for App and dashboard
  sections; nested durations overlap. Normal production React profiling is off.

The production adapters, order-book manager, `process_market_event`, broadcaster,
SQLite writer, and API are exercised. External REST snapshot latency, exchange
reconnect stress, the periodic REST reconciler, many simultaneous dashboard
clients, and large-history statistics queries are outside this workload.

Raw JSON event/browser/process samples, screenshots, temporary databases, and
`.pstats` files remain locally in the ignored `raw/` directory. Small summaries
and human-readable profiles are retained here for review.

Reference: [Python profiling documentation](https://docs.python.org/3/library/profile.html),
[React Profiler documentation](https://react.dev/reference/react/Profiler).
