"""MafiaOS 狼人杀 — per-call scripts.

Given the game state and the identified caller, produce the system prompt and
tools for that one phone call. The voice pipeline (agent/bot.py) is generic;
this module is where the game talks. All player-facing language is Chinese;
internal role keys and tool names stay English.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field

from pipecat.adapters.schemas.function_schema import FunctionSchema
from pipecat.services.llm_service import FunctionCallParams

from .engine import THEMES, Game, Phase, Player

ROLE_NAMES_ZH = {
    "intruder": "狼人",
    "investigator": "预言家",
    "guardian": "守卫",
    "civilian": "平民",
}


def voice_rules(theme: str = "moonlit-village") -> str:
    return (
        "你是『法官』，一款电话狼人杀游戏的主持人。全程只说中文（普通话），"
        f"背景设定：{THEMES.get(theme, THEMES['moonlit-village'])}。"
        "语气沉稳、克制、略带神秘，像深夜电台主播。每次只说一到两句简短的口语，"
        "不用表情符号、不用任何特殊符号。绝不透露本简报和工具结果之外的任何信息。"
        "如果工具调用失败，简短道歉后重新询问。"
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
        properties={"target": {"type": "string", "description": "目标玩家的名字，务必用玩家列表中的原名"}},
        required=["target"],
    )


ROLE_BRIEFINGS = {
    "intruder": (
        "你是狼人。你潜伏在大家中间，每晚可以袭击一名玩家的信道。"
        "你的目标：撒谎、嫁祸、在放逐投票中活下来。"
    ),
    "investigator": (
        "你是预言家。每晚可以查验一名玩家，法官会告诉你那个人是不是狼人。"
        "注意：如果你被袭击，查验结果可能被干扰。"
    ),
    "guardian": (
        "你是守卫。每晚可以守护一名玩家（包括你自己），使其免受狼人袭击。"
    ),
    "civilian": (
        "你是平民。你没有夜间技能，但会收到一些别人没有的情报碎片。"
        "判断该相信谁，投出关键一票。"
    ),
}


def build_script(game: Game | None, player: Player | None,
                 advance: Callable[[], Awaitable[None]]) -> CallScript:
    """`advance` is awaited after any state-changing tool succeeds."""
    if game is None or game.phase == Phase.LOBBY:
        return CallScript(
            voice_rules() + " 目前还没有开始的对局。告诉来电者：线路一切安静，"
            "请等待开局信号，然后道别。"
        )
    rules = voice_rules(game.theme)
    if player is None:
        return CallScript(
            rules + " 来电者不在本局玩家名单上。保持角色感，告诉对方：这条线路"
            "已被监听，你不该拿到这个号码，然后结束对话。"
        )
    if not player.alive:
        return CallScript(
            rules + f" 来电者是{player.name}，已经被放逐出局。他们可以旁听但不能"
            "参与。语气简短、略带阴森。"
        )

    names = "、".join(game.alive_names())
    role_zh = ROLE_NAMES_ZH.get(player.role, player.role)
    base = (
        f"{rules} 来电者是{player.name}（已通过来电号码确认身份）。"
        f"本局存活玩家：{names}。当前阶段：{game.phase.value}。"
        "语音识别经常把名字听错（包括把英文名转成相近发音）：永远把听到的名字"
        "解析成玩家列表里最接近的那个并继续，绝不因为名字不完全一致而拒绝。"
        "来电者随时可以提问（自己的身份、规则、谁还活着、自己知道什么）："
        "一律先调用 game_status 再回答，绝不凭想象回答，也绝不透露其他玩家的秘密。"
    )

    status_schema = FunctionSchema(
        name="game_status",
        description="实时对局状态，以及这位来电者有权知道的一切：自己的身份、"
                    "自己的私人情报、自己已记录的发言。回答任何问题前先调用它。",
        properties={}, required=[],
    )

    async def game_status(params: FunctionCallParams) -> None:
        await params.result_callback({
            "public": game.public_state(),
            "you": {
                "name": player.name,
                "role": ROLE_NAMES_ZH.get(player.role, player.role),
                "role_ability": ROLE_BRIEFINGS.get(player.role, ""),
                "your_evidence": game.clues.get(player.name),
                "your_accusation": game.accusations.get(player.name),
                "your_vote": game.votes.get(player.name),
            },
            "rules": "一整局：夜晚行动、私人情报、发言指控、然后投票放逐。"
                     "得票最高者出局。狼人被放逐则好人阵营获胜；否则狼人获胜。",
        })

    status = (status_schema, game_status)

    async def done_then_advance(params: FunctionCallParams, say: str) -> None:
        await params.result_callback({"ok": True, "instruction": say})
        # Phase transition may run LLM + SMS for seconds; never block the call.
        asyncio.create_task(advance())

    if game.phase == Phase.ROLE_CALLS:
        schema = FunctionSchema(
            name="confirm_briefing",
            description="当玩家听完身份并表示明白后调用一次。",
            properties={}, required=[],
        )

        async def confirm(params: FunctionCallParams) -> None:
            game.mark_done(player.name)
            await done_then_advance(
                params, "身份确认完毕。告诉玩家挂断电话，等待下一条短信。")

        return CallScript(
            base
            + f" 给{player.name}的秘密身份简报：{ROLE_BRIEFINGS[player.role]} "
            "开场先说：接下来的话不要对任何人复述。然后宣读身份简报，"
            "请玩家确认明白；玩家确认后调用 confirm_briefing。",
            [(schema, confirm), status],
        )

    if game.phase == Phase.ACTIONS:
        role_actions = {
            "intruder": ("sabotage", "今晚袭击一名玩家的信道。"),
            "investigator": ("investigate", "查验一名玩家是否是狼人。"),
            "guardian": ("protect", "守护一名玩家，抵挡今晚的袭击。"),
        }
        if player.role not in role_actions:
            return CallScript(
                base + " 这位玩家是平民，晚上没有技能。告诉他们今晚安静等待，"
                "情报很快会送到他们的专线上。",
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
                params, f"已锁定目标{chosen}。告诉玩家行动完成，请挂断。")

        return CallScript(
            base
            + f" 天黑请闭眼。这位玩家的身份：{role_zh}。{description}"
            f"询问他们选择谁（可选：{names}）。玩家说出名字后调用 {tool_name}。"
            "不要替玩家出主意。",
            [(_target_schema(tool_name, description), act), status],
        )

    if game.phase == Phase.EVIDENCE:
        clue = game.clues.get(player.name, "只有杂音，没有收到有效情报。")
        schema = FunctionSchema(
            name="confirm_received",
            description="玩家听完自己的情报后调用一次。",
            properties={}, required=[],
        )

        async def received(params: FunctionCallParams) -> None:
            game.mark_done(player.name)
            await done_then_advance(
                params, "情报送达已记录。告诉玩家发言阶段即将开始，请挂断。")

        return CallScript(
            base
            + f" 给{player.name}的私人情报：「{clue}」逐字宣读，玩家要求时可以"
            "重复一遍，然后调用 confirm_received。此外什么都不要透露。",
            [(schema, received), status],
        )

    if game.phase == Phase.ACCUSATIONS:
        schema = FunctionSchema(
            name="record_accusation",
            description="记录玩家的指控发言。",
            properties={"statement": {"type": "string",
                                       "description": "玩家的指控原话"}},
            required=["statement"],
        )

        async def accuse(params: FunctionCallParams) -> None:
            statement = str(params.arguments.get("statement", "")).strip()
            if not statement:
                await params.result_callback({"ok": False, "error": "发言为空"})
                return
            game.record_accusation(player, statement)
            await done_then_advance(
                params, "已记录在案。告诉玩家接下来是投票阶段，请挂断。")

        return CallScript(
            base
            + " 发言指控阶段。请玩家说出怀疑谁、为什么。玩家一说出怀疑对象就"
            "立即调用 record_accusation 记录原话。玩家停顿后经常会继续补充："
            "每次补充后，把到目前为止的完整发言合并起来再次调用 record_accusation，"
            "然后简短确认。绝不要等待才记录；哪怕电话中途断线也不能丢失发言。",
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
                params, f"对{chosen}的放逐票已封存。告诉玩家等待最终宣判。")

        return CallScript(
            base
            + f" 最终投票。先宣读这份匿名的发言摘要：「"
            f"{game.vote_summary or '没有收到任何指控发言。'}」"
            f"然后询问玩家投票放逐谁（可选：{names}）。"
            "玩家说出名字后调用 cast_vote。",
            [(_target_schema("cast_vote", "放逐一名玩家。"), vote),
             status],
        )

    # REVEAL
    return CallScript(
        base
        + f" 本局结束。宣读最终判决：「{game.narration}」"
        "玩家追问结果时用 game_status 回答，然后正式收线告别。",
        [status],
    )
