---
module: exchange-adapters
path: 02-Adapters
keywords: websocket, normalization, reconnect, resync, sequence
---

# Exchange Adapters

#module-adapters #pattern-adapter #pattern-resync

## Purpose

Adapters isolate Gemini, Coinbase, and Binance message formats behind one asynchronous contract. The base class owns reconnect-with-backoff, status tracking, HTTP snapshot access, and generic sequence finalization.

## Key Files

| File | Role |
|---|---|
| `server/arb/adapters/base.py` | Abstract contract, reconnect loop, status, gap resync |
| `server/arb/adapters/gemini.py` | Gemini symbols and message parsing |
| `server/arb/adapters/coinbase.py` | Coinbase level2 parsing |
| `server/arb/adapters/binance.py` | Binance depth parsing and local sequence assignment |

## Public Interface

| Export | Type | Description |
|---|---|---|
| `ExchangeAdapter` | abstract class | `connect`, `subscribe`, `parse_message`, `fetch_snapshot` |
| `AdapterStatusSnapshot` | dataclass | Health data for the API |
| `normalize_*_symbol` | function | Converts venue symbols to canonical pairs |

## Internal Flow

```text
raw WebSocket message
  -> venue parser
  -> canonical MarketEvent
  -> finalize_events()
  -> snapshot or contiguous delta
```

Gemini and Binance assign per-pair local sequences because their wire sequences are not suitable for direct per-pair gap checks. Coinbase uses its sequence numbers directly.

## Dependencies

| Direction | Module | Via |
|---|---|---|
| Uses | `types.py` | `MarketEvent`, `PriceLevel` |
| Uses | `metrics.py` | reconnect counter |
| Used by | `main.py` | adapter consumer tasks |
| Used by | `reconcile.py` | REST snapshots |

## Configuration

Exchange symbols come from `[exchanges]` in `config.toml`. WebSocket and snapshot URLs are class attributes.

## Testing

Run `python -m pytest server/tests/test_adapters -q` and replay fixtures. Tests should cover symbol normalization, snapshots, deltas, sequence gaps, and reconnect state reset.

## Related Notes

- [[Order Book State]]
- [[Request Flow]]
- [[API and Observability]]
