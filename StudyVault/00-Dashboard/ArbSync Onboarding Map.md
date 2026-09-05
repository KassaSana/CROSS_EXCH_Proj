---
module: dashboard
path: 00-Dashboard
keywords: onboarding, architecture, arbitrage, python, react
---

# ArbSync — Onboarding Map

#dashboard #onboarding

## Architecture Overview

- Pattern: single-process asynchronous event pipeline with an HTTP/WebSocket presentation layer.
- Backend: Python 3.11, asyncio, FastAPI, WebSockets, SQLite, Decimal arithmetic.
- Frontend: React, TypeScript, Vite, Tailwind, Recharts.
- → [[System Architecture]]
- → [[Request Flow]]

## Module Map

| Module | Purpose | Key Entry Point | Notes |
|---|---|---|---|
| Exchange adapters | Connect to venues and normalize messages | `server/arb/adapters/base.py` | [[Exchange Adapters]] |
| Order books | Maintain per-exchange, per-pair L2 state | `server/arb/orderbook.py` | [[Order Book State]] |
| Detection | Compare top-of-book prices | `server/arb/detector.py` | [[Arbitrage Detection]] |
| Persistence | Batch opportunities into SQLite and query stats | `server/arb/persistence.py` | [[Persistence]] |
| API and metrics | Expose REST, WebSocket, health, and Prometheus surfaces | `server/arb/api.py` | [[API and Observability]] |
| Dashboard | Render live state and historical statistics | `dashboard/src/App.tsx` | [[React Dashboard]] |
| Runtime configuration | Wire components and load TOML settings | `server/arb/main.py` | [[System Architecture]] |

## API Surface

| Method | Path | Purpose |
|---|---|---|
| GET | `/healthz` | Liveness |
| GET | `/readyz` | Adapter and book readiness |
| GET | `/api/opportunities/recent` | Recent persisted opportunities |
| GET | `/api/stats` | Legacy window summary |
| GET | `/api/system/overview` | Uptime and all-time peaks |
| GET | `/api/system/stats` | Windowed aggregate statistics |
| GET | `/api/system/timeseries` | Bucketed chart data |
| POST | `/api/system/reset` | Reset displayed uptime |
| GET | `/api/pairs` | Known exchange/pair books |
| GET | `/api/adapters` | Adapter health |
| GET | `/metrics` | Prometheus metrics |
| WS | `/ws/live` | Top-of-book and opportunity messages |

## Getting Started

1. Use Python 3.11+.
2. Install backend dependencies: `python -m pip install -e .[dev]`.
3. Start backend: `python -m arb.main` from the project root.
4. In `dashboard/`, run `npm install` and `npm run dev`.
5. Verify with `python -m pytest -q`, `python -m mypy --strict server/arb`, and `python -m ruff check server`.

## Tag Index

| Tag | Meaning |
|---|---|
| `#arch-*` | System-level architecture and flows |
| `#module-*` | A major code module |
| `#pattern-*` | Reusable implementation pattern |
| `#config-*` | Runtime or build configuration |
| `#api-*` | HTTP/WebSocket or metrics surface |
| `#test-*` | Test strategy and guarantees |

## Onboarding Path

1. [[System Architecture]]
2. [[Request Flow]]
3. [[Exchange Adapters]] → [[Order Book State]] → [[Arbitrage Detection]]
4. [[Persistence]] → [[API and Observability]] → [[React Dashboard]]
5. [[Quick Reference]]
6. [[ArbSync Exercises]]

## Scope Boundary

All detected opportunities are theoretical. The detector excludes fees, slippage, transfer latency, inventory constraints, and execution risk. ArbSync detects and observes market differences; it does not place trades.
