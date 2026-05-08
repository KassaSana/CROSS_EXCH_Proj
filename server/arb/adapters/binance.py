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
    ws_url = "wss://stream.binance.com:9443/ws"
    snapshot_url = "https://api.binance.com/api/v3/depth"

    async def subscribe(self, websocket: Any) -> None:
        params = [f"{pair.lower()}@depth" for pair in self.pairs]
        await websocket.send(self.encode({"method": "SUBSCRIBE", "params": params, "id": 1}))

    async def parse_message(self, message: str) -> list[MarketEvent]:
        payload = json.loads(message)
        if "b" in payload and "a" in payload and "s" in payload:
            return await self.finalize_events([
                MarketEvent(
                    exchange=self.name,
                    pair=normalize_binance_symbol(payload["s"]),
                    kind=EventKind.DELTA,
                    sequence=int(payload["u"]),
                    timestamp_ns=time.time_ns(),
                    bids=tuple(PriceLevel(price=Decimal(price), size=Decimal(size)) for price, size in payload["b"]),
                    asks=tuple(PriceLevel(price=Decimal(price), size=Decimal(size)) for price, size in payload["a"]),
                    raw_timestamp_ms=int(payload.get("E", 0)),
                )
            ])

        if "bids" not in payload or "asks" not in payload:
            return []
        return await self.finalize_events([
            MarketEvent(
                exchange=self.name,
                pair=normalize_binance_symbol(payload.get("symbol", self.pairs[0])),
                kind=EventKind.SNAPSHOT,
                sequence=int(payload["lastUpdateId"]),
                timestamp_ns=time.time_ns(),
                bids=tuple(PriceLevel(price=Decimal(price), size=Decimal(size)) for price, size in payload["bids"]),
                asks=tuple(PriceLevel(price=Decimal(price), size=Decimal(size)) for price, size in payload["asks"]),
            )
        ])

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
