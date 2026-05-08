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
    ws_url = "wss://api.gemini.com/v1/marketdata"
    snapshot_url = "https://api.gemini.com/v1/book"

    async def subscribe(self, websocket: Any) -> None:
        # Gemini uses per-symbol URLs for market data, so the adapter currently
        # expects one symbol per websocket in a production deployment.
        await websocket.send(self.encode({"type": "subscribe", "subscriptions": self.pairs}))

    async def parse_message(self, message: str) -> list[MarketEvent]:
        payload = json.loads(message)
        if "bids" in payload and "asks" in payload:
            return await self.finalize_events([
                MarketEvent(
                    exchange=self.name,
                    pair=normalize_gemini_symbol(payload.get("symbol", self.pairs[0])),
                    kind=EventKind.SNAPSHOT,
                    sequence=int(payload.get("lastUpdateId", payload.get("socket_sequence", 0))),
                    timestamp_ns=time.time_ns(),
                    bids=tuple(PriceLevel(price=Decimal(price), size=Decimal(size)) for price, size in payload["bids"]),
                    asks=tuple(PriceLevel(price=Decimal(price), size=Decimal(size)) for price, size in payload["asks"]),
                )
            ])
        if "events" not in payload:
            return []
        pair = normalize_gemini_symbol(payload["symbol"])
        levels_bid: list[PriceLevel] = []
        levels_ask: list[PriceLevel] = []
        for item in payload["events"]:
            side = levels_bid if item["side"] == "bid" else levels_ask
            side.append(PriceLevel(price=Decimal(item["price"]), size=Decimal(item["remaining"])))
        return await self.finalize_events([
            MarketEvent(
                exchange=self.name,
                pair=pair,
                kind=EventKind.DELTA,
                sequence=int(payload.get("socket_sequence", 0)),
                timestamp_ns=time.time_ns(),
                bids=tuple(levels_bid),
                asks=tuple(levels_ask),
            )
        ])

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
