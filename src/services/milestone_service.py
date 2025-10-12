from bson import ObjectId
from pyparsing import Enum
from datetime import datetime
from src.utils.logging.base_logger import setup_logger
from pymongo.errors import PyMongoError
from src.utils.database import db_manager

logger = setup_logger(__name__)

class MilestoneType(str, Enum):
    """Milestone types"""
    MESSAGING = "messaging"

class MilestoneService:
    
    def __init__(self):
        self.milestone_collection = db_manager.db["milestones"]

    async def _create_milestone(self, user_id:str|ObjectId, milestone_type:MilestoneType, current_step:int=0):
        """Create a new milestone for a user"""
        try:
            try:
                user_object_id = ObjectId(user_id)
            except Exception:
                logger.error(f"Invalid ObjectId format: {user_id}")
                return None

            # Create new milestone with initial values
            now = datetime.utcnow()
            milestone_data = {
                "user_id": user_object_id,
                "type": milestone_type.value,
                "current_step": current_step,
                "step_history": [] if current_step == 0 else [{"step": current_step, "completed_at": now}],
                "created_at": now,
                "updated_at": now
            }

            # Insert into database
            result = await self.milestone_collection.insert_one(milestone_data)

            if result.inserted_id:
                milestone_data['_id'] = result.inserted_id
                logger.info(f"Created milestone {milestone_data['_id']} of type {milestone_type.value} for user {user_id}")
                return milestone_data
            else:
                logger.error(f"Failed to create milestone for user {user_id}")
                return None

        except PyMongoError as e:
            logger.error(f"Database error creating milestone for user {user_id}: {e}")
            return None
        except Exception as e:
            logger.error(f"Unexpected error creating milestone for user {user_id}: {e}")
            return None
        
    
    async def _set_milestone_step(self, user_id:str|ObjectId, milestone_type:MilestoneType, new_step):
        """Set the current step of a milestone"""
        milestone = await self.milestone_collection.find_one({
            "user_id": ObjectId(user_id),
            "type": milestone_type.value
        })

        if not milestone:
            milestone = await self._create_milestone(user_id, MilestoneType.MESSAGING, new_step)
            return
        
        if milestone['current_step'] >= new_step:
            return

        now = datetime.utcnow()
        await self.milestone_collection.update_one(
            {
                "_id": ObjectId(id),
                "current_step": {"$lt": new_step}
            },
            {
                "$set": {
                    "current_step": new_step,
                    "updated_at": now
                },
                "$push": {
                    "step_history": {
                        "step": new_step,
                        "completed_at": now
                    }
                }
            }
        )
        logger.info(f"Updated milestone {milestone['_id']} to step {new_step} for user {user_id}")

    async def user_setup_messaging(self, user_id:str|ObjectId):
        """Set up messaging milestone for a user"""
        await self._set_milestone_step(user_id, MilestoneType.MESSAGING, 3)
    
    async def user_send_message(self, user_id:str|ObjectId):
        """Update milestone when user sends first message"""
        await self._set_milestone_step(user_id, MilestoneType.MESSAGING, 4)
        
    
milestone_service = MilestoneService()