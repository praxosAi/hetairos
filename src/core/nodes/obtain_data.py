
from typing import Literal
from langchain_core.messages import AIMessage, ToolMessage
from langgraph.types import Command

from src.core.models.agent_runner_models import AgentState
from src.tools.tool_types import ToolExecutionResponse
from src.utils.logging import setup_logger
logger = setup_logger('obtain_data')
async def obtain_data(state: AgentState) -> Command[Literal["action","finalize"]]:
    """
    Single-purpose node to solicit missing params without creating loops.
    It appends a clear instruction for the next tool node and marks the probe as done.
    """
    config = state['config']
    current = state.get("data_iter_counter", 0) + 1
    current = state.get("data_iter_counter", 0) + 1
    if current > config.MAX_DATA_ITERS:
        logger.info("obtain_data cap reached; finalizing.")
        return Command(goto="finalize")

    msg = AIMessage(
        content=(
            "We are missing required parameters. Call the `ask_user_for_missing_params` tool now to craft a single, "
            "concise question to the user that gathers ONLY the missing fields. After receiving the user's answer, "
            "continue with the main plan."
        )
    )
    logger.info(f"Routing to action with obtain_data instruction (iteration {current}).")
    return Command(
        goto="agent",
        update={
            "messages": state["messages"] + [msg],
            "data_iter_counter": current,
            "param_probe_done": True,   # prevent immediate re-entry from router
        },
    )