"""Dead Air — LLM game director.

Turns resolved game facts into in-world text: private evidence clues, an
anonymized accusation summary, and the final reveal narration.

Every function has a deterministic fallback so a flaky API can never stall a
live demo — worst case the game gets template prose instead of bespoke noir.
"""

from __future__ import annotations

import json
import os
import random

from loguru import logger
from openai import AsyncOpenAI

from .engine import Game


def _env(name: str) -> str | None:
    value = os.getenv(name, "")
    return value if value and "replace" not in value else None


def _client() -> AsyncOpenAI:
    return AsyncOpenAI(
        api_key=_env("LLM_API_KEY") or _env("OPENAI_API_KEY"),
        base_url=_env("LLM_BASE_URL"),
    )


MODEL = _env("LLM_MODEL") or "gpt-4o-mini"


def _style(game: Game) -> str:
    from .engine import THEMES
    return (
        f"Style: terse noir set in {THEMES.get(game.theme, 'a compromised network')}. "
        "Stay in that world's imagery. No emoji, no markdown; plain spoken "
        "sentences suitable for text-to-speech."
    )


async def _complete(game: Game, prompt: str, want_json: bool = False) -> str:
    response = await _client().chat.completions.create(
        model=MODEL,
        messages=[{"role": "system", "content": _style(game)},
                  {"role": "user", "content": prompt}],
        temperature=0.9,
        **({"response_format": {"type": "json_object"}} if want_json else {}),
    )
    return response.choices[0].message.content or ""


async def generate_clues(game: Game, facts: dict[str, str]) -> dict[str, str]:
    """One private clue per living player, grounded in the resolved actions."""
    intruder = facts["intruder"]
    sabotaged = facts["sabotaged"]
    blocked = facts["sabotage_blocked"] == "True"
    others = [n for n in game.alive_names() if n != intruder]
    decoy = random.choice(others)

    briefs: dict[str, str] = {}
    for player in game.players:
        if not player.alive:
            continue
        if player.role == "investigator":
            if facts["investigator_sabotaged"] == "True":
                briefs[player.name] = (
                    "Their trace ran but came back corrupted by sabotage — the result "
                    "is unreadable static. Say so; give no reliable name."
                )
            else:
                verdict = "IS" if facts["investigated"] == intruder else "is NOT"
                briefs[player.name] = (
                    f"Their trace completed: {facts['investigated']} {verdict} the Intruder. "
                    "State it as a signal trace result, not as certainty about guilt."
                )
        elif player.role == "guardian":
            briefs[player.name] = (
                f"They shielded {facts['protected']}'s line. "
                + ("The shield absorbed a live intrusion attempt tonight."
                   if blocked else "The shielded line stayed quiet all night.")
            )
        elif player.role == "civilian":
            briefs[player.name] = (
                f"A partial trace: the intrusion signal came from either {intruder} "
                f"or {decoy}. The trace may not be complete."
            )
        elif player.role == "intruder":
            briefs[player.name] = (
                f"This player IS the Intruder (do not remind them; they know). Give them "
                f"their cover story: a fabricated clue implicating {decoy}, styled "
                "exactly like a real intercept so they can repeat it aloud."
            )
        if player.name == sabotaged and not blocked and player.role != "investigator":
            briefs[player.name] += (
                " Their line was sabotaged: corrupt the middle of the clue with "
                "static, dropping a key word."
            )

    prompt = (
        "Write one private evidence transmission per player for a phone game. "
        "Each is 1-2 short spoken sentences. Ground every clue in its brief; "
        "invent flavor (timestamps, terminal letters) but never new facts.\n"
        f"Briefs: {json.dumps(briefs)}\n"
        'Return JSON: {"PlayerName": "clue", ...}'
    )
    try:
        clues = json.loads(await _complete(game, prompt, want_json=True))
        assert set(clues) >= set(briefs), "missing players"
        return {k: str(v) for k, v in clues.items() if k in briefs}
    except Exception as error:  # demo must not stall
        logger.warning(f"Director clue generation failed ({error}); using templates")
        return {
            name: f"Encrypted transmission for {name}. {brief}"
            for name, brief in briefs.items()
        }


async def accusation_summary(game: Game) -> str:
    """Anonymized digest of all accusations, read to everyone before the vote."""
    statements = list(game.accusations.values())
    if not statements:
        return "No accusations were recorded. The channel stays silent."
    prompt = (
        "Summarize these accusations from a social-deduction phone game in 2-3 "
        "spoken sentences. Anonymize completely: never say or hint who made "
        f"which accusation. Accusations: {json.dumps(statements)}"
    )
    try:
        return await _complete(game, prompt)
    except Exception as error:
        logger.warning(f"Director summary failed ({error}); using template")
        counts = game.suspicion()
        top = max(counts, key=counts.get)
        return (
            f"{len(statements)} accusations were recorded. "
            f"Suspicion centers most heavily on {top}."
        )


async def director_tick(game: Game) -> None:
    """The AI Director: observes the full secret state after evidence lands and
    may intervene once — an extra private clue to keep the game tense, or a
    public event that muddies an obvious solve. Interventions are logged to the
    (host-only) director notes; failures are silently skipped.
    """
    state = {
        "theme": game.theme,
        "players": [{"name": p.name, "role": p.role} for p in game.players],
        "night_actions": game.actions,
        "clues_delivered": game.clues,
        "who_has_called_in": game.done,
    }
    prompt = (
        "You are the AI Director of a 4-player phone deduction game. Objective: "
        "keep the round tense and fair; no player should be able to solve it "
        "instantly, and quiet players should get a reason to speak. Given the "
        "full secret state, choose AT MOST one intervention and return JSON only:\n"
        '{"public_event": "one spoken sentence for the public record, or null", '
        '"extra_clue": {"player": "name", "text": "1-2 sentence private clue"} or null, '
        '"reasoning": "one sentence, for the host console"}\n'
        "Interventions must be consistent with the true facts and never state "
        "outright who the Intruder is. If the game is already balanced, return "
        "nulls.\n"
        f"State: {json.dumps(state)}"
    )
    try:
        verdict = json.loads(await _complete(game, prompt, want_json=True))
    except Exception as error:
        logger.warning(f"Director tick failed ({error}); skipping intervention")
        return
    reasoning = str(verdict.get("reasoning", ""))[:300]
    game.director_notes.append(f"[{game.phase.value}] {reasoning or 'no intervention'}")
    if event := verdict.get("public_event"):
        game.log(f"INTERCEPTED: {str(event)[:200]}")
    if (clue := verdict.get("extra_clue")) and isinstance(clue, dict):
        target = game.player_by_name(str(clue.get("player", "")))
        text = str(clue.get("text", "")).strip()
        if target and target.alive and text:
            game.clues[target.name] = f"{game.clues.get(target.name, '')} NEW INTERCEPT: {text}".strip()
            game.director_notes.append(f"extra clue -> {target.name}: {text}")
            from . import notify
            await notify.send_sms(
                target.phone,
                f"MAFIAOS // A new intercept just hit your line. Call {notify.hotline()}.",
            )
    game.save()


async def postgame_explanation(game: Game) -> str:
    """Full debrief for after the reveal: what actually happened and why."""
    facts = {
        "roles": {p.name: p.role for p in game.players},
        "night_actions": game.actions,
        "clues": game.clues,
        "accusations": game.accusations,
        "votes": game.votes,
        "eliminated": game.eliminated,
        "winner": game.winner,
    }
    prompt = (
        "Write the postgame debrief for a phone deduction game in 4-6 short "
        "spoken sentences: who was who, what happened at night, which clues "
        "were true, which was the Intruder's fabrication, and how the vote "
        f"landed. Be concrete and name names. Facts: {json.dumps(facts)}"
    )
    try:
        return await _complete(game, prompt)
    except Exception as error:
        logger.warning(f"Postgame generation failed ({error}); using template")
        roles = ", ".join(f"{p.name} was the {p.role}" for p in game.players)
        return f"Debrief: {roles}. Votes: {game.votes}. Winner: {game.winner}."


async def reveal_narration(game: Game) -> str:
    intruder = game.by_role("intruder").name
    if game.eliminated:
        eliminated_role = game.player_by_name(game.eliminated).role
        outcome = (
            f"The group disconnected {game.eliminated}, who was the "
            f"{eliminated_role}. "
        )
    else:
        outcome = "The vote tied. Nobody was disconnected. "
    outcome += (
        f"The Intruder was {intruder}. "
        + ("The network is clean — the operators win."
           if game.winner == "network" else "The Intruder wins.")
    )
    prompt = (
        "Narrate this ending of a phone-based deduction game in 3 short spoken "
        f"sentences, dramatic radio-operator style. Facts, keep exactly: {outcome}"
    )
    try:
        return await _complete(game, prompt)
    except Exception as error:
        logger.warning(f"Director narration failed ({error}); using template")
        return outcome
