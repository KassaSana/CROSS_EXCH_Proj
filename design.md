# Cross-Exchange Crypto Arbitrage Detector — Design Doc

> Hand this file to Claude Code as the source of truth. Treat it as a contract: if you (Claude Code) want to deviate, surface the deviation and ask before changing direction.

---

## 1. What this is

A real-time system that ingests public order book data from **Gemini, Coinbase, and Binance**, maintains live L2 order books in memory, detects cross-exchange arbitrage opportunities above a configurable threshold, persists them to SQLite, and exposes a React dashboard showing live spreads and historical statistics.

This is **detection only** — no order execution, no trading, no API keys. Public market data feeds only.

## 2. The single most important constraint

**Ship in 3–4 focused days.** This is a portfolio project for a Gemini intern application. Every architectural decision below trades against this constraint. If something would take more than half a day and isn't on the critical path, defer it.

## 3. Resume-targeted numbers

The build is designed around proving these claims:

- Sub-50 ms detection latency (event ingestion → arbitrage event emitted)
- 100K+ order book updates processed per minute (sustained)
- 30+ trading pairs across 3 exchanges
- Theoretical arbitrage opportunities identified over a 24–72 hour soak run

**Build a benchmark harness from day 1** so these numbers are real, not invented. A single `scripts/benchmark.py` that times the detection path under synthetic load is enough.

---

## 4. Tech stack (decisions made — don't relitigate)

| Layer | Choice | Why |
|-------|--------|-----|
| Backend language | **Python 3.11+** | Kassahun's stack; asyncio is mature; ships fastest |
| Async runtime | `asyncio` + `websockets` library | Standard, well-documented, plenty of exchange examples |
| HTTP/WS server | **FastAPI** + `uvicorn` | One server for both REST endpoints and the dashboard's WebSocket feed |
| Storage | **SQLite** with WAL mode | Zero ops overhead; fine for this volume; can swap to Postgres later if needed |
| Frontend | **React + Vite + TypeScript** | Kassahun's stack |
| Charts | **Recharts** | Simple, React-native, sufficient |
| Styling | **Tailwind** | Fast iteration |
| Logging | `structlog` (JSON logs) | Makes the demo video / screenshots look professional |
| Testing | `pytest` + `pytest-asyncio` | Standard |
| Packaging | `uv` or `poetry` | Either is fine; pick one and stick with it |

**Explicitly NOT using:** Redis, Kafka, Postgres, Docker Compose multi-service setups, Celery, Kubernetes, Lambda. All of these are tempting and all of them are wrong for a 3–4 day timeline.

---

## 5. System architecture

### Data flow (one tick's journey)

```
Exchange WebSocket
        │
        ▼
ExchangeAdapter (per exchange)
        │  normalizes to internal MarketEvent
        ▼
asyncio.Queue
        │
        ▼
OrderBookManager
        ~│  applies delta, updates in-memory book
        ▼
ArbitrageDetector
        │  compares top-of-book across exchanges
        ▼
       ├──────────────► SQLite (async write, batched)
       │
       └──────────────► WebSocket broadcaster ──► React dashboard
```

Single process, single event loop. All components communicate through `asyncio.Queue` instances. No threading, no multiprocessing.

### Components

#### 5.1 `ExchangeAdapter` (3 implementations: Gemini, Coinbase, Binance)

**Responsibility:** Connect to the exchange's public WebSocket, subscribe to order book channels for the configured trading pairs, normalize every message into a common `MarketEvent` shape, and push to the shared queue.

**Interface (Python protocol):**

```python
class ExchangeAdapter(Protocol):
    name: str  # "gemini" | "coinbase" | "binance"
    
    async def connect(self) -> None: ...
    async def subscribe(self, pairs: list[str]) -> None: ...
    async def stream(self) -> AsyncIterator[MarketEvent]: ...
    async def disconnect(self) -> None: ...
```

**Required behavior:**
- Auto-reconnect with exponential backoff on disconnect
- Detect sequence number gaps and trigger a fresh snapshot if supported
- Symbol normalization (Gemini uses `btcusd`, Binance uses `BTCUSDT`, Coinbase uses `BTC-USD` — the adapter is responsible for emitting a canonical symbol like `BTC-USD`)
- Log every reconnect with reason at WARN level

**Gotcha:** Each exchange has different message formats and different ways of delivering snapshots vs deltas. Read each exchange's WebSocket docs before implementing. Do **not** assume they're similar.

#### 5.2 `OrderBookManager`

**Responsibility:** Maintain an in-memory L2 order book for every (exchange, pair) combination. Apply deltas. Detect and recover from sequence gaps.

**Internal data structure:** `dict[(exchange, pair), OrderBook]`, where `OrderBook` holds sorted bid and ask sides. Use `sortedcontainers.SortedDict` for the price levels — keeps insertion and best-price-lookup fast (O(log n) insertion, O(1) for best price).

**Public interface:**

```python
class OrderBookManager:
    def apply(self, event: MarketEvent) -> None: ...
    def best_bid(self, exchange: str, pair: str) -> Decimal | None: ...
    def best_ask(self, exchange: str, pair: str) -> Decimal | None: ...
    def top_of_book(self, exchange: str, pair: str) -> TopOfBook | None: ...
```

**This is the gnarly component.** Most of your bugs will live here. Write the test suite for this *first*, before the detector. Test cases must include: snapshot application, delta application, out-of-order delta, sequence gap, price level removal (size = 0), and crossed book recovery.

> **Implementation gap for you to fill:** Decide how you handle a detected sequence gap. Two reasonable options: (a) drop the book and request a fresh snapshot, (b) buffer incoming deltas while resyncing. Pick one, write down why, document the tradeoff in the README.

#### 5.3 `ArbitrageDetector`

**Responsibility:** When the order book changes, check every (pair, exchange_a, exchange_b) tuple for an arbitrage spread. If `best_bid(A) > best_ask(B) * (1 + threshold)`, emit an `ArbitrageOpportunity` event.

**Trigger model:** Run on every order book update for the affected pair. Don't poll — react.

```python
@dataclass(frozen=True)
class ArbitrageOpportunity:
    timestamp_ns: int
    pair: str            # e.g. "BTC-USD"
    buy_exchange: str
    sell_exchange: str
    buy_price: Decimal
    sell_price: Decimal
    spread_pct: Decimal  # ((sell - buy) / buy) * 100
    max_size: Decimal    # min of top-of-book sizes
    theoretical_profit_usd: Decimal  # max_size * (sell - buy)
```

**Important honesty caveat to bake into the README:** "theoretical profit" excludes exchange fees, withdrawal fees, slippage, and execution risk. Real-world arb after costs is dramatically smaller. Be intellectually honest about this — Gemini engineers will respect it more than inflated numbers.

#### 5.4 `Persistence`

**Responsibility:** Async writes of `ArbitrageOpportunity` rows to SQLite. Batched (e.g., flush every 500 events or 1 second, whichever first) to avoid write contention.

**Schema (single table is fine):**

```sql
CREATE TABLE opportunities (
    id INTEGER PRIMARY KEY,
    timestamp_ns INTEGER NOT NULL,
    pair TEXT NOT NULL,
    buy_exchange TEXT NOT NULL,
    sell_exchange TEXT NOT NULL,
    buy_price TEXT NOT NULL,    -- store Decimals as TEXT to avoid float drift
    sell_price TEXT NOT NULL,
    spread_pct TEXT NOT NULL,
    max_size TEXT NOT NULL,
    theoretical_profit_usd TEXT NOT NULL
);

CREATE INDEX idx_opps_timestamp ON opportunities(timestamp_ns);
CREATE INDEX idx_opps_pair_ts ON opportunities(pair, timestamp_ns);
```

Use `aiosqlite` so writes don't block the event loop.

#### 5.5 `WebSocket broadcaster` (FastAPI)

**Responsibility:** Maintain a set of connected dashboard clients. On every new `ArbitrageOpportunity`, broadcast as JSON. Also serve a few REST endpoints for historical data.

**Endpoints:**

- `GET /api/opportunities/recent?limit=100` — last N opportunities
- `GET /api/stats?window=1h` — count, max spread, total theoretical profit in window
- `GET /api/pairs` — list of tracked (exchange, pair) combinations
- `WS /ws/live` — stream of opportunities and top-of-book updates

#### 5.6 React dashboard

**Single page. Three sections:**

1. **Live spreads table** — for every tracked pair, show current best bid/ask on each exchange and the cross-exchange spread. Highlight in green when spread > threshold.
2. **Recent opportunities feed** — scrolling list of detected arbs with timestamp, pair, exchanges, profit.
3. **Stats cards** — opportunities/hour, total theoretical profit, max spread seen, uptime.

Use the WebSocket for live updates. Use REST for the initial load and stats.

> **Implementation gap for you to fill:** Decide whether the spread chart goes in v1 or v2. A 24-hour line chart of spread-over-time per pair is cool but adds a day. Recommendation: v2.

---

## 6. Project structure

```
arb-detector/
├── README.md
├── pyproject.toml              # uv or poetry
├── server/
│   ├── arb/
│   │   ├── __init__.py
│   │   ├── main.py             # entry point: wires everything together
│   │   ├── config.py           # pairs, threshold, exchange URLs
│   │   ├── types.py            # MarketEvent, ArbitrageOpportunity, etc.
│   │   ├── adapters/
│   │   │   ├── __init__.py
│   │   │   ├── base.py         # Protocol + shared reconnect logic
│   │   │   ├── gemini.py
│   │   │   ├── coinbase.py
│   │   │   └── binance.py
│   │   ├── orderbook.py        # OrderBookManager
│   │   ├── detector.py         # ArbitrageDetector
│   │   ├── persistence.py      # async SQLite writer
│   │   └── api.py              # FastAPI app + WS broadcaster
│   ├── tests/
│   │   ├── test_orderbook.py   # write these FIRST
│   │   ├── test_detector.py
│   │   └── test_adapters/
│   └── scripts/
│       ├── benchmark.py        # for the resume numbers
│       └── replay.py           # replay recorded ws traffic for testing
└── dashboard/
    ├── package.json
    ├── vite.config.ts
    ├── src/
    │   ├── App.tsx
    │   ├── main.tsx
    │   ├── components/
    │   │   ├── LiveSpreads.tsx
    │   │   ├── OpportunityFeed.tsx
    │   │   └── StatsCards.tsx
    │   ├── hooks/
    │   │   └── useWebSocket.ts
    │   └── api/
    │       └── client.ts
    └── index.html
```

## 7. Configuration

A single `config.toml` (or env-var-driven) with:

```toml
[detector]
threshold_pct = 0.1   # 0.1% spread minimum

[exchanges]
gemini   = ["btcusd", "ethusd", "solusd", ...]
coinbase = ["BTC-USD", "ETH-USD", "SOL-USD", ...]
binance  = ["BTCUSDT", "ETHUSDT", "SOLUSDT", ...]

[server]
host = "0.0.0.0"
port = 8000
```

Pick **at least 10 pairs per exchange** to hit the "30+ trading pairs" claim.

## 8. Build order (the actual day-by-day)

This sequence is critical. Do **not** jump ahead.

**Day 1 — Foundations**
- Project skeleton (server + dashboard scaffolding)
- Define `MarketEvent`, `ArbitrageOpportunity`, `OrderBook` types
- Implement `OrderBookManager` with full unit test coverage (snapshot, delta, gap detection)
- Implement `ArbitrageDetector` against a mock book — pure logic, no exchanges yet
- This is the hardest day. By end of day, you should be able to feed a sequence of synthetic events into the system and see correct opportunities emitted.

**Day 2 — Real data**
- Implement Gemini adapter end-to-end. Get one pair working. Add reconnect logic.
- Implement Coinbase adapter (it's the most idiosyncratic — sequence numbers behave differently than Gemini).
- Implement Binance adapter.
- All three adapters feeding the same OrderBookManager. Confirm books look sane via a quick CLI dump command.

**Day 3 — Persistence + dashboard**
- Add SQLite persistence with batched writes
- FastAPI server with REST endpoints + WS broadcaster
- React dashboard wireframe — live spreads table + opportunities feed
- End of day: full pipeline works locally, dashboard updates in real time

**Day 4 — Polish + numbers**
- Run the benchmark harness, capture real latency and throughput numbers
- Run a 24-hour soak in the background while you work on README
- README with: architecture diagram, screenshots, benchmark numbers, honesty caveat about fees, design tradeoffs section
- Record a 60-second demo video (huge for the resume — recruiters love it)
- Push to GitHub with a clean commit history

## 9. Explicitly deferred (do NOT build these)

- User auth — there's no concept of a user
- Real trading / order execution — adds compliance, API keys, money
- Fee modeling — call it out in README as a v2; "theoretical" is fine for now
- Multi-instance scaling / horizontal scale — single process is correct for this scope
- Postgres — SQLite is enough; don't add ops for nothing
- Redis — same
- Docker Compose with separate frontend/backend containers — one Dockerfile if you Dockerize at all
- Slippage simulation
- Withdrawal time / cross-chain logistics
- Historical backtesting framework
- Alerts (email, SMS, Discord)

## 10. The README is part of the deliverable

Recruiters will spend 30 seconds on the README and that's it. It must include, in this order:

1. One-sentence pitch
2. Architecture diagram (an actual image, not ASCII — use Excalidraw)
3. Screenshot of the dashboard (animated GIF if possible)
4. The numbers, with how they were measured
5. The honesty caveat about real-world fees and slippage
6. Tech stack
7. How to run it locally
8. Design tradeoffs (this is the section that signals seniority — explain *why* you chose SQLite, *why* one process, *why* asyncio over threads)
9. What you'd build next

## 11. Bugs and traps to expect

A non-exhaustive list, so you don't get blindsided:

- **Decimals matter.** Use `decimal.Decimal` for all prices and sizes. Floats will silently lose precision and give you spurious arb signals.
- **Crossed books are real and not always your fault.** Sometimes an exchange's deltas arrive out of order during high volatility. Decide how you handle it (drop one side? log and skip? resync?).
- **Clock skew between local time and exchange timestamps.** For your latency claims, measure within your own process — don't subtract exchange-supplied timestamps from local clocks.
- **Binance has stricter rate limits and a more complex stream subscription model.** Read the docs.
- **Coinbase Advanced Trade WebSocket replaced the old one.** Make sure you're on the current API.
- **Reconnect storms.** If all three exchanges disconnect at once and your backoff has no jitter, you'll get repeating thundering-herd reconnects. Add jitter.

## 12. What "done" looks like

You're done when, simultaneously:
- The system has been running for 24+ hours without crashing
- The benchmark script reports the resume numbers and you trust them
- A non-technical person can read the README and understand what the project does
- The repo is public on GitHub, the LinkedIn post is drafted, and the resume bullet is written