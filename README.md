# MafiaOS

*A phone-native social deduction game run by an autonomous AI game master.*
*A1 Mobile hackathon — "Close the Loop"*

Players do not download an app. **A phone call is the interface.** An AI
operator ("HQ") privately briefs each player's secret role, collects night
actions, generates asymmetric evidence, records accusations, runs the vote,
and narrates the ending — while an **AI Director** above the rules engine
watches the round and intervenes to keep it tense and fair.

```text
SMS: "MAFIAOS // Call HQ NOW for your classified briefing."
HQ (voice): "Do not repeat this message. You are the Intruder."
```

**Built for this hackathon on the A1 Mobile stack:** inbound voice webhooks,
SMS pacing, OTP consent — plus outbound ringing and a conference bridge we
built ourselves because the platform has neither.

## The round (4–12 players, ~10 minutes)

Roles: **狼人 Intruder / 预言家 Investigator / 守卫 Guardian / 平民 Civilian**,
dealt secretly on standard 狼人杀 ratios (~1 wolf per 3 players; 6 players = 2
wolves who are told each other's names). Phases auto-advance as calls come in:

role calls → night actions → evidence → **open discussion** → accusations →
vote → reveal + postgame

- Evidence is LLM-generated but **grounded in the resolved night actions**;
  the Intruder receives a fabricated cover story to repeat aloud.
- Players can call HQ **any time and interrogate it** (their role, the rules,
  who is alive): the agent answers from live game state via a `game_status`
  tool — never leaks another player's secrets.
- The **AI Director** reviews the full secret state after evidence lands and
  may plant one extra clue or a public event (its reasoning shows in the host
  console).
- The reveal includes an LLM postgame debrief: who was who, which clues were
  true, which was the fabrication.
- **Open discussion** puts every caller on one mixed party line — a real
  conference bridge (`game/conference.py`), because the carrier has none.
- **The game calls you**: phase announcements ring every player over SIP
  (`game/outbound.py`), a capability the platform's API does not expose.
- **One toggle switches the whole game between 中文 and English** — the
  judge's voice, speech recognition, SMS, AI narration and the dashboard.
- Themes re-skin everything: 月夜村庄, signal-station, haunted-hotel,
  spaceship, spy-agency.

## The dashboard (three views, one page)

Open the tunnel URL — near-black switchboard aesthetic, projector-ready:

- **PUBLIC** — four phone lines with live states (CONNECTED / AWAITING CALL /
  DECISION RECEIVED / DISCONNECTED), signals counter, public record, reveal +
  postgame. Night-phase ambience (generated radio static, toggleable).
- **LOBBY** — create a room: theme, four names + phones, per-player OTP
  consent (SEND CODE → confirm) with verified dots, BEGIN TRANSMISSION.
- **DIRECTOR** — token-gated: full secret table (roles, actions, clues,
  votes), the Director's intervention notes, FORCE ADVANCE / NEW GAME
  overrides. Host token: `ADMIN_TOKEN` env (default `deadair`).

## Run it

```bash
npm start        # server on :3000 (webhook + websocket + dashboard)
npm run tunnel   # public https url -> PUBLIC_BASE_URL in .env, restart
npm run point    # aim the claimed A1 number at it
```

Then open the dashboard → LOBBY → create the room → verify each phone →
BEGIN TRANSMISSION. Players just answer their SMS and call the number.

## Test without phones

```bash
.venv/bin/python tests/test_engine.py                       # rules engine
.venv/bin/python scripts/sim_call.py +1555… "Understood." 35  # one fake caller
```

A complete 4-player round has been played this way end-to-end (concurrent
callers, correct elimination, narrated reveal).

## Architecture

```text
player phone ─► A1/Telnyx ─► POST /voice (TeXML <Connect><Stream>)
                                │ caller id in wss url
                                ▼
                  /ws  per-call Pipecat pipeline
                  VAD ► STT ► LLM (+ per-phase tools) ► TTS
                                │
            game/calls.py    CallScript per phase + game_status interrogation
            game/engine.py   deterministic rules (tested, persisted, fuzzy names)
            game/director.py clues / summaries / narration / AI Director / postgame
            game/flow.py     auto-advance + side effects
            game/notify.py   SMS pacing via A1 /api/sms (OTP-consented only)
            agent/static/    MAFIAOS dashboard (public / lobby / director)
```

The LLM interprets language; **Python decides what is legal.** Every director
LLM call has a deterministic fallback so the demo cannot stall.

## Voice

Default TTS is OpenAI (`onyx`). For the signature narrator, drop a Fish Audio
key in `.env` and it switches automatically (Pipecat `FishAudioTTSService`,
`s2.1-pro`, PCM):

```bash
FISH_API_KEY=...        # optional
FISH_VOICE_ID=...       # optional custom reference voice
```

## Platform constraint worth knowing

The event platform is **inbound-only** (no outbound call API — verified
against REST and MCP). MafiaOS therefore runs hotline-style: SMS paces the
game, players dial in. A missed call is handled by deadline + host
force-advance rather than retry-dialing. If outbound ships, a call scheduler
slots into `game/flow.py` cleanly.

## Env

`A1_TEAM_KEY`, `A1_PHONE_NUMBER`, `PUBLIC_BASE_URL`, `OPENAI_API_KEY`
(STT/TTS/LLM), optional `LLM_*` (event AI gateway), optional `FISH_*`,
optional `ADMIN_TOKEN`.
