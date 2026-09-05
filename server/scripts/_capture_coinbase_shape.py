import asyncio
import json

import websockets


async def main() -> None:
    async with websockets.connect(
        "wss://advanced-trade-ws.coinbase.com", max_size=10_000_000
    ) as websocket:
        for subscription in (
            {"type": "subscribe", "channel": "level2", "product_ids": ["BTC-USD", "ETH-USD"]},
            {"type": "subscribe", "channel": "heartbeats"},
        ):
            await websocket.send(json.dumps(subscription))
        previous_sequence = None
        gaps: list[tuple[int, int]] = []
        first_sequence_by_channel: dict[str, int] = {}
        for _ in range(500):
            payload = json.loads(await asyncio.wait_for(websocket.recv(), timeout=10))
            channel = payload.get("channel")
            sequence = payload.get("sequence_num")
            first_sequence_by_channel.setdefault(channel, sequence)
            if previous_sequence is not None and sequence != previous_sequence + 1:
                gaps.append((previous_sequence, sequence))
            previous_sequence = sequence
            if channel == "heartbeats":
                break
        print(json.dumps({"first_sequences": first_sequence_by_channel, "gaps": gaps}))


asyncio.run(main())
