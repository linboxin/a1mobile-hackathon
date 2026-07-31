"""MafiaOS outbound announcement calls.

The platform has no outbound-call API, but the claimed number CAN originate
calls over SIP: an INVITE to sip.telnyx.com authenticated with the team's SIP
credentials, with the claimed number as the From identity (registration is
refused, but calls go through — verified live).

We use baresip as the dialer with a pre-generated TTS wav as the call audio:
ring the player, the judge speaks the phase announcement, hang up. Private
interactions still happen when the player calls the hotline back.

Enable with OUTBOUND_RING=1 in .env. Requires: baresip (brew install baresip)
and the gitignored hidden.md with current SIP credentials.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import shutil
import tempfile
from pathlib import Path

import httpx
from loguru import logger

from . import i18n
from .engine import Game, Phase

ROOT = Path(__file__).parent.parent
CACHE = Path(tempfile.gettempdir()) / "mafiaos-announce"



def enabled() -> bool:
    return os.getenv("OUTBOUND_RING", "") == "1" and shutil.which("baresip") is not None


def _sip_creds() -> tuple[str, str] | None:
    try:
        data = json.loads((ROOT / "hidden.md").read_text())
        return data["sip_username"], data["sip_password"]
    except Exception:
        return None


async def _tts_wav(text: str) -> Path | None:
    """Generate (and cache) the announcement audio."""
    CACHE.mkdir(exist_ok=True)
    path = CACHE / f"{hashlib.md5(text.encode()).hexdigest()}.wav"
    if path.exists():
        return path
    key = os.getenv("OPENAI_API_KEY", "")
    try:
        async with httpx.AsyncClient(timeout=60) as client:
            response = await client.post(
                "https://api.openai.com/v1/audio/speech",
                headers={"Authorization": f"Bearer {key}"},
                json={"model": "gpt-4o-mini-tts", "voice": os.getenv("TTS_VOICE", "onyx"),
                      "input": text, "response_format": "wav"},
            )
            response.raise_for_status()
        path.write_bytes(response.content)
        return path
    except Exception as error:
        logger.warning(f"announcement TTS failed: {error}")
        return None


def _write_baresip_config(directory: Path, wav: Path) -> None:
    creds = _sip_creds()
    if creds is None:
        raise RuntimeError("no SIP credentials in hidden.md")
    username, password = creds
    own_number = os.getenv("A1_PHONE_NUMBER", "")
    (directory / "accounts").write_text(
        f"<sip:{own_number}@sip.telnyx.com;transport=udp>"
        f";auth_user={username};auth_pass={password}"
        f';outbound="sip:sip.telnyx.com;transport=udp";regint=0'
        f";audio_codecs=pcmu,pcma;answermode=manual\n"
    )
    (directory / "config").write_text(f"""
sip_cafile      /etc/ssl/cert.pem
module_path     /opt/homebrew/Cellar/baresip/4.10.0/lib/baresip/modules
module          stdio.so
module          g711.so
module          auconv.so
module          auresamp.so
module          aufile.so
module          coreaudio.so
module_app      account.so
module_app      menu.so
audio_source    aufile,{wav}
audio_player    coreaudio,default
audio_alert     none,
""")


async def ring_player(phone: str, wav: Path, max_secs: int = 32) -> bool:
    """Place one announcement call. Returns True if the call connected."""
    with tempfile.TemporaryDirectory(prefix="mafiaos-dial-") as tmp:
        directory = Path(tmp)
        _write_baresip_config(directory, wav)
        proc = await asyncio.create_subprocess_exec(
            "baresip", "-f", str(directory),
            "-e", f"/dial sip:{phone}@sip.telnyx.com",
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT,
        )
        established = False
        try:
            async with asyncio.timeout(max_secs):
                while True:
                    line = await proc.stdout.readline()
                    if not line:
                        break
                    text = line.decode("utf-8", "replace")
                    if "Call established" in text:
                        established = True
                        logger.info(f"outbound ring: {phone} answered")
                    if "session closed" in text and established:
                        break
                    if "session closed" in text and "403" in text:
                        logger.warning(f"outbound ring to {phone} rejected: {text.strip()}")
                        break
        except TimeoutError:
            pass
        finally:
            try:
                proc.terminate()
                await asyncio.wait_for(proc.wait(), 5)
            except Exception:
                proc.kill()
        return established


async def announce_phase(game: Game) -> None:
    """Ring every living player with the phase announcement, sequentially."""
    if not enabled():
        return
    key = f"announce_{game.phase.value}"
    if key not in i18n.STRINGS:
        return
    text = game.t(key)
    wav = await _tts_wav(text)
    if wav is None:
        return
    for player in game.players:
        if not player.alive or player.phone.startswith("+1555"):
            continue  # skip fictional bot seats
        connected = await ring_player(player.phone, wav)
        status = game.t("outbound_connected" if connected else "outbound_missed")
        game.log(game.t("log_outbound", name=player.name, status=status))
    game.save()
