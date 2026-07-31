"""Localization guards — run with: .venv/bin/python tests/test_i18n.py

These exist because a duplicate key ("brief_civilian" was used for both the
Civilian's ROLE briefing and the director's civilian CLUE brief) silently
overwrote the role briefing, and a player was told their clue instead of their
role. Python dicts dedupe silently, so the source itself must be checked.
"""

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from game import i18n
from game.engine import ROLES, THEMES


def test_no_duplicate_keys_in_source():
    source = (Path(__file__).parent.parent / "game" / "i18n.py").read_text()
    body = source.split("STRINGS: dict[str, dict[str, str]] = {", 1)[1]
    keys = re.findall(r'^    "([a-z_0-9]+)": \{', body, flags=re.M)
    duplicates = {k for k in keys if keys.count(k) > 1}
    assert not duplicates, f"duplicate STRINGS keys silently overwrite: {duplicates}"


def test_every_string_has_both_languages():
    missing = [k for k, v in i18n.STRINGS.items()
               if not v.get("zh") or not v.get("en")]
    assert not missing, f"strings missing a language: {missing}"


def test_no_unfilled_placeholders_in_static_strings():
    """Keys used without kwargs must not contain format placeholders."""
    static = ["voice_no_game", "voice_stranger", "summary_empty", "no_clue",
              "voice_status_rules", "script_accusation", "script_civilian_night",
              "log_win_network", "log_room_open", "log_game_start"]
    for key in static:
        for lang in i18n.LANGS:
            text = i18n.t(lang, key)
            assert "{" not in text, f"{lang}/{key} has an unfilled placeholder"


def test_role_briefings_are_distinct_and_self_describing():
    for lang in i18n.LANGS:
        briefs = {role: i18n.t(lang, f"brief_{role}") for role in ROLES}
        assert len(set(briefs.values())) == len(ROLES), f"{lang}: role briefings collide"
        for role, text in briefs.items():
            name = i18n.role_name(lang, role)
            assert name.lower() in text.lower(), \
                f"{lang}/{role}: briefing does not name the role ({text[:40]})"


def test_every_theme_and_role_translated():
    for lang in i18n.LANGS:
        for theme in THEMES:
            assert i18n.theme_desc(lang, theme), f"{lang}: theme {theme} untranslated"
        for role in ROLES:
            assert i18n.role_name(lang, role) != role or lang == "en", \
                f"{lang}: role {role} untranslated"


def test_phase_keyed_strings_exist_for_every_phase():
    from game.engine import Phase
    for phase in Phase:
        if phase in (Phase.LOBBY,):
            continue
        assert f"sms_{phase.value}" in i18n.STRINGS, f"missing SMS for {phase.value}"
        assert f"announce_{phase.value}" in i18n.STRINGS, f"missing announcement for {phase.value}"


if __name__ == "__main__":
    tests = [f for name, f in sorted(globals().items()) if name.startswith("test_")]
    for test in tests:
        test()
        print(f"ok  {test.__name__}")
    print(f"\n{len(tests)} i18n tests passed")
