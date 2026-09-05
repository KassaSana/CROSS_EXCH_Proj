import asyncio
import types
from decimal import Decimal
from typing import Any

import pytest
import websockets
from arb.adapters.base import ExchangeAdapter
from arb.adapters.binance import BinanceAdapter, normalize_binance_symbol
from arb.adapters.coinbase import CoinbaseAdapter, normalize_coinbase_symbol
from arb.adapters.gemini import GeminiAdapter, normalize_gemini_symbol
from arb.types import EventKind, MarketEvent, PriceLevel


class ReceiptTimeAdapter(ExchangeAdapter):
    name = "receipt-test"
    ws_url = "wss://example.test"
    snapshot_url = "https://example.test"

    async def subscribe(self, websocket: Any) -> None:
        return None

    async def parse_message(self, message: str) -> list[MarketEvent]:
        return [
            MarketEvent(
                exchange=self.name,
                pair="BTC-USD",
                kind=EventKind.SNAPSHOT,
                sequence=1,
                timestamp_ns=1,
            )
        ]

    async def fetch_snapshot(self, pair: str, trigger_sequence: int) -> MarketEvent:
        raise AssertionError("not used")


class OneMessageSocket:
    async def __aenter__(self) -> "OneMessageSocket":
        return self

    async def __aexit__(self, *args: object) -> None:
        return None

    async def __aiter__(self):
        yield "{}"


class ControlledSocket:
    def __init__(self) -> None:
        self.messages: asyncio.Queue[str | None] = asyncio.Queue()

    def __aiter__(self) -> "ControlledSocket":
        return self

    async def __anext__(self) -> str:
        message = await self.messages.get()
        if message is None:
            raise StopAsyncIteration
        return message

    async def push(self, message: str) -> None:
        await self.messages.put(message)


def binance_snapshot(sequence: int) -> MarketEvent:
    return MarketEvent(
        exchange="binance",
        pair="BTC-USD",
        kind=EventKind.SNAPSHOT,
        sequence=sequence,
        timestamp_ns=1,
        bids=(PriceLevel(price=Decimal("100"), size=Decimal("1")),),
        asks=(PriceLevel(price=Decimal("101"), size=Decimal("1")),),
        exchange_last_sequence=sequence,
        received_monotonic_ns=1,
    )


def test_symbol_normalization() -> None:
    assert normalize_gemini_symbol("btcusd") == "BTC-USD"
    assert normalize_coinbase_symbol("BTC-USD") == "BTC-USD"
    assert normalize_binance_symbol("BTCUSDT") == "BTC-USD"


@pytest.mark.asyncio
async def test_connect_stamps_receipt_time_before_parsing(monkeypatch) -> None:
    adapter = ReceiptTimeAdapter(["BTC-USD"])
    socket = OneMessageSocket()
    monkeypatch.setattr(websockets, "connect", lambda *args, **kwargs: socket)
    monkeypatch.setattr("arb.adapters.base.time.monotonic_ns", lambda: 123)

    events = adapter.connect()
    event = await anext(events)
    await events.aclose()

    assert event.received_monotonic_ns == 123


def test_coinbase_snapshot_parsing() -> None:
    adapter = CoinbaseAdapter(["BTC-USD"])
    payload = '{"type":"snapshot","product_id":"BTC-USD","sequence_num":10,"updates":[{"side":"bid","price_level":"100","new_quantity":"1"},{"side":"offer","price_level":"101","new_quantity":"2"}]}'
    events = asyncio.run(adapter.parse_message(payload))
    assert len(events) == 1
    assert events[0].kind is EventKind.SNAPSHOT
    assert events[0].pair == "BTC-USD"


def test_coinbase_nested_envelope_preserves_outer_sequence_per_product() -> None:
    adapter = CoinbaseAdapter(["BTC-USD", "ETH-USD"])
    payload = (
        '{"channel":"l2_data","sequence_num":42,"events":['
        '{"type":"snapshot","product_id":"BTC-USD","updates":[]},'
        '{"type":"snapshot","product_id":"ETH-USD","updates":[]}]}'
    )
    events = asyncio.run(adapter.parse_message(payload))
    assert [(event.pair, event.sequence) for event in events] == [("BTC-USD", 42), ("ETH-USD", 42)]


def test_binance_depth_update_parsing() -> None:
    adapter = BinanceAdapter(["BTCUSDT"])
    asyncio.run(adapter.parse_message('{"symbol":"BTCUSDT","lastUpdateId":14,"bids":[["99","1"]],"asks":[["101","2"]]}'))
    payload = '{"s":"BTCUSDT","U":15,"u":15,"E":123,"b":[["100","1"]],"a":[["101","2"]]}'
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


def test_binance_subsequent_deltas_are_sequential() -> None:
    # Binance exchange IDs may advance by a range, while local event sequences
    # remain contiguous for OrderBookManager.
    adapter = BinanceAdapter(["BTCUSDT"])
    asyncio.run(adapter.parse_message('{"symbol":"BTCUSDT","lastUpdateId":100,"bids":[["100","1"]],"asks":[["101","2"]]}'))
    e1 = asyncio.run(adapter.parse_message('{"s":"BTCUSDT","u":105,"U":101,"E":1,"b":[["100","1"]],"a":[["101","1"]]}'))
    e2 = asyncio.run(adapter.parse_message('{"s":"BTCUSDT","u":120,"U":106,"E":1,"b":[["100","1"]],"a":[["101","1"]]}'))
    assert e1[0].kind is EventKind.DELTA
    assert e2[0].kind is EventKind.DELTA
    assert e2[0].sequence == e1[0].sequence + 1
    assert e1[0].exchange_first_sequence == 101
    assert e1[0].exchange_last_sequence == 105


def _stub_snapshot(adapter: object, sequence: int = 1) -> None:
    async def fetch_snapshot(self, pair: str, trigger_sequence: int) -> MarketEvent:
        return MarketEvent(
            exchange=self.name,
            pair=pair,
            kind=EventKind.SNAPSHOT,
            sequence=sequence,
            timestamp_ns=1,
            bids=(PriceLevel(price=Decimal("100"), size=Decimal("1")),),
            asks=(PriceLevel(price=Decimal("101"), size=Decimal("1")),),
            exchange_last_sequence=sequence,
        )

    adapter.fetch_snapshot = types.MethodType(fetch_snapshot, adapter)


def test_coinbase_gap_waits_for_stream_snapshot_without_using_rest_sequence() -> None:
    adapter = CoinbaseAdapter(["BTC-USD"])
    # First message establishes a sequence baseline.
    asyncio.run(adapter.parse_message('{"type":"snapshot","product_id":"BTC-USD","sequence_num":1,"updates":[{"side":"bid","price_level":"100","new_quantity":"1"}]}'))
    # Skipping sequence 2 invalidates the stream; REST sequence numbers must not
    # be used to pretend the Advanced Trade stream is synchronized again.
    events = asyncio.run(adapter.parse_message('{"type":"update","product_id":"BTC-USD","sequence_num":3,"updates":[{"side":"bid","price_level":"99","new_quantity":"1"}]}'))
    assert events == []
    assert adapter.gap_count == 1
    assert adapter._reconnect_requested is True
    asyncio.run(adapter.reset_state())
    assert adapter._reconnect_requested is False
    events = asyncio.run(adapter.parse_message('{"type":"snapshot","product_id":"BTC-USD","sequence_num":10,"updates":[]}'))
    assert len(events) == 1
    assert events[0].kind is EventKind.SNAPSHOT


def test_coinbase_update_before_stream_snapshot_is_ignored() -> None:
    adapter = CoinbaseAdapter(["BTC-USD"])
    events = asyncio.run(adapter.parse_message('{"type":"update","product_id":"BTC-USD","sequence_num":1,"updates":[]}'))
    assert events == []
    assert adapter.gap_count == 0
    snapshot = asyncio.run(adapter.parse_message('{"type":"snapshot","product_id":"BTC-USD","sequence_num":2,"updates":[]}'))
    assert snapshot[0].kind is EventKind.SNAPSHOT


def test_gemini_first_v2_message_triggers_rest_snapshot() -> None:
    # Gemini v2 socket_sequence is connection-global (not per-symbol), so the adapter
    # fetches a REST snapshot on the first WS message for each pair instead of
    # relying on socket_sequence for gap detection.
    adapter = GeminiAdapter(["btcusd"])
    _stub_snapshot(adapter)
    events = asyncio.run(adapter.parse_message('{"type":"l2_updates","symbol":"BTCUSD","changes":[["buy","100","1"],["sell","101","2"]]}'))
    assert len(events) == 1
    assert events[0].kind is EventKind.SNAPSHOT


def test_gemini_subsequent_v2_messages_are_sequential_deltas() -> None:
    adapter = GeminiAdapter(["btcusd"])
    _stub_snapshot(adapter)
    # First message → REST snapshot.
    asyncio.run(adapter.parse_message('{"type":"l2_updates","symbol":"BTCUSD","changes":[["buy","100","1"],["sell","101","2"]]}'))
    # Second and third messages → sequential DELTAs, no gap triggered.
    e2 = asyncio.run(adapter.parse_message('{"type":"l2_updates","symbol":"BTCUSD","changes":[["buy","100","1"]]}'))
    e3 = asyncio.run(adapter.parse_message('{"type":"l2_updates","symbol":"BTCUSD","changes":[["sell","101","1"]]}'))
    assert e2[0].kind is EventKind.DELTA
    assert e3[0].kind is EventKind.DELTA
    assert e3[0].sequence == e2[0].sequence + 1
    assert adapter.gap_count == 0


def test_binance_subsequent_messages_dont_trigger_rest_calls() -> None:
    # Once aligned, exchange update ranges advance without another REST call.
    adapter = BinanceAdapter(["BTCUSDT"])
    fetch_calls = 0

    async def counting_fetch(self: BinanceAdapter, pair: str, trigger_sequence: int) -> MarketEvent:
        nonlocal fetch_calls
        fetch_calls += 1
        return MarketEvent(
            exchange=self.name, pair=pair, kind=EventKind.SNAPSHOT,
            sequence=100, timestamp_ns=1,
            bids=(PriceLevel(price=Decimal("100"), size=Decimal("1")),),
            asks=(PriceLevel(price=Decimal("101"), size=Decimal("1")),),
        )

    adapter.fetch_snapshot = types.MethodType(counting_fetch, adapter)
    asyncio.run(adapter.parse_message('{"s":"BTCUSDT","u":101,"U":100,"E":1,"b":[["100","1"]],"a":[]}'))
    asyncio.run(adapter.parse_message('{"s":"BTCUSDT","u":120,"U":102,"E":1,"b":[["100","1"]],"a":[]}'))
    asyncio.run(adapter.parse_message('{"s":"BTCUSDT","u":300,"U":121,"E":1,"b":[["100","1"]],"a":[]}'))
    assert fetch_calls == 1


def test_first_delta_with_no_prior_baseline_triggers_snapshot() -> None:
    adapter = BinanceAdapter(["BTCUSDT"])
    _stub_snapshot(adapter)
    # No snapshot yet — the first delta is buffered while REST snapshot state is fetched.
    events = asyncio.run(adapter.parse_message('{"s":"BTCUSDT","u":7,"U":1,"E":1,"b":[["100","1"]],"a":[["101","1"]]}'))
    assert len(events) == 2
    assert events[0].kind is EventKind.SNAPSHOT
    assert events[1].kind is EventKind.DELTA


def test_sequential_deltas_pass_through_without_snapshot() -> None:
    adapter = BinanceAdapter(["BTCUSDT"])
    _stub_snapshot(adapter)
    asyncio.run(adapter.parse_message('{"symbol":"BTCUSDT","lastUpdateId":1,"bids":[["100","1"]],"asks":[["101","2"]]}'))
    e2 = asyncio.run(adapter.parse_message('{"s":"BTCUSDT","u":2,"U":2,"E":1,"b":[["100","1"]],"a":[["101","1"]]}'))
    e3 = asyncio.run(adapter.parse_message('{"s":"BTCUSDT","u":3,"U":3,"E":1,"b":[["100","1"]],"a":[["101","1"]]}'))
    assert e2[0].kind is EventKind.DELTA
    assert e3[0].kind is EventKind.DELTA
    assert e3[0].sequence == e2[0].sequence + 1
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


def test_binance_reset_state_forces_resnapshot_after_reconnect() -> None:
    # Regression: previously _initialized persisted across reconnects, so the
    # first message after a reconnect skipped the REST snapshot and emitted a
    # delta on top of a stale book. reset_state() must clear that state.
    adapter = BinanceAdapter(["BTCUSDT"])
    _stub_snapshot(adapter, sequence=2)
    asyncio.run(adapter.parse_message('{"symbol":"BTCUSDT","lastUpdateId":1,"bids":[["100","1"]],"asks":[["101","2"]]}'))
    asyncio.run(adapter.parse_message('{"s":"BTCUSDT","u":2,"U":2,"E":1,"b":[["100","1"]],"a":[["101","1"]]}'))

    asyncio.run(adapter.reset_state())

    events = asyncio.run(adapter.parse_message('{"s":"BTCUSDT","u":3,"U":2,"E":1,"b":[["100","1"]],"a":[["101","1"]]}'))
    assert events[0].kind is EventKind.SNAPSHOT


def test_binance_initial_buffer_aligns_snapshot_and_discards_covered_updates() -> None:
    adapter = BinanceAdapter(["BTCUSDT"])
    snapshots = 0

    async def snapshot_at_100(self: BinanceAdapter, pair: str, trigger_sequence: int) -> MarketEvent:
        nonlocal snapshots
        snapshots += 1
        return MarketEvent(
            exchange=self.name, pair=pair, kind=EventKind.SNAPSHOT, sequence=100, timestamp_ns=1,
            bids=(PriceLevel(price=Decimal("100"), size=Decimal("1")),),
            asks=(PriceLevel(price=Decimal("101"), size=Decimal("1")),),
            exchange_last_sequence=100,
        )

    adapter.fetch_snapshot = types.MethodType(snapshot_at_100, adapter)
    first = asyncio.run(adapter.parse_message('{"s":"BTCUSDT","u":99,"U":95,"E":1,"b":[],"a":[]}'))
    assert [event.kind for event in first] == [EventKind.SNAPSHOT]
    second = asyncio.run(adapter.parse_message('{"s":"BTCUSDT","u":105,"U":100,"E":1,"b":[["100","2"]],"a":[]}'))
    assert snapshots == 1
    assert [event.kind for event in second] == [EventKind.DELTA]
    assert second[0].exchange_first_sequence == 100


def test_binance_gap_requests_reconnect_and_does_not_emit_delta() -> None:
    adapter = BinanceAdapter(["BTCUSDT"])
    asyncio.run(adapter.parse_message('{"symbol":"BTCUSDT","lastUpdateId":100,"bids":[["100","1"]],"asks":[["101","1"]]}'))
    events = asyncio.run(adapter.parse_message('{"s":"BTCUSDT","u":110,"U":108,"E":1,"b":[],"a":[]}'))
    assert events == []
    assert adapter.gap_count == 1
    assert adapter._reconnect_requested is True


@pytest.mark.asyncio
async def test_binance_buffers_updates_while_snapshot_is_in_flight() -> None:
    adapter = BinanceAdapter(["BTCUSDT"])
    socket = ControlledSocket()
    snapshot_started = asyncio.Event()
    release_snapshot = asyncio.Event()

    async def delayed_snapshot(
        self: BinanceAdapter, pair: str, trigger_sequence: int
    ) -> MarketEvent:
        snapshot_started.set()
        await release_snapshot.wait()
        return binance_snapshot(100)

    adapter.fetch_snapshot = types.MethodType(delayed_snapshot, adapter)
    await socket.push('{"s":"BTCUSDT","U":95,"u":99,"b":[],"a":[]}')
    stream = adapter.stream_events(socket)
    first_event = asyncio.create_task(anext(stream))
    await snapshot_started.wait()
    await socket.push('{"s":"BTCUSDT","U":99,"u":105,"b":[["100","2"]],"a":[]}')

    for _ in range(10):
        if len(adapter._buffers["BTC-USD"]) == 2:
            break
        await asyncio.sleep(0)
    assert len(adapter._buffers["BTC-USD"]) == 2

    release_snapshot.set()
    snapshot = await first_event
    delta = await anext(stream)
    await stream.aclose()

    assert snapshot.kind is EventKind.SNAPSHOT
    assert delta.kind is EventKind.DELTA
    assert delta.exchange_first_sequence == 99
    assert delta.exchange_last_sequence == 105
    assert delta.received_monotonic_ns is not None


@pytest.mark.asyncio
async def test_binance_buffer_overflow_aborts_synchronization() -> None:
    adapter = BinanceAdapter(["BTCUSDT"])
    adapter.max_buffered_updates = 2
    socket = ControlledSocket()
    snapshot_started = asyncio.Event()
    never_release = asyncio.Event()

    async def blocked_snapshot(
        self: BinanceAdapter, pair: str, trigger_sequence: int
    ) -> MarketEvent:
        snapshot_started.set()
        await never_release.wait()
        return binance_snapshot(1)

    adapter.fetch_snapshot = types.MethodType(blocked_snapshot, adapter)
    stream = adapter.stream_events(socket)
    pending = asyncio.create_task(anext(stream))
    await socket.push('{"s":"BTCUSDT","U":1,"u":1,"b":[],"a":[]}')
    await snapshot_started.wait()
    await socket.push('{"s":"BTCUSDT","U":2,"u":2,"b":[],"a":[]}')
    await socket.push('{"s":"BTCUSDT","U":3,"u":3,"b":[],"a":[]}')

    with pytest.raises(RuntimeError, match="requested reconnect"):
        await pending
    assert adapter._reconnect_requested is True
    assert "BTC-USD" not in adapter._buffers


@pytest.mark.asyncio
async def test_binance_snapshot_failure_aborts_synchronization() -> None:
    adapter = BinanceAdapter(["BTCUSDT"])
    socket = ControlledSocket()

    async def failed_snapshot(
        self: BinanceAdapter, pair: str, trigger_sequence: int
    ) -> MarketEvent:
        raise OSError("REST unavailable")

    adapter.fetch_snapshot = types.MethodType(failed_snapshot, adapter)
    await socket.push('{"s":"BTCUSDT","U":1,"u":1,"b":[],"a":[]}')
    stream = adapter.stream_events(socket)
    with pytest.raises(RuntimeError, match="snapshot retrieval failed"):
        await anext(stream)
    assert adapter._reconnect_requested is True


@pytest.mark.asyncio
async def test_binance_reconnects_when_snapshot_never_catches_up() -> None:
    adapter = BinanceAdapter(["BTCUSDT"])
    socket = ControlledSocket()
    calls = 0

    async def stale_snapshot(
        self: BinanceAdapter, pair: str, trigger_sequence: int
    ) -> MarketEvent:
        nonlocal calls
        calls += 1
        return binance_snapshot(90)

    adapter.fetch_snapshot = types.MethodType(stale_snapshot, adapter)
    await socket.push('{"s":"BTCUSDT","U":95,"u":105,"b":[],"a":[]}')
    stream = adapter.stream_events(socket)

    with pytest.raises(RuntimeError, match="snapshot did not catch up"):
        await anext(stream)
    assert calls == 3
    assert adapter._reconnect_requested is True


@pytest.mark.asyncio
async def test_binance_server_shutdown_requests_reconnect() -> None:
    adapter = BinanceAdapter(["BTCUSDT"])
    socket = ControlledSocket()
    await socket.push('{"e":"serverShutdown"}')
    stream = adapter.stream_events(socket)

    with pytest.raises(RuntimeError, match="requested reconnect"):
        await anext(stream)
    assert adapter._reconnect_requested is True


def test_binance_initial_update_must_span_snapshot_id() -> None:
    adapter = BinanceAdapter(["BTCUSDT"])
    adapter._buffer(
        adapter._decode_depth_update(
            {"s": "BTCUSDT", "U": 95, "u": 99, "b": [], "a": []}
        )
    )
    adapter._buffer(
        adapter._decode_depth_update(
            {"s": "BTCUSDT", "U": 101, "u": 105, "b": [], "a": []}
        )
    )

    events = adapter._align_snapshot("BTC-USD", binance_snapshot(100))

    assert events == []
    assert adapter.gap_count == 1
    assert adapter._reconnect_requested is True


def test_binance_retries_snapshot_that_predates_first_buffered_update() -> None:
    adapter = BinanceAdapter(["BTCUSDT"])
    sequences = iter((90, 100))

    async def advancing_snapshot(
        self: BinanceAdapter, pair: str, trigger_sequence: int
    ) -> MarketEvent:
        return binance_snapshot(next(sequences))

    adapter.fetch_snapshot = types.MethodType(advancing_snapshot, adapter)
    events = asyncio.run(
        adapter.parse_message('{"s":"BTCUSDT","U":95,"u":105,"b":[],"a":[]}')
    )
    assert [event.kind for event in events] == [EventKind.SNAPSHOT, EventKind.DELTA]
    assert events[0].sequence == 100


def test_binance_snapshot_requests_documented_depth_limit() -> None:
    adapter = BinanceAdapter(["BTCUSDT"])
    requested_url = ""

    async def get_json(url: str) -> dict[str, object]:
        nonlocal requested_url
        requested_url = url
        return {"lastUpdateId": 1, "bids": [], "asks": []}

    adapter.client_get_json = get_json  # type: ignore[method-assign]
    asyncio.run(adapter.fetch_snapshot("BTC-USD", trigger_sequence=0))
    assert requested_url.endswith("symbol=BTCUSDT&limit=5000")


def test_gemini_reset_state_forces_resnapshot_after_reconnect() -> None:
    adapter = GeminiAdapter(["btcusd"])
    _stub_snapshot(adapter)
    asyncio.run(adapter.parse_message('{"type":"l2_updates","symbol":"BTCUSD","changes":[["buy","100","1"]]}'))
    asyncio.run(adapter.parse_message('{"type":"l2_updates","symbol":"BTCUSD","changes":[["sell","101","1"]]}'))

    asyncio.run(adapter.reset_state())

    events = asyncio.run(adapter.parse_message('{"type":"l2_updates","symbol":"BTCUSD","changes":[["buy","100","1"]]}'))
    assert events[0].kind is EventKind.SNAPSHOT


def test_binance_symbol_normalization_handles_non_usdt() -> None:
    assert normalize_binance_symbol("ethusdt") == "ETH-USD"
    assert normalize_binance_symbol("BTCUSDT") == "BTC-USD"
    # Non-USDT pairs pass through uppercased.
    assert normalize_binance_symbol("btcbusd") == "BTCBUSD"
