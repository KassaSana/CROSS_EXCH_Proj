# ArbSync repository guidance

ArbSync ingests public Gemini, Coinbase, and Binance.US order books, maintains
trusted in-memory L2 books, detects theoretical cross-exchange opportunities, stores
them in SQLite, and streams state to a React dashboard.

Read [`AGENTS.md`](AGENTS.md) for repository-wide contribution and commit rules.

## Layout

```text
server/arb/          Backend package
server/arb/adapters/ Exchange-specific protocol and recovery logic
server/tests/        Backend tests
dashboard/src/       React/TypeScript dashboard
tools/                Benchmark, replay, profiling, and soak tools
artifacts/benchmarks/ Benchmark results and live-run artifacts
docs/RESYNC.md       Recovery design decision
docs/VALIDATION.md   Current verification status and remaining evidence
docs/BENCHMARKS.md   Benchmark and soak methodology
config.toml          Runtime configuration
var/                 Ignored runtime data
```

## Architectural invariants

- Adapters own exchange-specific sequence validation and recovery.
- `OrderBookManager` owns the canonical eligibility decision shared by detection,
  readiness, metrics, and dashboard state.
- A disconnected, uninitialized, discontinuous, stale, incomplete, or crossed book
  must not contribute to detection.
- Persistence and per-client WebSocket delivery remain bounded and must not block
  market-data ingestion.
- SQLite stores opportunities, not order books.
- Decimal values are stored and serialized without converting through binary floats.
- Opportunities are theoretical and exclude fees, slippage, latency, inventory, and
  execution risk.

See [`docs/RESYNC.md`](docs/RESYNC.md) before changing adapter recovery or normalized
sequence behavior.

## Run and verify

From the repository root:

```powershell
uv run pytest -q server/tests
uv run mypy --strict server/arb
uv run ruff check server
uv run ruff format --check server
uv run python -m arb.main
```

From `dashboard/`:

```bash
npm run typecheck
npm run lint
npm run build
npm run dev
```

Use small batch sizes and short flush intervals in tests. Tests that open SQLite more
than once should use a file under pytest's `tmp_path`, not `:memory:`.

Update [`docs/VALIDATION.md`](docs/VALIDATION.md) only when verification evidence or
the remaining validation gap materially changes.
