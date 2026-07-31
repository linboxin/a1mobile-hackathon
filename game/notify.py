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
    Phase.ROLE_CALLS: "狼人杀 // 游戏开始。立即拨打 {line} 领取你的秘密身份。先不要和任何人交谈。",
    Phase.ACTIONS: "狼人杀 // 天黑请闭眼。找个没人的地方拨打 {line} 完成你的夜间行动。",
    Phase.EVIDENCE: "狼人杀 // 你的专线收到了新情报。拨打 {line} 收听。",
    Phase.ACCUSATIONS: "狼人杀 // 发言阶段。拨打 {line} 说出你怀疑谁。",
    Phase.VOTE: "狼人杀 // 最终投票。拨打 {line} 放逐一名玩家。",
    Phase.REVEAL: "狼人杀 // 审判已定。拨打 {line} 收听最终结局。",
}

# The civilian has no night action; don't send them a misleading action prompt.
SKIP = {(Phase.ACTIONS, "civilian")}


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
    game.log(f"短信已发送 {sum(results)}/{len(sends)}。")
    game.save()
