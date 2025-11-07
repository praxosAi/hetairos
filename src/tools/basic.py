from datetime import datetime
import pytz
from langchain_core.tools import tool
from src.tools.tool_types import ToolExecutionResponse
from src.tools.error_helpers import ErrorResponseBuilder


def create_basic_tools(user_time_zone, tool_registry) -> list:
    """Create basic information tools"""

    @tool
    def get_current_time() -> ToolExecutionResponse:
        """Returns the current time in the user's timezone."""
        try:
            est = pytz.timezone(user_time_zone)
            current_time = datetime.now(est).strftime('%Y-%m-%d %H:%M:%S %Z%z')
            return ToolExecutionResponse(
                status="success",
                result=f"The current date and time is: {current_time}"
            )
        except Exception as e:
            return ErrorResponseBuilder.from_exception(
                operation="get_current_time",
                exception=e,
                context={"user_time_zone": user_time_zone}
            )

    @tool
    def get_current_task_plan_and_step(plan: str) -> ToolExecutionResponse:
        """Returns the current plan for performing the task, and the current step in that plan. it should be of form:
        Step 1: ... DONE
        Step 2: ... IN PROGRESS
        Step 3: ... NOT STARTED """

        return ToolExecutionResponse(
            status="success",
            result=plan
        )

    # @tool
    # def ask_user_for_missing_params(params: str, question: str) -> ToolExecutionResponse:
    #     """Ask the user for missing parameters. this is a record keeping tool. you should call it if this is the case, as it will allow you to continue and ask the user. otherwise, you will get stuck. after this, you should simply reply to the user appropriately."""

    #     return ToolExecutionResponse(
    #         status="need_user_input",
    #         result=f"To proceed, please provide the following missing parameters: {params}. Here is a question to ask the user to help you gather this information: {question} reply to the user accordingly."
    #     )

    # return [get_current_time, get_current_task_plan_and_step, ask_user_for_missing_params]
    all_tools = [get_current_time, get_current_task_plan_and_step]
    tool_registry.apply_descriptions_to_tools(all_tools)
    return all_tools
