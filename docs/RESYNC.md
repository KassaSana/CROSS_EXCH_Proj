# Resync Strategy

This project uses adapter-driven resync on sequence gaps.

Chosen strategy:
- Drop the local sequence chain for the affected `(exchange, pair)` stream
- Fetch a fresh REST snapshot for that exchange/pair
- Emit a synthetic `snapshot` `MarketEvent`
- Resume processing future deltas from the snapshot sequence

Why this approach:
- It is simpler and more reliable for a portfolio-scale single-process system than buffering out-of-order deltas during resync.
- It keeps the recovery logic close to the exchange adapter, which is where exchange-specific sequence semantics already live.
- It gives the `OrderBookManager` a clean snapshot boundary instead of forcing it to recover from partially trusted delta streams.

Tradeoffs:
- A REST snapshot introduces extra latency during the resync window.
- If the exchange snapshot endpoint doesn't provide an exact sequence number, the adapter falls back to the triggering live sequence so the stream can continue.
- This is less exact than exchange-specific buffered reconciliation, but it is operationally simpler and aligned with the project scope.

Per exchange:
- `Gemini`: on gap, fetches `GET /v1/book/{symbol}` and emits a snapshot using the returned sequence if available, otherwise the triggering sequence.
- `Coinbase`: on gap, fetches `GET /products/{id}/book?level=2` and emits a snapshot using the returned sequence if present, otherwise the triggering sequence.
- `Binance`: on gap, fetches `GET /api/v3/depth?symbol=...&limit=1000` and emits a snapshot keyed to `lastUpdateId`.
