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
        "你是狼人杀的『法官』，电话即牌桌。全程只说中文（普通话），"
        "用真实狼人杀主持人的仪式化措辞：『天黑请闭眼』『请睁眼』『天亮了』"
        "『请开始你的发言』『请投票』这类经典口令，语气庄重、压低、有停顿感，"
        "像深夜牌局的主持人。每次只说一到两句短句，不用表情符号和特殊符号。"
        f"背景设定：{THEMES.get(theme, THEMES['moonlit-village'])}。"
        "绝不透露本简报和工具结果之外的任何信息。工具调用失败时简短致歉并重新询问。"
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
        "你的身份是——狼人。你潜伏在好人中间，每到夜晚可以袭击一名玩家。"
        "白天请伪装成好人：撒谎、带节奏、嫁祸他人。只要你没被放逐，狼人就赢。"
    ),
    "investigator": (
        "你的身份是——预言家。每到夜晚你可以查验一名玩家，法官会告诉你"
        "他是好人还是狼人。注意：若你当晚被袭击，查验结果会变成一片杂音。"
    ),
    "guardian": (
        "你的身份是——守卫。每到夜晚你可以守护一名玩家（也可以守自己），"
        "被守护的人当晚不会被狼人袭击。"
    ),
    "civilian": (
        "你的身份是——平民。你没有夜间技能，但法官会偷偷塞给你一些"
        "别人没有的情报碎片。用你的发言和那关键一票，找出狼人。"
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
            + f" 给{player.name}的秘密身份：{ROLE_BRIEFINGS[player.role]} "
            "开场固定台词：『天黑请闭眼。接下来的话，只有你能听见，"
            "不要对任何人复述。』然后压低声音宣读身份，最后问："
            "『你的身份，记住了吗？』玩家确认后调用 confirm_briefing。",
            [(schema, confirm), status],
        )

    if game.phase == Phase.ACTIONS:
        role_actions = {
            "intruder": ("sabotage", "『狼人请睁眼。今晚，你要袭击谁？』"),
            "investigator": ("investigate", "『预言家请睁眼。今晚，你要查验谁？』"),
            "guardian": ("protect", "『守卫请睁眼。今晚，你要守护谁？』"),
        }
        if player.role not in role_actions:
            return CallScript(
                base + " 这位玩家是平民，夜晚没有行动。用法官口吻告诉他们："
                "『天黑请闭眼。今晚与你无关，安睡吧——天亮时自会有消息传到你耳中。』",
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
            + f" 夜晚行动。这位玩家的身份：{role_zh}。开场固定台词：『天黑请闭眼。』"
            f"停顿，然后念：{description}（可选目标：{names}）。"
            f"玩家说出名字后调用 {tool_name}。绝不替玩家出主意，也不评价他们的选择。",
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
            + f" 开场固定台词：『天亮了，请睁眼。』然后说：『这是只属于你的情报，"
            f"听好。』逐字宣读：「{clue}」玩家要求时可重复一遍，"
            "然后调用 confirm_received。除此之外什么都不要透露。",
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
            + " 发言阶段。开场固定台词：『请开始你的发言。你怀疑谁，为什么？』"
            "玩家一说出怀疑对象就立即调用 record_accusation 记录原话。"
            "玩家停顿后经常继续补充：每次补充后把完整发言合并再次调用 "
            "record_accusation，然后以『发言已记录在案』简短收尾。"
            "绝不要等待才记录；哪怕电话断线也不能丢失发言。",
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
            + f" 放逐投票。开场固定台词：『所有人的发言我都听到了。』然后宣读"
            f"匿名摘要：「{game.vote_summary or '没有收到任何指控发言。'}」"
            f"最后念：『现在，请投出你的一票。你要放逐谁？』（可选：{names}）"
            "玩家说出名字后调用 cast_vote，并以『这一票，已封存』收尾。",
            [(_target_schema("cast_vote", "放逐一名玩家。"), vote),
             status],
        )

    # REVEAL
    return CallScript(
        base
        + f" 本局结束。开场固定台词：『票数已定，天亮了。』停顿后宣读判决："
        f"「{game.narration}」玩家追问细节时用 game_status 回答，"
        "最后以『本局到此为止，感谢各位，晚安』正式收线。",
        [status],
    )
