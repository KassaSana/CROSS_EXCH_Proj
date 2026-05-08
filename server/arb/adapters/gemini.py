from __future__ import annotations

import json
import time
from decimal import Decimal
from typing import Any

from arb.adapters.base import ExchangeAdapter
from arb.types import EventKind, MarketEvent, PriceLevel


def normalize_gemini_symbol(symbol: str) -> str:
    s = symbol.upper()
    if s.endswith("USDT"):
        return f"{s[:-4]}-USD"
    if s.endswith("USD"):
        return f"{s[:-3]}-USD"
    return s


class GeminiAdapter(ExchangeAdapter):
    name = "gemini"
    ws_url = "wss://api.gemini.com/v2/marketdata"
    snapshot_url = "https://api.gemini.com/v1/book"

    def __init__(self, pairs: list[str]) -> None:
        super().__init__(pairs)
        # Track which pairs have been initialized via REST snapshot.
        # Gemini v2 socket_sequence is connection-level (not per-symbol), so we
        # cannot use it for per-pair gap detection. Instead, fetch a REST snapshot
        # on first WS message per pair and assign our own monotonic sequence.
        self._initialized: set[str] = set()
        self._pair_seq: dict[str, int] = {}

    async def subscribe(self, websocket: Any) -> None:
        symbols = [pair.upper().replace("-", "") for pair in self.pairs]
        await websocket.send(self.encode({
            "type": "subscribe",
            "subscriptions": [{"name": "l2", "symbols": symbols}],
        }))

    async def parse_message(self, message: str) -> list[MarketEvent]:
        payload = json.loads(message)
        msg_type = payload.get("type")

        # v2 API: all book updates arrive as l2_updates with a "changes" array.
        # Each entry is [side, price, quantity] where side is "buy" or "sell".
        if msg_type == "l2_updates":
            symbol = payload.get("symbol", "")
            if not symbol:
                return []
            pair = normalize_gemini_symbol(symbol)
            changes = payload.get("changes", [])
            bids = tuple(PriceLevel(price=Decimal(c[1]), size=Decimal(c[2])) for c in changes if c[0] == "buy")
            asks = tuple(PriceLevel(price=Decimal(c[1]), size=Decimal(c[2])) for c in changes if c[0] == "sell")
            return await self._emit(pair, bids, asks)

        # v1-style snapshot (bids/asks as list-of-lists) — kept for test fixtures.
        if "bids" in payload and "asks" in payload:
            pair = normalize_gemini_symbol(payload.get("symbol", self.pairs[0]))
            bids = tuple(PriceLevel(price=Decimal(p), size=Decimal(s)) for p, s in payload["bids"])
            asks = tuple(PriceLevel(price=Decimal(p), size=Decimal(s)) for p, s in payload["asks"])
            seq = int(payload.get("socket_sequence", payload.get("lastUpdateId", 0)))
            self._initialized.add(pair)
            self._pair_seq[pair] = seq
            self._last_sequence_by_pair[pair] = seq
            return [MarketEvent(
                exchange=self.name, pair=pair, kind=EventKind.SNAPSHOT,
                sequence=seq, timestamp_ns=time.time_ns(), bids=bids, asks=asks,
            )]

        # v1-style delta (events array with side/price/remaining) — kept for test fixtures.
        if "events" in payload and "symbol" in payload:
            pair = normalize_gemini_symbol(payload["symbol"])
            bids = tuple(PriceLevel(price=Decimal(e["price"]), size=Decimal(e["remaining"])) for e in payload["events"] if e["side"] == "bid")
            asks = tuple(PriceLevel(price=Decimal(e["price"]), size=Decimal(e["remaining"])) for e in payload["events"] if e["side"] == "ask")
            return await self._emit(pair, bids, asks)

        return []

    async def _emit(self, pair: str, bids: tuple[PriceLevel, ...], asks: tuple[PriceLevel, ...]) -> list[MarketEvent]:
        """Emit a snapshot on first message for a pair, then sequential deltas."""
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
        symbol = pair.replace("-", "").lower()
        payload = await self.client_get_json(f"{self.snapshot_url}/{symbol}?limit_bids=100&limit_asks=100")
        sequence = int(payload.get("socket_sequence", payload.get("lastUpdateId", trigger_sequence)))
        return MarketEvent(
            exchange=self.name,
            pair=pair,
            kind=EventKind.SNAPSHOT,
            sequence=max(sequence, trigger_sequence),
            timestamp_ns=time.time_ns(),
            bids=tuple(PriceLevel(price=Decimal(level["price"]), size=Decimal(level["amount"])) for level in payload["bids"]),
            asks=tuple(PriceLevel(price=Decimal(level["price"]), size=Decimal(level["amount"])) for level in payload["asks"]),
        )
