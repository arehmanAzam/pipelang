#
# Copyright (c) 2024–2025, Daily
#
# SPDX-License-Identifier: BSD 2-Clause License
#

import os

from dotenv import load_dotenv
from langchain.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_community.chat_message_histories import ChatMessageHistory
from langchain_core.chat_history import BaseChatMessageHistory
from langchain_core.runnables.history import RunnableWithMessageHistory
from langchain_openai import ChatOpenAI
from loguru import logger

from pipecat.audio.vad.silero import SileroVADAnalyzer
from pipecat.frames.frames import LLMMessagesFrame
from pipecat.pipeline.pipeline import Pipeline
from pipecat.pipeline.runner import PipelineRunner
from pipecat.pipeline.task import PipelineParams, PipelineTask
from pipecat.processors.aggregators.llm_response import (
    LLMAssistantResponseAggregator,
    LLMUserResponseAggregator,
)
from pipecat.processors.frameworks.langchain import LangchainProcessor
from pipecat.services.cartesia.tts import CartesiaTTSService
from pipecat.services.deepgram.stt import DeepgramSTTService
from pipecat.transports.base_transport import TransportParams
from pipecat.transports.network.small_webrtc import SmallWebRTCTransport
from pipecat.transports.network.webrtc_connection import SmallWebRTCConnection
from langchain_core.runnables import RunnableLambda
from langchain.chains.base import Chain
from typing import Dict, List, Any
from langchain.callbacks.manager import CallbackManagerForChainRun
from supervisor import supervisor_node
load_dotenv(override=True)


message_store = {}
class SupervisorChain(Chain):
    @property
    def input_keys(self):
        # Define the keys required as input by your chain.
        return ["input"]

    @property
    def output_keys(self):
        # Define the keys returned by your chain.
        return ["output"]
    
    def _call(self, inputs: Dict, run_manager: CallbackManagerForChainRun = None) -> Dict:
        return supervisor_node(inputs)
    
    async def _acall(self, inputs: Dict, run_manager: CallbackManagerForChainRun = None) -> Dict:
        return self._call(inputs, run_manager=run_manager)

    # astream() must be implemented so that LangchainProcessor can iterate tokens.
    # In this simple example, we yield the full output text as a single token.
    async def astream(self, inputs: Dict, config: Dict = None) -> Any:
        result = await self._acall(inputs)
        output_text = result.get("output", "")
        # Optionally, you can yield chunks of text; here we yield the full result as one token.
        yield output_text

# Now instantiate your chain

def get_session_history(session_id: str) -> BaseChatMessageHistory:
    if session_id not in message_store:
        message_store[session_id] = ChatMessageHistory()
    return message_store[session_id]


async def run_bot(webrtc_connection: SmallWebRTCConnection):
    logger.info(f"Starting bot")

    transport = SmallWebRTCTransport(
        webrtc_connection=webrtc_connection,
        params=TransportParams(
            audio_in_enabled=True,
            audio_out_enabled=True,
            vad_enabled=True,
            vad_analyzer=SileroVADAnalyzer(),
            vad_audio_passthrough=True,
        ),
    )

    stt = DeepgramSTTService(api_key=os.getenv("DEEPGRAM_API_KEY"))

    tts = CartesiaTTSService(
        api_key=os.getenv("CARTESIA_API_KEY"),
        voice_id="71a7ad14-091c-4e8e-a314-022ece01c121",  # British Reading Lady
    )

    prompt = ChatPromptTemplate.from_messages(
        [
            (
                "system",
                "Be nice and helpful. Answer very briefly and without special characters like `#` or `*`. "
                "Your response will be synthesized to voice and those characters will create unnatural sounds.",
            ),
            MessagesPlaceholder("chat_history"),
            ("human", "{input}"),
        ]
    )
    chain = prompt | ChatOpenAI(model="gpt-4.1", temperature=0.7,api_key=os.getenv('OPENAI_API_KEY'))
    supervisor_chain = SupervisorChain()
    history_chain = RunnableWithMessageHistory(
        supervisor_chain,
        get_session_history,
        history_messages_key="chat_history",
        input_messages_key="input",
    )
    lc = LangchainProcessor(history_chain)

    tma_in = LLMUserResponseAggregator()
    tma_out = LLMAssistantResponseAggregator()

    pipeline = Pipeline(
        [
            transport.input(),  # Transport user input
            stt,
            tma_in,  # User responses
            lc,  # Langchain
            tts,  # TTS
            transport.output(),  # Transport bot output
            tma_out,  # Assistant spoken responses
        ]
    )

    task = PipelineTask(
        pipeline,
        params=PipelineParams(
            allow_interruptions=True,
            enable_metrics=True,
            enable_usage_metrics=True,
            report_only_initial_ttfb=True,
        ),
    )

    @transport.event_handler("on_client_connected")
    async def on_client_connected(transport, client):
        logger.info(f"Client connected")
        # Kick off the conversation.
        # the `LLMMessagesFrame` will be picked up by the LangchainProcessor using
        # only the content of the last message to inject it in the prompt defined
        # above. So no role is required here.
        messages = [({"content": "Please briefly introduce yourself to the user."})]
        await task.queue_frames([LLMMessagesFrame(messages)])

    @transport.event_handler("on_client_disconnected")
    async def on_client_disconnected(transport, client):
        logger.info(f"Client disconnected")

    @transport.event_handler("on_client_closed")
    async def on_client_closed(transport, client):
        logger.info(f"Client closed connection")
        await task.cancel()

    runner = PipelineRunner(handle_sigint=False)

    await runner.run(task)


if __name__ == "__main__":
    from run import main

    main()