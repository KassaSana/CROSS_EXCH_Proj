from __future__ import annotations

import asyncio
from dataclasses import dataclass
from decimal import Decimal
from itertools import cycle

import structlog

from arb.adapters.base import ExchangeAdapter
from arb.metrics import reconcile_mismatches_total
from arb.orderbook import OrderBookManager
from arb.types import PriceLevel

logger = structlog.get_logger(__name__)

MISMATCH_THRESHOLD_PCT = Decimal("0.5")


@dataclass(frozen=True)
class ReconcileTarget:
    exchange: str
    pair: str


class SnapshotReconciler:
    def __init__(self, adapters: list[ExchangeAdapter], book_manager: OrderBookManager, pairs: list[tuple[str, str]], interval_seconds: float = 60.0) -> None:
        self._adapter_by_name = {adapter.name: adapter for adapter in adapters}
        self.book_manager = book_manager
        self.interval_seconds = interval_seconds
        self._targets = cycle(ReconcileTarget(exchange, pair) for exchange, pair in pairs)

    async def run(self) -> None:
        while True:
            await asyncio.sleep(self.interval_seconds)
            await self.reconcile_next()

    async def reconcile_next(self) -> None:
        target = next(self._targets, None)
        if target is None:
            return
        adapter = self._adapter_by_name.get(target.exchange)
        if adapter is None:
            return

        live_levels = self.book_manager.level_snapshot(target.exchange, target.pair, limit=10)
        if live_levels is None:
            return

        snapshot = await adapter.fetch_snapshot(target.pair, trigger_sequence=0)
        snapshot_levels = (list(snapshot.bids[:10]), list(snapshot.asks[:10]))
        mismatch_pct = max(
            self._side_mismatch_pct(live_levels[0], snapshot_levels[0]),
            self._side_mismatch_pct(live_levels[1], snapshot_levels[1]),
        )
        if mismatch_pct <= MISMATCH_THRESHOLD_PCT:
            return

        reconcile_mismatches_total.labels(exchange=target.exchange, pair=target.pair).inc()
        logger.warning(
            "snapshot_reconcile_mismatch",
            exchange=target.exchange,
            pair=target.pair,
            mismatch_pct=str(mismatch_pct),
        )

    def _side_mismatch_pct(self, live_levels: list[PriceLevel], snapshot_levels: list[PriceLevel]) -> Decimal:
        comparisons = zip(live_levels, snapshot_levels)
        mismatch_pct = Decimal("0")
        for live_level, snapshot_level in comparisons:
            baseline = snapshot_level.price if snapshot_level.price != Decimal("0") else Decimal("1")
            diff_pct = (abs(live_level.price - snapshot_level.price) / baseline) * Decimal("100")
            mismatch_pct = max(mismatch_pct, diff_pct)
        return mismatch_pct
