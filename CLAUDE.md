# Cross-Exchange Arbitrage Detector

Real-time crypto arbitrage detection system. Backend ingests live order books from Gemini, Coinbase, and Binance over WebSocket, maintains in-memory L2 books, runs a detector, persists opportunities to SQLite, and streams updates to a React dashboard.

## Tech stack

- **Backend**: Python 3.11, asyncio, FastAPI, websockets, aiosqlite, structlog, httpx
- **Frontend**: React 18, Vite, TypeScript, Tailwind, react-router-dom 6, recharts
- **Tests**: pytest, hypothesis, mypy strict, ruff

## Repo layout

```
server/arb/              # backend package
  adapters/              # one file per exchange (binance, coinbase, gemini) + base
  api.py                 # FastAPI routes + WebSocket broadcaster
  detector.py            # arbitrage detector logic
  orderbook.py           # in-memory L2 book manager
  persistence.py         # batched async SQLite writer + queries
  reconcile.py           # periodic snapshot reconciliation
  metrics.py             # Prometheus counters/histograms
  main.py                # entry point — wires everything together
  config.py / types.py
server/tests/            # pytest suite, mirrors server/arb/ layout
dashboard/src/
  pages/                 # Dashboard, Statistics
  components/            # presentational components
  hooks/                 # useWebSocket
  api/client.ts          # all fetch + types
config.toml              # exchange pairs, detector threshold, server config
arb.sqlite3              # local dev DB (gitignored)
```

## Run locally

```bash
# Backend (in repo root)
python3 -m pip install -e .[dev]   # one-time
python3 -m arb.main                # serves on :8000

# Frontend (in dashboard/)
npm install                        # one-time
npm run dev                        # serves on :5173
```

Open http://localhost:5173. Frontend talks to backend at `localhost:8000` in dev (vite proxy), and the deployed Render URL in prod.

## Verification commands

Run these before pushing:

```bash
# Backend
python3 -m pytest server/tests -q
python3 -m mypy --strict server/arb
python3 -m ruff check server

# Frontend (in dashboard/)
npm run typecheck
npm run lint
npm run build
```

`npm run lint` may crash with `util.styleText is not a function` due to a Node/ESLint formatter incompatibility on macOS — workaround is `npx eslint src --ext .ts,.tsx -f json`.

## Deployment

Auto-deploy on push to `main`:
- **Backend** → Render: https://arb-detector-api.onrender.com (config in Render dashboard, no `render.yaml` in repo)
- **Frontend** → Vercel: https://cross-exch-proj.vercel.app (config via `dashboard/vercel.json` for SPA rewrites)

Render's free tier sleeps after 15 min of inactivity — when sleeping, the backend can't maintain WebSocket connections to exchanges, so live data freezes. Upgrade or accept this tradeoff.

## Key endpoints

- `GET /healthz`, `GET /readyz` — liveness/readiness
- `GET /api/adapters` — per-exchange adapter status (connected, last message age, reconnects)
- `GET /api/opportunities/recent?limit=N` — recent opportunities
- `GET /api/stats?window=1h|4h|1d|1w` — legacy stats
- `GET /api/system/overview` — uptime + all-time peaks
- `GET /api/system/stats?window=...` — windowed stats with top pair, peak minute
- `GET /api/system/timeseries?window=...&bucket_seconds=...` — time-bucketed counts
- `POST /api/system/reset` — zero the uptime counter (does not clear data)
- `GET /metrics` — Prometheus
- `WS /ws/live` — live top-of-book + opportunity stream

## Architectural conventions

- **Adapters**: each exchange has a class extending `ExchangeAdapter` (server/arb/adapters/base.py). The base class handles reconnect-with-backoff in `connect()`. Subclasses override `subscribe`, `parse_message`, `fetch_snapshot`, and optionally `reset_state` (called before each subscribe, used by Binance/Gemini to clear `_initialized`/`_pair_seq` so the next message after reconnect re-fetches a fresh REST snapshot).
- **Persistence is batched**: opportunities are enqueued; a background task flushes by size (500) or interval (1s). Don't block the detection path with sync writes.
- **Books are in-memory only**: `OrderBookManager` holds L2 books. SQLite stores opportunities, not books.
- **Tests use file-based SQLite via `tmp_path`**: `:memory:` SQLite gives a fresh DB per `aiosqlite.connect()`, so tests that hit the table need `tmp_path / "x.sqlite3"`.

## Known quirks

- **Coinbase adapter receives very few events** in production compared to Gemini/Binance (~500 vs ~20M). Suspected broken — needs investigation.
- **MATIC was removed** from `config.toml` because Polygon rebranded to POL in late 2024 and the major exchanges delisted MATIC. Adding any new pair requires checking listing status on all three venues.
- **All detected opportunities are theoretical** — no fees, slippage, transfer time, or inventory constraints are accounted for. This is a detection/observability system, not an execution engine.

## Working style preferences

- Don't add backwards-compat shims for code that doesn't exist yet. Prefer simplicity over hypothetical future flexibility.
- Tests should run fast — use small batch sizes and short flush intervals in fixtures.
- When making fullstack changes, run the backend verification before touching frontend, and finish with the full battery (pytest + mypy + ruff + typecheck + lint + build) before declaring done.
