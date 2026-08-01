"""Pipecat voice pipeline for MafiaOS.

Generic phone plumbing: audio in/out, VAD, STT, LLM, TTS. Everything
game-specific (prompt + tools) arrives as a CallScript from game/calls.py.
"""

import os
import sys
from pathlib import Path

from fastapi import WebSocket
from loguru import logger

sys.path.insert(0, str(Path(__file__).parent.parent))

from pipecat.audio.vad.silero import SileroVADAnalyzer
from pipecat.frames.frames import LLMRunFrame
from pipecat.pipeline.pipeline import Pipeline
from pipecat.pipeline.runner import PipelineRunner
from pipecat.pipeline.task import PipelineParams, PipelineTask
from pipecat.processors.aggregators.llm_context import LLMContext
from pipecat.processors.aggregators.llm_response_universal import LLMContextAggregatorPair
from pipecat.processors.audio.vad_processor import VADProcessor
from pipecat.serializers.telnyx import TelnyxFrameSerializer
from pipecat.transcriptions.language import Language
from pipecat.services.openai.llm import OpenAILLMService
from pipecat.services.openai.stt import OpenAISTTService
from pipecat.services.openai.tts import OpenAITTSService
from pipecat.transports.websocket.fastapi import (
    FastAPIWebsocketParams,
    FastAPIWebsocketTransport,
)

from game.calls import CallScript
from game.transcript import TranscriptLogger


def _env(name: str) -> str | None:
    value = os.getenv(name, "")
    return value if value and "replace" not in value else None


async def run_bot(
    websocket: WebSocket,
    stream_id: str,
    call_control_id: str | None,
    inbound_encoding: str,
    script: CallScript,
    record: "callable | None" = None,
) -> None:
    serializer = TelnyxFrameSerializer(
        stream_id=stream_id,
        call_control_id=call_control_id,
        outbound_encoding="PCMU",
        inbound_encoding=inbound_encoding,
        # No Telnyx API key at the hackathon (the platform owns the account),
        # so the serializer can't hang calls up itself.
        params=TelnyxFrameSerializer.InputParams(auto_hang_up=False),
    )

    transport = FastAPIWebsocketTransport(
        websocket=websocket,
        params=FastAPIWebsocketParams(
            audio_in_enabled=True,
            audio_out_enabled=True,
            add_wav_header=False,
            serializer=serializer,
            session_timeout=60 * 5,
        ),
    )

    openai_key = _env("OPENAI_API_KEY")
    # Phone calls live or die on turn latency: the -mini transcribe model and
    # tts-1 are OpenAI's low-latency pair. Override per-env if you want the
    # higher-fidelity (slower) models.
    stt = OpenAISTTService(
        api_key=openai_key,
        model=os.getenv("STT_MODEL", "gpt-4o-mini-transcribe"),
        language=Language.ZH if script.lang == "zh" else Language.EN,
    )
    if fish_key := _env("FISH_API_KEY"):
        # Signature narrator voice (see MafiaOS product doc): Fish Audio,
        # activated simply by adding FISH_API_KEY (+ optional FISH_VOICE_ID).
        from pipecat.services.fish.tts import FishAudioTTSService

        tts = FishAudioTTSService(
            api_key=fish_key,
            reference_id=_env("FISH_VOICE_ID"),
            model_id=os.getenv("FISH_MODEL", "s2.1-pro"),
            output_format="pcm",
        )
        logger.info("TTS: Fish Audio narrator voice")
    else:
        tts = OpenAITTSService(
            api_key=openai_key,
            model=os.getenv("TTS_MODEL", "tts-1"),
            voice=os.getenv("TTS_VOICE", "onyx"),
        )
    llm = OpenAILLMService(
        api_key=_env("LLM_API_KEY") or openai_key,
        base_url=_env("LLM_BASE_URL"),
        model=_env("LLM_MODEL") or "gpt-4o-mini",
    )

    schemas = []
    for schema, handler in script.tools:
        llm.register_function(schema.name, handler)
        schemas.append(schema)

    messages = [{"role": "system", "content": script.system_prompt}]
    context = LLMContext(messages, tools=schemas) if schemas else LLMContext(messages)
    aggregators = LLMContextAggregatorPair(context)

    heard = TranscriptLogger(record) if record else None
    spoken = TranscriptLogger(record) if record else None
    pipeline = Pipeline(
        [
            p for p in [
                transport.input(),
                VADProcessor(vad_analyzer=SileroVADAnalyzer()),
                stt,
                heard,                    # what the caller said
                aggregators.user(),
                llm,
                tts,
                spoken,                   # what the judge said
                transport.output(),
                aggregators.assistant(),
            ] if p is not None
        ]
    )

    task = PipelineTask(
        pipeline,
        params=PipelineParams(
            audio_in_sample_rate=8000,
            # OpenAI TTS emits 24 kHz; the Telnyx serializer resamples down to
            # the 8 kHz PCMU phone wire.
            audio_out_sample_rate=24000,
        ),
    )

    @transport.event_handler("on_client_connected")
    async def on_client_connected(transport, client):
        logger.info("Caller connected; opening line")
        await task.queue_frames([LLMRunFrame()])

    @transport.event_handler("on_client_disconnected")
    async def on_client_disconnected(transport, client):
        logger.info("Caller disconnected; stopping pipeline")
        await task.cancel()

    runner = PipelineRunner(handle_sigint=False)
    await runner.run(task)
