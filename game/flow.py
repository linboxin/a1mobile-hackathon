"""Dead Air — phase orchestration.

Watches for completed phases, advances the engine, runs director side effects
(clues, summaries, narration), and triggers SMS pacing.
"""

from __future__ import annotations

import asyncio
import os

from loguru import logger

from . import director, notify, outbound
from .engine import Game, Phase

_lock = asyncio.Lock()


async def maybe_advance(game: Game, force: bool = False) -> bool:
    """Advance if the current phase has everything it needs. Returns True if advanced."""
    async with _lock:
        if game.phase in (Phase.LOBBY, Phase.REVEAL):
            return False
        if not force and not game.phase_complete():
            return False

        old = game.phase
        new = game.advance()
        logger.info(f"Phase {old.value} -> {new.value}")

        if new == Phase.DISCUSSION:
            secs = int(os.getenv("DISCUSSION_SECS", "180"))
            asyncio.create_task(_close_discussion_after(game, secs))
        if new == Phase.EVIDENCE:
            facts = game.resolve_actions()
            game.clues = await director.generate_clues(game, facts)
            game.log("Evidence transmitted to every operator's private line.")
        elif new == Phase.ACCUSATIONS:
            await director.director_tick(game)
        elif new == Phase.VOTE:
            game.vote_summary = await director.accusation_summary(game)
            game.log("Accusation summary compiled. The vote is open.")
        elif new == Phase.REVEAL:
            game.narration = await director.reveal_narration(game)
            game.postgame = await director.postgame_explanation(game)

        game.save()
        await notify.phase_sms(game)
        asyncio.create_task(outbound.announce_phase(game))
        return True


async def _close_discussion_after(game: Game, seconds: int) -> None:
    """The party line closes on its own so nobody has to watch the clock."""
    await asyncio.sleep(seconds)
    if game.phase == Phase.DISCUSSION:
        logger.info("discussion window closed; moving to accusations")
        await maybe_advance(game, force=True)


async def start_game(game: Game) -> None:
    game.start()
    await notify.phase_sms(game)
    asyncio.create_task(outbound.announce_phase(game))
