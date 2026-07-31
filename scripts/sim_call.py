"""Simulate one phone call to the local Dead Air server, no telephone needed.

    .venv/bin/python scripts/sim_call.py +15550100001 "Understood." [seconds]

Synthesizes the utterance with OpenAI TTS, streams it like a Telnyx call from
that caller id, and reports how much bot speech came back.
"""

import asyncio
import audioop  # noqa: deprecated in 3.13, fine on 3.12
import base64
import io
import json
import os
import sys
import wave
from pathlib import Path

import httpx
import websockets
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env")

FRAME = 160  # 20 ms of 8 kHz mu-law


async def synthesize_ulaw(text: str) -> bytes:
    async with httpx.AsyncClient(timeout=60) as client:
        response = await client.post(
            "https://api.openai.com/v1/audio/speech",
            headers={"Authorization": f"Bearer {os.environ['OPENAI_API_KEY']}"},
            json={"model": "gpt-4o-mini-tts", "voice": "echo",
                  "input": text, "response_format": "wav"},
        )
        response.raise_for_status()
    with wave.open(io.BytesIO(response.content), "rb") as w:
        pcm, rate = w.readframes(w.getnframes()), w.getframerate()
    pcm8k, _ = audioop.ratecv(pcm, 2, 1, rate, 8000, None)
    return audioop.lin2ulaw(pcm8k, 2)


async def main() -> None:
    caller = sys.argv[1]
    text = sys.argv[2]
    total_secs = int(sys.argv[3]) if len(sys.argv) > 3 else 30
    speech = await synthesize_ulaw(text)
    silence = b"\xff" * FRAME
    received: list[bytes] = []

    url = f"ws://localhost:{os.getenv('PORT', '3000')}/ws?caller={caller.replace('+', '%2B')}"
    async with websockets.connect(url, max_size=None) as ws:
        await ws.send(json.dumps({"event": "connected"}))
        await ws.send(json.dumps({
            "event": "start", "stream_id": f"sim-{caller[-4:]}",
            "start": {"call_control_id": f"cc-{caller[-4:]}",
                       "media_format": {"encoding": "PCMU", "sample_rate": 8000, "channels": 1}},
        }))

        async def receiver():
            try:
                async for raw in ws:
                    msg = json.loads(raw)
                    if msg.get("event") == "media":
                        received.append(base64.b64decode(msg["media"]["payload"]))
            except websockets.ConnectionClosed:
                pass

        recv_task = asyncio.create_task(receiver())
        # let the bot greet first, then speak, then wait out the reply
        utter_start = int(6000 / 20)
        frames = [speech[i:i + FRAME] for i in range(0, len(speech), FRAME)]
        for tick in range(total_secs * 50):
            if utter_start <= tick < utter_start + len(frames):
                chunk = frames[tick - utter_start].ljust(FRAME, b"\xff")
            else:
                chunk = silence
            await ws.send(json.dumps({"event": "media",
                                       "media": {"track": "inbound",
                                                  "payload": base64.b64encode(chunk).decode()}}))
            await asyncio.sleep(0.02)
        recv_task.cancel()

    print(f"[sim {caller}] said {text!r}; bot spoke {len(b''.join(received))/8000:.1f}s")


asyncio.run(main())
