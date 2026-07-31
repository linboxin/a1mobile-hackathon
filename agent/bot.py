"""Pipecat voice pipeline for the A1 Mobile demo.

phone audio -> Telnyx media stream (websocket) -> STT -> LLM -> TTS -> phone audio
"""

import os

from fastapi import WebSocket
from loguru import logger

from pipecat.audio.vad.silero import SileroVADAnalyzer
from pipecat.frames.frames import LLMRunFrame
from pipecat.pipeline.pipeline import Pipeline
from pipecat.pipeline.runner import PipelineRunner
from pipecat.pipeline.task import PipelineParams, PipelineTask
from pipecat.processors.aggregators.llm_context import LLMContext
from pipecat.processors.aggregators.llm_response_universal import LLMContextAggregatorPair
from pipecat.processors.audio.vad_processor import VADProcessor
from pipecat.serializers.telnyx import TelnyxFrameSerializer
from pipecat.services.openai.llm import OpenAILLMService
from pipecat.services.openai.stt import OpenAISTTService
from pipecat.services.openai.tts import OpenAITTSService
from pipecat.transports.websocket.fastapi import (
    FastAPIWebsocketParams,
    FastAPIWebsocketTransport,
)

SYSTEM_PROMPT = os.getenv(
    "SYSTEM_PROMPT",
    "You are a friendly voice agent for the A1 Mobile hackathon demo. "
    "Open by greeting the caller and saying the webhook voice agent is live. "
    "Keep every reply to one or two short sentences of plain spoken language. "
    "Never use emoji, markdown, or special characters.",
)


async def run_bot(
    websocket: WebSocket,
    stream_id: str,
    call_control_id: str | None,
    inbound_encoding: str,
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

    def env(name: str) -> str | None:
        value = os.getenv(name, "")
        return value if value and "replace" not in value else None

    openai_key = env("OPENAI_API_KEY")
    stt = OpenAISTTService(api_key=openai_key)
    tts = OpenAITTSService(api_key=openai_key, voice=os.getenv("TTS_VOICE", "alloy"))
    llm = OpenAILLMService(
        api_key=env("LLM_API_KEY") or openai_key,
        base_url=env("LLM_BASE_URL"),
        model=env("LLM_MODEL") or "gpt-4o-mini",
    )

    context = LLMContext([{"role": "system", "content": SYSTEM_PROMPT}])
    aggregators = LLMContextAggregatorPair(context)

    pipeline = Pipeline(
        [
            transport.input(),
            VADProcessor(vad_analyzer=SileroVADAnalyzer()),
            stt,
            aggregators.user(),
            llm,
            tts,
            transport.output(),
            aggregators.assistant(),
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
        logger.info("Caller connected; asking LLM for the greeting")
        await task.queue_frames([LLMRunFrame()])

    @transport.event_handler("on_client_disconnected")
    async def on_client_disconnected(transport, client):
        logger.info("Caller disconnected; stopping pipeline")
        await task.cancel()

    runner = PipelineRunner(handle_sigint=False)
    await runner.run(task)
