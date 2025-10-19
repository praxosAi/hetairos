import json
from typing import Literal
from langchain_core.messages import AIMessage, ToolMessage
from langgraph.types import Command

from src.core.models.agent_runner_models import AgentState
from src.tools.tool_types import ToolExecutionResponse, ErrorDetails
from src.utils.logging import setup_logger

logger = setup_logger('should_continue_router')


def _format_error_for_ai(error_details: ErrorDetails) -> str:
    """Format error details into AI-readable guidance"""
    msg = f"**Error in {error_details.operation}**\n\n"
    msg += f"Category: {error_details.category.value}\n"
    msg += f"Message: {error_details.error_message}\n\n"

    if error_details.recovery_actions:
        msg += "**Recovery Options:**\n"
        for i, action in enumerate(error_details.recovery_actions, 1):
            msg += f"{i}. {action.description}\n"
            if action.parameters:
                msg += f"   Parameters: {action.parameters}\n"

    if error_details.technical_details:
        msg += f"\n**Technical Details:** {error_details.technical_details}\n"

    if error_details.documentation_link:
        msg += f"\n**See:** {error_details.documentation_link}\n"

    return msg


def _build_retry_message(error_details: ErrorDetails, attempt: int, max_attempts: int) -> str:
    """Build context-aware retry message for the AI"""
    if not error_details:
        return f"The last tool execution resulted in an error. Retrying with adjusted approach (attempt {attempt}/{max_attempts})..."

    msg = f"**Tool Execution Failed:** {error_details.operation}\n\n"
    msg += f"**Error Type:** {error_details.category.value}\n"
    msg += f"**Issue:** {error_details.error_message}\n\n"

    if error_details.recovery_actions:
        best_action = error_details.recovery_actions[0]
        msg += f"**Recovery Strategy:** {best_action.description}\n"

        if best_action.action_type == "fix_parameter" and best_action.parameters:
            params = best_action.parameters
            msg += f"- Need to fix parameter: '{params.get('param_name')}'\n"
            msg += f"- Expected format: {params.get('expected_format')}\n"
            msg += f"- Current value: {params.get('current_value')}\n"

        elif best_action.action_type == "verify_resource" and best_action.parameters:
            msg += f"- Resource type: {best_action.parameters.get('resource_type')}\n"
            msg += f"- Resource ID: {best_action.parameters.get('resource_id')}\n"

        if len(error_details.recovery_actions) > 1:
            msg += f"\n**Alternative approaches:**\n"
            for action in error_details.recovery_actions[1:3]:  # Show up to 2 more
                msg += f"- {action.description}\n"

    msg += f"\n**Attempt {attempt} of {max_attempts}** - Applying recovery strategy and retrying..."

    return msg


def should_continue_router(state: AgentState) -> Command[Literal["obtain_data", "action", "finalize"]]:
    """
    Enhanced router with intelligent error handling.
    Directs the graph's flow by reading context from the state's config object.
    It can jump to obtain_data (missing params), action (tool execution), or finalize.
    """
    # Access the config object from the state. This is our "toolbox".
    config = state['config']

    try:
        # Determine new messages by slicing based on the initial history length from config
        new_messages = state['messages'][config.initial_state_len:]
        last_message = state['messages'][-1] if state['messages'] else None
        logger.info(f"last message: {json.dumps(last_message.to_json()) if last_message else 'None'}")
        # --- Early exit conditions and specific routing ---
        if last_message is isinstance(last_message,AIMessage) and last_message.tool_calls:
            for tool_call in last_message.tool_calls:
                logger.info(f"tool call detected: {json.dumps(tool_call)}")
                if 'reply_to_user_on_' in tool_call.get('name') and tool_call.get('args', {}).get('final_message', True):
                    logger.info("Detected a final message sent to user; proceeding to finalize.")
                    return Command(goto="finalize")
                # Special case: Scheduled/recurring/triggered note detected
        if isinstance(last_message, AIMessage) and last_message.content and "NOTE: This command was previously" in last_message.content:
            logger.info("Detected scheduled/recurring/triggered note; proceeding to action.")
            return Command(goto="action")

        if isinstance(last_message, ToolMessage):
            # Check if the last tool call resulted in an error and if we can retry
            tool_response = last_message.content
            if isinstance(tool_response, ToolExecutionResponse) and tool_response.status == "error":
                error_details = tool_response.error_details

                # Log rich error information
                if error_details:
                    logger.warning(
                        f"Tool error detected in {error_details.operation}: "
                        f"{error_details.category.value} - {error_details.error_message}"
                    )
                else:
                    logger.warning("Tool error detected (no error_details provided)")

                # Non-retryable errors should finalize immediately
                if error_details and not error_details.is_retryable:
                    logger.warning(
                        f"Non-retryable error ({error_details.category.value}). "
                        f"Finalizing to inform user."
                    )
                    appended_msg = AIMessage(content=_format_error_for_ai(error_details))
                    return Command(
                        goto="finalize",
                        update={"messages": state["messages"] + [appended_msg]}
                    )

                # Check retry limit
                current_count = state.get("tool_iter_counter", 0)
                if current_count >= config.MAX_TOOL_ITERS:
                    logger.error(
                        f"Max retries ({config.MAX_TOOL_ITERS}) reached for error: "
                        f"{error_details.category.value if error_details else 'unknown'}"
                    )
                    if error_details:
                        final_msg = AIMessage(content=_format_error_for_ai(error_details))
                    else:
                        final_msg = AIMessage(content="Maximum retry attempts reached. Unable to complete the operation.")
                    return Command(
                        goto="finalize",
                        update={"messages": state["messages"] + [final_msg]}
                    )

                # Retryable errors - build smart retry message with recovery guidance
                next_count = current_count + 1
                if error_details:
                    retry_msg = _build_retry_message(error_details, next_count, config.MAX_TOOL_ITERS)

                    # Log retry with delay if specified
                    if error_details.retry_after_seconds:
                        logger.info(
                            f"Retrying after {error_details.retry_after_seconds}s "
                            f"(rate limit/service issue). Attempt {next_count}/{config.MAX_TOOL_ITERS}"
                        )
                        # Note: Actual delay implementation would go here if needed
                    else:
                        logger.info(f"Retrying with recovery strategy. Attempt {next_count}/{config.MAX_TOOL_ITERS}")
                else:
                    retry_msg = f"The last tool execution resulted in an error. Retrying with adjusted approach (attempt {next_count}/{config.MAX_TOOL_ITERS})..."
                    logger.warning(f"Retrying without error_details. Attempt {next_count}/{config.MAX_TOOL_ITERS}")

                return Command(
                    goto="action",
                    update={"messages": state["messages"] + [AIMessage(content=retry_msg)], "tool_iter_counter": next_count},
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