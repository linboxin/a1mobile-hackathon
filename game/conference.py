"""MafiaOS — the party line.

A real conference bridge for the discussion phase. Every call already flows
through this server as raw μ-law, so we mix it ourselves instead of needing
carrier conferencing (the platform has none).

Classic N-1 mixer: a single 20 ms ticker pulls one frame from each caller's
jitter buffer, sums them all, and sends every caller the sum *minus their own
voice* so nobody hears themselves echoed.

    caller A ─┐                        ┌─► A hears B+C
    caller B ─┼─► [ 20ms mix tick ] ───┼─► B hears A+C
    caller C ─┘                        └─► C hears A+B
"""

from __future__ import annotations

import asyncio
import audioop
import base64
import json
from collections import deque

from loguru import logger

FRAME_BYTES = 160          # 20 ms of 8 kHz μ-law
TICK = 0.02
SILENCE_ULAW = b"\xff" * FRAME_BYTES
MAX_BUFFER = 10            # ~200 ms of jitter tolerance


class Participant:
    def __init__(self, name: str, websocket, stream_id: str):
        self.name = name
        self.ws = websocket
        self.stream_id = stream_id
        self.buffer: deque[bytes] = deque(maxlen=MAX_BUFFER)
        self.speaking = False

    def push(self, ulaw: bytes) -> None:
        self.buffer.append(ulaw)

    def take_pcm(self) -> bytes:
        """One frame of this caller's audio as PCM16, silence if starved."""
        ulaw = self.buffer.popleft() if self.buffer else SILENCE_ULAW
        pcm = audioop.ulaw2lin(ulaw, 2)
        self.speaking = audioop.rms(pcm, 2) > 500
        return pcm


class Room:
    """One live conference. Created on demand, torn down when empty."""

    def __init__(self, name: str = "discussion"):
        self.name = name
        self.participants: dict[str, Participant] = {}
        self._task: asyncio.Task | None = None

    def speakers(self) -> list[str]:
        return [p.name for p in self.participants.values() if p.speaking]

    async def join(self, participant: Participant) -> None:
        self.participants[participant.name] = participant
        logger.info(f"conference: {participant.name} joined ({len(self.participants)} on the line)")
        if self._task is None or self._task.done():
            self._task = asyncio.create_task(self._run())

    async def leave(self, name: str) -> None:
        self.participants.pop(name, None)
        logger.info(f"conference: {name} left ({len(self.participants)} remain)")
        if not self.participants and self._task:
            self._task.cancel()
            self._task = None

    async def _run(self) -> None:
        """Mix and distribute every 20 ms until the room empties."""
        try:
            while self.participants:
                started = asyncio.get_running_loop().time()
                current = list(self.participants.values())
                frames = {p.name: p.take_pcm() for p in current}

                total = bytes(len(next(iter(frames.values()))))
                for pcm in frames.values():
                    total = audioop.add(total, pcm, 2)

                for p in current:
                    # subtract this caller's own voice: they hear everyone else
                    mine = frames[p.name]
                    others = audioop.add(total, audioop.mul(mine, 2, -1), 2)
                    payload = base64.b64encode(audioop.lin2ulaw(others, 2)).decode()
                    message = {"event": "media", "media": {"payload": payload},
                               "stream_id": p.stream_id}
                    try:
                        await p.ws.send_text(json.dumps(message))
                    except Exception:
                        pass  # a dropped caller is reaped by its own handler

                elapsed = asyncio.get_running_loop().time() - started
                await asyncio.sleep(max(0, TICK - elapsed))
        except asyncio.CancelledError:
            pass
        except Exception:
            logger.exception("conference mixer crashed")


ROOM = Room()


async def run_conference(websocket, stream_id: str, name: str,
                         is_open) -> None:
    """Hold this caller in the party line until they hang up or the phase ends.

    `is_open` is a zero-arg callable so the room closes the moment the game
    leaves the discussion phase.
    """
    participant = Participant(name, websocket, stream_id)
    await ROOM.join(participant)
    try:
        while is_open():
            raw = await websocket.receive_text()
            message = json.loads(raw)
            if message.get("event") == "media":
                participant.push(base64.b64decode(message["media"]["payload"]))
            elif message.get("event") == "stop":
                break
    except Exception:
        pass
    finally:
        await ROOM.leave(name)
