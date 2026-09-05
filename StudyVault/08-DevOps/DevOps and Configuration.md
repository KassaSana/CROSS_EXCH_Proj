---
module: devops
path: 08-DevOps
keywords: environment, ci, deployment, benchmarks, configuration
---

# DevOps and Configuration

#module-devops #config-runtime #test-validation

## Runtime Configuration

`config.toml` defines exchange subscriptions, detector threshold, server bind/port/database path, and persistence queue settings. The environment variable `ARB_LOG_LEVEL` controls logging verbosity.

## Validation

Backend checks are pytest, strict mypy, and Ruff. Frontend checks are TypeScript typecheck, ESLint, and Vite build. Replay fixtures exercise all three adapters without requiring live exchange traffic.

## Deployment Shape

The backend is deployed separately from the Vercel-hosted frontend. The backend serves REST and WebSocket traffic from one FastAPI process. Render's free tier can sleep, which stops live feed processing while sleeping.

## Benchmarks

`server/scripts/benchmark.py` measures detector throughput; `bench_e2e.py` measures synthetic ingest-to-opportunity latency. Benchmark claims are synthetic and opportunities remain theoretical.

## Related Notes

- [[Quick Reference]]
- [[System Architecture]]
- [[Arbitrage Detection]]
