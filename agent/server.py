"""FastAPI server for the A1 Mobile demo.

POST /voice  -> TeXML telling A1/Telnyx to open a bidirectional media stream
WS   /ws     -> the media stream; runs the Pipecat pipeline (see bot.py)
"""

import json
import os
from urllib.parse import urlparse

import uvicorn
from dotenv import load_dotenv
from fastapi import FastAPI, Request, WebSocket
from fastapi.responses import JSONResponse, Response
from loguru import logger

load_dotenv(override=False)

from bot import run_bot  # noqa: E402  (needs env loaded first)

app = FastAPI()


def public_ws_url() -> str:
    base = os.getenv("PUBLIC_BASE_URL", "").rstrip("/")
    host = urlparse(base).netloc or "localhost:3000"
    return f"wss://{host}/ws"


@app.get("/")
async def health():
    return {
        "service": "a1mobile-webhook-demo",
        "ok": True,
        "voiceWebhook": "/voice",
        "mediaStream": public_ws_url(),
    }


@app.api_route("/voice", methods=["GET", "POST"])
async def voice(request: Request):
    body = (await request.body()).decode("utf-8", "replace")
    logger.info(f"/voice hit: method={request.method} body={body!r}")

    texml = f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
  <Connect>
    <Stream url="{public_ws_url()}" bidirectionalMode="rtp" bidirectionalCodec="PCMU" />
  </Connect>
</Response>"""
    return Response(content=texml, media_type="application/xml")


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()

    # Telnyx sends two JSON text frames before audio: "connected" then "start".
    connected = json.loads(await websocket.receive_text())
    start_msg = json.loads(await websocket.receive_text())
    logger.info(f"Media stream opened: {start_msg}")

    start = start_msg.get("start", {})
    stream_id = start_msg.get("stream_id") or start.get("stream_id") or ""
    call_control_id = start.get("call_control_id")
    inbound_encoding = start.get("media_format", {}).get("encoding", "PCMU")

    try:
        await run_bot(websocket, stream_id, call_control_id, inbound_encoding)
    except Exception:
        logger.exception("Pipeline crashed")


@app.exception_handler(404)
async def not_found(request: Request, exc):
    logger.info(f"unhandled path: {request.method} {request.url.path}")
    return JSONResponse({"error": "Not found"}, status_code=404)


if __name__ == "__main__":
    port = int(os.getenv("PORT", "3000"))
    logger.info(f"A1 Mobile agent listening on http://localhost:{port}")
    logger.info(f"Voice webhook: /voice ; media stream: {public_ws_url()}")
    uvicorn.run(app, host="0.0.0.0", port=port)
