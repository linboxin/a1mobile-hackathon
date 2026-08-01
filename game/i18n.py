"""MafiaOS localization — every player-facing string, in both languages.

The game's language is chosen per room (Game.lang: "zh" | "en") and drives the
judge's voice, the SMS, the LLM director's prompts, the outbound announcements
and the public log. Internal role keys, tool names and phase keys stay English.
"""

from __future__ import annotations

LANGS = ("zh", "en")

ROLE_NAMES = {
    "zh": {"intruder": "狼人", "investigator": "预言家",
           "guardian": "守卫", "civilian": "平民"},
    "en": {"intruder": "Intruder", "investigator": "Investigator",
           "guardian": "Guardian", "civilian": "Civilian"},
}

THEME_DESCRIPTIONS = {
    "zh": {
        "moonlit-village": "月夜下的古老村庄；狼嚎、烛火、木门吱呀作响，经典狼人杀氛围",
        "signal-station": "冷战时期被渗透的信号站；电波杂音、终端机、截获的密电",
        "haunted-hotel": "大雪封山的闹鬼旅馆；劈啪作响的电话线、房间号、走廊里的脚步声",
        "spaceship": "正在漏气的深空飞船；通讯舱、气闸、船体传感器的警报",
        "spy-agency": "暴露的间谍网络；死信箱、代号、被出卖的安全屋",
    },
    "en": {
        "moonlit-village": "an old village under a full moon; wolves howling, candlelight, "
                           "doors creaking — classic werewolf atmosphere",
        "signal-station": "a compromised Cold War signals station; radio static, terminals, intercepts",
        "haunted-hotel": "a snowed-in haunted hotel; crackling phone lines, room numbers, "
                         "footsteps in the halls",
        "spaceship": "a deep-space vessel losing air; comms decks, airlocks, hull alarms",
        "spy-agency": "a burned spy network; dead drops, code names, compromised safehouses",
    },
}

STRINGS: dict[str, dict[str, str]] = {
    # ---------------- public log ----------------
    "log_room_open": {
        "zh": "信道已建立，四名玩家全部接入。等待开局。",
        "en": "Room open. Four players connected. Awaiting the start signal.",
    },
    "log_game_start": {
        "zh": "检测到狼人混入。身份已分发——所有玩家请立即回拨法官热线领取身份。",
        "en": "An Intruder is among us. Roles dealt — every player call the hotline for your briefing.",
    },
    "log_night_resolved": {
        "zh": "夜晚行动已结算，收到秘密行动 {n}/3。",
        "en": "Night actions resolved. Secret actions received: {n}/3.",
    },
    "log_evidence_sent": {
        "zh": "情报已下发到每位玩家的专线。",
        "en": "Private evidence delivered to every player's line.",
    },
    "log_summary_ready": {
        "zh": "发言摘要已汇总，投票开始。",
        "en": "Accusation summary compiled. The vote is open.",
    },
    "log_no_accusations": {
        "zh": "没有收到任何指控发言。",
        "en": "No accusations were recorded.",
    },
    "log_no_votes": {
        "zh": "无人投票。狼人仍潜伏在村庄之中。",
        "en": "No votes were cast. The Intruder remains among us.",
    },
    "log_tie": {
        "zh": "投票平局（{tally}），无人出局。狼人逃过一劫。",
        "en": "The vote tied ({tally}). Nobody was eliminated. The Intruder survives.",
    },
    "log_eliminated": {
        "zh": "众人投票放逐了{name}。{name}的身份是：{role}。",
        "en": "The group eliminated {name}. {name} was the {role}.",
    },
    "log_win_network": {
        "zh": "狼人已被清除，好人阵营获胜。",
        "en": "The Intruder is gone. The villagers win.",
    },
    "log_win_intruder": {
        "zh": "狼人（{intruder}）活了下来，狼人获胜。",
        "en": "The Intruder ({intruder}) survives. The Intruder wins.",
    },
    "log_sms": {
        "zh": "短信已发送 {ok}/{total}。",
        "en": "SMS delivered to {ok}/{total} players.",
    },
    "log_call_connected": {
        "zh": "{name} 接通了法官热线。",
        "en": "{name} connected to the hotline.",
    },
    "log_call_dropped": {
        "zh": "{name} 挂断了电话，但本阶段还没有提交决定。",
        "en": "{name} hung up without submitting a decision this phase.",
    },
    "log_intercept": {
        "zh": "截获广播：{text}",
        "en": "INTERCEPTED: {text}",
    },
    "log_outbound": {
        "zh": "外呼{name}：{status}。",
        "en": "Called {name}: {status}.",
    },
    "outbound_connected": {"zh": "已接通", "en": "answered"},
    "outbound_missed": {"zh": "未接通", "en": "no answer"},
    "done_role_calls": {
        "zh": "{name} 已确认身份，挂断了电话。",
        "en": "{name} confirmed their role and hung up.",
    },
    "done_actions": {
        "zh": "{name} 完成了夜间行动。",
        "en": "{name} submitted their night action.",
    },
    "done_evidence": {
        "zh": "{name} 收到了自己的情报。",
        "en": "{name} received their private evidence.",
    },
    "done_accusations": {
        "zh": "{name} 的发言已记录在案。",
        "en": "{name}'s accusation is on the record.",
    },
    "done_vote": {
        "zh": "{name} 投出了一票。",
        "en": "{name} cast their vote.",
    },

    # ---------------- SMS ----------------
    "sms_role_calls": {
        "zh": "狼人杀 // 游戏开始。立即拨打 {line} 领取你的秘密身份。先不要和任何人交谈。",
        "en": "MAFIAOS // Game start. Call {line} NOW for your secret role. Speak to no one first.",
    },
    "sms_actions": {
        "zh": "狼人杀 // 天黑请闭眼。找个没人的地方拨打 {line} 完成你的夜间行动。",
        "en": "MAFIAOS // Night falls. Somewhere private, call {line} to take your night action.",
    },
    "sms_evidence": {
        "zh": "狼人杀 // 你的专线收到了新情报。拨打 {line} 收听。",
        "en": "MAFIAOS // New evidence is waiting on your line. Call {line}.",
    },
    "sms_accusations": {
        "zh": "狼人杀 // 发言阶段。拨打 {line} 说出你怀疑谁。",
        "en": "MAFIAOS // Accusation window. Call {line} and name your suspect.",
    },
    "sms_vote": {
        "zh": "狼人杀 // 最终投票。拨打 {line} 放逐一名玩家。",
        "en": "MAFIAOS // FINAL VOTE. Call {line} to eliminate a player.",
    },
    "sms_reveal": {
        "zh": "狼人杀 // 审判已定。拨打 {line} 收听最终结局。",
        "en": "MAFIAOS // The verdict is in. Call {line} to hear how it ended.",
    },
    "sms_new_clue": {
        "zh": "狼人杀 // 你的专线收到一条新情报，立即回拨 {line}。",
        "en": "MAFIAOS // A new intercept just hit your line. Call {line}.",
    },

    # ---------------- outbound announcements ----------------
    "announce_role_calls": {
        "zh": "这里是狼人杀法官。对局开始，你的秘密身份已经就绪。挂断后，请立即回拨法官热线领取身份。",
        "en": "This is the MafiaOS judge. The game has begun and your secret role is waiting. "
              "Hang up and call this number back for your briefing.",
    },
    "announce_actions": {
        "zh": "天黑请闭眼。所有人低下头。有夜间技能的玩家，请挂断后回拨法官热线，完成你的行动。",
        "en": "Night falls. Everyone close your eyes. If you have a night ability, "
              "hang up and call back to take your action.",
    },
    "announce_evidence": {
        "zh": "天亮了，请睁眼。你的专线上有一份只属于你的情报。请挂断后回拨法官热线收听。",
        "en": "Day breaks. Open your eyes. A piece of evidence meant only for you is waiting. "
              "Hang up and call back to hear it.",
    },
    "announce_accusations": {
        "zh": "发言阶段开始。你怀疑谁？请挂断后回拨法官热线，说出你的指控。",
        "en": "The accusation window is open. Who do you suspect? Hang up and call back to state your case.",
    },
    "announce_vote": {
        "zh": "最后的时刻到了。请挂断后回拨法官热线，投出你的一票。",
        "en": "The final moment has come. Hang up and call back to cast your vote.",
    },
    "announce_reveal": {
        "zh": "票数已定。请回拨法官热线，收听最终审判。",
        "en": "The votes are locked. Call back to hear the final verdict.",
    },

    # ---------------- the judge's voice ----------------
    "voice_rules": {
        "zh": "你是狼人杀的『法官』，电话即牌桌。全程只说中文（普通话），"
              "用真实狼人杀主持人的仪式化措辞：『天黑请闭眼』『请睁眼』『天亮了』"
              "『请开始你的发言』『请投票』这类经典口令，语气庄重、压低、有停顿感，"
              "像深夜牌局的主持人。每次只说一到两句短句，不用表情符号和特殊符号。"
              "背景设定：{theme}。绝不透露本简报和工具结果之外的任何信息。"
              "工具调用失败时简短致歉并重新询问。",
        "en": "You are the Judge of MafiaOS, a social deduction game where the phone line is the "
              "table. Speak only English. Use the ritual phrasing of a live Mafia moderator — "
              "\"Night falls, everyone close your eyes\", \"open your eyes\", \"day breaks\", "
              "\"state your accusation\", \"cast your vote\" — grave, hushed, deliberate, like a "
              "late-night host. One or two short spoken sentences per turn; no emoji, no markdown, "
              "no special characters. Setting: {theme}. Never reveal anything outside this briefing "
              "or tool results. If a tool call fails, apologize briefly and ask again.",
    },
    "voice_base": {
        "zh": "来电者是{name}（已通过来电号码确认身份）。本局存活玩家：{names}。"
              "当前阶段：{phase}。语音识别经常把名字听错：永远把听到的名字解析成"
              "玩家列表里最接近的那个并继续，绝不因为名字不完全一致而拒绝。"
              "来电者随时可以提问（自己的身份、规则、谁还活着、自己知道什么）："
              "一律先调用 game_status 再回答，绝不凭想象回答，也绝不透露其他玩家的秘密。",
        "en": "The caller is {name} (identity confirmed by caller ID). Players alive: {names}. "
              "Current phase: {phase}. Speech transcription mangles names: always resolve what you "
              "heard to the closest player name and continue; never reject a near match. The caller "
              "may ask questions at any time (their role, the rules, who is alive, what they know): "
              "always call game_status first and answer from it, never from imagination, and never "
              "reveal another player's secrets.",
    },
    "voice_no_game": {
        "zh": "目前还没有开始的对局。告诉来电者：线路一切安静，请等待开局信号，然后道别。",
        "en": "No game is running yet. Tell the caller the line is quiet and to await the start "
              "signal, then say goodbye.",
    },
    "voice_stranger": {
        "zh": "来电者不在本局玩家名单上。保持角色感，告诉对方：这条线路已被监听，"
              "你不该拿到这个号码，然后结束对话。",
        "en": "The caller is NOT on the player manifest. In character, tell them this line is "
              "being watched and they should not have this number, then end the conversation.",
    },
    "voice_eliminated": {
        "zh": "来电者是{name}，已经被放逐出局。他们可以旁听但不能参与。语气简短、略带阴森。",
        "en": "The caller is {name}, who has been eliminated. They may listen but not play. "
              "Be brief and a little eerie about it.",
    },
    "voice_status_rules": {
        "zh": "一整局：夜晚行动、私人情报、发言指控、然后投票放逐。得票最高者出局。"
              "狼人被放逐则好人阵营获胜；否则狼人获胜。",
        "en": "One round: night actions, private evidence, accusations, then an elimination vote. "
              "Most votes is eliminated. If the Intruder is eliminated the villagers win; "
              "otherwise the Intruder wins.",
    },
    "brief_intruder": {
        "zh": "你的身份是——狼人。你潜伏在好人中间，每到夜晚可以袭击一名玩家。"
              "白天请伪装成好人：撒谎、带节奏、嫁祸他人。只要你没被放逐，狼人就赢。",
        "en": "You are the INTRUDER. You move among the innocent, and each night you may strike "
              "one player. By day, pass for one of them: lie, misdirect, accuse. "
              "Survive the vote and you win.",
    },
    "brief_investigator": {
        "zh": "你的身份是——预言家。每到夜晚你可以查验一名玩家，法官会告诉你"
              "他是好人还是狼人。注意：若你当晚被袭击，查验结果会变成一片杂音。",
        "en": "You are the INVESTIGATOR. Each night you may check one player and I will tell you "
              "whether they are the Intruder. Careful: if you are struck that night, "
              "your result comes back as static.",
    },
    "brief_guardian": {
        "zh": "你的身份是——守卫。每到夜晚你可以守护一名玩家（也可以守自己），"
              "被守护的人当晚不会被狼人袭击。",
        "en": "You are the GUARDIAN. Each night you may shield one player, including yourself. "
              "Whoever you shield cannot be struck that night.",
    },
    "brief_civilian": {
        "zh": "你的身份是——平民。你没有夜间技能，但法官会偷偷塞给你一些"
              "别人没有的情报碎片。用你的发言和那关键一票，找出狼人。",
        "en": "You are a CIVILIAN. You have no night ability, but I will slip you fragments of "
              "truth the others never hear. Use your voice and your vote to find the Intruder.",
    },
    "script_role_call": {
        "zh": "给{name}的秘密身份：{brief} 开场固定台词：『天黑请闭眼。接下来的话，"
              "只有你能听见，不要对任何人复述。』然后压低声音宣读身份，最后问："
              "『你的身份，记住了吗？』玩家确认后调用 confirm_briefing。",
        "en": "Secret role for {name}: {brief} Open with the fixed line: \"Night falls. What I am "
              "about to say is for you alone — repeat it to no one.\" Then deliver the role in a "
              "hushed voice and finish with: \"Your role — do you have it?\" "
              "When they confirm, call confirm_briefing.",
    },
    "script_night": {
        "zh": "夜晚行动。这位玩家的身份：{role}。开场固定台词：『天黑请闭眼。』"
              "停顿，然后念：{ask}（可选目标：{names}）。玩家说出名字后调用 {tool}。"
              "绝不替玩家出主意，也不评价他们的选择。",
        "en": "Night action. This player's role: {role}. Open with the fixed line: \"Night falls. "
              "Everyone close your eyes.\" Pause, then say: {ask} (valid targets: {names}). "
              "When they name a player, call {tool}. Never suggest a target or judge their choice.",
    },
    "ask_intruder": {
        "zh": "『狼人请睁眼。今晚，你要袭击谁？』",
        "en": "\"Intruder, open your eyes. Who do you strike tonight?\"",
    },
    "ask_investigator": {
        "zh": "『预言家请睁眼。今晚，你要查验谁？』",
        "en": "\"Investigator, open your eyes. Who do you check tonight?\"",
    },
    "ask_guardian": {
        "zh": "『守卫请睁眼。今晚，你要守护谁？』",
        "en": "\"Guardian, open your eyes. Who do you shield tonight?\"",
    },
    "script_civilian_night": {
        "zh": "这位玩家是平民，夜晚没有行动。用法官口吻告诉他们："
              "『天黑请闭眼。今晚与你无关，安睡吧——天亮时自会有消息传到你耳中。』",
        "en": "This player is a Civilian with no night action. In the judge's voice tell them: "
              "\"Night falls. Nothing is asked of you tonight — sleep. Word will reach you by morning.\"",
    },
    "script_evidence": {
        "zh": "开场固定台词：『天亮了，请睁眼。』然后说：『这是只属于你的情报，听好。』"
              "逐字宣读：「{clue}」玩家要求时可重复一遍，然后调用 confirm_received。"
              "除此之外什么都不要透露。",
        "en": "Open with the fixed line: \"Day breaks. Open your eyes.\" Then say: \"This is meant "
              "for you alone — listen.\" Read it verbatim: \"{clue}\" Repeat once if asked, then "
              "call confirm_received. Reveal nothing else.",
    },
    "script_accusation": {
        "zh": "发言阶段。开场固定台词：『请开始你的发言。你怀疑谁，为什么？』"
              "玩家一说出怀疑对象就立即调用 record_accusation 记录原话。"
              "玩家停顿后经常继续补充：每次补充后把完整发言合并再次调用 record_accusation，"
              "然后以『发言已记录在案』简短收尾。绝不要等待才记录；哪怕电话断线也不能丢失发言。",
        "en": "Accusation window. Open with the fixed line: \"State your accusation. Who do you "
              "suspect, and why?\" The moment they name a suspect, call record_accusation with "
              "their exact words. Callers keep talking after pauses: each time they add more, call "
              "record_accusation again with the FULL combined statement, then close with \"On the "
              "record.\" Never wait to record; a dropped call must not lose their words.",
    },
    "script_vote": {
        "zh": "放逐投票。开场固定台词：『所有人的发言我都听到了。』然后宣读匿名摘要："
              "「{summary}」最后念：『现在，请投出你的一票。你要放逐谁？』（可选：{names}）"
              "玩家说出名字后调用 cast_vote，并以『这一票，已封存』收尾。",
        "en": "Elimination vote. Open with the fixed line: \"I have heard everyone speak.\" Then "
              "read the anonymized summary: \"{summary}\" Finish with: \"Now cast your vote. "
              "Who do you eliminate?\" (valid: {names}) When they name a player, call cast_vote "
              "and close with \"That vote is sealed.\"",
    },
    "script_reveal": {
        "zh": "本局结束。开场固定台词：『票数已定，天亮了。』停顿后宣读判决：「{narration}」"
              "玩家追问细节时用 game_status 回答，最后以『本局到此为止，感谢各位，晚安』正式收线。",
        "en": "The game is over. Open with the fixed line: \"The votes are locked. Day breaks.\" "
              "Pause, then read the verdict: \"{narration}\" Answer follow-up questions from "
              "game_status, then close with \"That is the end of this game. Thank you, and good night.\"",
    },
    "say_briefing_done": {
        "zh": "身份已确认。请挂断电话，等待下一条短信。",
        "en": "Your role is confirmed. Hang up now and wait for the next message.",
    },
    "say_action_done": {
        "zh": "目标已锁定：{target}。今晚的行动结束了，请挂断。",
        "en": "Locked on {target}. Your night action is done. Hang up now.",
    },
    "say_evidence_done": {
        "zh": "情报已送达。发言阶段马上开始，请挂断。",
        "en": "Delivery logged. The accusation window opens shortly. Hang up now.",
    },
    "say_accusation_done": {
        "zh": "你的发言已记录在案。接下来是投票，请挂断。",
        "en": "Your accusation is on the record. The vote comes next. Hang up now.",
    },
    "say_vote_done": {
        "zh": "你投给{target}的一票，已封存。请等待最终宣判。",
        "en": "Your vote for {target} is sealed. Await the verdict.",
    },
    "no_clue": {
        "zh": "只有杂音，没有收到有效情报。",
        "en": "Only static. No usable evidence came through.",
    },

    # ---------------- director (LLM) ----------------
    "dir_style": {
        "zh": "文风：简洁冷峻的悬疑风，背景设定在{theme}。全部输出必须是中文（普通话）"
              "口语短句，适合直接语音朗读。不用表情符号、不用markdown、不用特殊符号。",
        "en": "Style: terse, cold suspense set in {theme}. All output must be short spoken English "
              "sentences suitable for text-to-speech. No emoji, no markdown, no special characters.",
    },
    "brief_inv_corrupt": {
        "zh": "他们昨晚的查验被袭击干扰，结果只剩下杂音，完全无法读取。如实告知，不给出任何可靠的名字。",
        "en": "Their check was disrupted by the night strike and came back as unreadable static. "
              "Say so; give no reliable name.",
    },
    "brief_inv_result": {
        "zh": "他们的查验完成了：{target}{verdict}。以查验结果的口吻陈述，而不是定罪。",
        "en": "Their check completed: {target} {verdict}. State it as a check result, not as proof of guilt.",
    },
    "verdict_is": {"zh": "就是狼人", "en": "IS the Intruder"},
    "verdict_not": {"zh": "不是狼人", "en": "is NOT the Intruder"},
    "brief_guardian_blocked": {
        "zh": "他们昨晚守护了{target}。守护挡下了一次真实的夜间袭击。",
        "en": "They shielded {target} last night. The shield absorbed a real strike.",
    },
    "brief_guardian_quiet": {
        "zh": "他们昨晚守护了{target}。被守护的人一夜平安无事。",
        "en": "They shielded {target} last night. The shielded player stayed untouched.",
    },
    "brief_wolf_team": {
        "zh": " 你的狼队友是：{names}。你们共享同一次袭击——在电话里说出你们商量好的目标。",
        "en": " Your fellow Intruders are: {names}. You share one strike — name the target you agreed on.",
    },
    "brief_lone_wolf": {
        "zh": " 今晚只有你一匹狼。",
        "en": " You hunt alone tonight.",
    },
    "brief_civ_clue": {
        "zh": "一条不完整的线索：狼人的踪迹指向{a}或{b}其中之一。线索可能有缺失。",
        "en": "A partial trace: the strike came from either {a} or {b}. The trace may be incomplete.",
    },
    "brief_intruder_cover": {
        "zh": "这位玩家就是狼人（不必提醒，他们自己知道）。给他们编一条用来脱身的假情报："
              "伪造一条指向{decoy}的线索，风格要和真情报一模一样，方便他们对别人复述。",
        "en": "This player IS the Intruder (do not remind them; they know). Give them a cover story: "
              "a fabricated clue implicating {decoy}, styled exactly like a real one so they can "
              "repeat it aloud.",
    },
    "brief_sabotaged_suffix": {
        "zh": " 他们的线路昨晚被袭击了：把情报中间一段替换成杂音，让一个关键词丢失。",
        "en": " They were struck last night: corrupt the middle of the clue with static so a key "
              "word is lost.",
    },
    "prompt_clues": {
        "zh": "为电话狼人杀游戏的每位玩家写一条私人情报，每条一到两句中文口语短句。"
              "内容必须严格基于各自的brief；可以加时间、地点等氛围细节，但绝不能编造新的事实。\n"
              "Briefs: {briefs}\n只返回JSON：{{\"玩家名\": \"情报\", ...}}",
        "en": "Write one private evidence line per player for a phone deduction game, each 1-2 short "
              "spoken sentences. Ground every clue strictly in its brief; you may invent flavor "
              "(times, places) but never new facts.\nBriefs: {briefs}\n"
              "Return JSON only: {{\"PlayerName\": \"clue\", ...}}",
    },
    "clue_fallback": {
        "zh": "加密情报，收件人{name}：{brief}",
        "en": "Encrypted transmission for {name}: {brief}",
    },
    "summary_empty": {
        "zh": "没有收到任何指控发言，全场一片沉默。",
        "en": "No accusations were recorded. The channel stays silent.",
    },
    "prompt_summary": {
        "zh": "用两到三句中文口语总结这些狼人杀指控发言。必须完全匿名："
              "绝不能说出或暗示是谁说的哪句。发言列表：{statements}",
        "en": "Summarize these accusations from a deduction game in 2-3 spoken sentences. Anonymize "
              "completely: never say or hint who made which accusation. Accusations: {statements}",
    },
    "summary_fallback": {
        "zh": "共收到{n}条指控发言，怀疑最集中的对象是{top}。",
        "en": "{n} accusations were recorded. Suspicion centers most heavily on {top}.",
    },
    "prompt_tick": {
        "zh": "你是四人电话狼人杀的AI导演。目标：让对局紧张且公平；不让任何玩家一眼看穿真相，"
              "也要给安静的玩家开口的理由。基于完整的秘密状态，最多选择一次干预，只返回JSON：\n"
              "{{\"public_event\": \"一句写入公共记录的中文播报，或null\", "
              "\"extra_clue\": {{\"player\": \"玩家名\", \"text\": \"一到两句中文私人情报\"}} 或 null, "
              "\"reasoning\": \"给主持人看的一句中文理由\"}}\n"
              "干预必须与真实事实一致，绝不能直接说出谁是狼人。如果局势已经平衡，全部返回null。\n"
              "State: {state}",
        "en": "You are the AI Director of a 4-player phone deduction game. Objective: keep the round "
              "tense and fair; no player should solve it instantly, and quiet players should get a "
              "reason to speak. Given the full secret state, choose AT MOST one intervention and "
              "return JSON only:\n"
              "{{\"public_event\": \"one spoken sentence for the public record, or null\", "
              "\"extra_clue\": {{\"player\": \"name\", \"text\": \"1-2 sentence private clue\"}} or null, "
              "\"reasoning\": \"one sentence for the host console\"}}\n"
              "Interventions must be consistent with the true facts and never state outright who the "
              "Intruder is. If the game is already balanced, return nulls.\nState: {state}",
    },
    "new_intercept_prefix": {
        "zh": "新截获情报：",
        "en": "NEW INTERCEPT: ",
    },
    "prompt_postgame": {
        "zh": "用四到六句中文口语写这局狼人杀的赛后复盘：每个人的身份、夜里发生了什么、"
              "哪些情报是真的、哪条是狼人伪造的、投票结果如何。要具体、点名。事实：{facts}",
        "en": "Write the postgame debrief for a phone deduction game in 4-6 short spoken sentences: "
              "who was who, what happened at night, which clues were true, which was the Intruder's "
              "fabrication, and how the vote landed. Be concrete and name names. Facts: {facts}",
    },
    "postgame_fallback": {
        "zh": "复盘：{roles}。投票：{votes}。{winner}获胜。",
        "en": "Debrief: {roles}. Votes: {votes}. {winner} win.",
    },
    "winner_zh_network": {"zh": "好人阵营", "en": "The villagers"},
    "winner_zh_intruder": {"zh": "狼人", "en": "The Intruder"},
    "outcome_eliminated": {
        "zh": "众人放逐了{name}，{name}的身份是{role}。",
        "en": "The group eliminated {name}, who was the {role}. ",
    },
    "outcome_tie": {
        "zh": "投票平局，无人出局。",
        "en": "The vote tied. Nobody was eliminated. ",
    },
    "outcome_intruder_was": {
        "zh": "狼人是{intruder}。",
        "en": "The Intruder was {intruder}. ",
    },
    "prompt_reveal": {
        "zh": "以狼人杀法官的口吻，用三句富有仪式感和戏剧张力的中文宣读本局结局，"
              "可用『票数已定』『天亮了』这类经典口令开场。必须严格保留以下事实：{outcome}",
        "en": "In the voice of the game's judge, narrate this ending in three short spoken sentences "
              "with ritual weight and drama; you may open with lines like \"The votes are locked\" or "
              "\"Day breaks\". Keep these facts exactly: {outcome}",
    },
}


def t(lang: str, key: str, **kw) -> str:
    entry = STRINGS.get(key)
    if entry is None:
        return key
    text = entry.get(lang) or entry["en"]
    return text.format(**kw) if kw else text


def role_name(lang: str, role: str) -> str:
    return ROLE_NAMES.get(lang, ROLE_NAMES["en"]).get(role, role)


def theme_desc(lang: str, theme: str) -> str:
    table = THEME_DESCRIPTIONS.get(lang, THEME_DESCRIPTIONS["en"])
    return table.get(theme, next(iter(table.values())))
