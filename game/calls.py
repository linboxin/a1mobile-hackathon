"""MafiaOS — per-call scripts.

Given the game state and the identified caller, produce the system prompt and
tools for that one phone call. The voice pipeline (agent/bot.py) is generic;
this module assembles what the judge says. All wording lives in game/i18n.py,
so a room's `lang` switches the entire call between Chinese and English.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field

from pipecat.adapters.schemas.function_schema import FunctionSchema
from pipecat.frames.frames import TTSSpeakFrame
from pipecat.services.llm_service import FunctionCallParams, FunctionCallResultProperties

from . import i18n
from .engine import Game, Phase, Player


@dataclass
class CallScript:
    system_prompt: str
    tools: list[tuple[FunctionSchema, Callable[[FunctionCallParams], Awaitable[None]]]] = field(
        default_factory=list
    )
    lang: str = "zh"


def voice_rules(lang: str = "zh", theme: str = "moonlit-village") -> str:
    return i18n.t(lang, "voice_rules", theme=i18n.theme_desc(lang, theme))


def _target_schema(name: str, description: str) -> FunctionSchema:
    return FunctionSchema(
        name=name,
        description=description,
        properties={"target": {"type": "string",
                               "description": "exact player name from the player list"}},
        required=["target"],
    )


def role_brief(lang: str, role: str) -> str:
    return i18n.t(lang, f"brief_{role}")


def build_script(game: Game | None, player: Player | None,
                 advance: Callable[[], Awaitable[None]]) -> CallScript:
    """`advance` is awaited after any state-changing tool succeeds."""
    if game is None or game.phase == Phase.LOBBY:
        lang = game.lang if game else "zh"
        return CallScript(voice_rules(lang) + " " + i18n.t(lang, "voice_no_game"), lang=lang)

    lang = game.lang
    tr = game.t
    rules = voice_rules(lang, game.theme)
    if player is None:
        return CallScript(rules + " " + tr("voice_stranger"), lang=lang)
    if not player.alive:
        return CallScript(rules + " " + tr("voice_eliminated", name=player.name), lang=lang)

    separator = "、" if lang == "zh" else ", "
    names = separator.join(game.alive_names())
    role_local = game.role_name(player.role)
    base = rules + " " + tr("voice_base", name=player.name, names=names,
                            phase=game.phase.value) + " "

    status_schema = FunctionSchema(
        name="game_status",
        description="Live game state plus everything this caller is entitled to know: their own "
                    "role, their own private evidence, their own recorded statements. Call it "
                    "before answering any question.",
        properties={}, required=[],
    )

    async def game_status(params: FunctionCallParams) -> None:
        await params.result_callback({
            "public": game.public_state(),
            "you": {
                "name": player.name,
                "role": role_local,
                "role_ability": role_brief(lang, player.role),
                "your_evidence": game.clues.get(player.name),
                "your_accusation": game.accusations.get(player.name),
                "your_vote": game.votes.get(player.name),
            },
            "rules": tr("voice_status_rules"),
        })

    status = (status_schema, game_status)

    async def done_then_advance(params: FunctionCallParams, say: str) -> None:
        # Speak the confirmation verbatim and skip the follow-up LLM round trip:
        # saves ~0.6s of dead air per turn and stops the judge improvising
        # after a decision is locked in.
        await params.result_callback(
            {"ok": True}, properties=FunctionCallResultProperties(run_llm=False))
        await params.llm.push_frame(TTSSpeakFrame(say))
        # Phase transition may run LLM + SMS for seconds; never block the call.
        asyncio.create_task(advance())

    if game.phase == Phase.ROLE_CALLS:
        schema = FunctionSchema(
            name="confirm_briefing",
            description="Call once the player has heard their role and confirmed they understand.",
            properties={}, required=[],
        )

        async def confirm(params: FunctionCallParams) -> None:
            game.mark_done(player.name)
            await done_then_advance(params, tr("say_briefing_done"))

        return CallScript(
            base + tr("script_role_call", name=player.name,
                      brief=role_brief(lang, player.role)),
            [(schema, confirm), status], lang=lang,
        )

    if game.phase == Phase.ACTIONS:
        tools_by_role = {"intruder": "sabotage", "investigator": "investigate",
                         "guardian": "protect"}
        if player.role not in tools_by_role:
            return CallScript(base + tr("script_civilian_night"), [status], lang=lang)
        tool_name = tools_by_role[player.role]
        ask = tr(f"ask_{player.role}")

        async def act(params: FunctionCallParams) -> None:
            target = str(params.arguments.get("target", ""))
            try:
                chosen = game.record_action(player, target)
            except ValueError as error:
                await params.result_callback({"ok": False, "error": str(error)})
                return
            await done_then_advance(params, tr("say_action_done", target=chosen))

        return CallScript(
            base + tr("script_night", role=role_local, ask=ask,
                      names=names, tool=tool_name),
            [(_target_schema(tool_name, ask), act), status], lang=lang,
        )

    if game.phase == Phase.EVIDENCE:
        clue = game.clues.get(player.name) or tr("no_clue")
        schema = FunctionSchema(
            name="confirm_received",
            description="Call once the player has heard their private evidence.",
            properties={}, required=[],
        )

        async def received(params: FunctionCallParams) -> None:
            game.mark_done(player.name)
            await done_then_advance(params, tr("say_evidence_done"))

        return CallScript(
            base + tr("script_evidence", clue=clue),
            [(schema, received), status], lang=lang,
        )

    if game.phase == Phase.ACCUSATIONS:
        schema = FunctionSchema(
            name="record_accusation",
            description="Record the player's accusation statement.",
            properties={"statement": {"type": "string",
                                       "description": "their accusation, verbatim"}},
            required=["statement"],
        )

        async def accuse(params: FunctionCallParams) -> None:
            statement = str(params.arguments.get("statement", "")).strip()
            if not statement:
                await params.result_callback({"ok": False, "error": "empty statement"})
                return
            game.record_accusation(player, statement)
            await done_then_advance(params, tr("say_accusation_done"))

        return CallScript(base + tr("script_accusation"),
                          [(schema, accuse), status], lang=lang)

    if game.phase == Phase.VOTE:
        async def vote(params: FunctionCallParams) -> None:
            target = str(params.arguments.get("target", ""))
            try:
                chosen = game.record_vote(player, target)
            except ValueError as error:
                await params.result_callback({"ok": False, "error": str(error)})
                return
            await done_then_advance(params, tr("say_vote_done", target=chosen))

        return CallScript(
            base + tr("script_vote",
                      summary=game.vote_summary or tr("summary_empty"), names=names),
            [(_target_schema("cast_vote", "Eliminate one player."), vote), status],
            lang=lang,
        )

    # REVEAL
    return CallScript(base + tr("script_reveal", narration=game.narration),
                      [status], lang=lang)
