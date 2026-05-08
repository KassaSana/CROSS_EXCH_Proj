from __future__ import annotations

import json
import time
from decimal import Decimal
from typing import Any

from arb.adapters.base import ExchangeAdapter
from arb.types import EventKind, MarketEvent, PriceLevel


def normalize_coinbase_symbol(symbol: str) -> str:
    return symbol.upper()


class CoinbaseAdapter(ExchangeAdapter):
    name = "coinbase"
    ws_url = "wss://advanced-trade-ws.coinbase.com"
    snapshot_url = "https://api.exchange.coinbase.com/products"

    async def subscribe(self, websocket: Any) -> None:
        await websocket.send(
            self.encode(
                {
                    "type": "subscribe",
                    "channel": "level2",
                    "product_ids": self.pairs,
                }
            )
        )

    async def parse_message(self, message: str) -> list[MarketEvent]:
        payload = json.loads(message)
        if payload.get("type") in {"snapshot", "update"} and payload.get("product_id"):
            return await self.finalize_events([self._build_event(payload)])

        events: list[MarketEvent] = []
        for channel_event in payload.get("events", []):
            if channel_event.get("type") not in {"snapshot", "update"}:
                continue
            events.append(self._build_event(channel_event))
        return await self.finalize_events(events)

    def _build_event(self, payload: dict[str, Any]) -> MarketEvent:
        pair = normalize_coinbase_symbol(payload["product_id"])
        bids = tuple(
            PriceLevel(price=Decimal(update["price_level"]), size=Decimal(update["new_quantity"]))
            for update in payload.get("updates", [])
            if update["side"] == "bid"
        )
        asks = tuple(
            PriceLevel(price=Decimal(update["price_level"]), size=Decimal(update["new_quantity"]))
            for update in payload.get("updates", [])
            if update["side"] == "offer"
        )
        return MarketEvent(
            exchange=self.name,
            pair=pair,
            kind=EventKind.SNAPSHOT if payload.get("type") == "snapshot" else EventKind.DELTA,
            sequence=int(payload.get("sequence_num", 0)),
            timestamp_ns=time.time_ns(),
            bids=bids,
            asks=asks,
        )

    async def fetch_snapshot(self, pair: str, trigger_sequence: int) -> MarketEvent:
        payload = await self.client_get_json(f"{self.snapshot_url}/{pair}/book?level=2")
        return MarketEvent(
            exchange=self.name,
            pair=pair,
            kind=EventKind.SNAPSHOT,
            sequence=max(int(payload.get("sequence", trigger_sequence)), trigger_sequence),
            timestamp_ns=time.time_ns(),
            bids=tuple(PriceLevel(price=Decimal(price), size=Decimal(size)) for price, size, *_ in payload["bids"]),
            asks=tuple(PriceLevel(price=Decimal(price), size=Decimal(size)) for price, size, *_ in payload["asks"]),
        )
