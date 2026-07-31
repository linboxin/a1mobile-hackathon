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
        f"文风：简洁冷峻的悬疑风，背景设定在{THEMES.get(game.theme, '被渗透的村庄')}。"
        "全部输出必须是中文（普通话）口语短句，适合直接语音朗读。"
        "不用表情符号、不用markdown、不用特殊符号。"
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
                    "他们昨晚的查验被袭击干扰，结果只剩下杂音，完全无法读取。"
                    "如实告知，不给出任何可靠的名字。"
                )
            else:
                verdict = "就是狼人" if facts["investigated"] == intruder else "不是狼人"
                briefs[player.name] = (
                    f"他们的查验完成了：{facts['investigated']}{verdict}。"
                    "以查验结果的口吻陈述，而不是定罪。"
                )
        elif player.role == "guardian":
            briefs[player.name] = (
                f"他们昨晚守护了{facts['protected']}。"
                + ("守护挡下了一次真实的夜间袭击。"
                   if blocked else "被守护的人一夜平安无事。")
            )
        elif player.role == "civilian":
            briefs[player.name] = (
                f"一条不完整的线索：狼人的踪迹指向{intruder}或{decoy}其中之一。"
                "线索可能有缺失。"
            )
        elif player.role == "intruder":
            briefs[player.name] = (
                f"这位玩家就是狼人（不必提醒，他们自己知道）。给他们编一条用来"
                f"脱身的假情报：伪造一条指向{decoy}的线索，风格要和真情报一模一样，"
                "方便他们对别人复述。"
            )
        if player.name == sabotaged and not blocked and player.role != "investigator":
            briefs[player.name] += (
                " 他们的线路昨晚被袭击了：把情报中间一段替换成杂音，"
                "让一个关键词丢失。"
            )

    prompt = (
        "为电话狼人杀游戏的每位玩家写一条私人情报，每条一到两句中文口语短句。"
        "内容必须严格基于各自的brief；可以加时间、地点等氛围细节，"
        "但绝不能编造新的事实。\n"
        f"Briefs: {json.dumps(briefs, ensure_ascii=False)}\n"
        '只返回JSON：{"玩家名": "情报", ...}'
    )
    try:
        clues = json.loads(await _complete(game, prompt, want_json=True))
        assert set(clues) >= set(briefs), "missing players"
        return {k: str(v) for k, v in clues.items() if k in briefs}
    except Exception as error:  # demo must not stall
        logger.warning(f"Director clue generation failed ({error}); using templates")
        return {
            name: f"加密情报，收件人{name}：{brief}"
            for name, brief in briefs.items()
        }


async def accusation_summary(game: Game) -> str:
    """Anonymized digest of all accusations, read to everyone before the vote."""
    statements = list(game.accusations.values())
    if not statements:
        return "没有收到任何指控发言，全场一片沉默。"
    prompt = (
        "用两到三句中文口语总结这些狼人杀指控发言。必须完全匿名："
        "绝不能说出或暗示是谁说的哪句。发言列表："
        f"{json.dumps(statements, ensure_ascii=False)}"
    )
    try:
        return await _complete(game, prompt)
    except Exception as error:
        logger.warning(f"Director summary failed ({error}); using template")
        counts = game.suspicion()
        top = max(counts, key=counts.get)
        return (
            f"共收到{len(statements)}条指控发言，"
            f"怀疑最集中的对象是{top}。"
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
        "你是四人电话狼人杀的AI导演。目标：让对局紧张且公平；不让任何玩家"
        "一眼看穿真相，也要给安静的玩家开口的理由。基于完整的秘密状态，"
        "最多选择一次干预，只返回JSON：\n"
        '{"public_event": "一句写入公共记录的中文播报，或null", '
        '"extra_clue": {"player": "玩家名", "text": "一到两句中文私人情报"} 或 null, '
        '"reasoning": "给主持人看的一句中文理由"}\n'
        "干预必须与真实事实一致，绝不能直接说出谁是狼人。"
        "如果局势已经平衡，全部返回null。\n"
        f"State: {json.dumps(state, ensure_ascii=False)}"
    )
    try:
        verdict = json.loads(await _complete(game, prompt, want_json=True))
    except Exception as error:
        logger.warning(f"Director tick failed ({error}); skipping intervention")
        return
    reasoning = str(verdict.get("reasoning", ""))[:300]
    game.director_notes.append(f"[{game.phase.value}] {reasoning or 'no intervention'}")
    if event := verdict.get("public_event"):
        game.log(f"截获广播：{str(event)[:200]}")
    if (clue := verdict.get("extra_clue")) and isinstance(clue, dict):
        target = game.player_by_name(str(clue.get("player", "")))
        text = str(clue.get("text", "")).strip()
        if target and target.alive and text:
            game.clues[target.name] = f"{game.clues.get(target.name, '')} 新截获情报：{text}".strip()
            game.director_notes.append(f"extra clue -> {target.name}: {text}")
            from . import notify
            await notify.send_sms(
                target.phone,
                f"狼人杀 // 你的专线收到一条新情报，立即回拨 {notify.hotline()}。",
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
        "用四到六句中文口语写这局狼人杀的赛后复盘：每个人的身份、夜里发生了"
        "什么、哪些情报是真的、哪条是狼人伪造的、投票结果如何。"
        f"要具体、点名。事实：{json.dumps(facts, ensure_ascii=False)}"
    )
    try:
        return await _complete(game, prompt)
    except Exception as error:
        logger.warning(f"Postgame generation failed ({error}); using template")
        zh = {"intruder": "狼人", "investigator": "预言家", "guardian": "守卫", "civilian": "平民"}
        roles = "，".join(f"{p.name}是{zh.get(p.role, p.role)}" for p in game.players)
        winner = "好人阵营" if game.winner == "network" else "狼人"
        return f"复盘：{roles}。投票：{game.votes}。{winner}获胜。"


async def reveal_narration(game: Game) -> str:
    intruder = game.by_role("intruder").name
    if game.eliminated:
        eliminated_role = game.player_by_name(game.eliminated).role
        zh = {"intruder": "狼人", "investigator": "预言家", "guardian": "守卫", "civilian": "平民"}
        outcome = (
            f"众人放逐了{game.eliminated}，{game.eliminated}的身份是"
            f"{zh.get(eliminated_role, eliminated_role)}。"
        )
    else:
        outcome = "投票平局，无人出局。"
    outcome += (
        f"狼人是{intruder}。"
        + ("狼人已被清除，好人阵营获胜。"
           if game.winner == "network" else "狼人获胜。")
    )
    prompt = (
        "以狼人杀法官的口吻，用三句富有仪式感和戏剧张力的中文宣读本局结局，"
        "可用『票数已定』『天亮了』这类经典口令开场。"
        f"必须严格保留以下事实：{outcome}"
    )
    try:
        return await _complete(game, prompt)
    except Exception as error:
        logger.warning(f"Director narration failed ({error}); using template")
        return outcome
