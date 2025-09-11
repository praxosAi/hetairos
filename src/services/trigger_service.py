import logging
from typing import Dict, Any, List, Optional
from pydantic import BaseModel, Field
import uuid

from src.utils.database import db_manager
from src.core.llm_handler import LLMHandler

from src.utils.logging.base_logger import setup_logger
logger = setup_logger(__name__)

# Pydantic models for the trigger data structure
class TriggerCondition(BaseModel):
    source: str = Field(..., description="The source of the event, e.g., 'gmail', 'whatsapp'.")
    criteria: Dict[str, Any] = Field(..., description="Key-value pairs for simple filtering, e.g., {'from_email': 'boss@example.com'}.")
    llm_judge_prompt: Optional[str] = Field(None, description="An optional natural language prompt for an LLM to evaluate the event against.")

class TriggerAction(BaseModel):
    prompt: str = Field(..., description="The task or prompt for the agent to execute.")
    agent_config: Dict[str, Any] = Field(default_factory=dict, description="Specific agent configuration for this action.")

class Trigger(BaseModel):
    trigger_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    user_id: str
    name: str
    condition: TriggerCondition
    action: TriggerAction
    is_active: bool = True

class TriggerService:
    """
    Manages the creation, retrieval, and evaluation of triggers.
    """

    def __init__(self):
        self.db = db_manager.db["triggers"]
        self.llm_handler = LLMHandler()

    async def create_trigger(self, user_id: str, name: str, condition: Dict, action: Dict) -> Trigger:
        """Creates and stores a new trigger."""
        trigger = Trigger(
            user_id=user_id,
            name=name,
            condition=TriggerCondition(**condition),
            action=TriggerAction(**action)
        )
        await self.db.insert_one(trigger.dict())
        return trigger

    async def get_user_triggers(self, user_id: str, source: str) -> List[Trigger]:
        """Retrieves all active triggers for a user and a specific source."""
        cursor = self.db.find({
            "user_id": user_id,
            "condition.source": source,
            "is_active": True
        })
        triggers = await cursor.to_list(length=100)
        return [Trigger(**t) for t in triggers]

    async def evaluate_triggers(self, user_id: str, source: str, event_data: Dict) -> Optional[TriggerAction]:
        """
        Evaluates an incoming event against a user's triggers.

        Returns:
            The TriggerAction to execute if a trigger matches, otherwise None.
        """
        triggers = await self.get_user_triggers(user_id, source)
        for trigger in triggers:
            if self._matches_criteria(trigger.condition.criteria, event_data):
                if trigger.condition.llm_judge_prompt:
                    # TODO: Implement the LLM judge logic
                    pass
                else:
                    # Simple criteria match
                    return trigger.action
        return None

    def _matches_criteria(self, criteria: Dict, event_data: Dict) -> bool:
        """Checks if the event data matches the simple criteria."""
        for key, value in criteria.items():
            if event_data.get(key) != value:
                return False
        return True

trigger_service = TriggerService()
