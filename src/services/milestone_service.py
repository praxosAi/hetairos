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

    def _create_milestone(self, user_id:str|ObjectId, milestone_type:MilestoneType):
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
                "current_step": 0,
                "step_history": [],
                "created_at": now,
                "updated_at": now
            }

            # Insert into database
            result = self.milestone_collection.insert_one(milestone_data)

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
        
    
    def _set_milestone_step(self, id:str|ObjectId, new_step:int):
        """Set the current step of a milestone"""
        now = datetime.utcnow()
        self.collection.find_one_and_update(
            {
                "id": ObjectId(id),
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

    # @todo make them async 
    def user_setup_messaging(self, user_id:str|ObjectId):
        """Set up messaging milestone for a user"""
        milestone = self.milestone_collection.find_one({
            "user_id": ObjectId(user_id),
            "type": MilestoneType.MESSAGING.value
        })
        
        if not milestone:
            self._create_milestone(user_id, MilestoneType.MESSAGING)

        self._set_milestone_step(milestone['_id'], 3)
    
    # @todo make them async 
    def user_send_message(self, user_id:str|ObjectId):
        """Update milestone when user sends first message"""
        milestone = self.milestone_collection.find_one({
            "user_id": ObjectId(user_id),
            "type": MilestoneType.MESSAGING.value
        })
        
        if not milestone:
            self._create_milestone(user_id, MilestoneType.MESSAGING)
        self._set_milestone_step(milestone['_id'], 4)
        
    
milestone_service = MilestoneService()