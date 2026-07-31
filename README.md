# A1 Mobile Hackathon Demo — Pipecat Voice Agent

Inbound calls to the claimed A1 Mobile number stream into a
[Pipecat](https://pipecat.ai) pipeline over the **recommended webhook** path:

```text
caller -> A1/Telnyx -> POST /voice (TeXML <Connect><Stream>)
       -> wss://tunnel/ws -> STT -> LLM -> TTS -> caller hears the agent
```

> **Status: fully working (2026-07-31).** The platform's earlier
> `/api/numbers/point` bug is fixed. Note the platform resets wiped team
> claims twice today — if calls stop landing, re-claim and re-point:
> `curl -X POST https://hack.a1mobile.com/api/numbers/claim -H "X-Team-Key: $A1_TEAM_KEY"`
> then `npm run point` (the number may change; check the claim response).

## Setup

1. `.env` needs two things you can only get from the team page / your accounts:
   - `OPENAI_API_KEY` — a real OpenAI key (used for STT + TTS, and the LLM by
     default).
   - Optional `LLM_API_KEY` / `LLM_BASE_URL` / `LLM_MODEL` — the event's
     `a1hk_` key + AI_GATEWAY base URL to route the LLM through the $50 event
     budget instead.
2. Python deps are already installed in `.venv` (`uv venv --python 3.12 .venv &&
   uv pip install --python .venv/bin/python "pipecat-ai[openai,silero]" fastapi
   "uvicorn[standard]" websockets python-dotenv loguru`).

## Run (three terminals)

```bash
# 1 — the agent (TeXML webhook + media-stream websocket on :3000)
npm start

# 2 — public HTTPS/WSS tunnel
npm run tunnel
# copy the printed https url into PUBLIC_BASE_URL in .env, restart terminal 1

# 3 — point the A1 number at it
npm run point
```

Then call the claimed number (`A1_PHONE_NUMBER` in `.env`) and talk to the
agent. It greets you, holds a conversation, and supports barge-in — talk over
it and it stops to listen.

## Text a real phone (OTP consent first)

```bash
npm run verify -- +15551234567          # OTP text to that phone
npm run confirm -- +15551234567 123456  # code the phone received
npm run sms -- +15551234567 "hello from my agent"
```

## Troubleshooting

- **Tunnel URL rotates** every `npm run tunnel` restart → update
  `PUBLIC_BASE_URL`, restart `npm start` (the TeXML embeds the wss URL), re-run
  `npm run point`.
- **Venue Wi-Fi DNS lags** on fresh trycloudflare hostnames; A1 reaches them
  fine (public DNS works). Check with `dig @1.1.1.1 <host>`.
- **401 in the agent log** → paste a real `OPENAI_API_KEY` in `.env`.
- **Where's my old Node greeting server?** Replaced by `agent/server.py`
  (same `/voice` webhook, now with a real agent behind it).

## Fallback: direct SIP softphone

`npm run softphone` registers the number as a baresip softphone
(`.baresip-demo/`, credentials already updated for the new number) — works
today, no webhook needed. `a` answers, `b` hangs up.
