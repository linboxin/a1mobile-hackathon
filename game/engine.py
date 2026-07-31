"""MafiaOS — game engine.

Pure state machine: no network, no LLM, no audio. The phone/LLM layers call
into this and render whatever it returns.

Demo cut: exactly 4 players, one round.
  Roles: intruder, investigator, guardian, civilian.
  Phases: lobby -> role_calls -> actions -> evidence -> accusations -> vote -> reveal
"""

from __future__ import annotations

import difflib
import json
import random
import secrets
import time
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path

STATE_FILE = Path(__file__).parent.parent / "game_state.json"

ROLES = ["intruder", "investigator", "guardian", "civilian"]


class Phase(StrEnum):
    LOBBY = "lobby"
    ROLE_CALLS = "role_calls"
    ACTIONS = "actions"
    EVIDENCE = "evidence"
    ACCUSATIONS = "accusations"
    VOTE = "vote"
    REVEAL = "reveal"


PHASE_ORDER = list(Phase)

# Which players owe an input in each phase (by role). None = everyone alive.
PHASE_INPUTS: dict[Phase, list[str] | None] = {
    Phase.ROLE_CALLS: None,
    Phase.ACTIONS: ["intruder", "investigator", "guardian"],  # civilian has no night action
    Phase.EVIDENCE: None,
    Phase.ACCUSATIONS: None,
    Phase.VOTE: None,
}


@dataclass
class Player:
    name: str
    phone: str
    role: str = ""
    alive: bool = True


THEMES = {
    "moonlit-village": "月夜下的古老村庄；狼嚎、烛火、木门吱呀作响，经典狼人杀氛围",
    "signal-station": "冷战时期被渗透的信号站；电波杂音、终端机、截获的密电",
    "haunted-hotel": "大雪封山的闹鬼旅馆；劈啪作响的电话线、房间号、走廊里的脚步声",
    "spaceship": "正在漏气的深空飞船；通讯舱、气闸、船体传感器的警报",
    "spy-agency": "暴露的间谍网络；死信箱、代号、被出卖的安全屋",
}


@dataclass
class Game:
    code: str = ""
    theme: str = "moonlit-village"
    phase: Phase = Phase.LOBBY
    players: list[Player] = field(default_factory=list)
    # phase inputs, keyed by player name
    done: dict[str, list[str]] = field(default_factory=dict)  # phase -> names done
    actions: dict[str, str] = field(default_factory=dict)  # role -> target name
    clues: dict[str, str] = field(default_factory=dict)  # name -> private clue text
    accusations: dict[str, str] = field(default_factory=dict)  # name -> statement
    votes: dict[str, str] = field(default_factory=dict)  # name -> target name
    eliminated: str | None = None
    winner: str | None = None  # "network" | "intruder"
    phase_started: float = 0.0
    vote_summary: str = ""
    narration: str = ""
    postgame: str = ""
    director_notes: list[str] = field(default_factory=list)
    public_log: list[str] = field(default_factory=list)

    # ---------- setup ----------

    @staticmethod
    def create(entries: list[tuple[str, str]], theme: str = "moonlit-village") -> "Game":
        if len(entries) != 4:
            raise ValueError("MafiaOS demo needs exactly 4 players")
        names = [n.strip() for n, _ in entries]
        if len({n.lower() for n in names}) != 4:
            raise ValueError("player names must be unique")
        if theme not in THEMES:
            raise ValueError(f"theme must be one of: {', '.join(THEMES)}")
        game = Game(code=secrets.token_hex(3), theme=theme)
        game.players = [Player(name=n.strip(), phone=p.strip()) for n, p in entries]
        game.log("信道已建立，四名玩家全部接入。等待开局。")
        game.save()
        return game

    def start(self) -> None:
        self.require_phase(Phase.LOBBY)
        roles = ROLES[:]
        random.shuffle(roles)
        for player, role in zip(self.players, roles):
            player.role = role
        self.phase = Phase.ROLE_CALLS
        self.phase_started = time.time()
        self.log("检测到狼人混入。身份已分发——所有玩家请立即回拨法官热线领取身份。")
        self.save()

    # ---------- lookups ----------

    def player_by_phone(self, phone: str) -> Player | None:
        tail = phone[-10:]
        return next((p for p in self.players if p.phone[-10:] == tail), None)

    def player_by_name(self, name: str) -> Player | None:
        needle = name.strip().lower()
        exact = next((p for p in self.players if p.name.lower() == needle), None)
        if exact:
            return exact
        # Phone STT mangles names ("Ria" for "Rhea"); resolve near-matches.
        close = difflib.get_close_matches(
            needle, [p.name.lower() for p in self.players], n=1, cutoff=0.6)
        return self.player_by_name(close[0]) if close else None

    def by_role(self, role: str) -> Player:
        return next(p for p in self.players if p.role == role)

    def alive_names(self) -> list[str]:
        return [p.name for p in self.players if p.alive]

    # ---------- phase mechanics ----------

    def require_phase(self, *phases: Phase) -> None:
        if self.phase not in phases:
            raise ValueError(f"not allowed in phase {self.phase}")

    def expected_names(self) -> list[str]:
        spec = PHASE_INPUTS.get(self.phase)
        if spec is None:
            return self.alive_names()
        return [self.by_role(r).name for r in spec if self.by_role(r).alive]

    def done_names(self) -> list[str]:
        return self.done.get(self.phase.value, [])

    DONE_WORDING = {
        "role_calls": "{name} 已确认身份，挂断了电话。",
        "actions": "{name} 完成了夜间行动。",
        "evidence": "{name} 收到了自己的情报。",
        "accusations": "{name} 的发言已记录在案。",
        "vote": "{name} 投出了一票。",
    }

    def mark_done(self, name: str) -> None:
        names = self.done.setdefault(self.phase.value, [])
        if name not in names:
            names.append(name)
            wording = self.DONE_WORDING.get(self.phase.value)
            if wording:
                self.log(wording.format(name=name))
        self.save()

    def phase_complete(self) -> bool:
        return set(self.expected_names()) <= set(self.done_names())

    def advance(self) -> Phase:
        """Move to the next phase. Returns the new phase."""
        index = PHASE_ORDER.index(self.phase)
        if self.phase == Phase.REVEAL:
            return self.phase
        self.phase = PHASE_ORDER[index + 1]
        self.phase_started = time.time()
        if self.phase == Phase.VOTE and not self.accusations:
            self.log("没有收到任何指控发言。")
        if self.phase == Phase.REVEAL:
            self.resolve_vote()
        self.save()
        return self.phase

    # ---------- inputs from calls ----------

    def record_action(self, actor: Player, target_name: str) -> str:
        self.require_phase(Phase.ACTIONS)
        target = self.player_by_name(target_name)
        if target is None:
            raise ValueError(f"no player called {target_name}")
        if actor.role == "civilian":
            raise ValueError("the civilian has no night action")
        if actor.role != "intruder" and target.name == actor.name:
            pass  # protecting/investigating yourself is allowed
        self.actions[actor.role] = target.name
        self.mark_done(actor.name)
        return target.name

    def record_accusation(self, actor: Player, statement: str) -> None:
        self.require_phase(Phase.ACCUSATIONS)
        self.accusations[actor.name] = statement.strip()[:400]
        self.mark_done(actor.name)

    def record_vote(self, actor: Player, target_name: str) -> str:
        self.require_phase(Phase.VOTE)
        target = self.player_by_name(target_name)
        if target is None or not target.alive:
            raise ValueError(f"cannot vote for {target_name}")
        self.votes[actor.name] = target.name
        self.mark_done(actor.name)
        return target.name

    # ---------- resolution ----------

    def resolve_actions(self) -> dict[str, str]:
        """Called entering EVIDENCE. Returns facts for the director."""
        sabotaged = self.actions.get("intruder")
        protected = self.actions.get("guardian")
        investigated = self.actions.get("investigator")
        blocked = sabotaged is not None and sabotaged == protected
        facts = {
            "sabotaged": sabotaged or "nobody",
            "protected": protected or "nobody",
            "investigated": investigated or "nobody",
            "sabotage_blocked": str(blocked),
            "intruder": self.by_role("intruder").name,
            "investigator": self.by_role("investigator").name,
            "investigator_sabotaged": str(sabotaged == self.by_role("investigator").name and not blocked),
        }
        self.log(
            f"夜晚行动已结算，收到秘密行动 "
            f"{len(self.done.get(Phase.ACTIONS.value, []))}/3。"
        )
        return facts

    def resolve_vote(self) -> None:
        tally: dict[str, int] = {}
        for target in self.votes.values():
            tally[target] = tally.get(target, 0) + 1
        if not tally:
            self.winner = "intruder"
            self.log("无人投票。狼人仍潜伏在村庄之中。")
            return
        top = sorted(tally.items(), key=lambda kv: -kv[1])
        if len(top) > 1 and top[0][1] == top[1][1]:
            self.eliminated = None
            self.winner = "intruder"
            self.log(f"投票平局（{dict(tally)}），无人出局。狼人逃过一劫。")
            return
        name = top[0][0]
        player = self.player_by_name(name)
        player.alive = False
        self.eliminated = name
        intruder = self.by_role("intruder").name
        self.winner = "network" if name == intruder else "intruder"
        role_zh = {"intruder": "狼人", "investigator": "预言家",
                   "guardian": "守卫", "civilian": "平民"}.get(player.role, player.role)
        self.log(f"众人投票放逐了{name}。{name}的身份是：{role_zh}。")
        self.log(
            "狼人已被清除，好人阵营获胜。" if self.winner == "network"
            else f"狼人（{intruder}）活了下来，狼人获胜。"
        )

    # ---------- public view (dashboard-safe: no secrets) ----------

    def suspicion(self) -> dict[str, int]:
        counts = {p.name: 0 for p in self.players}
        for statement in self.accusations.values():
            for p in self.players:
                if p.name.lower() in statement.lower():
                    counts[p.name] += 1
        for target in self.votes.values():
            counts[target] = counts.get(target, 0) + 1
        return counts

    def public_state(self) -> dict:
        return {
            "code": self.code,
            "theme": self.theme,
            "phase": self.phase.value,
            "players": [{"name": p.name, "alive": p.alive} for p in self.players],
            "waiting_on": sorted(set(self.expected_names()) - set(self.done_names()))
            if self.phase in PHASE_INPUTS else [],
            "received": f"{len(self.done_names())}/{len(self.expected_names())}"
            if self.phase in PHASE_INPUTS else "",
            "suspicion": self.suspicion(),
            "log": self.public_log[-14:],
            "phase_started": self.phase_started,
            "done_names": self.done_names(),
            "winner": self.winner,
            "narration": self.narration if self.phase == Phase.REVEAL else "",
            "postgame": self.postgame if self.phase == Phase.REVEAL else "",
        }

    def director_state(self) -> dict:
        """FULL secret state. Only ever serve behind the host token."""
        return {
            **self.public_state(),
            "players_full": [vars(p) for p in self.players],
            "actions": self.actions,
            "clues": self.clues,
            "accusations": self.accusations,
            "votes": self.votes,
            "director_notes": self.director_notes,
        }

    # ---------- misc ----------

    def log(self, line: str) -> None:
        from datetime import datetime
        self.public_log.append(f"{datetime.now().strftime('%H:%M:%S')} {line}")

    def save(self) -> None:
        data = {
            "code": self.code, "theme": self.theme, "phase": self.phase.value,
            "players": [vars(p) for p in self.players],
            "done": self.done, "actions": self.actions, "clues": self.clues,
            "accusations": self.accusations, "votes": self.votes,
            "eliminated": self.eliminated, "winner": self.winner,
            "phase_started": self.phase_started,
            "vote_summary": self.vote_summary,
            "narration": self.narration, "postgame": self.postgame,
            "director_notes": self.director_notes, "public_log": self.public_log,
        }
        STATE_FILE.write_text(json.dumps(data, indent=1))

    @staticmethod
    def load() -> "Game | None":
        if not STATE_FILE.exists():
            return None
        data = json.loads(STATE_FILE.read_text())
        game = Game(code=data["code"], theme=data.get("theme", "signal-station"),
                    phase=Phase(data["phase"]))
        game.players = [Player(**p) for p in data["players"]]
        game.done = data["done"]
        game.actions = data["actions"]
        game.clues = data["clues"]
        game.accusations = data["accusations"]
        game.votes = data["votes"]
        game.eliminated = data["eliminated"]
        game.winner = data["winner"]
        game.phase_started = data.get("phase_started", 0.0)
        game.vote_summary = data.get("vote_summary", "")
        game.narration = data["narration"]
        game.postgame = data.get("postgame", "")
        game.director_notes = data.get("director_notes", [])
        game.public_log = data["public_log"]
        return game
