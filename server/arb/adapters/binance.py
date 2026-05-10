from __future__ import annotations

import json
import time
from decimal import Decimal
from typing import Any

from arb.adapters.base import ExchangeAdapter
from arb.types import EventKind, MarketEvent, PriceLevel


def normalize_binance_symbol(symbol: str) -> str:
    upper = symbol.upper()
    if upper.endswith("USDT"):
        return f"{upper[:-4]}-USD"
    return upper


class BinanceAdapter(ExchangeAdapter):
    name = "binance"
    ws_url = "wss://stream.binance.us:9443/ws"
    snapshot_url = "https://api.binance.us/api/v3/depth"

    def __init__(self, pairs: list[str]) -> None:
        super().__init__(pairs)
        # Binance depth deltas carry a [U, u] range; u jumps by >1 between
        # messages, so using u as a per-event sequence triggers false gaps.
        # Track per-pair init state and assign our own monotonic sequence.
        self._initialized: set[str] = set()
        self._pair_seq: dict[str, int] = {}

    async def reset_state(self) -> None:
        await super().reset_state()
        self._initialized.clear()
        self._pair_seq.clear()

    async def subscribe(self, websocket: Any) -> None:
        params = [f"{pair.lower()}@depth" for pair in self.pairs]
        await websocket.send(self.encode({"method": "SUBSCRIBE", "params": params, "id": 1}))

    async def parse_message(self, message: str) -> list[MarketEvent]:
        payload = json.loads(message)

        # Depth diff stream: {"s": symbol, "U": first_id, "u": last_id, "b": bids, "a": asks}
        if "b" in payload and "a" in payload and "s" in payload:
            pair = normalize_binance_symbol(payload["s"])
            bids = tuple(PriceLevel(price=Decimal(p), size=Decimal(s)) for p, s in payload["b"])
            asks = tuple(PriceLevel(price=Decimal(p), size=Decimal(s)) for p, s in payload["a"])
            return await self._emit(pair, bids, asks)

        # REST snapshot shape (used by tests / direct calls).
        if "bids" in payload and "asks" in payload:
            pair = normalize_binance_symbol(payload.get("symbol", self.pairs[0]))
            bids = tuple(PriceLevel(price=Decimal(p), size=Decimal(s)) for p, s in payload["bids"])
            asks = tuple(PriceLevel(price=Decimal(p), size=Decimal(s)) for p, s in payload["asks"])
            seq = int(payload["lastUpdateId"])
            self._initialized.add(pair)
            self._pair_seq[pair] = seq
            self._last_sequence_by_pair[pair] = seq
            return [MarketEvent(
                exchange=self.name, pair=pair, kind=EventKind.SNAPSHOT,
                sequence=seq, timestamp_ns=time.time_ns(), bids=bids, asks=asks,
            )]

        return []

    async def _emit(self, pair: str, bids: tuple[PriceLevel, ...], asks: tuple[PriceLevel, ...]) -> list[MarketEvent]:
        """Emit a REST snapshot on first message per pair, then sequential deltas."""
        if pair not in self._initialized:
            self._initialized.add(pair)
            snapshot = await self.fetch_snapshot(pair, trigger_sequence=0)
            self._pair_seq[pair] = snapshot.sequence
            self._last_sequence_by_pair[pair] = snapshot.sequence
            return [snapshot]
        seq = self._pair_seq[pair] + 1
        self._pair_seq[pair] = seq
        self._last_sequence_by_pair[pair] = seq
        return [MarketEvent(
            exchange=self.name, pair=pair, kind=EventKind.DELTA,
            sequence=seq, timestamp_ns=time.time_ns(), bids=bids, asks=asks,
        )]

    async def fetch_snapshot(self, pair: str, trigger_sequence: int) -> MarketEvent:
        symbol = pair.replace("-USD", "USDT")
        payload = await self.client_get_json(f"{self.snapshot_url}?symbol={symbol}&limit=1000")
        sequence = int(payload.get("lastUpdateId", trigger_sequence))
        return MarketEvent(
            exchange=self.name,
            pair=pair,
            kind=EventKind.SNAPSHOT,
            sequence=max(sequence, trigger_sequence),
            timestamp_ns=time.time_ns(),
            bids=tuple(PriceLevel(price=Decimal(price), size=Decimal(size)) for price, size in payload["bids"]),
            asks=tuple(PriceLevel(price=Decimal(price), size=Decimal(size)) for price, size in payload["asks"]),
        )
