from __future__ import annotations

import asyncio
import time
from collections.abc import Iterable
from decimal import Decimal
from typing import Any

import aiosqlite

from arb.metrics import persistence_queue_drops_total
from arb.types import ArbitrageOpportunity

CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS opportunities (
    id INTEGER PRIMARY KEY,
    timestamp_ns INTEGER NOT NULL,
    pair TEXT NOT NULL,
    buy_exchange TEXT NOT NULL,
    sell_exchange TEXT NOT NULL,
    buy_price TEXT NOT NULL,
    sell_price TEXT NOT NULL,
    spread_pct TEXT NOT NULL,
    max_size TEXT NOT NULL,
    theoretical_profit_usd TEXT NOT NULL
);
"""

CREATE_INDEX_SQL = """
CREATE INDEX IF NOT EXISTS idx_opps_timestamp ON opportunities(timestamp_ns);
CREATE INDEX IF NOT EXISTS idx_opps_pair_ts ON opportunities(pair, timestamp_ns);
"""


class OpportunityStore:
    def __init__(
        self,
        db_path: str,
        batch_size: int = 500,
        flush_interval_seconds: float = 1.0,
        queue_maxsize: int = 10_000,
    ) -> None:
        self.db_path = db_path
        self.batch_size = batch_size
        self.flush_interval_seconds = flush_interval_seconds
        self._queue: asyncio.Queue[ArbitrageOpportunity] = asyncio.Queue(maxsize=queue_maxsize)
        self._stop_event = asyncio.Event()

    async def initialize(self) -> None:
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("PRAGMA journal_mode=WAL;")
            await db.executescript(CREATE_TABLE_SQL + CREATE_INDEX_SQL)
            await db.commit()

    async def enqueue(self, opportunity: ArbitrageOpportunity) -> bool:
        try:
            self._queue.put_nowait(opportunity)
        except asyncio.QueueFull:
            persistence_queue_drops_total.inc()
            return False
        return True

    async def run(self) -> None:
        batch: list[ArbitrageOpportunity] = []
        while not self._stop_event.is_set():
            try:
                item = await asyncio.wait_for(self._queue.get(), timeout=self.flush_interval_seconds)
                batch.append(item)
                if len(batch) >= self.batch_size:
                    await self._flush(batch)
                    batch.clear()
            except TimeoutError:
                if batch:
                    await self._flush(batch)
                    batch.clear()

        if batch:
            await self._flush(batch)

    async def close(self) -> None:
        self._stop_event.set()

    async def recent(self, limit: int = 100) -> list[dict[str, Any]]:
        query = """
        SELECT timestamp_ns, pair, buy_exchange, sell_exchange, buy_price, sell_price,
               spread_pct, max_size, theoretical_profit_usd
        FROM opportunities
        ORDER BY timestamp_ns DESC
        LIMIT ?
        """
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute(query, (limit,))
            rows = await cursor.fetchall()
        return [
            {
                "timestamp_ns": row[0],
                "pair": row[1],
                "buy_exchange": row[2],
                "sell_exchange": row[3],
                "buy_price": row[4],
                "sell_price": row[5],
                "spread_pct": row[6],
                "max_size": row[7],
                "theoretical_profit_usd": row[8],
            }
            for row in rows
        ]

    async def stats(self, window_ns: int) -> dict[str, str | int]:
        query = """
        SELECT COUNT(*), COALESCE(MAX(CAST(spread_pct AS REAL)), 0), COALESCE(SUM(CAST(theoretical_profit_usd AS REAL)), 0)
        FROM opportunities
        WHERE timestamp_ns >= ?
        """
        cutoff_ns = time.time_ns() - window_ns
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute(query, (cutoff_ns,))
            row = await cursor.fetchone()
        if row is None:
            return {
                "count": 0,
                "max_spread_pct": "0",
                "total_theoretical_profit_usd": "0",
            }
        return {
            "count": int(row[0]),
            "max_spread_pct": str(Decimal(str(row[1]))),
            "total_theoretical_profit_usd": str(Decimal(str(row[2]))),
        }

    async def _flush(self, batch: Iterable[ArbitrageOpportunity]) -> None:
        rows = [
            (
                opp.timestamp_ns,
                opp.pair,
                opp.buy_exchange,
                opp.sell_exchange,
                str(opp.buy_price),
                str(opp.sell_price),
                str(opp.spread_pct),
                str(opp.max_size),
                str(opp.theoretical_profit_usd),
            )
            for opp in batch
        ]
        async with aiosqlite.connect(self.db_path) as db:
            await db.executemany(
                """
                INSERT INTO opportunities (
                    timestamp_ns, pair, buy_exchange, sell_exchange, buy_price, sell_price,
                    spread_pct, max_size, theoretical_profit_usd
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                rows,
            )
            await db.commit()
