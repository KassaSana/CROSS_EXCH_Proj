---
module: detection
path: 04-Detection
keywords: spread, threshold, permutations, decimal, opportunity
---

# Arbitrage Detection

#module-detection #pattern-pure-calculation

## Purpose

`ArbitrageDetector` compares every ordered pair of valid exchange books for one canonical trading pair. It treats one venue's best ask as the buy price and another venue's best bid as the sell price.

## Key File

| File | Role |
|---|---|
| `server/arb/detector.py` | detector implementation |
| `server/arb/types.py` | `ArbitrageOpportunity` |
| `server/tests/test_detector.py` | spread and precision tests |

## Calculation

```text
if sell_bid <= buy_ask: skip
spread_pct = (sell_bid - buy_ask) / buy_ask * 100
if spread_pct < threshold: skip
max_size = min(buy_ask_size, sell_bid_size)
profit = max_size * (sell_bid - buy_ask)
```

The implementation uses `itertools.permutations`, so with three books it evaluates six directed legs. It emits only legs whose sell bid exceeds the other book's ask by at least the configured threshold.

## Dependencies

The detector depends on `TopOfBook` and `ArbitrageOpportunity`. `main.py` invokes it after a book update; persistence and broadcasting consume its output.

## Configuration

`[detector].threshold_pct` in `config.toml` is currently `0.1`, meaning 0.1 percent.

## Testing

Run `python -m pytest server/tests/test_detector.py -q`. Tests cover incomplete books, threshold boundaries, multiple exchanges, max size, theoretical profit, and Decimal serialization.

## Related Notes

- [[Order Book State]]
- [[Persistence]]
- [[System Architecture]]
