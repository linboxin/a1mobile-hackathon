"""MafiaOS — LLM game director.

Turns resolved game facts into in-world text: private evidence clues, an
anonymized accusation summary, the AI Director's interventions, the final
narration and the postgame debrief. All wording comes from game/i18n.py, so
everything follows the room's language.

Every function has a deterministic fallback so a flaky API can never stall a
live demo — worst case the game gets template prose instead of bespoke drama.
"""

from __future__ import annotations

import json
import os
import random

from loguru import logger
from openai import AsyncOpenAI

from . import i18n
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


async def _complete(game: Game, prompt: str, want_json: bool = False) -> str:
    style = game.t("dir_style", theme=i18n.theme_desc(game.lang, game.theme))
    response = await _client().chat.completions.create(
        model=MODEL,
        messages=[{"role": "system", "content": style},
                  {"role": "user", "content": prompt}],
        temperature=0.9,
        **({"response_format": {"type": "json_object"}} if want_json else {}),
    )
    return response.choices[0].message.content or ""


def _dumps(value) -> str:
    return json.dumps(value, ensure_ascii=False)


async def generate_clues(game: Game, facts: dict[str, str]) -> dict[str, str]:
    """One private clue per living player, grounded in the resolved actions."""
    tr = game.t
    intruder = facts["intruder"]
    intruders = facts.get("intruders", intruder).split(",")
    sabotaged = facts["sabotaged"]
    blocked = facts["sabotage_blocked"] == "True"
    others = [n for n in game.alive_names() if n not in intruders]
    decoy = random.choice(others)

    briefs: dict[str, str] = {}
    for player in game.players:
        if not player.alive:
            continue
        if player.role == "investigator":
            if facts["investigator_sabotaged"] == "True":
                briefs[player.name] = tr("brief_inv_corrupt")
            else:
                verdict = (tr("verdict_is") if facts["investigated"] in intruders
                           else tr("verdict_not"))
                briefs[player.name] = tr("brief_inv_result",
                                         target=facts["investigated"], verdict=verdict)
        elif player.role == "guardian":
            key = "brief_guardian_blocked" if blocked else "brief_guardian_quiet"
            briefs[player.name] = tr(key, target=facts["protected"])
        elif player.role == "civilian":
            briefs[player.name] = tr("brief_civ_clue",
                                     a=random.choice(intruders), b=decoy)
        elif player.role == "intruder":
            briefs[player.name] = tr("brief_intruder_cover", decoy=decoy)
        if player.name == sabotaged and not blocked and player.role != "investigator":
            briefs[player.name] += tr("brief_sabotaged_suffix")

    try:
        clues = json.loads(await _complete(
            game, tr("prompt_clues", briefs=_dumps(briefs)), want_json=True))
        assert set(clues) >= set(briefs), "missing players"
        return {k: str(v) for k, v in clues.items() if k in briefs}
    except Exception as error:  # demo must not stall
        logger.warning(f"Director clue generation failed ({error}); using templates")
        return {name: tr("clue_fallback", name=name, brief=brief)
                for name, brief in briefs.items()}


async def accusation_summary(game: Game) -> str:
    """Anonymized digest of all accusations, read to everyone before the vote."""
    tr = game.t
    statements = list(game.accusations.values())
    if not statements:
        return tr("summary_empty")
    try:
        return await _complete(game, tr("prompt_summary", statements=_dumps(statements)))
    except Exception as error:
        logger.warning(f"Director summary failed ({error}); using template")
        counts = game.suspicion()
        return tr("summary_fallback", n=len(statements), top=max(counts, key=counts.get))


async def director_tick(game: Game) -> None:
    """The AI Director: observes the full secret state after evidence lands and
    may intervene once — an extra private clue to keep the game tense, or a
    public event that muddies an obvious solve. Interventions are logged to the
    (host-only) director notes; failures are silently skipped.
    """
    tr = game.t
    state = {
        "theme": game.theme,
        "players": [{"name": p.name, "role": p.role} for p in game.players],
        "night_actions": game.actions,
        "clues_delivered": game.clues,
        "who_has_called_in": game.done,
    }
    try:
        verdict = json.loads(await _complete(
            game, tr("prompt_tick", state=_dumps(state)), want_json=True))
    except Exception as error:
        logger.warning(f"Director tick failed ({error}); skipping intervention")
        return
    reasoning = str(verdict.get("reasoning", ""))[:300]
    game.director_notes.append(f"[{game.phase.value}] {reasoning or 'no intervention'}")
    if event := verdict.get("public_event"):
        game.log(tr("log_intercept", text=str(event)[:200]))
    if (clue := verdict.get("extra_clue")) and isinstance(clue, dict):
        target = game.player_by_name(str(clue.get("player", "")))
        text = str(clue.get("text", "")).strip()
        if target and target.alive and text:
            prefix = tr("new_intercept_prefix")
            game.clues[target.name] = f"{game.clues.get(target.name, '')} {prefix}{text}".strip()
            game.director_notes.append(f"extra clue -> {target.name}: {text}")
            from . import notify
            await notify.send_sms(target.phone,
                                  tr("sms_new_clue", line=notify.hotline()))
    game.save()


async def postgame_explanation(game: Game) -> str:
    """Full debrief for after the reveal: what actually happened and why."""
    tr = game.t
    facts = {
        "roles": {p.name: game.role_name(p.role) for p in game.players},
        "night_actions": game.actions,
        "clues": game.clues,
        "accusations": game.accusations,
        "votes": game.votes,
        "eliminated": game.eliminated,
        "winner": game.winner,
    }
    try:
        return await _complete(game, tr("prompt_postgame", facts=_dumps(facts)))
    except Exception as error:
        logger.warning(f"Postgame generation failed ({error}); using template")
        joiner = "，" if game.lang == "zh" else ", "
        roles = joiner.join(
            (f"{p.name}是{game.role_name(p.role)}" if game.lang == "zh"
             else f"{p.name} was the {game.role_name(p.role)}")
            for p in game.players)
        winner = tr("winner_zh_network" if game.winner == "network" else "winner_zh_intruder")
        return tr("postgame_fallback", roles=roles, votes=_dumps(game.votes), winner=winner)


async def reveal_narration(game: Game) -> str:
    tr = game.t
    joiner = "、" if game.lang == "zh" else ", "
    intruder = joiner.join(game.intruder_names())
    if game.eliminated:
        eliminated_role = game.player_by_name(game.eliminated).role
        outcome = tr("outcome_eliminated", name=game.eliminated,
                     role=game.role_name(eliminated_role))
    else:
        outcome = tr("outcome_tie")
    outcome += tr("outcome_intruder_was", intruder=intruder)
    outcome += tr("log_win_network") if game.winner == "network" \
        else tr("log_win_intruder", intruder=intruder)
    try:
        return await _complete(game, tr("prompt_reveal", outcome=outcome))
    except Exception as error:
        logger.warning(f"Director narration failed ({error}); using template")
        return outcome
