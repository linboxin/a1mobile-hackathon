"""Dead Air — SMS pacing via the A1 Mobile event API.

Public instructions only. Secrets travel by voice, never by text.
Recipients must be OTP-verified with the event platform (event consent rule).
"""

from __future__ import annotations

import asyncio
import os

import httpx
from dotenv import load_dotenv
from loguru import logger

from .engine import Game, Phase

API = "https://hack.a1mobile.com/api/sms"


def hotline() -> str:
    load_dotenv(override=True)  # number can change after a platform reset
    return os.getenv("A1_PHONE_NUMBER", "the game number")


PHASE_TEXTS: dict[Phase, str] = {
    Phase.ROLE_CALLS: "DEAD AIR // Game start. Call {line} NOW for your classified briefing. Speak to no one first.",
    Phase.ACTIONS: "DEAD AIR // Secret action window is OPEN. Call {line} in private.",
    Phase.EVIDENCE: "DEAD AIR // New evidence is waiting on your line. Call {line}.",
    Phase.ACCUSATIONS: "DEAD AIR // Accusation window. Call {line} and state your case.",
    Phase.VOTE: "DEAD AIR // FINAL VOTE. Call {line} to disconnect a player.",
    Phase.REVEAL: "DEAD AIR // The network has decided. Call {line} for the verdict.",
}

# Witness has no night action; don't send them a misleading action prompt.
SKIP = {(Phase.ACTIONS, "witness")}


async def send_sms(to: str, body: str) -> bool:
    team_key = os.getenv("A1_TEAM_KEY", "")
    async with httpx.AsyncClient(timeout=15) as client:
        try:
            response = await client.post(
                API,
                headers={"X-Team-Key": team_key, "Content-Type": "application/json"},
                json={"to": to, "body": body},
            )
            if response.status_code >= 400:
                logger.warning(f"SMS to {to} failed {response.status_code}: {response.text}")
                return False
            return True
        except httpx.HTTPError as error:
            logger.warning(f"SMS to {to} failed: {error}")
            return False


async def phase_sms(game: Game) -> None:
    text = PHASE_TEXTS.get(game.phase)
    if not text:
        return
    body = text.format(line=hotline())
    sends = [
        send_sms(p.phone, body)
        for p in game.players
        if p.alive and (game.phase, p.role) not in SKIP
    ]
    results = await asyncio.gather(*sends)
    game.log(f"SMS dispatched to {sum(results)}/{len(sends)} operators.")
    game.save()
