import logging
from datetime import datetime, timezone
from croniter import croniter
from src.utils.database import db_manager
from src.core.event_queue import event_queue
from src.utils.logging.base_logger import setup_logger
from typing import List, Dict, Optional
logger = setup_logger(__name__)
from zoneinfo import ZoneInfo # Use this for Python 3.9+

from datetime import datetime, timezone, timedelta


def nyc_to_utc(nyc_dt: datetime) -> datetime:
    """
    Converts a naive datetime object from NYC time to UTC.

    This function correctly handles both Standard Time (EST, UTC-5) and
    Daylight Saving Time (EDT, UTC-4) by using the 'America/New_York'
    timezone database.
    """
    # Define the New York timezone using the IANA database
    nyc_tz = ZoneInfo("America/New_York")
    
    # Localize the naive datetime by applying the NYC timezone.
    # This step correctly determines whether the datetime falls in EST or EDT.
    aware_nyc_dt = nyc_dt.replace(tzinfo=nyc_tz)
    
    # Convert the timezone-aware NYC datetime to UTC
    utc_dt = aware_nyc_dt.astimezone(timezone.utc)
    
    return utc_dt

class SchedulingService:
    """
    Provides tools for the agent to schedule one time future tasks and recurring future tasks.
    """
    async def create_future_task(self, user_id: str, time_to_do: str, command_to_perform: str, delivery_platform: str = "whatsapp", original_source: str = 'whatsapp') -> str:
        """
        Creates a new scheduled task for the agent. this is to be used for one time future tasks.
        """
        try:
            ## convert the EST time to UTC time.

            task_id = f"task_{user_id}_{datetime.utcnow().timestamp()}"
            time_to_do = nyc_to_utc(time_to_do)
            await db_manager.create_scheduled_task(
                task_id=task_id,
                user_id=user_id,
                task_type="scheduled",
                cron_expression='ONE-TIME',
                task_data={'description': command_to_perform},
                cron_description='One time task',
                command=command_to_perform,
                next_execution=time_to_do,
                start_time=time_to_do,
                end_time=None,
                run_count=0,
                delivery_platform=delivery_platform,
                original_source = original_source
            )

            
            event = {
                "user_id": str(user_id),
                "source": "scheduled",
                "payload": {"text": command_to_perform},
                "metadata": {"task_id": task_id, 'output_type': delivery_platform, 'original_source': original_source, 'source': original_source + '_recurring'},
                "output_type": delivery_platform
            }
            logger.info(f"Publishing scheduled event for user {user_id} at {time_to_do.isoformat()}")
            await event_queue.publish_scheduled_event(
                event=event,
                timestamp=time_to_do
            )
            ### now, we should put it on the event queue to be executed, at a later time.
            return f"Task scheduled successfully. Next run at {time_to_do.isoformat()}."
        


        except Exception as e:
            logger.error(f"Failed to create future task for user {user_id}: {e}")
            return "Failed to create schedule."

        
    async def create_recurring_task(self, user_id: str, cron_expression: str, cron_description: str, command_to_perform: str, start_time: datetime, end_time: datetime = None, delivery_platform: str = "whatsapp",original_source: str = 'whatsapp') -> str:
        """
        Creates a new scheduled task for the agent. this is to be used for recurring future tasks.

        Args:
            user_id: The ID of the user for whom the task is scheduled.
            cron_expression: The cron expression for the schedule.
            task_description: A natural language description of the task.
            agent_config: The configuration for the agent to run.

        Returns:
            A confirmation message.
        """
        try:
            # Validate the cron expression
            # base_time = datetime.utcnow()
            # if not croniter.is_valid(cron_expression):
            #     return "Invalid cron expression."
            # cron = croniter(cron_expression, base_time)
            # next_run_time = cron.get_next(datetime)

            task_id = f"task_{user_id}_{datetime.utcnow().timestamp()}"
            start_time = nyc_to_utc(start_time)
            base_time = datetime.utcnow()
            if not croniter.is_valid(cron_expression):
                logger.error(f"Invalid cron expression: {cron_expression}")
                return "Invalid cron expression."
            cron = croniter(cron_expression, base_time)
            next_run_time = cron.get_next(datetime)
            await db_manager.create_scheduled_task(
                task_id=task_id,
                user_id=user_id,
                task_type="recurring",
                cron_expression=cron_expression,
                task_data={'description': command_to_perform},
                cron_description=cron_description,
                command=command_to_perform,
                start_time=start_time,
                end_time=end_time,
                next_execution=start_time,
                run_count=0,
                delivery_platform=delivery_platform,
                original_source = original_source
            )
            event = {
                "user_id": str(user_id),
                "source": "recurring",
                "payload": {"text": command_to_perform},
                "metadata": {"task_id": task_id,'output_type': delivery_platform, 'original_source':original_source, 'source': original_source + '_recurring'},
                "output_type": delivery_platform
            }
            await event_queue.publish_scheduled_event(
                event=event,
                timestamp=start_time
            )
            return f"Task scheduled successfully. Next run at {start_time.isoformat()}, happening every {cron_expression}"

        except Exception as e:
            logger.error(f"Failed to create schedule for user {user_id}: {e}")
            return "Failed to create schedule."
    async def schedule_next_run(self,  task_id: str) -> str:
        ## get current date time.
        current_time = datetime.utcnow() + timedelta(seconds=5)
        #get task from database.
        task = await db_manager.get_scheduled_task(task_id)
        if not task:
            return "Task not found."
        ## validate the cron expression.
        if not croniter.is_valid(task.cron_expression):
            logger.error(f"Invalid cron expression: {task.cron_expression}")
            return "Invalid cron expression."
        #get the next run time for the task.
        next_run_time = croniter(task.cron_expression, current_time).get_next(datetime)
        ## schedule the next run.
        await db_manager.update_task_execution(task_id, next_run_time)
        event = {
            "user_id": str(task.user_id),
            "source": "recurring",
            "payload": {"text": task.command},
            "metadata": event['metadata']
        }
        await event_queue.publish_scheduled_event(
            event=event,
            timestamp=next_run_time
        )
        return f"Next run scheduled successfully at {next_run_time.isoformat()}."

    async def get_user_tasks(self, user_id: str) -> List[Dict]:
        """Gets all future scheduled tasks for a user."""
        try:
            tasks = await db_manager.get_user_tasks(user_id)
            return tasks
        except Exception as e:
            logger.error(f"Failed to get tasks for user {user_id}: {e}")
            return []

    async def cancel_task(self, task_id: str) -> str:
        """Cancels a scheduled task."""
        try:
            await db_manager.deactivate_task(task_id)
            # We should also remove it from the event queue, but that's a more complex operation.
            # Deactivating it in the DB will prevent it from running again.
            return f"Task {task_id} cancelled successfully."
        except Exception as e:
            logger.error(f"Failed to cancel task {task_id}: {e}")
            return "Failed to cancel task."

    async def update_task(self, task_id: str, new_time: Optional[datetime] = None, new_command: Optional[str] = None) -> str:
        """Updates a scheduled task."""
        try:
            update_data = {}
            if new_time:
                update_data["next_execution"] = nyc_to_utc(new_time)
            if new_command:
                update_data["command"] = new_command
            
            if not update_data:
                return "No updates provided."

            await db_manager.update_task(task_id, update_data)
            return f"Task {task_id} updated successfully."
        except Exception as e:
            logger.error(f"Failed to update task {task_id}: {e}")
            return "Failed to update task."

    async def verify_task_active(self, task_id: str) -> bool:
        """Verifies if a scheduled task is active."""
        task = await db_manager.get_scheduled_task(task_id)
        if not task:
            return False
        return task.get('is_active')

scheduling_service = SchedulingService()
