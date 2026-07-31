"""Dead Air — phase orchestration.

Watches for completed phases, advances the engine, runs director side effects
(clues, summaries, narration), and triggers SMS pacing.
"""

from __future__ import annotations

import asyncio

from loguru import logger

from . import director, notify
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

        if new == Phase.EVIDENCE:
            facts = game.resolve_actions()
            game.clues = await director.generate_clues(game, facts)
            game.log("Evidence transmitted to every operator's private line.")
        elif new == Phase.VOTE:
            game.vote_summary = await director.accusation_summary(game)
            game.log("Accusation summary compiled. The vote is open.")
        elif new == Phase.REVEAL:
            game.narration = await director.reveal_narration(game)

        game.save()
        await notify.phase_sms(game)
        return True


async def start_game(game: Game) -> None:
    game.start()
    await notify.phase_sms(game)
