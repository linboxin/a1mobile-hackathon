# A1 Mobile Hackathon Demo

This repository contains a minimal inbound-call demo for the A1 Mobile hackathon.
Calling the claimed number reaches a public webhook and plays a spoken confirmation.

## What the first demo proves

1. Your claimed A1 Mobile number receives a call.
2. A1 Mobile sends the call to your public `/voice` webhook.
3. Your server returns TeXML that speaks a greeting to the caller.

No AI-provider keys are required for this first test.

## Direct SIP softphone

If the event webhook API is unavailable, the claimed number can also register as
a SIP phone against `sip.telnyx.com`. This repository's local demo uses Baresip:

```bash
npm run softphone
```

Keep that terminal open and call your A1 Mobile number from another phone. Use
`a` to answer and `b` to hang up. The local `.baresip-demo` directory contains
the SIP credentials and is intentionally excluded from Git.

## Run locally

```bash
npm start
```

In another terminal, expose port `3000` with an HTTPS tunnel such as ngrok or
Cloudflare Tunnel. Then point the number at the tunnel:

```bash
A1_TEAM_KEY=team_your_key \
PUBLIC_BASE_URL=https://your-public-host.example.com \
npm run point
```

Call the claimed phone number. You should hear:

> Hello! Your A1 Mobile demo is working. The phone number reached your local
> webhook successfully.

The terminal running the server logs the webhook request so you can inspect what
A1 Mobile sends.

## Secrets

Keep the team key and SIP password in `.env` or another ignored local file. Do
not place real credentials in source code or commit them to Git.

## Next step: conversational agent

Once the greeting works, replace the static TeXML response with a bidirectional
WebSocket media stream and connect it to a voice pipeline such as Pipecat. The
typical pipeline is:

```text
phone audio -> speech-to-text -> language model -> text-to-speech -> phone audio
```
