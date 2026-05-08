from __future__ import annotations

import json
import time
from decimal import Decimal
from typing import Any

from arb.adapters.base import ExchangeAdapter
from arb.types import EventKind, MarketEvent, PriceLevel


def normalize_gemini_symbol(symbol: str) -> str:
    base = symbol[:3].upper()
    quote = symbol[3:].upper()
    return f"{base}-{quote}"


class GeminiAdapter(ExchangeAdapter):
    name = "gemini"
    ws_url = "wss://api.gemini.com/v2/marketdata"
    snapshot_url = "https://api.gemini.com/v1/book"

    async def subscribe(self, websocket: Any) -> None:
        # Gemini v2 API: subscribe to l2 channel with normalized symbols.
        symbols = [pair.lower().replace("-", "") for pair in self.pairs]
        await websocket.send(self.encode({
            "type": "subscribe",
            "subscriptions": [{"name": "l2", "symbols": symbols}],
        }))

    async def parse_message(self, message: str) -> list[MarketEvent]:
        payload = json.loads(message)
        msg_type = payload.get("type")

        # v2 API: initial full book snapshot
        if msg_type == "l2_updates" and payload.get("changes") is None:
            events: list[MarketEvent] = []
            for update in payload.get("updates", [{}]):
                symbol = update.get("symbol", "")
                if not symbol:
                    continue
                pair = normalize_gemini_symbol(symbol)
                bids = tuple(PriceLevel(price=Decimal(c[1]), size=Decimal(c[2])) for c in update.get("changes", []) if c[0] == "buy")
                asks = tuple(PriceLevel(price=Decimal(c[1]), size=Decimal(c[2])) for c in update.get("changes", []) if c[0] == "sell")
                events.append(MarketEvent(
                    exchange=self.name,
                    pair=pair,
                    kind=EventKind.SNAPSHOT if update.get("type") == "initial" else EventKind.DELTA,
                    sequence=int(payload.get("socket_sequence", 0)),
                    timestamp_ns=time.time_ns(),
                    bids=bids,
                    asks=asks,
                ))
            return await self.finalize_events(events)

        # v2 API: incremental updates
        if msg_type == "l2_updates":
            symbol = payload.get("symbol", "")
            if not symbol:
                return []
            pair = normalize_gemini_symbol(symbol)
            bids = tuple(PriceLevel(price=Decimal(c[1]), size=Decimal(c[2])) for c in payload.get("changes", []) if c[0] == "buy")
            asks = tuple(PriceLevel(price=Decimal(c[1]), size=Decimal(c[2])) for c in payload.get("changes", []) if c[0] == "sell")
            return await self.finalize_events([MarketEvent(
                exchange=self.name,
                pair=pair,
                kind=EventKind.DELTA,
                sequence=int(payload.get("socket_sequence", 0)),
                timestamp_ns=time.time_ns(),
                bids=bids,
                asks=asks,
            )])

        # v1-style fallback (legacy shape)
        if "bids" in payload and "asks" in payload:
            return await self.finalize_events([MarketEvent(
                exchange=self.name,
                pair=normalize_gemini_symbol(payload.get("symbol", self.pairs[0])),
                kind=EventKind.SNAPSHOT,
                sequence=int(payload.get("socket_sequence", 0)),
                timestamp_ns=time.time_ns(),
                bids=tuple(PriceLevel(price=Decimal(p), size=Decimal(s)) for p, s in payload["bids"]),
                asks=tuple(PriceLevel(price=Decimal(p), size=Decimal(s)) for p, s in payload["asks"]),
            )])

        return []

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
