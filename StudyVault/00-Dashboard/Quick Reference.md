---
module: dashboard
path: 00-Dashboard
keywords: commands, setup, debugging, configuration
---

# Quick Reference

#dashboard #quick-reference

## Key Commands

| Action | Command |
|---|---|
| Install backend | `python -m pip install -e .[dev]` |
| Run backend | `python -m arb.main` |
| Run tests | `python -m pytest -q` |
| Type check | `python -m mypy --strict server/arb` |
| Lint backend | `python -m ruff check server` |
| Run frontend | `cd dashboard; npm run dev` |
| Frontend checks | `npm run typecheck; npm run lint; npm run build` |
| Replay fixtures | `python server/scripts/replay.py server/tests/fixtures/recorded` |

## Important File Locations

| File | Purpose |
|---|---|
| `server/arb/main.py` | Composition root and event consumer |
| `server/arb/types.py` | Shared immutable event/data types |
| `server/arb/adapters/base.py` | Reconnect and sequence finalization |
| `server/arb/orderbook.py` | Sorted L2 state and gap handling |
| `server/arb/detector.py` | Pairwise opportunity calculation |
| `server/arb/persistence.py` | Async SQLite queue and reports |
| `server/arb/api.py` | FastAPI routes and live broadcaster |
| `config.toml` | Pairs, threshold, server, persistence |
| `server/tests/` | Unit, property, API, and replay tests |

## Common Debugging

| Symptom | First place to look |
|---|---|
| No opportunities | `config.toml`, `detector.py`, and top-of-book state |
| Book becomes stale | adapter sequence logic and `OrderBookManager.apply` |
| Live UI freezes | `/readyz`, `/api/adapters`, WebSocket hook |
| Data missing from history | persistence queue, flush loop, SQLite path |
| Tests fail at collection | Python version and `pip install -e .[dev]` |
