"""Dead Air — FastAPI server.

POST /voice  -> TeXML opening a media stream, caller number embedded in the WS url
WS   /ws     -> per-call Pipecat pipeline with a phase-specific CallScript
GET  /       -> public dashboard (no secrets)
POST /api/game, /api/game/start, /api/game/advance -> host controls
"""

import json
import os
import sys
from pathlib import Path
from urllib.parse import parse_qs, quote, urlparse

import uvicorn
from dotenv import load_dotenv
from fastapi import FastAPI, Request, WebSocket
from fastapi.responses import HTMLResponse, JSONResponse, Response
from loguru import logger

sys.path.insert(0, str(Path(__file__).parent.parent))
load_dotenv(override=False)

from agent.bot import run_bot  # noqa: E402
from game import flow  # noqa: E402
from game.calls import build_script  # noqa: E402
from game.engine import Game  # noqa: E402

app = FastAPI()


class State:
    game: Game | None = Game.load()


ADMIN_TOKEN = os.getenv("ADMIN_TOKEN", "deadair")


def public_ws_url(caller: str) -> str:
    base = os.getenv("PUBLIC_BASE_URL", "").rstrip("/")
    host = urlparse(base).netloc or "localhost:3000"
    return f"wss://{host}/ws?caller={quote(caller)}"


async def caller_from_request(request: Request) -> str:
    body = (await request.body()).decode("utf-8", "replace")
    content_type = request.headers.get("content-type", "")
    caller = ""
    if "urlencoded" in content_type:
        caller = parse_qs(body).get("From", [""])[0]
    elif body.startswith("{"):
        try:
            caller = json.loads(body).get("from", "") or json.loads(body).get("From", "")
        except json.JSONDecodeError:
            pass
    logger.info(f"/voice: caller={caller!r} body={body[:300]!r}")
    return caller


@app.get("/health")
async def health():
    return {"service": "dead-air", "ok": True, "game": bool(State.game)}


@app.api_route("/voice", methods=["GET", "POST"])
async def voice(request: Request):
    caller = await caller_from_request(request)
    texml = f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
  <Connect>
    <Stream url="{public_ws_url(caller)}" bidirectionalMode="rtp" bidirectionalCodec="PCMU" />
  </Connect>
</Response>"""
    return Response(content=texml, media_type="application/xml")


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    caller = websocket.query_params.get("caller", "")

    connected = json.loads(await websocket.receive_text())
    start_msg = json.loads(await websocket.receive_text())
    start = start_msg.get("start", {})
    stream_id = start_msg.get("stream_id") or start.get("stream_id") or ""
    call_control_id = start.get("call_control_id")
    inbound_encoding = start.get("media_format", {}).get("encoding", "PCMU")

    game = State.game
    player = game.player_by_phone(caller) if (game and caller) else None
    logger.info(
        f"Call: caller={caller!r} player={player.name if player else None} "
        f"phase={game.phase.value if game else 'none'}"
    )

    async def advance() -> None:
        if State.game:
            await flow.maybe_advance(State.game)

    script = build_script(game, player, advance)
    try:
        await run_bot(websocket, stream_id, call_control_id, inbound_encoding, script)
    except Exception:
        logger.exception("Pipeline crashed")


# ---------- host controls ----------


def check_token(payload: dict) -> JSONResponse | None:
    if payload.get("token") != ADMIN_TOKEN:
        return JSONResponse({"error": "bad token"}, status_code=403)
    return None


@app.post("/api/game")
async def create_game(request: Request):
    payload = await request.json()
    if denied := check_token(payload):
        return denied
    entries = [(p["name"], p["phone"]) for p in payload.get("players", [])]
    try:
        State.game = Game.create(entries)
    except (KeyError, ValueError) as error:
        return JSONResponse({"error": str(error)}, status_code=400)
    return State.game.public_state()


@app.post("/api/game/start")
async def start_game(request: Request):
    if denied := check_token(await request.json()):
        return denied
    if State.game is None:
        return JSONResponse({"error": "no game"}, status_code=400)
    try:
        await flow.start_game(State.game)
    except ValueError as error:
        return JSONResponse({"error": str(error)}, status_code=400)
    return State.game.public_state()


@app.post("/api/game/advance")
async def force_advance(request: Request):
    if denied := check_token(await request.json()):
        return denied
    if State.game is None:
        return JSONResponse({"error": "no game"}, status_code=400)
    advanced = await flow.maybe_advance(State.game, force=True)
    return {"advanced": advanced, **State.game.public_state()}


@app.get("/api/state")
async def state():
    if State.game is None:
        return {"phase": "none", "log": ["No game. POST /api/game to begin."]}
    return State.game.public_state()


# ---------- dashboard ----------

DASHBOARD = """<!doctype html><html><head><meta charset="utf-8">
<title>DEAD AIR</title>
<meta name="viewport" content="width=device-width, initial-scale=1">
<style>
  body { background:#050805; color:#9dff9d; font-family:'SF Mono',Menlo,monospace;
         margin:0; padding:2rem; text-shadow:0 0 6px #2f5; }
  .crt::after { content:""; position:fixed; inset:0; pointer-events:none;
    background:repeating-linear-gradient(0deg,transparent 0 2px,rgba(0,0,0,.25) 2px 4px); }
  h1 { letter-spacing:.4em; border-bottom:1px solid #2f5; padding-bottom:.5rem; }
  .dim { color:#4a7d4a; } .amber { color:#ffcf6b; text-shadow:0 0 6px #fa0; }
  .dead { color:#f66; text-decoration:line-through; }
  .bar { color:#ffcf6b; } pre { white-space:pre-wrap; margin:.2rem 0; }
  #log { margin-top:1.5rem; border-top:1px dashed #2f5; padding-top:.8rem; }
</style></head><body class="crt">
<h1>DEAD AIR</h1>
<div id="main">connecting…</div>
<div id="log"></div>
<script>
async function tick() {
  try {
    const s = await (await fetch('/api/state')).json();
    let h = `<pre>PHASE: <span class="amber">${(s.phase||'none').toUpperCase()}</span></pre>`;
    if (s.players) {
      h += `<pre>OPERATORS:</pre>`;
      for (const p of s.players) {
        const bars = '█'.repeat((s.suspicion&&s.suspicion[p.name])||0) || '·';
        h += `<pre>  <span class="${p.alive?'':'dead'}">${p.name.padEnd(10)}</span> <span class="bar">${bars}</span></pre>`;
      }
      if (s.received) h += `<pre>SIGNALS RECEIVED: <span class="amber">${s.received}</span></pre>`;
      if (s.waiting_on && s.waiting_on.length)
        h += `<pre class="dim">WAITING ON: ${s.waiting_on.join(', ')}</pre>`;
      if (s.narration) h += `<pre class="amber">${s.narration}</pre>`;
    }
    document.getElementById('main').innerHTML = h;
    document.getElementById('log').innerHTML =
      (s.log||[]).map(l=>`<pre class="dim">> ${l}</pre>`).join('');
  } catch (e) {}
}
tick(); setInterval(tick, 2000);
</script></body></html>"""


@app.get("/")
async def dashboard():
    return HTMLResponse(DASHBOARD)


if __name__ == "__main__":
    port = int(os.getenv("PORT", "3000"))
    logger.info(f"Dead Air listening on http://localhost:{port}")
    uvicorn.run(app, host="0.0.0.0", port=port)
