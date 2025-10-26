from datetime import datetime
from typing import List, Optional
from langchain_core.tools import tool
from src.tools.tool_types import ToolExecutionResponse
from src.tools.error_helpers import ErrorResponseBuilder
from src.services.scheduling_service import scheduling_service
from src.utils.logging import setup_logger
from enum import Enum
class DeliveryPlatform(str, Enum):
    WHATSAPP = 'whatsapp'
    TELEGRAM = 'telegram'
    EMAIL = 'email'
    imessage = 'imessage'

class FutureTaskType(str, Enum):
    ONE_TIME = 'one_time'
    RECURRING = 'recurring'
    TRIGGER = 'trigger'

logger = setup_logger(__name__)
def create_scheduling_tools(user_id: str,source:str,conversation_id:str) -> List:
    """Creates all scheduling-related tools for a given user."""

    @tool
    async def schedule_task(time_to_do: datetime, command_to_perform: str, delivery_platform: DeliveryPlatform ) -> ToolExecutionResponse:
        """
        Schedules a new task for the agent to run in the future. this is for one time future tasks.
        time_to_do: The time to run the task. this should be a timestamp in the future. If the user provides a general time, such as tomorrow morning, use your best judgement for the timestamp.
        command_to_perform: The command to perform. this should be a string that describes what the agent should do. It should be a string that describes as much as possible what the agent should do, as well as providing the parameteres provided by the user.
        delivery_platform: The platform on which the output should be sent if applicable, after the running is done. unless otherwise specified, use the same platform as the user is using to interact with the agent. Must be one of: whatsapp, telegram, email, imessage, matching the source channel unless otherwise specified.
        Note: Always assume time in EST timezone. the current EST time is provided to you in the prompt. since the times are datetime objects, add -05:00 to the end of the datetime string, so that it parses correctly.
        Note: If the user asked to be reminded of performing a task themselves, you should add the prefix "Remind user to " to the command_to_perform parameter. for example, if the user says "remind me to call John at 3pm tomorrow", you should set the command_to_perform parameter to "Remind user to call John".
        """
        from src.services.scheduling_service import scheduling_service
        logger.info(f"Scheduling task for user {user_id} at {time_to_do} with command: {command_to_perform} via {delivery_platform}")
        result = await scheduling_service.create_future_task(
            user_id=user_id,
            conversation_id=conversation_id,
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
        delivery_platform: The platform on which the output should be sent if applicable, after the running is done. unless otherwise specified, use the same platform as the user is using to interact with the agent. Must be one of: whatsapp, telegram, email, imessage, matching the source channel unless otherwise specified.
        end_time: The end time of the task. this should be a timestamp in the future. If the user does not provide a fully detailed end time, make it go on indefinitely.
        Note: Always assume time in EST timezone. since the times are datetime objects, add -05:00 to the end of the datetime string, so that it parses correctly.
        Note: If the user asked to be reminded of performing a task themselves, you should add the prefix "Remind user to " to the command_to_perform parameter. for example, if the user says "remind me to call my mom every day", you should set the command_to_perform parameter to "Remind user to call their mom".

        """
        logger.info(f"Scheduling recurring task for user {user_id} starting at {start_time} with command: {command_to_perform} via {delivery_platform} using cron: {cron_expression}")
        from src.services.scheduling_service import scheduling_service
        result = await scheduling_service.create_recurring_task(
            user_id=user_id,
            conversation_id=conversation_id,
            cron_expression=cron_expression,
            cron_description=cron_description,
            command_to_perform=command_to_perform,
            start_time=start_time,
            end_time=end_time,
            delivery_platform=delivery_platform.value,
            original_source = source,
        )
        return ToolExecutionResponse(status="success", result=result)





    # @tool
    # async def get_scheduled_tasks() -> ToolExecutionResponse:
    #     """Gets all scheduled tasks for the user."""
    #     try:
    #         tasks = await scheduling_service.get_user_tasks(user_id)
    #         if not tasks:
    #             return ToolExecutionResponse(status="success", result="You have no upcoming scheduled tasks.")
    #         # Format the tasks for better readability
    #         formatted_tasks = [
    #             {
    #                 "task_id": task.get("id"),
    #                 "description": task.get("agent_config", {}).get("description"),
    #                 "schedule": task.get("cron_description"),
    #                 "next_run": task.get("next_run").isoformat() if task.get("next_run") else "N/A"
    #             } for task in tasks
    #         ]
    #         return ToolExecutionResponse(status="success", result=formatted_tasks)
    #     except Exception as e:
    #         logger.error(f"Error in scheduling operation: {e}", exc_info=True)
    #         return ErrorResponseBuilder.from_exception(
    #             operation="scheduling_operation",
    #             exception=e,
    #             integration="scheduling_service"
    #         )
    @tool
    async def get_scheduled_tasks(future_only: bool = True, task_type: Optional[FutureTaskType] = None) -> ToolExecutionResponse:
        """Gets all scheduled, recurring, and trigger sensitive tasks for the user. 
        args:
            future_only: If true, only returns future scheduled tasks.
            task_type: If provided, filters tasks by the specified type (one_time, recurring, triggers).
        
            
        Generally, unless the user specifies otherwise, assume they want to see only future scheduled tasks.
        """
        try:
            if task_type == FutureTaskType.TRIGGER:
                # Get user triggers
                triggers = await scheduling_service.get_user_triggers(user_id)
                if not triggers:
                    return ToolExecutionResponse(status="success", result="You have no active triggers.")
                # Format the triggers for better readability
                formatted_triggers = [
                    {
                        "trigger_id": trigger.get("rule_id"),
                        "trigger_text": trigger.get("trigger_text"),
                        "created_at": trigger.get("created_at").isoformat() if trigger.get("created_at") else "N/A",
                        "is_one_time": trigger.get("is_one_time", False),
                        "status": trigger.get("status", "active")
                    } for trigger in triggers
                ]
                return ToolExecutionResponse(status="success", result=formatted_triggers)
            else:
                # Convert task_type to name filter for database query
                name_filter = None
                if task_type == FutureTaskType.ONE_TIME:
                    name_filter = ["scheduled"]
                elif task_type == FutureTaskType.RECURRING:
                    name_filter = ["recurring"]
                
                tasks = await scheduling_service.get_user_tasks_with_filter(user_id, future_only, name_filter)
                if not tasks:
                    task_scope = "upcoming" if future_only else "scheduled"
                    return ToolExecutionResponse(status="success", result=f"You have no {task_scope} scheduled tasks.")
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
            logger.error(f"Error in scheduling operation: {e}", exc_info=True)
            return ErrorResponseBuilder.from_exception(
                operation="scheduling_operation",
                exception=e,
                integration="scheduling_service"
            )

    @tool
    async def cancel_scheduled_task(task_id: str) -> ToolExecutionResponse:
        """Cancels a future scheduled task by its ID."""
        try:
            result = await scheduling_service.cancel_task(task_id)
            return ToolExecutionResponse(status="success", result=result)
        except Exception as e:
            logger.error(f"Error in scheduling operation: {e}", exc_info=True)
            return ErrorResponseBuilder.from_exception(
                operation="scheduling_operation",
                exception=e,
                integration="scheduling_service"
            )

    @tool
    async def update_scheduled_task(task_id: str, new_time: Optional[datetime] = None, new_command: Optional[str] = None) -> ToolExecutionResponse:
        """Updates the time or command for a future scheduled task."""
        try:
            result = await scheduling_service.update_task(task_id, new_time, new_command)
            return ToolExecutionResponse(status="success", result=result)
        except Exception as e:
            logger.error(f"Error in scheduling operation: {e}", exc_info=True)
            return ErrorResponseBuilder.from_exception(
                operation="scheduling_operation",
                exception=e,
                integration="scheduling_service"
            )

    @tool
    async def cancel_trigger(rule_id: str) -> ToolExecutionResponse:
        """Cancels an active trigger by its rule ID."""
        try:
            result = await scheduling_service.cancel_trigger(rule_id)
            return ToolExecutionResponse(status="success", result=result)
        except Exception as e:
            logger.error(f"Error cancelling trigger: {e}", exc_info=True)
            return ErrorResponseBuilder.from_exception(
                operation="cancel_trigger",
                exception=e,
                integration="scheduling_service"
            )

    return [schedule_task, create_recurring_future_task, get_scheduled_tasks, cancel_scheduled_task, update_scheduled_task, cancel_trigger]