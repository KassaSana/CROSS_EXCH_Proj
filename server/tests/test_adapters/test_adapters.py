import asyncio
import types
from decimal import Decimal

from arb.adapters.binance import BinanceAdapter, normalize_binance_symbol
from arb.adapters.coinbase import CoinbaseAdapter, normalize_coinbase_symbol
from arb.adapters.gemini import GeminiAdapter, normalize_gemini_symbol
from arb.types import EventKind, MarketEvent, PriceLevel


def test_symbol_normalization() -> None:
    assert normalize_gemini_symbol("btcusd") == "BTC-USD"
    assert normalize_coinbase_symbol("BTC-USD") == "BTC-USD"
    assert normalize_binance_symbol("BTCUSDT") == "BTC-USD"


def test_coinbase_snapshot_parsing() -> None:
    adapter = CoinbaseAdapter(["BTC-USD"])
    payload = '{"type":"snapshot","product_id":"BTC-USD","sequence_num":10,"updates":[{"side":"bid","price_level":"100","new_quantity":"1"},{"side":"offer","price_level":"101","new_quantity":"2"}]}'
    events = asyncio.run(adapter.parse_message(payload))
    assert len(events) == 1
    assert events[0].kind is EventKind.SNAPSHOT
    assert events[0].pair == "BTC-USD"


def test_binance_depth_update_parsing() -> None:
    adapter = BinanceAdapter(["BTCUSDT"])
    asyncio.run(adapter.parse_message('{"symbol":"BTCUSDT","lastUpdateId":14,"bids":[["99","1"]],"asks":[["101","2"]]}'))
    payload = '{"s":"BTCUSDT","u":15,"E":123,"b":[["100","1"]],"a":[["101","2"]]}'
    events = asyncio.run(adapter.parse_message(payload))
    assert len(events) == 1
    assert events[0].kind is EventKind.DELTA
    assert events[0].pair == "BTC-USD"


def test_gemini_snapshot_parsing() -> None:
    adapter = GeminiAdapter(["btcusd"])
    payload = '{"symbol":"btcusd","lastUpdateId":7,"bids":[["100","1"]],"asks":[["101","2"]]}'
    events = asyncio.run(adapter.parse_message(payload))
    assert len(events) == 1
    assert events[0].kind is EventKind.SNAPSHOT
    assert events[0].pair == "BTC-USD"


def test_binance_gap_triggers_snapshot_resync() -> None:
    adapter = BinanceAdapter(["BTCUSDT"])

    async def fetch_snapshot(self: BinanceAdapter, pair: str, trigger_sequence: int) -> MarketEvent:
        return MarketEvent(
            exchange=self.name,
            pair=pair,
            kind=EventKind.SNAPSHOT,
            sequence=trigger_sequence,
            timestamp_ns=1,
            bids=(PriceLevel(price=Decimal("100"), size=Decimal("1")),),
            asks=(PriceLevel(price=Decimal("101"), size=Decimal("1")),),
        )

    adapter.fetch_snapshot = types.MethodType(fetch_snapshot, adapter)

    asyncio.run(adapter.parse_message('{"symbol":"BTCUSDT","lastUpdateId":1,"bids":[["100","1"]],"asks":[["101","2"]]}'))
    events = asyncio.run(adapter.parse_message('{"s":"BTCUSDT","u":3,"E":123,"b":[["100","1"]],"a":[["101","2"]]}'))

    assert len(events) == 1
    assert events[0].kind is EventKind.SNAPSHOT
    assert events[0].sequence == 3
    assert adapter.gap_count == 1


def _stub_snapshot(adapter: object, sequence: int = 0) -> None:
    async def fetch_snapshot(self, pair: str, trigger_sequence: int) -> MarketEvent:
        return MarketEvent(
            exchange=self.name,
            pair=pair,
            kind=EventKind.SNAPSHOT,
            sequence=trigger_sequence,
            timestamp_ns=1,
            bids=(PriceLevel(price=Decimal("100"), size=Decimal("1")),),
            asks=(PriceLevel(price=Decimal("101"), size=Decimal("1")),),
        )

    adapter.fetch_snapshot = types.MethodType(fetch_snapshot, adapter)


def test_coinbase_gap_triggers_snapshot_resync() -> None:
    adapter = CoinbaseAdapter(["BTC-USD"])
    _stub_snapshot(adapter)
    # First message establishes a sequence baseline.
    asyncio.run(adapter.parse_message('{"type":"snapshot","product_id":"BTC-USD","sequence_num":1,"updates":[{"side":"bid","price_level":"100","new_quantity":"1"}]}'))
    # Skipping sequence 2 should trigger a gap-driven snapshot at sequence 3.
    events = asyncio.run(adapter.parse_message('{"type":"update","product_id":"BTC-USD","sequence_num":3,"updates":[{"side":"bid","price_level":"99","new_quantity":"1"}]}'))
    assert len(events) == 1
    assert events[0].kind is EventKind.SNAPSHOT
    assert adapter.gap_count == 1


def test_gemini_gap_triggers_snapshot_resync() -> None:
    adapter = GeminiAdapter(["btcusd"])
    _stub_snapshot(adapter)
    # Snapshot establishes baseline sequence 1.
    asyncio.run(adapter.parse_message('{"symbol":"btcusd","lastUpdateId":1,"bids":[["100","1"]],"asks":[["101","2"]]}'))
    # Skip sequence 2.
    events = asyncio.run(adapter.parse_message('{"symbol":"btcusd","socket_sequence":3,"events":[{"side":"bid","price":"99","remaining":"1"}]}'))
    assert len(events) == 1
    assert events[0].kind is EventKind.SNAPSHOT
    assert adapter.gap_count == 1


def test_out_of_order_delta_is_dropped_silently() -> None:
    adapter = BinanceAdapter(["BTCUSDT"])
    _stub_snapshot(adapter)
    asyncio.run(adapter.parse_message('{"symbol":"BTCUSDT","lastUpdateId":5,"bids":[["100","1"]],"asks":[["101","2"]]}'))
    # Delta with sequence == last is older — must be dropped, not re-snapshot.
    events = asyncio.run(adapter.parse_message('{"s":"BTCUSDT","u":4,"E":1,"b":[["100","1"]],"a":[["101","1"]]}'))
    assert events == []
    assert adapter.gap_count == 0


def test_first_delta_with_no_prior_baseline_triggers_snapshot() -> None:
    adapter = BinanceAdapter(["BTCUSDT"])
    _stub_snapshot(adapter)
    # No snapshot yet — first delta must request one.
    events = asyncio.run(adapter.parse_message('{"s":"BTCUSDT","u":7,"E":1,"b":[["100","1"]],"a":[["101","1"]]}'))
    assert len(events) == 1
    assert events[0].kind is EventKind.SNAPSHOT
    assert adapter.gap_count == 1


def test_sequential_deltas_pass_through_without_snapshot() -> None:
    adapter = BinanceAdapter(["BTCUSDT"])
    _stub_snapshot(adapter)
    asyncio.run(adapter.parse_message('{"symbol":"BTCUSDT","lastUpdateId":1,"bids":[["100","1"]],"asks":[["101","2"]]}'))
    e2 = asyncio.run(adapter.parse_message('{"s":"BTCUSDT","u":2,"E":1,"b":[["100","1"]],"a":[["101","1"]]}'))
    e3 = asyncio.run(adapter.parse_message('{"s":"BTCUSDT","u":3,"E":1,"b":[["100","1"]],"a":[["101","1"]]}'))
    assert e2[0].kind is EventKind.DELTA and e2[0].sequence == 2
    assert e3[0].kind is EventKind.DELTA and e3[0].sequence == 3
    assert adapter.gap_count == 0


def test_status_snapshot_reports_age_and_counters() -> None:
    adapter = BinanceAdapter(["BTCUSDT"])
    adapter.connected = True
    adapter.reconnect_count = 4
    adapter.gap_count = 2
    adapter.last_error = "boom"
    adapter.last_message_ns = 1_000_000_000
    status = adapter.status_snapshot(now_ns=2_500_000_000)
    assert status.exchange == "binance"
    assert status.connected is True
    assert status.last_message_age_ms == 1_500
    assert status.gap_count == 2
    assert status.reconnect_count == 4
    assert status.last_error == "boom"


def test_status_snapshot_age_is_none_before_first_message() -> None:
    adapter = BinanceAdapter(["BTCUSDT"])
    status = adapter.status_snapshot(now_ns=1_000_000_000)
    assert status.last_message_age_ms is None
    assert status.connected is False


def test_coinbase_delta_parses_offer_to_ask() -> None:
    adapter = CoinbaseAdapter(["BTC-USD"])
    _stub_snapshot(adapter)
    asyncio.run(adapter.parse_message('{"type":"snapshot","product_id":"BTC-USD","sequence_num":1,"updates":[]}'))
    events = asyncio.run(adapter.parse_message('{"type":"update","product_id":"BTC-USD","sequence_num":2,"updates":[{"side":"offer","price_level":"105","new_quantity":"3"}]}'))
    assert len(events) == 1
    assert events[0].kind is EventKind.DELTA
    assert events[0].asks == (PriceLevel(price=Decimal("105"), size=Decimal("3")),)
    assert events[0].bids == ()


def test_unrecognized_message_returns_no_events() -> None:
    adapter = GeminiAdapter(["btcusd"])
    assert asyncio.run(adapter.parse_message('{"type":"heartbeat"}')) == []
    coinbase = CoinbaseAdapter(["BTC-USD"])
    assert asyncio.run(coinbase.parse_message('{"type":"subscriptions"}')) == []
    binance = BinanceAdapter(["BTCUSDT"])
    assert asyncio.run(binance.parse_message('{"result":null,"id":1}')) == []


def test_binance_symbol_normalization_handles_non_usdt() -> None:
    assert normalize_binance_symbol("ethusdt") == "ETH-USD"
    assert normalize_binance_symbol("BTCUSDT") == "BTC-USD"
    # Non-USDT pairs pass through uppercased.
    assert normalize_binance_symbol("btcbusd") == "BTCBUSD"
