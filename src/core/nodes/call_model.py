import json
from typing import Literal
from langchain_core.messages import AIMessage, ToolMessage
from langgraph.types import Command

from src.core.models.agent_runner_models import AgentState
from src.tools.tool_types import ToolExecutionResponse
from src.utils.logging import setup_logger
logger = setup_logger('call_model')
async def call_model(state: AgentState):
    """Invokes the LLM with the current state to decide the next step."""
    config = state['config']
    for msg in state['messages']:
        logger.info(f"Message: {msg}")
    response = await config.llm_with_tools.ainvoke(
        [("system", config.system_prompt)] + state['messages']
    )
    logger.info(f"LLM Response: {response}")
    return {"messages": state['messages'] + [response]}