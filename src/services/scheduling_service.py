import logging
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
from bson import ObjectId
from croniter import croniter
from src.utils.database import db_manager
from src.core.event_queue import event_queue
from src.utils.logging.base_logger import setup_logger
from typing import List, Dict, Optional
logger = setup_logger(__name__)

from src.services.user_service import user_service
from datetime import datetime, timezone, timedelta

from src.utils.timezone_utils import to_utc, to_ZoneInfo

def get_next_run_time_utc(cron_expression: str, timezone: str|ZoneInfo, base_time_delay:timedelta = timedelta()) -> datetime:
    """
    Given a cron expression and a base time, returns the next run time as a datetime object.
    """


    if isinstance(timezone, str):
        zoneinfo = to_ZoneInfo(timezone)
    else:
        zoneinfo = timezone

    base_time = datetime.now(zoneinfo) + base_time_delay
    cron = croniter(cron_expression, base_time)
    next_run_time = cron.get_next(datetime)
    return to_utc(next_run_time, zoneinfo)

class SchedulingService:
    """
    Provides tools for the agent to schedule one time future tasks and recurring future tasks.
    """
    async def create_future_task(self, user_id: str,conversation_id:str, time_to_do: str, command_to_perform: str, delivery_platform: str = None, original_source: str = 'whatsapp') -> str:
        """
        Creates a new scheduled task for the agent. this is to be used for one time future tasks.
        """
        try:
            ## convert the EST time to UTC time.
            if delivery_platform is None:
                delivery_platform = original_source
            task_id = f"task_{user_id}_{datetime.utcnow().timestamp()}"
            user_preferences = user_service.get_user_preferences(user_id)    
            timezone_name = user_preferences.get('timezone', 'America/New_York') if user_preferences else 'America/New_York'
            time_to_do = to_utc(time_to_do, timezone_name)
            await db_manager.create_scheduled_task(
                task_id=task_id,
                user_id=user_id,
                conversation_id=conversation_id,
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
                "metadata": {"task_id": task_id, 'output_type': delivery_platform, 'original_source': original_source, 'source': original_source, 'source_flag': f"{original_source}_future", 'conversation_id': conversation_id},
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


    async def create_recurring_task(self, user_id: str, conversation_id: str, cron_expression: str, cron_description: str, command_to_perform: str, start_time: datetime, end_time: datetime = None, delivery_platform: str = None,original_source: str = None) -> str:
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
            if delivery_platform is None:
                delivery_platform = original_source
            task_id = f"task_{user_id}_{datetime.utcnow().timestamp()}"
            user_preferences = user_service.get_user_preferences(user_id)    
            timezone_name = user_preferences.get('timezone', 'America/New_York') if user_preferences else 'America/New_York'
            logger.info(f"User {user_id} timezone: {timezone_name}")
            zoneinfo = to_ZoneInfo(timezone_name)

            start_time = to_utc(start_time, zoneinfo)
            if not croniter.is_valid(cron_expression):
                logger.error(f"Invalid cron expression: {cron_expression}")
                return "Invalid cron expression."
            
            next_run_time = get_next_run_time_utc(cron_expression, zoneinfo)

            await db_manager.create_scheduled_task(
                task_id=task_id,
                user_id=user_id,
                conversation_id=conversation_id,
                task_type="recurring",
                cron_expression=cron_expression,
                task_data={'description': command_to_perform},
                cron_description=cron_description,
                command=command_to_perform,
                start_time=start_time,
                end_time=end_time,
                next_execution=next_run_time,
                run_count=0,
                delivery_platform=delivery_platform,
                original_source = original_source
            )

            event = {
                "user_id": str(user_id),
                "source": "recurring",
                "payload": {"text": command_to_perform},
                "metadata": {"task_id": task_id,'output_type': delivery_platform, 'original_source':original_source, 'source': original_source, 'source_flag': f"{original_source}_recurring",'conversation_id': conversation_id},
                "output_type": delivery_platform
            }
            await event_queue.publish_scheduled_event(
                event=event,
                timestamp=next_run_time
            )
            return f"Task scheduled successfully. Next run at {next_run_time.isoformat()}, happening every {cron_expression}"

        except Exception as e:
            logger.error(f"Failed to create schedule for user {user_id}: {e}")
            return "Failed to create schedule."
    
    async def schedule_next_run(self,event: Dict) -> str:
        task_id = event['metadata']['task_id']
        #get task from database.
        task = await db_manager.get_scheduled_task(task_id)
        if not task:
            return "Task not found."
        
        cron_expression = task['cron_expression']

        if not cron_expression or cron_expression == 'ONE-TIME':
            logger.error(f"Task {task_id} is not recurring.")
            return "Task is not recurring."
        ## validate the cron expression.
        if not croniter.is_valid(cron_expression):
            logger.error(f"Invalid cron expression: {cron_expression}")
            return "Invalid cron expression."
        #get the next run time for the task.
        
        user_id = str(task['user_id'])
        user_preferences = user_service.get_user_preferences(user_id)    
        timezone_name = user_preferences.get('timezone', 'America/New_York') if user_preferences else 'America/New_York'
        logger.info(f"User {user_id} timezone: {timezone_name}")
        zoneinfo = to_ZoneInfo(timezone_name)
        next_run_time = get_next_run_time_utc(cron_expression, zoneinfo, timedelta(seconds=5))
        ## schedule the next run.
        await db_manager.update_task_execution(task_id, next_run_time)
        new_event = {
            "user_id": user_id,
            "source": "recurring",
            "payload": {"text": task['command']},
            "metadata": event['metadata'],
            
        }
        if event.get('output_type'):
            new_event['output_type'] = event['output_type']
        await event_queue.publish_scheduled_event(
            event=new_event,
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

    async def get_user_future_tasks(self, user_id: str, name_filter: Optional[List[str]] = None) -> List[Dict]:
        """Gets all future scheduled tasks for a user."""
        try:
            tasks = await db_manager.get_future_tasks(user_id, name_filter)
            return tasks
        except Exception as e:
            logger.error(f"Failed to get future tasks for user {user_id}: {e}")
            return []

    async def get_user_tasks_with_filter(self, user_id: str, future_only: bool = True, name_filter: Optional[List[str]] = None) -> List[Dict]:
        """Gets scheduled tasks for a user with filtering options."""
        try:
            if future_only:
                tasks = await db_manager.get_future_tasks(user_id, name_filter)
            else:
                # For all tasks, we need to apply name_filter manually since get_user_tasks doesn't support it
                all_tasks = await db_manager.get_user_tasks(user_id)
                if name_filter:
                    # Normalize name_filter to list
                    if isinstance(name_filter, str):
                        filter_names = [name_filter]
                    else:
                        filter_names = name_filter
                    # Filter tasks by name
                    tasks = [task for task in all_tasks if task.get("name") in filter_names]
                else:
                    tasks = all_tasks
            return tasks
        except Exception as e:
            logger.error(f"Failed to get tasks for user {user_id}: {e}")
            return []

    async def get_user_triggers(self, user_id: str) -> List[Dict]:
        """Gets all active triggers for a user."""
        try:
            triggers = await db_manager.get_user_triggers(user_id)
            return triggers
        except Exception as e:
            logger.error(f"Failed to get triggers for user {user_id}: {e}")
            return []

    async def cancel_trigger(self, rule_id: str) -> str:
        """Cancels a trigger by its rule_id."""
        try:
            await db_manager.deactivate_trigger(rule_id)
            return f"Trigger {rule_id} cancelled successfully."
        except Exception as e:
            logger.error(f"Failed to cancel trigger {rule_id}: {e}")
            return "Failed to cancel trigger."

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
                update_data["next_execution"] = to_utc(new_time)
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
