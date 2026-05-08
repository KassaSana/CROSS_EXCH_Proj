from __future__ import annotations

import asyncio
import time
from decimal import Decimal
from pathlib import Path

import pytest
from arb.persistence import OpportunityStore
from arb.types import ArbitrageOpportunity


def make_opp(timestamp_ns: int, spread: str = "1", profit: str = "0.5") -> ArbitrageOpportunity:
    return ArbitrageOpportunity(
        timestamp_ns=timestamp_ns,
        pair="BTC-USD",
        buy_exchange="gemini",
        sell_exchange="coinbase",
        buy_price=Decimal("100.123456789"),
        sell_price=Decimal("101.987654321"),
        spread_pct=Decimal(spread),
        max_size=Decimal("0.5"),
        theoretical_profit_usd=Decimal(profit),
    )


@pytest.mark.asyncio
async def test_initialize_is_idempotent(tmp_path: Path) -> None:
    store = OpportunityStore(str(tmp_path / "db.sqlite3"))
    await store.initialize()
    # Calling twice must not raise — uses CREATE IF NOT EXISTS.
    await store.initialize()


@pytest.mark.asyncio
async def test_batched_flush_by_size_writes_all_rows(tmp_path: Path) -> None:
    store = OpportunityStore(str(tmp_path / "db.sqlite3"), batch_size=3, flush_interval_seconds=5.0)
    await store.initialize()
    runner = asyncio.create_task(store.run())
    for index in range(3):
        await store.enqueue(make_opp(timestamp_ns=index + 1))
    # Allow batch-by-size flush to complete (no need to wait the 5s interval).
    await asyncio.sleep(0.1)
    rows = await store.recent(limit=10)
    assert len(rows) == 3
    await store.close()
    runner.cancel()


@pytest.mark.asyncio
async def test_flush_interval_drains_partial_batch(tmp_path: Path) -> None:
    store = OpportunityStore(str(tmp_path / "db.sqlite3"), batch_size=500, flush_interval_seconds=0.05)
    await store.initialize()
    runner = asyncio.create_task(store.run())
    await store.enqueue(make_opp(timestamp_ns=1))
    # Far below batch_size, but interval should fire.
    await asyncio.sleep(0.2)
    rows = await store.recent(limit=10)
    assert len(rows) == 1
    await store.close()
    runner.cancel()


@pytest.mark.asyncio
async def test_queue_full_returns_false_and_increments_drop_metric(tmp_path: Path) -> None:
    from arb.metrics import persistence_queue_drops_total

    before = persistence_queue_drops_total._value.get()
    store = OpportunityStore(str(tmp_path / "db.sqlite3"), queue_maxsize=1)
    # No runner — queue stays full.
    assert await store.enqueue(make_opp(1)) is True
    assert await store.enqueue(make_opp(2)) is False
    after = persistence_queue_drops_total._value.get()
    assert after - before == 1


@pytest.mark.asyncio
async def test_decimal_round_trip_preserves_string_form(tmp_path: Path) -> None:
    store = OpportunityStore(str(tmp_path / "db.sqlite3"), batch_size=1, flush_interval_seconds=5.0)
    await store.initialize()
    runner = asyncio.create_task(store.run())
    await store.enqueue(make_opp(timestamp_ns=10))
    await asyncio.sleep(0.1)
    [row] = await store.recent(limit=10)
    # Stored as TEXT — exact round trip with no float drift.
    assert row["buy_price"] == "100.123456789"
    assert row["sell_price"] == "101.987654321"
    await store.close()
    runner.cancel()


@pytest.mark.asyncio
async def test_recent_orders_descending_by_timestamp(tmp_path: Path) -> None:
    store = OpportunityStore(str(tmp_path / "db.sqlite3"), batch_size=10, flush_interval_seconds=0.05)
    await store.initialize()
    runner = asyncio.create_task(store.run())
    for ts in (10, 30, 20):
        await store.enqueue(make_opp(timestamp_ns=ts))
    await asyncio.sleep(0.2)
    rows = await store.recent(limit=10)
    assert [row["timestamp_ns"] for row in rows] == [30, 20, 10]
    await store.close()
    runner.cancel()


@pytest.mark.asyncio
async def test_stats_window_filters_out_old_rows(tmp_path: Path) -> None:
    store = OpportunityStore(str(tmp_path / "db.sqlite3"), batch_size=10, flush_interval_seconds=0.05)
    await store.initialize()
    runner = asyncio.create_task(store.run())
    now_ns = time.time_ns()
    await store.enqueue(make_opp(timestamp_ns=now_ns, spread="2", profit="1"))
    await store.enqueue(make_opp(timestamp_ns=now_ns - 10_000_000_000_000, spread="9", profit="100"))  # ~3h old
    await asyncio.sleep(0.2)

    one_hour_ns = 3_600_000_000_000
    stats = await store.stats(window_ns=one_hour_ns)
    assert stats["count"] == 1
    assert Decimal(stats["max_spread_pct"]) == Decimal("2")
    assert Decimal(stats["total_theoretical_profit_usd"]) == Decimal("1")
    await store.close()
    runner.cancel()


@pytest.mark.asyncio
async def test_stats_with_no_rows_returns_zeros(tmp_path: Path) -> None:
    store = OpportunityStore(str(tmp_path / "db.sqlite3"))
    await store.initialize()
    stats = await store.stats(window_ns=3_600_000_000_000)
    assert stats["count"] == 0
    assert Decimal(stats["max_spread_pct"]) == Decimal("0")
    assert Decimal(stats["total_theoretical_profit_usd"]) == Decimal("0")


@pytest.mark.asyncio
async def test_recent_on_empty_store_returns_empty_list(tmp_path: Path) -> None:
    store = OpportunityStore(str(tmp_path / "db.sqlite3"))
    await store.initialize()
    assert await store.recent(limit=5) == []
