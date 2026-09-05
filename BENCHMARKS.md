# Benchmarks

This repo ships two benchmark paths:

## 1. Detector Microbenchmark

Purpose:
- isolate `ArbitrageDetector.detect_for_pair()`
- measure pure comparison latency without socket IO, parsing, or persistence

Command:

```bash
python3 server/scripts/benchmark.py
```

Current output:

```text
iterations=100000
throughput_per_minute=16454491
p50_latency_us=3.42
p95_latency_us=3.88
```

## 2. End-to-End Synthetic Benchmark

Purpose:
- measure ingest-on-socket to arbitrage-opportunity-emitted latency inside one process
- include synthetic websocket receive, JSON parse, book update, and detector invocation

Command:

```bash
python3 server/scripts/bench_e2e.py --iterations 10000
```

Current output:

```text
iterations=10000
opportunities_emitted=10000
throughput_per_minute=1920581
p50_latency_us=16.00
p95_latency_us=17.33
p99_latency_us=27.29
max_latency_us=216.67
```

Notes:
- these numbers are measured under synthetic local load, not against the live internet
- the end-to-end benchmark uses an in-process synthetic websocket server
- the detector microbenchmark is not a valid claim for full pipeline throughput

Raw persisted results live in [benchmarks/results.json](benchmarks/results.json).

## 3. Live Soak Observer

Start the backend, note its process ID, then run:

```bash
python3 server/scripts/soak.py \
  --duration-seconds 86400 \
  --sample-seconds 300 \
  --pid <backend-pid> \
  --output benchmarks/soak_YYYY-MM-DD.md
```

The observer samples per-exchange ingest volume, adapter reconnects and gaps,
canonical book eligibility and age, readiness, opportunities, background-task
failures, HTTP failures, recovery durations, and backend RSS. Shorter durations
are useful as smoke tests but must not be described as the required 24-hour soak.
