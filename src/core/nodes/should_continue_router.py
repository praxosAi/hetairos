from typing import Literal
from langchain_core.messages import AIMessage, ToolMessage
from langgraph.types import Command

from src.core.models.agent_runner_models import AgentState
from src.tools.tool_types import ToolExecutionResponse
from src.utils.logging import setup_logger

logger = setup_logger('should_continue_router')

def should_continue_router(state: AgentState) -> Command[Literal["obtain_data", "action", "finalize"]]:
    """
    Router that directs the graph's flow by reading context from the state's config object.
    It can jump to obtain_data (missing params), action (tool execution), or finalize.
    """
    # Access the config object from the state. This is our "toolbox".
    config = state['config']

    try:
        # Determine new messages by slicing based on the initial history length from config
        new_messages = state['messages'][config.initial_state_len:]
        last_message = state['messages'][-1] if state['messages'] else None

        # --- Early exit conditions and specific routing ---

        if isinstance(last_message, AIMessage) and last_message.content and "NOTE: This command was previously" in last_message.content:
            logger.info("Detected scheduled/recurring/triggered note; proceeding to action.")
            return Command(goto="action")

        if isinstance(last_message, ToolMessage):
            # Check if the last tool call resulted in an error and if we can retry
            tool_response = last_message.content
            if isinstance(tool_response, ToolExecutionResponse) and tool_response.status == "error" and state.get("tool_iter_counter", 0) < config.MAX_TOOL_ITERS:
                next_count = state.get("tool_iter_counter", 0) + 1
                appended_msg = AIMessage(content="The last tool execution resulted in an error. I will retry, trying to analyze what failed and adjusting my approach.")
                logger.warning(f"Tool error detected. Retrying... (Attempt {next_count}/{config.MAX_TOOL_ITERS})")
                return Command(
                    goto="action",
                    update={"messages": state["messages"] + [appended_msg], "tool_iter_counter": next_count},
                )

        # 1) Missing-params path: Route to gather more data if needed.
        if not config.minimal_tools and config.required_tool_ids and 'ask_user_for_missing_params' in config.required_tool_ids:
            if state.get("param_probe_done", False) or state.get("data_iter_counter", 0) >= config.MAX_DATA_ITERS:
                logger.info("Missing-param probe already done or cap reached; finalizing.")
                return Command(goto="finalize")
            
            logger.info("Missing params required; routing to obtain_data node.")
            return Command(goto="obtain_data")

        # 2) Stalled-tool path: If tools are expected but none were called, force an action.
        if not config.minimal_tools:
            tool_called = any(isinstance(m, AIMessage) and getattr(m, "tool_calls", None) for m in new_messages)
            if not tool_called:
                next_count = state.get("tool_iter_counter", 0) + 1
                appended_msg = AIMessage(content=f"I need to use a tool to proceed. Consulting the plan and using the appropriate tool. Original plan:\n\n{config.plan_str}")
                
                if next_count > config.MAX_TOOL_ITERS:
                    logger.error("Too many iterations without tool usage; finalizing.")
                    return Command(goto="finalize", update={"messages": state["messages"] + [appended_msg], "tool_iter_counter": next_count})
                
                logger.info("No tool call detected when one was expected; forcing action.")
                return Command(goto="action", update={"messages": state["messages"] + [appended_msg], "tool_iter_counter": next_count})

    except Exception as e:
        logger.error(f"Error during router evaluation: {e}", exc_info=True)
        # Fall through to the default finalization logic in case of unexpected errors
        return Command(goto="finalize")

    # 3) Default path: If the last message from the AI has tool calls, execute them. Otherwise, we're done.
    last_message = state['messages'][-1] if state['messages'] else None
    if not isinstance(last_message, AIMessage) or not getattr(last_message, "tool_calls", None):
        logger.info("No more tool calls in the last message; proceeding to finalize.")
        return Command(goto="finalize")
    
    return Command(goto="action")