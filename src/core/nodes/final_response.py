from typing import Literal
from langchain_core.messages import AIMessage, ToolMessage,SystemMessage, HumanMessage
from langgraph.types import Command

from src.core.models.agent_runner_models import AgentState
from src.tools.tool_types import ToolExecutionResponse
from src.utils.logging import setup_logger
import json
logger = setup_logger('generate_final_response')


async def generate_final_response(state: AgentState):
    """Generate final response with fallback logic for cases where agent didn't use messaging tools."""

    config = state['config']
    source = config.source
    source_to_use = source
    system_prompt = config.system_prompt
    input_text = config.input_text

    # Check if agent used messaging tools (reply_to_user_on_{platform})
    messaging_tool_calls = []
    for msg in state['messages']:
        if isinstance(msg, AIMessage) and hasattr(msg, 'tool_calls') and msg.tool_calls:
            for tool_call in msg.tool_calls:
                tool_name = tool_call.get('name', '')
                if tool_name.startswith('reply_to_user_on_'):
                    messaging_tool_calls.append(tool_name)

    # If agent sent messages via tools, skip fallback
    if messaging_tool_calls:
        logger.info(f"Agent sent {len(messaging_tool_calls)} message(s) via tools: {messaging_tool_calls}")
        logger.info("Skipping fallback - agent handled messaging directly")

        # Create minimal response (no message to send)
        from src.core.models.agent_runner_models import AgentFinalResponse
        return {
            "final_response": AgentFinalResponse(
                response="",  # Empty - agent already sent messages
                execution_notes=f"Agent sent {len(messaging_tool_calls)} message(s) via communication tools: {', '.join(messaging_tool_calls)}",
                delivery_platform=source_to_use,
                output_modality="text",
                generation_instructions=None,
                file_links=[]
            ),
            "reply_sent": True,
            "reply_count": len(messaging_tool_calls)
        }

    # Agent DID NOT use messaging tools - use fallback system
    logger.warning("Agent did not use messaging tools - using fallback response generation")

    final_message = state['messages'][-2:] # Last message should be AI's final response
    final_message_history = []
    ### iterate in reverse until the first HumanMessage
    for msg in reversed(state['messages']):
        final_message_history.insert(0,msg)
        if isinstance(msg, HumanMessage):
            final_message_history.insert(0,msg)
            break

    # logger.info(f"final_message {str(state['messages'][-1])}")
    logger.info(f"Source channel: {source}, metadata: {state['metadata']}")
    if source in ['scheduled','recurring'] and state.get('metadata') and state['metadata'].get('output_type'):
        source_to_use = state['metadata']['output_type']
    prompt = (
        f"the system prompt given to the agent was: '''{system_prompt}'''\n\n"
        f"Given the following final response from an agent:"
        f"and knowing the initial request came from the '{source_to_use}' channel, "
        "format this into the required JSON structure. The delivery_platform must match the source channel, unless the user indicates or implies otherwise, or the command requires a different channel. Note that a scheduled/recurring/triggered command cannot have websocket as the delivery platform. If the user has specifically asked for a different delivery platform, you must comply. for example, if the user has sent an email, but requests a response on imessage, comply. Explain the choice of delivery platform in the execution_notes field, acknowledging if the user requested a particular platform or not. "
        "IF the source channel is 'websocket', you must always respond on websocket. assume that any actions that required different platforms, such as sending an email, have already been handled. "
        f"the user's original message in this case was {input_text}. pay attention to whether it contains a particular request for delivery platform. "
        " do not mention explicit tool ids in your final response. instead, focus on what the user wants to do, and how we can help them."
        "If the response requires generating audio, video, or image, set the output_modality and generation_instructions fields accordingly.  the response should simply acknowledge the request to generate the media, and not attempt to generate it yourself. this is not a task for you. simply trust in the systems that will handle it after you. "
        "this response will be sent to the user. if the task is to send a reminder to the user, the generation of this response here counts as sending a message to the user. This is not a failure, but a fundamental aspect of how the system works. "
    )

    msgs = [SystemMessage(content=prompt)] + final_message_history

    response = await config.structured_llm.ainvoke(msgs)

    # Mark that fallback was used (reply_sent remains False)
    logger.info("Generated fallback response - will be sent via egress service")
    return {
        "final_response": response,
        "reply_sent": False,  # Fallback used, not direct tool call
        "reply_count": 0
    }