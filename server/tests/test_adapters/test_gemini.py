from __future__ import annotations

import asyncio
import json

from arb.adapters.gemini import GeminiAdapter
from arb.types import EventKind


def test_gemini_first_depth_frame_is_stream_snapshot() -> None:
    adapter = GeminiAdapter(["btcusd"])
    payload = (
        '{"e":"depthUpdate","E":123,"s":"btcusd","U":5,"u":7,"b":[["100","1"]],"a":[["101","2"]]}'
    )
    events = asyncio.run(adapter.parse_message(payload))
    assert len(events) == 1
    assert events[0].kind is EventKind.SNAPSHOT
    assert events[0].pair == "BTC-USD"
    assert events[0].sequence == 1
    assert events[0].exchange_first_sequence == 5
    assert events[0].exchange_last_sequence == 7


def test_gemini_subscribes_to_current_depth_stream_with_full_snapshot() -> None:
    adapter = GeminiAdapter(["btcusd"])
    sent: list[str] = []

    class Socket:
        async def send(self, message: str) -> None:
            sent.append(message)

    asyncio.run(adapter.subscribe(Socket()))

    assert adapter.ws_url == "wss://ws.gemini.com?snapshot=-1"
    assert json.loads(sent[0]) == {
        "id": 1,
        "method": "SUBSCRIBE",
        "params": ["btcusd@depth"],
    }


def test_gemini_subsequent_depth_frames_are_sequential_local_deltas() -> None:
    adapter = GeminiAdapter(["btcusd"])
    asyncio.run(
        adapter.parse_message(
            '{"e":"depthUpdate","s":"BTCUSD","U":10,"u":12,"b":[["100","1"]],"a":[["101","2"]]}'
        )
    )
    e2 = asyncio.run(
        adapter.parse_message(
            '{"e":"depthUpdate","s":"BTCUSD","U":13,"u":15,"b":[["100","2"]],"a":[]}'
        )
    )
    e3 = asyncio.run(
        adapter.parse_message(
            '{"e":"depthUpdate","s":"BTCUSD","U":15,"u":18,"b":[],"a":[["101","1"]]}'
        )
    )
    assert e2[0].kind is EventKind.DELTA
    assert e3[0].kind is EventKind.DELTA
    assert e3[0].sequence == e2[0].sequence + 1
    assert e3[0].exchange_first_sequence == 15
    assert e3[0].exchange_last_sequence == 18
    assert adapter.gap_count == 0


def test_gemini_duplicate_depth_frame_is_ignored() -> None:
    adapter = GeminiAdapter(["btcusd"])
    message = '{"e":"depthUpdate","s":"BTCUSD","U":10,"u":12,"b":[],"a":[]}'
    asyncio.run(adapter.parse_message(message))

    assert asyncio.run(adapter.parse_message(message)) == []
    assert adapter.gap_count == 0


def test_gemini_gap_requests_reconnect_and_does_not_emit_delta() -> None:
    adapter = GeminiAdapter(["btcusd"])
    asyncio.run(
        adapter.parse_message('{"e":"depthUpdate","s":"BTCUSD","U":10,"u":12,"b":[],"a":[]}')
    )

    events = asyncio.run(
        adapter.parse_message('{"e":"depthUpdate","s":"BTCUSD","U":15,"u":16,"b":[],"a":[]}')
    )

    assert events == []
    assert adapter.gap_count == 1
    assert adapter._reconnect_requested is True
    assert "BTC-USD" not in adapter._initialized


def test_gemini_reset_state_forces_resnapshot_after_reconnect() -> None:
    adapter = GeminiAdapter(["btcusd"])
    asyncio.run(
        adapter.parse_message(
            '{"e":"depthUpdate","s":"BTCUSD","U":1,"u":1,"b":[["100","1"]],"a":[["101","1"]]}'
        )
    )
    delta = asyncio.run(
        adapter.parse_message(
            '{"e":"depthUpdate","s":"BTCUSD","U":2,"u":2,"b":[["100","2"]],"a":[]}'
        )
    )
    assert delta[0].kind is EventKind.DELTA

    asyncio.run(adapter.reset_state())

    events = asyncio.run(
        adapter.parse_message(
            '{"e":"depthUpdate","s":"BTCUSD","U":10,"u":10,"b":[["100","1"]],"a":[["101","1"]]}'
        )
    )
    assert events[0].kind is EventKind.SNAPSHOT
