"""MafiaOS — FastAPI server.

POST /voice  -> TeXML opening a media stream, caller number embedded in the WS url
WS   /ws     -> per-call Pipecat pipeline with a phase-specific CallScript
GET  /       -> public dashboard (no secrets)
POST /api/game, /api/game/start, /api/game/advance -> host controls
"""

import json
import os
import sys
import time
from datetime import datetime
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
from game import engine, flow  # noqa: E402
from game.calls import build_script  # noqa: E402
from game.engine import Game  # noqa: E402

app = FastAPI()


def boot_game() -> Game | None:
    """Restarting the server starts a fresh table by default.

    The finished/abandoned round is archived rather than deleted. Set
    RESUME_GAME=1 to pick a live round back up instead (useful if the server
    dies mid-game and players are still on the phone).
    """
    existing = Game.load()
    if existing is None:
        return None
    if os.getenv("RESUME_GAME", "") == "1":
        logger.info(f"resuming game {existing.code} at phase {existing.phase.value}")
        return existing
    archive = Path(engine.STATE_FILE).parent / "game_archive"
    archive.mkdir(exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    Path(engine.STATE_FILE).rename(archive / f"{stamp}-{existing.code}.json")
    logger.info(f"archived previous game {existing.code}; starting with an empty lobby")
    return None


class State:
    game: Game | None = boot_game()
    # live calls: player name (or "?1234" for a stranger) -> call start time
    on_call: dict[str, float] = {}


ADMIN_TOKEN = os.getenv("ADMIN_TOKEN", "deadair")


def fresh_env(name: str, default: str = "") -> str:
    # .env is rewritten by scripts/tunnel.sh when the tunnel URL rotates;
    # re-reading per request means no server restart after a tunnel restart.
    load_dotenv(override=True)
    return os.getenv(name, default)


def public_ws_url(caller: str) -> str:
    base = fresh_env("PUBLIC_BASE_URL").rstrip("/")
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

    label = player.name if player else f"?{caller[-4:]}"
    State.on_call[label] = time.time()
    if game and player:
        game.log(game.t("log_call_connected", name=player.name))
    script = build_script(game, player, advance)
    try:
        await run_bot(websocket, stream_id, call_control_id, inbound_encoding, script)
    except Exception:
        logger.exception("Pipeline crashed")
    finally:
        State.on_call.pop(label, None)
        if game and player and player.name not in game.done_names():
            # Sensor: they hung up owing this phase an input.
            game.log(game.t("log_call_dropped", name=player.name))


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
        State.game = Game.create(entries, theme=payload.get("theme", "moonlit-village"),
                                 lang=payload.get("lang", "zh"))
    except (KeyError, ValueError) as error:
        return JSONResponse({"error": str(error)}, status_code=400)
    return State.game.public_state()


A1_API = "https://hack.a1mobile.com"


async def a1_post(path: str, body: dict) -> tuple[int, str]:
    import httpx

    async with httpx.AsyncClient(timeout=15) as client:
        response = await client.post(
            f"{A1_API}{path}",
            headers={"X-Team-Key": os.getenv("A1_TEAM_KEY", ""),
                     "Content-Type": "application/json"},
            json=body,
        )
        return response.status_code, response.text


@app.post("/api/players/verify")
async def player_verify(request: Request):
    payload = await request.json()
    if denied := check_token(payload):
        return denied
    code, text = await a1_post("/api/verified-numbers", {"phone": payload["phone"]})
    return JSONResponse({"status": code, "body": text}, status_code=200 if code < 400 else 502)


@app.post("/api/players/confirm")
async def player_confirm(request: Request):
    payload = await request.json()
    if denied := check_token(payload):
        return denied
    code, text = await a1_post("/api/verified-numbers/confirm",
                               {"phone": payload["phone"], "code": payload["code"]})
    return JSONResponse({"status": code, "body": text}, status_code=200 if code < 400 else 502)


@app.get("/api/verified")
async def verified_numbers():
    import httpx

    async with httpx.AsyncClient(timeout=15) as client:
        response = await client.get(
            f"{A1_API}/api/verified-numbers",
            headers={"X-Team-Key": os.getenv("A1_TEAM_KEY", "")},
        )
        try:
            return response.json()
        except ValueError:
            return {"verified_numbers": []}


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
    hotline = fresh_env("A1_PHONE_NUMBER")
    now = time.time()
    on_call = {name: round(now - started) for name, started in State.on_call.items()}
    if State.game is None:
        return {"phase": "none", "hotline": hotline, "on_call": on_call, "log": []}
    return {**State.game.public_state(), "hotline": hotline,
            "on_call": on_call, "now": now}


@app.get("/api/director-state")
async def director_state(request: Request):
    if request.query_params.get("token") != ADMIN_TOKEN:
        return JSONResponse({"error": "bad token"}, status_code=403)
    if State.game is None:
        return {"phase": "none"}
    return State.game.director_state()


# ---------- dashboard ----------

STATIC_DIR = Path(__file__).parent / "static"


@app.get("/")
async def dashboard():
    return HTMLResponse((STATIC_DIR / "index.html").read_text())


if __name__ == "__main__":
    port = int(os.getenv("PORT", "3000"))
    logger.info(f"Dead Air listening on http://localhost:{port}")
    uvicorn.run(app, host="0.0.0.0", port=port)
