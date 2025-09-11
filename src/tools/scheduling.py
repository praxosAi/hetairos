from datetime import datetime
from typing import List, Optional
from langchain_core.tools import tool
from src.tools.tool_types import ToolExecutionResponse
from src.services.scheduling_service import scheduling_service
from enum import Enum
class DeliveryPlatform(str, Enum):
    WHATSAPP = 'whatsapp'
    TELEGRAM = 'telegram'
    EMAIL = 'email'
def create_scheduling_tools(user_id: str,source:str) -> List:
    """Creates all scheduling-related tools for a given user."""

    @tool
    async def schedule_task(time_to_do: datetime, command_to_perform: str, delivery_platform: DeliveryPlatform ) -> ToolExecutionResponse:
        """
        Schedules a new task for the agent to run in the future. this is for one time future tasks.
        time_to_do: The time to run the task. this should be a timestamp in the future. If the user provides a general time, such as tomorrow morning, use your best judgement for the timestamp.
        command_to_perform: The command to perform. this should be a string that describes what the agent should do. It should be a string that describes as much as possible what the agent should do, as well as providing the parameteres provided by the user.
        delivery_platform: The platform on which the output should be sent if applicable, after the running is done. unless otherwise specified, use the same platform as the user is using to interact with the agent.
        Note: Always assume time in EST timezone. the current EST time is provided to you in the prompt. since the times are datetime objects, add -05:00 to the end of the datetime string, so that it parses correctly.
        """
        from src.services.scheduling_service import scheduling_service
        result = await scheduling_service.create_future_task(
            user_id=user_id,
            time_to_do=time_to_do,
            command_to_perform=command_to_perform,
            delivery_platform=delivery_platform.value,
            original_source= source
        )
        return ToolExecutionResponse(status="success", result=result)

    @tool
    async def create_recurring_future_task(cron_expression: str, cron_description: str, command_to_perform: str, start_time: datetime,  delivery_platform: DeliveryPlatform, end_time: datetime = None) -> ToolExecutionResponse:
        """
        Schedules a new task for the agent to run in the future. this is for recurring future tasks.
        cron_expression: The cron expression to run the task. This should be a string in cron format.
        cron_description: A natural language description of how often the task should run, for example "every day at 9am" or "every week on monday at 10am".
        command_to_perform: The command to perform. this should be a string that describes what the agent should do. It should be a string that describes as much as possible what the agent should do, as well as providing the parameteres provided by the user.
        start_time: The start time of the task. this should be a timestamp in the future. If the user does not provide a fully detailed start time, use your best judgement for the timestamp.
        delivery_platform: The platform on which the output should be sent if applicable, after the running is done. unless otherwise specified, use the same platform as the user is using to interact with the agent.
        end_time: The end time of the task. this should be a timestamp in the future. If the user does not provide a fully detailed end time, make it go on indefinitely.
        Note: Always assume time in EST timezone. since the times are datetime objects, add -05:00 to the end of the datetime string, so that it parses correctly.
        """
        from src.services.scheduling_service import scheduling_service
        result = await scheduling_service.create_recurring_task(
            user_id=user_id,
            cron_expression=cron_expression,
            cron_description=cron_description,
            command_to_perform=command_to_perform,
            start_time=start_time,
            end_time=end_time,
            delivery_platform=delivery_platform.value,
            original_source = source
        )
        return ToolExecutionResponse(status="success", result=result)

    @tool
    async def get_scheduled_tasks() -> ToolExecutionResponse:
        """Gets all future scheduled tasks for the user."""
        try:
            tasks = await scheduling_service.get_user_tasks(user_id)
            if not tasks:
                return ToolExecutionResponse(status="success", result="You have no upcoming scheduled tasks.")
            # Format the tasks for better readability
            formatted_tasks = [
                {
                    "task_id": task.get("id"),
                    "description": task.get("agent_config", {}).get("description"),
                    "schedule": task.get("cron_description"),
                    "next_run": task.get("next_run").isoformat() if task.get("next_run") else "N/A"
                } for task in tasks
            ]
            return ToolExecutionResponse(status="success", result=formatted_tasks)
        except Exception as e:
            return ToolExecutionResponse(status="error", system_error=str(e))

    @tool
    async def cancel_scheduled_task(task_id: str) -> ToolExecutionResponse:
        """Cancels a future scheduled task by its ID."""
        try:
            result = await scheduling_service.cancel_task(task_id)
            return ToolExecutionResponse(status="success", result=result)
        except Exception as e:
            return ToolExecutionResponse(status="error", system_error=str(e))

    @tool
    async def update_scheduled_task(task_id: str, new_time: Optional[datetime] = None, new_command: Optional[str] = None) -> ToolExecutionResponse:
        """Updates the time or command for a future scheduled task."""
        try:
            result = await scheduling_service.update_task(task_id, new_time, new_command)
            return ToolExecutionResponse(status="success", result=result)
        except Exception as e:
            return ToolExecutionResponse(status="error", system_error=str(e))

    return [schedule_task, create_recurring_future_task, get_scheduled_tasks, cancel_scheduled_task, update_scheduled_task]