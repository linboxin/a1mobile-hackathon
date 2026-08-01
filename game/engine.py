"""MafiaOS — game engine.

Pure state machine: no network, no LLM, no audio. The phone/LLM layers call
into this and render whatever it returns.

4-12 players (wolves scale ~1 per 3), one round.
  Roles: intruder, investigator, guardian, civilian.
  Phases: lobby -> role_calls -> actions -> evidence -> accusations -> vote -> reveal
"""

from __future__ import annotations

import difflib
import json
import re
import random
import secrets
import time
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path

from . import i18n

STATE_FILE = Path(__file__).parent.parent / "game_state.json"

ROLES = ["intruder", "investigator", "guardian", "civilian"]

MIN_PLAYERS, MAX_PLAYERS = 4, 12


def normalize_phone(raw: str) -> str:
    """Accept whatever the host typed and store E.164.

    People type "555 010 0002", "(555) 010-0002" or drop the +; every one of
    those used to silently break bot detection and the outbound ringer.
    """
    digits = re.sub(r"\D", "", raw or "")
    if len(digits) == 10:
        digits = "1" + digits
    return f"+{digits}" if digits else ""


def is_bot_phone(phone: str) -> bool:
    """Fictional 555-01xx seats: auto-played by scripts/bot_players.py and
    never dialled by the outbound ringer."""
    return re.sub(r"\D", "", phone or "").startswith("1555")


def composition(n: int) -> list[str]:
    """Standard-ish 狼人杀 ratio: about one wolf per three players, one
    Investigator, one Guardian, the rest Civilians."""
    wolves = max(1, n // 3)
    roles = ["intruder"] * wolves + ["investigator", "guardian"]
    return roles + ["civilian"] * (n - len(roles))


class Phase(StrEnum):
    LOBBY = "lobby"
    ROLE_CALLS = "role_calls"
    ACTIONS = "actions"
    EVIDENCE = "evidence"
    DISCUSSION = "discussion"
    ACCUSATIONS = "accusations"
    VOTE = "vote"
    REVEAL = "reveal"


PHASE_ORDER = list(Phase)

# Which players owe an input in each phase (by role). None = everyone alive.
PHASE_INPUTS: dict[Phase, list[str] | None] = {
    Phase.ROLE_CALLS: None,
    Phase.ACTIONS: ["intruder", "investigator", "guardian"],  # civilian has no night action
    Phase.EVIDENCE: None,
    # DISCUSSION is the open party line: no per-player input, it ends on a
    # timer or when the host advances.
    Phase.ACCUSATIONS: None,
    Phase.VOTE: None,
}


@dataclass
class Player:
    name: str
    phone: str
    role: str = ""
    alive: bool = True


THEMES = tuple(i18n.THEME_DESCRIPTIONS["en"].keys())


@dataclass
class Game:
    code: str = ""
    theme: str = "moonlit-village"
    lang: str = "zh"
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
    transcript: list[dict] = field(default_factory=list)
    public_log: list[str] = field(default_factory=list)

    # ---------- setup ----------

    @staticmethod
    def create(entries: list[tuple[str, str]], theme: str = "moonlit-village",
               lang: str = "zh") -> "Game":
        if not MIN_PLAYERS <= len(entries) <= MAX_PLAYERS:
            raise ValueError(f"MafiaOS needs {MIN_PLAYERS}-{MAX_PLAYERS} players")
        names = [n.strip() for n, _ in entries]
        if len({n.lower() for n in names}) != len(entries):
            raise ValueError("player names must be unique")
        if theme not in THEMES:
            raise ValueError(f"theme must be one of: {', '.join(THEMES)}")
        if lang not in i18n.LANGS:
            raise ValueError(f"lang must be one of: {', '.join(i18n.LANGS)}")
        game = Game(code=secrets.token_hex(3), theme=theme, lang=lang)
        game.players = [Player(name=n.strip(), phone=normalize_phone(p))
                        for n, p in entries]
        game.log(game.t("log_room_open"))
        game.save()
        return game

    def start(self) -> None:
        self.require_phase(Phase.LOBBY)
        roles = composition(len(self.players))
        random.shuffle(roles)
        for player, role in zip(self.players, roles):
            player.role = role
        self.phase = Phase.ROLE_CALLS
        self.phase_started = time.time()
        self.log(self.t("log_game_start"))
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

    def all_by_role(self, role: str) -> list[Player]:
        return [p for p in self.players if p.role == role]

    def intruder_names(self) -> list[str]:
        return [p.name for p in self.players if p.role == "intruder"]

    def composition_summary(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for p in self.players:
            if p.role:
                counts[p.role] = counts.get(p.role, 0) + 1
        return counts

    def alive_names(self) -> list[str]:
        return [p.name for p in self.players if p.alive]

    # ---------- phase mechanics ----------

    def require_phase(self, *phases: Phase) -> None:
        if self.phase not in phases:
            raise ValueError(f"not allowed in phase {self.phase}")

    def expected_names(self) -> list[str]:
        if self.phase not in PHASE_INPUTS:
            return []
        spec = PHASE_INPUTS[self.phase]
        if spec is None:
            return self.alive_names()
        return [p.name for r in spec for p in self.all_by_role(r) if p.alive]

    def done_names(self) -> list[str]:
        return self.done.get(self.phase.value, [])

    def mark_done(self, name: str) -> None:
        names = self.done.setdefault(self.phase.value, [])
        if name not in names:
            names.append(name)
            key = f"done_{self.phase.value}"
            if key in i18n.STRINGS:
                self.log(self.t(key, name=name))
        self.save()

    def phase_complete(self) -> bool:
        if self.phase not in PHASE_INPUTS:
            return False          # host- or timer-driven phases only
        return set(self.expected_names()) <= set(self.done_names())

    def advance(self) -> Phase:
        """Move to the next phase. Returns the new phase."""
        index = PHASE_ORDER.index(self.phase)
        if self.phase == Phase.REVEAL:
            return self.phase
        self.phase = PHASE_ORDER[index + 1]
        self.phase_started = time.time()
        if self.phase == Phase.VOTE and not self.accusations:
            self.log(self.t("log_no_accusations"))
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
            "intruder": self.intruder_names()[0],
            "intruders": ",".join(self.intruder_names()),
            "investigator": self.by_role("investigator").name,
            "investigator_sabotaged": str(
                any(sabotaged == p.name for p in self.all_by_role("investigator")) and not blocked),
        }
        self.log(self.t("log_night_resolved",
                        n=len(self.done.get(Phase.ACTIONS.value, []))))
        return facts

    def resolve_vote(self) -> None:
        tally: dict[str, int] = {}
        for target in self.votes.values():
            tally[target] = tally.get(target, 0) + 1
        if not tally:
            self.winner = "intruder"
            self.log(self.t("log_no_votes"))
            return
        top = sorted(tally.items(), key=lambda kv: -kv[1])
        if len(top) > 1 and top[0][1] == top[1][1]:
            self.eliminated = None
            self.winner = "intruder"
            self.log(self.t("log_tie", tally=dict(tally)))
            return
        name = top[0][0]
        player = self.player_by_name(name)
        player.alive = False
        self.eliminated = name
        wolves = self.intruder_names()
        intruder = "、".join(wolves) if self.lang == "zh" else ", ".join(wolves)
        self.winner = "network" if player.role == "intruder" else "intruder"
        self.log(self.t("log_eliminated", name=name, role=self.role_name(player.role)))
        self.log(self.t("log_win_network") if self.winner == "network"
                 else self.t("log_win_intruder", intruder=intruder))

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
            "lang": self.lang,
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
            "composition": self.composition_summary(),
            "winner": self.winner,
            "narration": self.narration if self.phase == Phase.REVEAL else "",
            "postgame": self.postgame if self.phase == Phase.REVEAL else "",
            # Verbatim speech stays private during play — the board is projected.
            # At the reveal, the accusations become part of the debrief.
            "accusations": (
                [{"name": n, "text": s} for n, s in self.accusations.items()]
                if self.phase == Phase.REVEAL else []
            ),
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
            "transcript": self.transcript[-60:],
            "bots": [p.name for p in self.players if is_bot_phone(p.phone)],
        }

    # ---------- misc ----------

    def t(self, key: str, **kw) -> str:
        return i18n.t(self.lang, key, **kw)

    def role_name(self, role: str) -> str:
        return i18n.role_name(self.lang, role)

    def add_line(self, name: str, speaker: str, text: str) -> None:
        """Record one utterance. Consecutive lines from the same speaker on the
        same call are merged so the transcript reads as turns, not fragments."""
        now = time.time()
        last = self.transcript[-1] if self.transcript else None
        if (last and last["name"] == name and last["speaker"] == speaker
                and now - last["at"] < 12):
            last["text"] = f"{last['text']} {text}".strip()
            last["at"] = now
        else:
            self.transcript.append({
                "at": now, "phase": self.phase.value, "name": name,
                "speaker": speaker, "text": text,
            })
            del self.transcript[:-400]
        self.save()

    def log(self, line: str) -> None:
        from datetime import datetime
        self.public_log.append(f"{datetime.now().strftime('%H:%M:%S')} {line}")

    def save(self) -> None:
        data = {
            "code": self.code, "theme": self.theme, "lang": self.lang,
            "phase": self.phase.value,
            "players": [vars(p) for p in self.players],
            "done": self.done, "actions": self.actions, "clues": self.clues,
            "accusations": self.accusations, "votes": self.votes,
            "eliminated": self.eliminated, "winner": self.winner,
            "phase_started": self.phase_started,
            "vote_summary": self.vote_summary,
            "narration": self.narration, "postgame": self.postgame,
            "director_notes": self.director_notes, "transcript": self.transcript,
            "public_log": self.public_log,
        }
        STATE_FILE.write_text(json.dumps(data, indent=1))

    @staticmethod
    def load() -> "Game | None":
        if not STATE_FILE.exists():
            return None
        data = json.loads(STATE_FILE.read_text())
        game = Game(code=data["code"], theme=data.get("theme", "moonlit-village"),
                    lang=data.get("lang", "zh"), phase=Phase(data["phase"]))
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
        game.transcript = data.get("transcript", [])
        game.public_log = data["public_log"]
        return game
