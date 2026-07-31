"""MafiaOS bot players — auto-play empty seats so one human can play alone.

    .venv/bin/python scripts/bot_players.py            # bots = players with +1555… numbers
    .venv/bin/python scripts/bot_players.py Kit Rhea   # or name the seats to auto-play

Create the room with yourself on your real phone plus fictional +1555010000X
numbers for the empty seats, BEGIN TRANSMISSION, then run this in a terminal.
Bots watch the public state; whenever a bot owes the current phase an input,
it "calls in" through the real voice pipeline (scripts/sim_call.py) and speaks
an in-character line derived from its own private clue. Ctrl-C to stop.
"""

import asyncio
import os
import random
import subprocess
import sys
from pathlib import Path

import httpx
from dotenv import load_dotenv

ROOT = Path(__file__).parent.parent
load_dotenv(ROOT / ".env")

BASE = f"http://localhost:{os.getenv('PORT', '3000')}"
TOKEN = os.getenv("ADMIN_TOKEN", "deadair")
PY = str(ROOT / ".venv/bin/python")
SIM = str(ROOT / "scripts/sim_call.py")

CALL_SECONDS = {"role_calls": 35, "actions": 40, "evidence": 35,
                "accusations": 45, "vote": 50}


async def fetch(client: httpx.AsyncClient, path: str) -> dict:
    response = await client.get(f"{BASE}{path}", timeout=10)
    response.raise_for_status()
    return response.json()


def names_in(text: str, candidates: list[str], exclude: str) -> list[str]:
    lowered = (text or "").lower()
    return [n for n in candidates if n.lower() in lowered and n != exclude]


def line_for(bot: dict, phase: str, alive: list[str], clue: str) -> str:
    """Deterministic in-character speech for this bot in this phase."""
    me, role = bot["name"], bot.get("role", "")
    others = [n for n in alive if n != me]
    suspects = names_in(clue, alive, me) or others
    suspect = suspects[0]
    if phase == "role_calls":
        return "明白了，收到。"
    if phase == "actions":
        target = random.choice(others)
        verb = {"intruder": "袭击", "investigator": "查验",
                "guardian": "守护"}.get(role, "")
        if role == "guardian" and random.random() < 0.4:
            target = me
        return f"{verb}{target}。"
    if phase == "evidence":
        return "收到，明白。"
    if phase == "accusations":
        return f"我怀疑{suspect}。我的情报指向这个方向，而且他的说法对不上。"
    if phase == "vote":
        return f"我投{suspect}。放逐{suspect}。"
    return "Nothing further."


async def main() -> None:
    requested = set(sys.argv[1:])
    print(f"MafiaOS bots watching {BASE} (Ctrl-C to stop)")
    attempts: dict[tuple[str, str], int] = {}  # (phase, bot) -> tries (retry once)

    async with httpx.AsyncClient() as client:
        while True:
            try:
                state = await fetch(client, "/api/state")
                director = await fetch(client, f"/api/director-state?token={TOKEN}")
            except Exception as error:
                print(f"waiting for server: {error}")
                await asyncio.sleep(4)
                continue

            phase = state.get("phase")
            if phase in (None, "none", "lobby"):
                await asyncio.sleep(3)
                continue
            if phase == "reveal":
                print(f"Game over. {state.get('narration', '')}")
                return

            players = {p["name"]: p for p in director.get("players_full", [])}
            bots = {
                name for name, p in players.items()
                if (name in requested) or (not requested and p["phone"].startswith("+1555"))
            }
            alive = [p["name"] for p in state.get("players", []) if p["alive"]]
            waiting = [n for n in state.get("waiting_on", []) if n in bots]

            for name in waiting:
                key = (phase, name)
                if attempts.get(key, 0) >= 2:
                    continue
                attempts[key] = attempts.get(key, 0) + 1
                bot = players[name]
                clue = director.get("clues", {}).get(name, "")
                text = line_for(bot, phase, alive, clue)
                secs = CALL_SECONDS.get(phase, 40)
                print(f"[{phase}] {name} calling in: {text!r}")
                proc = await asyncio.create_subprocess_exec(
                    PY, SIM, bot["phone"], text, str(secs),
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                await proc.wait()
                print(f"[{phase}] {name} done")
            await asyncio.sleep(3)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nbots stopped")
