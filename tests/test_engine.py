"""Engine unit tests — run with: .venv/bin/python tests/test_engine.py"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from game import engine
from game.engine import Game, Phase

engine.STATE_FILE = Path("/tmp/dead-air-test-state.json")

PLAYERS = [("Nova", "+15550100001"), ("Kit", "+15550100002"),
           ("Rhea", "+15550100003"), ("Jude", "+15550100004")]


def fresh_started_game() -> Game:
    game = Game.create(PLAYERS)
    game.start()
    return game


def test_setup_and_roles():
    game = fresh_started_game()
    assert game.phase == Phase.ROLE_CALLS
    assert sorted(p.role for p in game.players) == ["civilian", "guardian", "intruder", "investigator"]
    assert game.player_by_phone("+15550100002").name == "Kit"
    assert game.player_by_phone("5550100002").name == "Kit"  # tail match
    assert game.player_by_phone("+19999999999") is None


def test_full_round_network_wins():
    game = fresh_started_game()
    for p in game.players:
        game.mark_done(p.name)
    assert game.phase_complete()
    game.advance()
    assert game.phase == Phase.ACTIONS

    intruder = game.by_role("intruder")
    investigator = game.by_role("investigator")
    guardian = game.by_role("guardian")
    civilian = game.by_role("civilian")

    game.record_action(intruder, investigator.name)  # sabotage the investigator
    game.record_action(investigator, intruder.name)  # investigator traces the intruder
    game.record_action(guardian, investigator.name)  # guardian shields the investigator
    try:
        game.record_action(civilian, intruder.name)
        raise AssertionError("civilian must have no action")
    except ValueError:
        pass
    assert game.phase_complete()
    game.advance()
    assert game.phase == Phase.EVIDENCE

    facts = game.resolve_actions()
    assert facts["sabotage_blocked"] == "True"      # operator shielded the target
    assert facts["investigator_sabotaged"] == "False"
    assert facts["intruder"] == intruder.name

    for p in game.players:
        game.mark_done(p.name)
    game.advance()
    assert game.phase == Phase.DISCUSSION      # open party line, host/timer driven
    assert game.expected_names() == []         # nobody owes an input
    assert not game.phase_complete()           # never auto-advances
    game.advance()
    assert game.phase == Phase.ACCUSATIONS

    for p in game.players:
        game.record_accusation(p, f"I think {intruder.name} is lying.")
    game.advance()
    assert game.phase == Phase.VOTE

    suspicion = game.suspicion()
    assert suspicion[intruder.name] == 4

    for p in game.players:
        game.record_vote(p, intruder.name)
    game.advance()
    assert game.phase == Phase.REVEAL
    assert game.eliminated == intruder.name
    assert game.winner == "network"
    assert not game.player_by_name(intruder.name).alive


def test_tie_vote_means_intruder_survives():
    game = fresh_started_game()
    game.phase = Phase.VOTE
    a, b, c, d = game.players
    game.record_vote(a, b.name)
    game.record_vote(b, a.name)
    game.record_vote(c, a.name)
    game.record_vote(d, b.name)
    game.advance()
    assert game.phase == Phase.REVEAL
    assert game.eliminated is None
    assert game.winner == "intruder"


def test_wrong_elimination_means_intruder_wins():
    game = fresh_started_game()
    game.phase = Phase.VOTE
    intruder = game.by_role("intruder")
    victim = next(p for p in game.players if p.role != "intruder")
    for p in game.players:
        game.record_vote(p, victim.name)
    game.advance()
    assert game.winner == "intruder"
    assert game.eliminated == victim.name


def test_persistence_roundtrip():
    game = fresh_started_game()
    game.record_accusation
    game.save()
    loaded = Game.load()
    assert loaded.code == game.code
    assert [p.name for p in loaded.players] == [p.name for p in game.players]
    assert loaded.phase == game.phase


def test_validation():
    try:
        Game.create(PLAYERS[:3])
        raise AssertionError("must require 4 players")
    except ValueError:
        pass
    game = fresh_started_game()
    game.phase = Phase.VOTE
    try:
        game.record_vote(game.players[0], "Nobody")
        raise AssertionError("must reject unknown vote target")
    except ValueError:
        pass




def test_standard_compositions():
    from game.engine import composition
    assert composition(4).count("intruder") == 1
    assert composition(6).count("intruder") == 2      # standard-ish ratio
    assert composition(9).count("intruder") == 3
    assert composition(12).count("intruder") == 4
    for n in range(4, 13):
        c = composition(n)
        assert len(c) == n
        assert c.count("investigator") == 1 and c.count("guardian") == 1
        assert c.count("intruder") < n - c.count("intruder"), "wolves must be a minority"


def test_six_player_game_with_two_wolves():
    six = [(f"P{i}", f"+1555010000{i}") for i in range(1, 7)]
    game = Game.create(six)
    game.start()
    wolves = game.intruder_names()
    assert len(wolves) == 2
    # every wolf plus the investigator and guardian owe a night action
    game.phase = Phase.ACTIONS
    assert sorted(game.expected_names()) == sorted(
        wolves + [game.by_role("investigator").name, game.by_role("guardian").name])
    # wolves share one strike: the last caller confirms the pack's target
    victim = next(p for p in game.players if p.role == "civilian")
    for wolf in game.all_by_role("intruder"):
        game.record_action(wolf, victim.name)
    assert game.actions["intruder"] == victim.name
    # eliminating either wolf wins the round for the villagers
    game.phase = Phase.VOTE
    for p in game.players:
        game.record_vote(p, wolves[0])
    game.advance()
    assert game.winner == "network"


def test_player_count_bounds():
    for bad in (3, 13):
        try:
            Game.create([(f"P{i}", f"+1555010{i:04d}") for i in range(bad)])
            raise AssertionError(f"{bad} players must be rejected")
        except ValueError:
            pass


if __name__ == "__main__":
    tests = [f for name, f in sorted(globals().items()) if name.startswith("test_")]
    for test in tests:
        test()
        print(f"ok  {test.__name__}")
    print(f"\n{len(tests)} engine tests passed")
