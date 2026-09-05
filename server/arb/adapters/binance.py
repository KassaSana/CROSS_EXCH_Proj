from __future__ import annotations

import json
import time
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from arb.adapters.base import ExchangeAdapter
from arb.types import EventKind, MarketEvent, PriceLevel


def normalize_binance_symbol(symbol: str) -> str:
    upper = symbol.upper()
    if upper.endswith("USDT"):
        return f"{upper[:-4]}-USD"
    return upper


@dataclass(frozen=True)
class _DepthUpdate:
    pair: str
    first_id: int
    last_id: int
    bids: tuple[PriceLevel, ...]
    asks: tuple[PriceLevel, ...]


class BinanceAdapter(ExchangeAdapter):
    name = "binance"
    ws_url = "wss://stream.binance.us:9443/ws"
    snapshot_url = "https://api.binance.us/api/v3/depth"
    max_buffered_updates = 1_000

    def __init__(self, pairs: list[str]) -> None:
        super().__init__(pairs)
        self._initialized: set[str] = set()
        self._local_seq: dict[str, int] = {}
        self._last_exchange_update_id: dict[str, int] = {}
        self._buffers: dict[str, list[_DepthUpdate]] = {}

    async def reset_state(self) -> None:
        await super().reset_state()
        self._initialized.clear()
        self._local_seq.clear()
        self._last_exchange_update_id.clear()
        self._buffers.clear()

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
            update = _DepthUpdate(
                pair=pair,
                first_id=int(payload["U"]),
                last_id=int(payload["u"]),
                bids=bids,
                asks=asks,
            )
            return await self._emit(update)

        # REST snapshot shape (used by tests / direct calls).
        if "bids" in payload and "asks" in payload:
            pair = normalize_binance_symbol(payload.get("symbol", self.pairs[0]))
            bids = tuple(PriceLevel(price=Decimal(p), size=Decimal(s)) for p, s in payload["bids"])
            asks = tuple(PriceLevel(price=Decimal(p), size=Decimal(s)) for p, s in payload["asks"])
            seq = int(payload["lastUpdateId"])
            self._initialized.add(pair)
            self._local_seq[pair] = seq
            self._last_exchange_update_id[pair] = seq
            self._last_sequence_by_pair[pair] = seq
            return [MarketEvent(
                exchange=self.name, pair=pair, kind=EventKind.SNAPSHOT,
                sequence=seq, timestamp_ns=time.time_ns(), bids=bids, asks=asks,
                exchange_last_sequence=seq,
            )]

        return []

    async def _emit(self, update: _DepthUpdate) -> list[MarketEvent]:
        """Buffer and align depth updates before exposing a trusted book."""
        if update.pair not in self._initialized:
            buffer = self._buffers.setdefault(update.pair, [])
            buffer.append(update)
            if len(buffer) > self.max_buffered_updates:
                self._restart_sync(update.pair)
                return []
            return await self._synchronize(update.pair)

        last_id = self._last_exchange_update_id[update.pair]
        if update.last_id <= last_id:
            return []
        if update.first_id > last_id + 1:
            self.gap_count += 1
            self._restart_sync(update.pair)
            return []
        return [self._delta_event(update)]

    async def _synchronize(self, pair: str) -> list[MarketEvent]:
        buffer = self._buffers.get(pair, [])
        for _ in range(3):
            snapshot = await self.fetch_snapshot(pair, trigger_sequence=0)
            snapshot_id = snapshot.exchange_last_sequence or snapshot.sequence
            if snapshot_id < buffer[0].first_id:
                continue

            pending = [update for update in buffer if update.last_id > snapshot_id]
            if pending and not (pending[0].first_id <= snapshot_id + 1 <= pending[0].last_id):
                self._restart_sync(pair)
                return []

            self._initialized.add(pair)
            self._local_seq[pair] = snapshot.sequence
            self._last_exchange_update_id[pair] = snapshot_id
            self._last_sequence_by_pair[pair] = snapshot.sequence
            self._buffers.pop(pair, None)
            events = [snapshot]
            for update in pending:
                last_id = self._last_exchange_update_id[pair]
                if update.last_id <= last_id:
                    continue
                if update.first_id > last_id + 1:
                    self.gap_count += 1
                    self._restart_sync(pair)
                    return []
                events.append(self._delta_event(update))
            return events

        self._restart_sync(pair)
        return []

    def _delta_event(self, update: _DepthUpdate) -> MarketEvent:
        sequence = self._local_seq[update.pair] + 1
        self._local_seq[update.pair] = sequence
        self._last_exchange_update_id[update.pair] = update.last_id
        self._last_sequence_by_pair[update.pair] = sequence
        return MarketEvent(
            exchange=self.name, pair=update.pair, kind=EventKind.DELTA,
            sequence=sequence, timestamp_ns=time.time_ns(), bids=update.bids, asks=update.asks,
            exchange_first_sequence=update.first_id,
            exchange_last_sequence=update.last_id,
        )

    def _restart_sync(self, pair: str) -> None:
        self._initialized.discard(pair)
        self._local_seq.pop(pair, None)
        self._last_exchange_update_id.pop(pair, None)
        self._last_sequence_by_pair.pop(pair, None)
        self._buffers.pop(pair, None)
        self.request_reconnect()

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
            exchange_last_sequence=sequence,
        )
