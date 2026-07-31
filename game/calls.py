"""Dead Air — per-call scripts.

Given the game state and the identified caller, produce the system prompt and
tools for that one phone call. The voice pipeline (agent/bot.py) is generic;
this module is where the game talks.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field

from pipecat.adapters.schemas.function_schema import FunctionSchema
from pipecat.services.llm_service import FunctionCallParams

from .engine import THEMES, Game, Phase, Player


def voice_rules(theme: str = "signal-station") -> str:
    return (
        "You are HQ, the operator voice of MafiaOS, a phone-based deduction "
        f"game. Setting: {THEMES.get(theme, THEMES['signal-station'])}. Stay in "
        "that world in every word. Terse, calm radio-operator delivery. One or "
        "two short spoken sentences per turn; no emoji, no markdown, no special "
        "characters. Never reveal any information that is not in this briefing "
        "or in tool results. If a tool call fails, apologize briefly and ask "
        "again."
    )


@dataclass
class CallScript:
    system_prompt: str
    tools: list[tuple[FunctionSchema, Callable[[FunctionCallParams], Awaitable[None]]]] = field(
        default_factory=list
    )


def _target_schema(name: str, description: str) -> FunctionSchema:
    return FunctionSchema(
        name=name,
        description=description,
        properties={"target": {"type": "string", "description": "exact player name"}},
        required=["target"],
    )


ROLE_BRIEFINGS = {
    "intruder": (
        "You are the INTRUDER. You have compromised this network. Each night you "
        "sabotage one operator's line. Your goal: survive the vote. Deny everything."
    ),
    "investigator": (
        "You are the INVESTIGATOR. Each night you may trace one player to learn whether "
        "they are the Intruder. Your trace can be corrupted by sabotage."
    ),
    "guardian": (
        "You are the GUARDIAN. Each night you may shield one player's line from "
        "sabotage, including your own."
    ),
    "civilian": (
        "You are the CIVILIAN. You take no night action, but you receive intercepted "
        "fragments of the truth. Decide whom to trust."
    ),
}


def build_script(game: Game | None, player: Player | None,
                 advance: Callable[[], Awaitable[None]]) -> CallScript:
    """`advance` is awaited after any state-changing tool succeeds."""
    if game is None or game.phase == Phase.LOBBY:
        return CallScript(
            voice_rules() + " No game is active on this line yet. Tell the caller "
            "the network is quiet and to await the start signal, then say goodbye."
        )
    rules = voice_rules(game.theme)
    if player is None:
        return CallScript(
            rules + " The caller is NOT on the network manifest. In character, "
            "tell them this line is compromised and they should not have this "
            "number, then end the conversation."
        )
    if not player.alive:
        return CallScript(
            rules + f" The caller is {player.name}, who has been disconnected "
            "from the network (eliminated). They may listen but not play. Be brief "
            "and a little eerie about it."
        )

    names = ", ".join(game.alive_names())
    base = (
        f"{rules} The caller is {player.name} (verified by caller ID). "
        f"Players on the network: {names}. Current phase: {game.phase.value}. "
        "Speech transcription mangles names (Ria means Rhea): always resolve "
        "what you heard to the closest player name and proceed; never reject a "
        "near-match. The caller may ask questions at any time (their role, the "
        "rules, who is alive, what they know): answer from game_status, never "
        "from imagination, and never reveal another player's secrets. "
    )

    status_schema = FunctionSchema(
        name="game_status",
        description="Live game state plus everything this caller is entitled to "
                    "know: their role, their private evidence, their recorded "
                    "statements. Use it to answer any question.",
        properties={}, required=[],
    )

    async def game_status(params: FunctionCallParams) -> None:
        await params.result_callback({
            "public": game.public_state(),
            "you": {
                "name": player.name,
                "role": player.role,
                "role_ability": ROLE_BRIEFINGS.get(player.role, ""),
                "your_evidence": game.clues.get(player.name),
                "your_accusation": game.accusations.get(player.name),
                "your_vote": game.votes.get(player.name),
            },
            "rules": "One round. Night actions, private evidence, accusations, "
                     "then a vote. Highest vote is disconnected. If the Intruder "
                     "is disconnected the operators win; otherwise the Intruder "
                     "wins.",
        })

    status = (status_schema, game_status)

    async def done_then_advance(params: FunctionCallParams, say: str) -> None:
        await params.result_callback({"ok": True, "instruction": say})
        # Phase transition may run LLM + SMS for seconds; never block the call.
        asyncio.create_task(advance())

    if game.phase == Phase.ROLE_CALLS:
        schema = FunctionSchema(
            name="confirm_briefing",
            description="Call once the player has heard their role and said they understand.",
            properties={}, required=[],
        )

        async def confirm(params: FunctionCallParams) -> None:
            game.mark_done(player.name)
            await done_then_advance(
                params, "Briefing confirmed. Tell them to hang up and await the next SMS.")

        return CallScript(
            base
            + f"SECRET ROLE BRIEFING for {player.name}: {ROLE_BRIEFINGS[player.role]} "
            "Open with: Do not repeat this message. Then deliver the briefing, ask "
            "them to confirm they understand, and when they do, use confirm_briefing.",
            [(schema, confirm), status],
        )

    if game.phase == Phase.ACTIONS:
        role_actions = {
            "intruder": ("sabotage", "Sabotage one player's line tonight."),
            "investigator": ("investigate", "Trace one player to learn if they are the Intruder."),
            "guardian": ("protect", "Shield one player's line from sabotage."),
        }
        if player.role not in role_actions:
            return CallScript(
                base + "This player is the Civilian and has no night action. Tell them "
                "the line is quiet for them tonight and evidence will reach them soon.",
                [status],
            )
        tool_name, description = role_actions[player.role]

        async def act(params: FunctionCallParams) -> None:
            target = str(params.arguments.get("target", ""))
            try:
                chosen = game.record_action(player, target)
            except ValueError as error:
                await params.result_callback({"ok": False, "error": str(error)})
                return
            await done_then_advance(
                params, f"Action locked on {chosen}. Tell them it is done and to hang up.")

        return CallScript(
            base
            + f"Secret action window. Their role: {player.role}. {description} "
            f"Ask who they choose (valid: {names}). When they name a player, use "
            f"{tool_name}. Do not suggest targets.",
            [(_target_schema(tool_name, description), act), status],
        )

    if game.phase == Phase.EVIDENCE:
        clue = game.clues.get(player.name, "Static. No transmission recovered.")
        schema = FunctionSchema(
            name="confirm_received",
            description="Call once the player has heard their evidence.",
            properties={}, required=[],
        )

        async def received(params: FunctionCallParams) -> None:
            game.mark_done(player.name)
            await done_then_advance(
                params, "Delivery logged. Tell them accusations open soon; hang up.")

        return CallScript(
            base
            + f"PRIVATE EVIDENCE for {player.name}: \"{clue}\" Read it verbatim, "
            "repeat once if asked, then use confirm_received. Reveal nothing else.",
            [(schema, received), status],
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
            await done_then_advance(
                params, "On the record. Tell them the vote comes next; hang up.")

        return CallScript(
            base
            + "Accusation window. Ask them to state who they suspect and why. As "
            "soon as they name a suspect, use record_accusation with their exact "
            "words. Callers keep talking after pauses: every time they add more, "
            "call record_accusation again with the FULL combined statement of "
            "everything they said so far, then confirm briefly. Never wait to "
            "record; a dropped call must not lose their words.",
            [(schema, accuse), status],
        )

    if game.phase == Phase.VOTE:
        async def vote(params: FunctionCallParams) -> None:
            target = str(params.arguments.get("target", ""))
            try:
                chosen = game.record_vote(player, target)
            except ValueError as error:
                await params.result_callback({"ok": False, "error": str(error)})
                return
            await done_then_advance(
                params, f"Vote for {chosen} sealed. Tell them to await the verdict.")

        return CallScript(
            base
            + f"Final vote. First read this anonymized summary of the accusations: "
            f"\"{game.vote_summary or 'No accusations were recorded.'}\" "
            f"Then ask who they vote to disconnect (valid: {names}). "
            "When they name a player, use cast_vote.",
            [(_target_schema("cast_vote", "Disconnect one player from the network."), vote),
             status],
        )

    # REVEAL
    return CallScript(
        base
        + f"The game is over. Read this verdict: \"{game.narration}\" "
        "Answer questions about the outcome using game_status, then sign off.",
        [status],
    )
