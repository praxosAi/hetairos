from datetime import datetime
import pytz
from langchain_core.tools import tool
from src.tools.tool_types import ToolExecutionResponse


def create_basic_tools(user_time_zone) -> list:
    """Create basic information tools"""
    

    
    @tool
    def get_current_time() -> str:
        """Returns the current time in EST timezone."""
        est = pytz.timezone(user_time_zone)
        return "the current date and time, in NYC, is: " + datetime.now(est).strftime('%Y-%m-%d %H:%M:%S %Z%z')
    

    @tool
    def get_current_task_plan_and_step(plan: str) -> str:
        """Returns the current plan for performing the task, and the current step in that plan. it should be of form:
        Step 1: ... DONE
        Step 2: ... IN PROGRESS
        Step 3: ... NOT STARTED """
        
        return ToolExecutionResponse(
            status="success",
            result=plan
            )

    return [get_current_time,get_current_task_plan_and_step]
