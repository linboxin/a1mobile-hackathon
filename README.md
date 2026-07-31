# DEAD AIR — a voice-native social deduction game

*A1 Mobile hackathon — "Close the Loop"*

Four players are trapped in a compromised communications network. One is
secretly the **Intruder**. The only interface is a real phone call: an AI
operator ("HQ") briefs each player privately, collects secret actions, leaks
asymmetric evidence, records accusations, and runs the final vote. No app.
**The phone network is the game platform.**

```text
SMS: "DEAD AIR // Call HQ NOW for your classified briefing."
HQ (voice): "Do not repeat this message. You are the Intruder."
```

## One round, six phases

| Phase | What happens on the phone |
|---|---|
| role_calls | Each player calls in, hears their secret role (Intruder / Analyst / Operator / Witness) |
| actions | Intruder sabotages, Analyst traces, Operator shields — all by private call |
| evidence | The AI director generates grounded-but-asymmetric clues; each player hears only theirs (the Intruder gets a fabricated cover story) |
| accusations | Every player states their case; recorded verbatim by voice |
| vote | HQ reads an anonymized accusation summary, then takes each vote |
| reveal | The AI narrates the verdict; dashboard shows who the Intruder was |

Phases auto-advance when everyone has called in; the host can force-advance if
someone's call drops. A public dashboard (CRT terminal aesthetic) shows only
public state: players alive, signals received, suspicion bars, event log.

## Run it

```bash
npm start        # game server on :3000 (webhook + websocket + dashboard)
npm run tunnel   # public https url -> put in PUBLIC_BASE_URL in .env, restart
npm run point    # aim the claimed A1 number at it
```

Players must OTP-consent first (event rule): `npm run verify -- +1XXX` then
`npm run confirm -- +1XXX <code>` for each phone.

Create and start a game (host):

```bash
curl -X POST localhost:3000/api/game -H 'content-type: application/json' -d '{
  "token":"deadair",
  "players":[{"name":"Nova","phone":"+1..."},{"name":"Kit","phone":"+1..."},
              {"name":"Rhea","phone":"+1..."},{"name":"Jude","phone":"+1..."}]}'
curl -X POST localhost:3000/api/game/start -H 'content-type: application/json' \
  -d '{"token":"deadair"}'
```

Dashboard: open the tunnel URL. Force a stuck phase:
`POST /api/game/advance {"token":"deadair"}`.

## Test a whole round with zero phones

```bash
.venv/bin/python tests/test_engine.py          # engine logic
.venv/bin/python scripts/sim_call.py +15550100001 "Understood." 35
```

`sim_call.py` synthesizes a voice, streams it exactly like a Telnyx call from
any caller id, and plays a full turn against the real pipeline. A complete
4-player round has been run this way end-to-end (concurrent calls included).

## Architecture

```text
player phone ──► A1/Telnyx ──► POST /voice (TeXML <Connect><Stream>)
                                  │ caller id embedded in wss url
                                  ▼
                    /ws  per-call Pipecat pipeline
                    VAD ► STT ► LLM (+ phase tools) ► TTS
                                  │
              game/calls.py  per-phase prompt + tools (CallScript)
              game/engine.py state machine (pure, tested, persisted)
              game/director.py LLM clue/summary/narration generation
              game/flow.py   auto-advance + side effects
              game/notify.py SMS pacing via A1 /api/sms
```

Hard-won robustness details: fuzzy player-name matching (phone STT hears
"Ria" for "Rhea"), record-immediately accusation capture (a dropped call
must not lose words), template fallbacks for every director LLM call, state
persisted to disk across restarts, and non-players get an in-world brushoff.

## Env

Same `.env` as main branch: `A1_TEAM_KEY`, `A1_PHONE_NUMBER`,
`PUBLIC_BASE_URL`, `OPENAI_API_KEY` (STT/TTS/LLM), optional `LLM_*` for the
event AI gateway, optional `ADMIN_TOKEN` (default `deadair`).
