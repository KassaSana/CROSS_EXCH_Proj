# Benchmark Results

Generated from the current repo state on 2026-05-08.

## Detector Microbenchmark

- iterations: `100000`
- throughput per minute: `16,454,491`
- p50 latency: `3.42 µs`
- p95 latency: `3.88 µs`

## End-to-End Synthetic Benchmark

- iterations: `10000`
- opportunities emitted: `10000`
- throughput per minute: `1,920,581`
- p50 latency: `16.00 µs`
- p95 latency: `17.33 µs`
- p99 latency: `27.29 µs`
- max latency: `216.67 µs`

Interpretation:
- the detector path comfortably clears the original sub-50 ms goal
- the synthetic end-to-end harness also clears the sub-50 ms goal by a wide margin
- these are local synthetic measurements, not long-duration live exchange measurements
