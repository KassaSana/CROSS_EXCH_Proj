# Production-Quality Polish Plan — Cross-Exchange Arb Detector

## Context

The MVP described in [design.md](/Users/kassahunsanayew/Project/serious/cross_EXCH_proj/design.md) is essentially **built**: all three adapters with reconnect+jitter, OrderBookManager with gap/crossed-book handling, ArbitrageDetector, batched aiosqlite persistence, FastAPI + WS, and the React dashboard with live spreads / feed / stats. Tests cover the §5.2 cases.

**What's missing to clear the bar from "MVP" to "production-quality system that impresses a Gemini/quant recruiter"** is not more features — it's **validation rigor, observability, real measured numbers, and presentation polish**. This plan turns that gap into a tracked checklist.

The plan below is the deliverable: a checklist designed to be dropped into the repo as `TASKS.md` and worked through item-by-item by Claude Code or Codex. Each item has explicit **Files**, **Acceptance**, and where useful **Notes**, so an agent can pick it up cold.

**Recommended landing path:** `/Users/kassahunsanayew/Project/serious/cross_EXCH_proj/TASKS.md` (copy this file's body, minus the Context section above, to that path on plan approval).

---

# TASKS.md — Production Readiness Checklist

> **Status legend:** `[ ]` todo · `[~]` in progress · `[x]` done · `[-]` skipped (with reason)
> **How to use with Claude/Codex:** Pick one unchecked task, read the Acceptance criteria, do the work, run the verification command, then flip the box. Do not batch unrelated tasks in one commit.

**Source of truth:** [design.md](design.md). If a task here conflicts with design.md, design.md wins — surface the conflict before changing course.

**Priority tiers:** P0 = required for "production-quality" claim · P1 = high recruiter signal · P2 = code-health hygiene · P3 = perf proof · P4 = recruiter-facing polish · P5 = stretch.

---

## P0 — Validation & Correctness

- [ ] **P0.1 End-to-end latency benchmark (ingest → emit)**
  - Files: `server/scripts/benchmark.py`, new `server/scripts/bench_e2e.py`
  - Acceptance: synthetic WS server feeds known-arb deltas; benchmark records `t_recv_on_socket` to `t_opportunity_yielded` for ≥10k events; reports p50/p95/p99/max latency and sustained events/min. Output written to `benchmarks/results.json`.
  - Notes: current benchmark only times `detect_for_pair` in isolation — that's not the §3 claim. Use `time.perf_counter_ns()` only inside our process (see design §11 "clock skew").

- [ ] **P0.2 Property-based tests for OrderBookManager invariants**
  - Files: `server/tests/test_orderbook_properties.py` (new)
  - Acceptance: using `hypothesis`, generate random snapshot+delta sequences and assert: (a) bids strictly decreasing, asks strictly increasing, (b) no level with size ≤ 0 retained, (c) `best_bid < best_ask` post-recovery, (d) sequence-gap detection fires when expected. Runs in <30s.

- [ ] **P0.3 Recorded WS replay regression tests**
  - Files: `server/tests/fixtures/recorded/{gemini,coinbase,binance}_btcusd_5min.jsonl`, `server/tests/test_replay.py`, leverage existing `server/scripts/replay.py`
  - Acceptance: capture 5 min of real WS traffic per exchange (one-time); test feeds fixture through real adapter parsing → OrderBookManager and asserts no crashes, no crossed books beyond N recovery events, final book has plausible size.

- [ ] **P0.4 Per-adapter sequence-gap handling per spec**
  - Files: `server/arb/adapters/{gemini,coinbase,binance}.py`, `server/arb/adapters/base.py`
  - Acceptance: on detected gap, adapter requests fresh REST snapshot (Binance `/depth`, Coinbase `/products/{id}/book?level=2`, Gemini REST book), emits a `snapshot` MarketEvent, then resumes deltas. Currently handled passively in OrderBookManager (clear+wait) — design §5.1 wants adapter-driven resync.
  - Notes: document the chosen strategy per exchange in `docs/RESYNC.md`. This is the §5.2 "implementation gap for you to fill."

- [ ] **P0.5 Snapshot reconciliation job**
  - Files: `server/arb/reconcile.py` (new), wired into `main.py`
  - Acceptance: every 60s, fetch REST snapshot for one (exchange, pair) round-robin, diff top-10 levels against live book, log mismatch >0.5%. Counter exposed as metric (see P1.1).

- [ ] **P0.6 24h+ soak run with artifacts**
  - Files: `benchmarks/soak_2026-05-DD.md` (new per run)
  - Acceptance: run system 24h+, capture: opportunity count, RSS over time (sample every 5 min), reconnect counts per exchange, gap counts, crash log (should be empty). Memory growth must be <10% drift.

---

## P1 — Observability & Ops

- [ ] **P1.1 Prometheus `/metrics` endpoint**
  - Files: `server/arb/metrics.py` (new), `server/arb/api.py`
  - Acceptance: expose `arb_events_ingested_total{exchange}`, `arb_book_updates_total{exchange,pair}`, `arb_opportunities_total{pair}`, `arb_detection_latency_seconds` (histogram), `arb_book_staleness_seconds{exchange,pair}` (gauge), `arb_adapter_reconnects_total{exchange,reason}`, `arb_ws_clients` (gauge). Use `prometheus-client`.

- [ ] **P1.2 `/healthz` and `/readyz`**
  - Files: `server/arb/api.py`
  - Acceptance: `/healthz` always 200 if process alive; `/readyz` 200 only if all 3 adapters connected AND each pair has had a book update in the last 30s.

- [ ] **P1.3 Per-adapter status surface**
  - Files: `server/arb/adapters/base.py`, `server/arb/api.py` (new `GET /api/adapters`)
  - Acceptance: returns `[{exchange, connected, last_message_age_ms, gap_count, reconnect_count, last_error}]`. Drives P1.4 banner.

- [ ] **P1.4 Dashboard connection-status banner**
  - Files: `dashboard/src/components/AdapterStatus.tsx` (new), `dashboard/src/App.tsx`
  - Acceptance: top banner with green/yellow/red dot per exchange, tooltip showing reconnects + last-message age. Polls `/api/adapters` every 2s.

- [ ] **P1.5 Verify structlog JSON output everywhere**
  - Files: `server/arb/main.py`, ad hoc grep for `print(` and stdlib `logging.getLogger`
  - Acceptance: all logs emitted as single-line JSON with `event`, `exchange`, `pair`, `level`, `timestamp`. No bare `print()`. Log level via env var `ARB_LOG_LEVEL`.

---

## P2 — Code Quality & CI

- [ ] **P2.1 mypy strict + ruff**
  - Files: `pyproject.toml`, new `mypy.ini` if needed
  - Acceptance: `mypy --strict server/arb` passes (allow targeted `# type: ignore[...]`). `ruff check server/` passes with project config (line length 100, isort, pyupgrade).

- [ ] **P2.2 Frontend lint + typecheck**
  - Files: `dashboard/.eslintrc`, `dashboard/package.json` scripts
  - Acceptance: `pnpm lint` and `pnpm tsc --noEmit` both pass clean.

- [ ] **P2.3 GitHub Actions CI**
  - Files: `.github/workflows/ci.yml` (new)
  - Acceptance: runs on push + PR: pytest (with coverage upload), mypy, ruff, frontend `tsc` + `vite build`. Fails on any non-zero. Caches uv/pnpm.

- [ ] **P2.4 Coverage ≥ 80% on detector + orderbook**
  - Files: `pyproject.toml` (coverage config), CI step
  - Acceptance: `pytest --cov=server/arb/orderbook --cov=server/arb/detector --cov-fail-under=80` green.

- [ ] **P2.5 Pre-commit hooks**
  - Files: `.pre-commit-config.yaml` (new)
  - Acceptance: ruff, mypy (changed files), end-of-file-fixer, trailing-whitespace, prettier for `dashboard/`. Documented in README run section.

---

## P3 — Performance Proof

- [ ] **P3.1 Hot-path profile**
  - Files: `benchmarks/profile_2026-05-DD.svg`
  - Acceptance: capture `py-spy record` flamegraph during synthetic 100k-events/min run; commit SVG. Identify top-3 hotspots in `benchmarks/PROFILE_NOTES.md`.

- [ ] **P3.2 Validate the §3 numbers**
  - Files: `benchmarks/RESULTS.md`
  - Acceptance: P0.1 benchmark + 100k/min sustained throughput run produces real numbers. Document the harness, hardware, and exact command. If sub-50ms p99 isn't met, write down the actual p99 and what the bottleneck is — honesty > inflation.

- [ ] **P3.3 Bounded queues + drop policy**
  - Files: `server/arb/main.py` (or wherever queue is created)
  - Acceptance: `asyncio.Queue(maxsize=N)` with documented drop-on-full + counter increment. Prevents OOM under hostile bursts.

---

## P4 — Documentation & Demo (recruiter-facing)

- [ ] **P4.1 README per [design §10](design.md)**
  - Files: `README.md`
  - Acceptance: in this exact order: 1-line pitch · architecture diagram (image) · dashboard GIF · numbers w/ methodology · honesty caveat (fees/slippage) · tech stack · run instructions · design tradeoffs (why SQLite, why one process, why asyncio) · what's next.

- [ ] **P4.2 Architecture diagram (PNG)**
  - Files: `docs/architecture.excalidraw`, `docs/architecture.png`
  - Acceptance: PNG referenced from README. Shows the data flow from design §5 with components labeled.

- [ ] **P4.3 Animated GIF of dashboard during a real arb**
  - Files: `docs/demo.gif`
  - Acceptance: ≤6 MB, ≤15s loop, shows live spread crossing threshold and entry appearing in feed.

- [ ] **P4.4 60-second demo video**
  - Files: `docs/demo.mp4` (or unlisted YouTube link in README)
  - Acceptance: voice-over walks through architecture → live feed → benchmark numbers. Linked from README.

- [ ] **P4.5 BENCHMARKS.md**
  - Files: `BENCHMARKS.md`
  - Acceptance: full reproduction steps for the resume numbers (commands, hardware, exact git SHA, raw output).

---

## P5 — Stretch (optional, only after P0–P4)

- [ ] **P5.1 Spread-over-time chart** — Recharts line chart per pair, last 1h sliding.
- [ ] **P5.2 Fee-aware net-profit toggle** — config-driven taker fees per exchange, optional toggle in dashboard with explicit "estimate, excludes withdrawal/slippage" caption.
- [ ] **P5.3 Per-pair configurable thresholds** — extend `config.toml` `[detector.pair_overrides]`.
- [ ] **P5.4 Replay UI** — scrub bar in dashboard reading from SQLite `opportunities` table.

---

## Verification (run before declaring "done")

```bash
# Backend
cd server && pytest --cov=arb --cov-fail-under=80
mypy --strict arb
ruff check .

# Frontend
cd dashboard && pnpm lint && pnpm tsc --noEmit && pnpm build

# E2E
python server/scripts/bench_e2e.py    # P0.1 numbers
python server/scripts/replay.py server/tests/fixtures/recorded/  # P0.3
# Soak: launch main, leave 24h, inspect benchmarks/soak_*.md
```

A reviewer should be able to clone, run the commands above, and reproduce the README numbers within ±20%.
