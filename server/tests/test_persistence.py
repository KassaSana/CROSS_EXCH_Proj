from __future__ import annotations

import asyncio
import time
from decimal import Decimal
from pathlib import Path

import pytest
from arb.persistence import OpportunityStore
from arb.types import ArbitrageOpportunity


def make_opp(
    timestamp_ns: int, spread: str = "1", profit: str = "0.5", pair: str = "BTC-USD"
) -> ArbitrageOpportunity:
    return ArbitrageOpportunity(
        timestamp_ns=timestamp_ns,
        pair=pair,
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
    store = OpportunityStore(
        str(tmp_path / "db.sqlite3"), batch_size=500, flush_interval_seconds=0.05
    )
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
async def test_close_drains_every_accepted_opportunity(tmp_path: Path) -> None:
    store = OpportunityStore(
        str(tmp_path / "db.sqlite3"),
        batch_size=500,
        flush_interval_seconds=60.0,
        queue_maxsize=10,
    )
    await store.initialize()
    runner = asyncio.create_task(store.run())

    for timestamp_ns in range(1, 6):
        assert await store.enqueue(make_opp(timestamp_ns)) is True

    await store.close()
    await asyncio.wait_for(runner, timeout=1.0)

    rows = await store.recent(limit=10)
    assert [row["timestamp_ns"] for row in rows] == [5, 4, 3, 2, 1]


@pytest.mark.asyncio
async def test_enqueue_rejects_new_work_after_close(tmp_path: Path) -> None:
    store = OpportunityStore(str(tmp_path / "db.sqlite3"))
    await store.initialize()
    runner = asyncio.create_task(store.run())

    await store.close()
    await runner

    assert await store.enqueue(make_opp(1)) is False


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
    store = OpportunityStore(
        str(tmp_path / "db.sqlite3"), batch_size=10, flush_interval_seconds=0.05
    )
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
    store = OpportunityStore(
        str(tmp_path / "db.sqlite3"), batch_size=10, flush_interval_seconds=0.05
    )
    await store.initialize()
    runner = asyncio.create_task(store.run())
    now_ns = time.time_ns()
    await store.enqueue(make_opp(timestamp_ns=now_ns, spread="2", profit="1"))
    await store.enqueue(
        make_opp(timestamp_ns=now_ns - 10_000_000_000_000, spread="9", profit="100")
    )  # ~3h old
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


@pytest.mark.asyncio
async def test_extended_stats_aggregates_within_window(tmp_path: Path) -> None:
    store = OpportunityStore(
        str(tmp_path / "db.sqlite3"), batch_size=10, flush_interval_seconds=0.05
    )
    await store.initialize()
    runner = asyncio.create_task(store.run())
    now_ns = time.time_ns()
    # 3 BTC opps, 1 ETH opp inside window; one stale ETH outside.
    await store.enqueue(make_opp(now_ns, spread="2", profit="1", pair="BTC-USD"))
    await store.enqueue(make_opp(now_ns - 1, spread="3", profit="2", pair="BTC-USD"))
    await store.enqueue(make_opp(now_ns - 2, spread="1", profit="0.5", pair="BTC-USD"))
    await store.enqueue(make_opp(now_ns - 3, spread="5", profit="10", pair="ETH-USD"))
    await store.enqueue(
        make_opp(now_ns - 10_000_000_000_000, spread="99", profit="999", pair="ETH-USD")
    )
    await asyncio.sleep(0.2)

    stats = await store.extended_stats(window_ns=3_600_000_000_000)
    assert stats["count"] == 4
    assert Decimal(str(stats["max_spread_pct"])) == Decimal("5")
    assert Decimal(str(stats["mean_spread_pct"])) == Decimal("2.75")
    assert Decimal(str(stats["total_theoretical_profit_usd"])) == Decimal("13.5")
    assert stats["top_pair"] == "BTC-USD"
    await store.close()
    runner.cancel()


@pytest.mark.asyncio
async def test_extended_stats_all_time_with_window_none(tmp_path: Path) -> None:
    store = OpportunityStore(
        str(tmp_path / "db.sqlite3"), batch_size=10, flush_interval_seconds=0.05
    )
    await store.initialize()
    runner = asyncio.create_task(store.run())
    await store.enqueue(make_opp(timestamp_ns=1, spread="2", pair="BTC-USD"))
    await store.enqueue(make_opp(timestamp_ns=2, spread="4", pair="BTC-USD"))
    await asyncio.sleep(0.2)

    stats = await store.extended_stats(window_ns=None)
    assert stats["count"] == 2
    assert Decimal(str(stats["max_spread_pct"])) == Decimal("4")
    assert stats["top_pair"] == "BTC-USD"
    await store.close()
    runner.cancel()


@pytest.mark.asyncio
async def test_extended_stats_empty_returns_safe_defaults(tmp_path: Path) -> None:
    store = OpportunityStore(str(tmp_path / "db.sqlite3"))
    await store.initialize()
    stats = await store.extended_stats(window_ns=3_600_000_000_000)
    assert stats["count"] == 0
    assert Decimal(str(stats["max_spread_pct"])) == Decimal("0")
    assert Decimal(str(stats["mean_spread_pct"])) == Decimal("0")
    assert Decimal(str(stats["total_theoretical_profit_usd"])) == Decimal("0")
    assert stats["top_pair"] is None


@pytest.mark.asyncio
async def test_peak_minute_returns_busiest_bucket(tmp_path: Path) -> None:
    store = OpportunityStore(
        str(tmp_path / "db.sqlite3"), batch_size=20, flush_interval_seconds=0.05
    )
    await store.initialize()
    runner = asyncio.create_task(store.run())
    minute_ns = 60_000_000_000
    base = (time.time_ns() // minute_ns) * minute_ns
    # Minute A: 2 opps. Minute B: 5 opps (the peak).
    for offset in range(2):
        await store.enqueue(make_opp(timestamp_ns=base + offset))
    for offset in range(5):
        await store.enqueue(make_opp(timestamp_ns=base + minute_ns + offset))
    await asyncio.sleep(0.2)

    peak = await store.peak_minute(window_ns=3_600_000_000_000)
    assert peak is not None
    assert peak["count"] == 5
    assert peak["minute_start_ns"] == base + minute_ns
    await store.close()
    runner.cancel()


@pytest.mark.asyncio
async def test_peak_minute_returns_none_when_empty(tmp_path: Path) -> None:
    store = OpportunityStore(str(tmp_path / "db.sqlite3"))
    await store.initialize()
    assert await store.peak_minute(window_ns=3_600_000_000_000) is None
    assert await store.peak_minute(window_ns=None) is None


@pytest.mark.asyncio
async def test_timeseries_buckets_and_orders_ascending(tmp_path: Path) -> None:
    store = OpportunityStore(
        str(tmp_path / "db.sqlite3"), batch_size=20, flush_interval_seconds=0.05
    )
    await store.initialize()
    runner = asyncio.create_task(store.run())
    bucket_seconds = 60
    bucket_ns = bucket_seconds * 1_000_000_000
    base = (time.time_ns() // bucket_ns) * bucket_ns
    await store.enqueue(make_opp(timestamp_ns=base, spread="1"))
    await store.enqueue(make_opp(timestamp_ns=base + 1, spread="3"))
    await store.enqueue(make_opp(timestamp_ns=base + bucket_ns, spread="2"))
    await asyncio.sleep(0.2)

    points = await store.timeseries(window_ns=3_600_000_000_000, bucket_seconds=bucket_seconds)
    assert len(points) == 2
    assert points[0]["bucket_start_ns"] == base
    assert points[0]["count"] == 2
    assert Decimal(str(points[0]["max_spread_pct"])) == Decimal("3")
    assert points[1]["bucket_start_ns"] == base + bucket_ns
    assert points[1]["count"] == 1
    await store.close()
    runner.cancel()


@pytest.mark.asyncio
async def test_timeseries_rejects_non_positive_bucket(tmp_path: Path) -> None:
    store = OpportunityStore(str(tmp_path / "db.sqlite3"))
    await store.initialize()
    with pytest.raises(ValueError):
        await store.timeseries(window_ns=3_600_000_000_000, bucket_seconds=0)
