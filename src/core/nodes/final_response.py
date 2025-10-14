from typing import Literal
from langchain_core.messages import AIMessage, ToolMessage
from langgraph.types import Command

from src.core.models.agent_runner_models import AgentState
from src.tools.tool_types import ToolExecutionResponse
from src.utils.logging import setup_logger
import json
logger = setup_logger('should_continue_router')


async def generate_final_response(state: AgentState):
    final_message = state['messages'][-2:] # Last message should be AI's final response

    config = state['config']
    final_message_history = state['messages'][-2:]
    logger.info(f"final_message {str(state['messages'][-1])}")
    source = config.source
    source_to_use = source
    system_prompt = config.system_prompt
    input_text = config.input_text
    logger.info(f"Final agent message before formatting: {str(final_message)}")
    logger.info(f"Source channel: {source}, metadata: {state['metadata']}")
    if source in ['scheduled','recurring'] and state.get('metadata') and state['metadata'].get('output_type'):
        source_to_use = state['metadata']['output_type']
    prompt = (
        f"the system prompt given to the agent was: '''{system_prompt}'''\n\n"
        f"Given the following final response from an agent: '{json.dumps(final_message,indent=3,default=str)} \n\n', "
        f"and knowing the initial request came from the '{source_to_use}' channel, "
        "format this into the required JSON structure. The delivery_platform must match the source channel, unless the user indicates or implies otherwise, or the command requires a different channel. Note that a scheduled/recurring/triggered command cannot have websocket as the delivery platform. If the user has specifically asked for a different delivery platform, you must comply. for example, if the user has sent an email, but requests a response on imessage, comply. Explain the choice of delivery platform in the execution_notes field, acknowledging if the user requested a particular platform or not. "
        "IF the source channel is 'websocket', you must always respond on websocket. assume that any actions that required different platforms, such as sending an email, have already been handled. "
        f"the user's original message in this case was {input_text}. pay attention to whether it contains a particular request for delivery platform. "
        " do not mention explicit tool ids in your final response. instead, focus on what the user wants to do, and how we can help them."
        "If the response requires generating audio, video, or image, set the output_modality and generation_instructions fields accordingly.  the response should simply acknowledge the request to generate the media, and not attempt to generate it yourself. this is not a task for you. simply trust in the systems that will handle it after you. "
    )
    response = await config.structured_llm.ainvoke(prompt)
    return {"final_response": response}