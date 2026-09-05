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

    def __init__(self, pairs: list[str]) -> None:
        super().__init__(pairs)
        self._awaiting_snapshot: set[str] = set()

    async def reset_state(self) -> None:
        await super().reset_state()
        self._awaiting_snapshot.clear()

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
            return self._finalize_stream_events([self._build_event(payload)])

        events: list[MarketEvent] = []
        envelope_sequence = payload.get("sequence_num")
        for channel_event in payload.get("events", []):
            if channel_event.get("type") not in {"snapshot", "update"}:
                continue
            events.append(self._build_event(channel_event, envelope_sequence))
        return self._finalize_stream_events(events)

    def _build_event(self, payload: dict[str, Any], envelope_sequence: Any = None) -> MarketEvent:
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
            sequence=int(payload.get("sequence_num", envelope_sequence or 0)),
            timestamp_ns=time.time_ns(),
            bids=bids,
            asks=asks,
        )

    def _finalize_stream_events(self, events: list[MarketEvent]) -> list[MarketEvent]:
        """Accept contiguous WebSocket events without mixing REST sequences."""
        finalized: list[MarketEvent] = []
        for event in events:
            pair = event.pair
            if event.kind is EventKind.SNAPSHOT:
                self._last_sequence_by_pair[pair] = event.sequence
                self._awaiting_snapshot.discard(pair)
                finalized.append(event)
                continue

            if pair in self._awaiting_snapshot:
                continue
            last_sequence = self._last_sequence_by_pair.get(pair)
            if last_sequence is None:
                self._awaiting_snapshot.add(pair)
                continue
            if event.sequence <= last_sequence:
                continue
            if event.sequence != last_sequence + 1:
                self.gap_count += 1
                self._last_sequence_by_pair.pop(pair, None)
                self._awaiting_snapshot.add(pair)
                self.request_reconnect()
                continue
            self._last_sequence_by_pair[pair] = event.sequence
            finalized.append(event)
        return finalized

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
