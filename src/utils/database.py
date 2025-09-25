
import logging
from src.config.settings import settings
import motor.motor_asyncio
import json
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
from bson import ObjectId
from pymongo.errors import OperationFailure
from pymongo import UpdateOne
from src.config.settings import settings
from src.utils.logging.base_logger import setup_logger
from src.services.ai_service.ai_service import ai_service
class ConversationDatabase:
    def __init__(self, connection_string: str = settings.MONGO_CONNECTION_STRING, db_name: str = settings.MONGO_DB_NAME):
        self.client = motor.motor_asyncio.AsyncIOMotorClient(connection_string)
        self.db = self.client[db_name]
        self.conversations = self.db["conversations"]
        self.users = self.db["users"]
        self.messages = self.db["messages"]
        self.search_attempts = self.db["search_attempts"]
        self.message_status = self.db["message_status"]
        self.logger = setup_logger(__name__)


    async def _create_index_if_not_exists(self, collection, keys, **kwargs):
        """Helper to create an index and ignore NamespaceExists error."""
        try:
            await collection.create_index(keys, **kwargs)
        except OperationFailure as e:
            if e.code != 48: # NamespaceExists error code
                raise

    async def init_database(self):
        """Initialize indexes for collections."""
        # Index for finding active conversations for a user, sorted by recent activity
        await self._create_index_if_not_exists(self.conversations, [("user_id", 1), ("status", 1), ("last_activity", -1)])
        
        # Existing indexes
        await self._create_index_if_not_exists(self.conversations, [("last_activity", 1)])
        await self._create_index_if_not_exists(self.messages, [("conversation_id", 1)])
        await self._create_index_if_not_exists(self.search_attempts, [("conversation_id", 1)])
        await self._create_index_if_not_exists(self.message_status, [("message_id", 1)])

    async def store_message_status(self, message_id: str, conversation_id: str, platform: str, 
                                   status: str, error_info: str = None):
        """Store message delivery status."""
        await self.message_status.insert_one({
            "message_id": message_id,
            "conversation_id": conversation_id,
            "platform": platform,
            "status": status,
            "error_info": error_info,
            "timestamp": datetime.utcnow()
        })

    async def get_message_status(self, message_id: str) -> Optional[Dict]:
        """Get message delivery status."""
        return await self.message_status.find_one(
            {"message_id": message_id},
            sort=[("timestamp", -1)]
        )

    async def get_failed_messages(self, conversation_id: str) -> List[Dict]:
        """Get failed messages for retry."""
        cursor = self.message_status.find({
            "conversation_id": conversation_id,
            "status": "failed"
        }).sort("timestamp", -1)
        return await cursor.to_list(length=100)

    async def create_conversation(self, user_id: str, platform: str) -> str:
        """Create a new conversation and return its ID."""
        result = await self.conversations.insert_one({
            "user_id": ObjectId(user_id),
            "platform": platform,
            "start_time": datetime.utcnow(),
            "last_activity": datetime.utcnow(),
            "status": "active",
            "metadata": {}
        })
        return str(result.inserted_id)

    async def get_active_conversation(self, user_id: str) -> Optional[str]:
        """Get the active conversation ID for a user."""
        convo = await self.conversations.find_one(
            {"user_id": ObjectId(user_id), "status": "active"},
            sort=[("last_activity", -1)]
        )
        return str(convo["_id"]) if convo else None

    async def get_conversation_info(self, conversation_id: str) -> Optional[Dict]:
        """Get conversation information by ID."""
        return await self.conversations.find_one({"_id": ObjectId(conversation_id)})

    async def update_conversation_praxos_source_id(self, conversation_id: str, source_id: str):
        """Update the Praxos source ID for a conversation."""
        await self.conversations.update_one(
            {"_id": ObjectId(conversation_id)},
            {"$set": {"praxos_source_id": source_id}}
        )

    async def add_message(self, conversation_id: str, role: str, content: str, 
                           message_type: str = 'text', metadata: Dict = None) -> str:
        """Add a message to a conversation and update last_activity."""
        if metadata is None:
            metadata = {}
        
        message_doc = {
            "conversation_id": conversation_id,
            "role": role,
            "content": content,
            "message_type": message_type,
            "metadata": metadata,
            "timestamp": datetime.utcnow()
        }
        result = await self.messages.insert_one(message_doc)
        
        await self.conversations.update_one(
            {"_id": ObjectId(conversation_id)},
            {"$set": {"last_activity": datetime.utcnow()}}
        )
        return str(result.inserted_id)
    async def get_conversation_messages(self, conversation_id: str, limit: int = 50) -> List[Dict]:
        """Get messages for a conversation, ordered by timestamp."""
        cursor = self.messages.find(
            {"conversation_id": conversation_id}
        ).sort("timestamp", 1)
        return await cursor.to_list()

    
    async def bulk_update_messages(self, messages_dict: Dict[str, Any]):
        """Bulk update multiple messages."""
        if not messages_dict:
            return
        
        operations = []
        for msg_id, update_fields in messages_dict.items():
            operations.append(
                UpdateOne(
                    {"_id": ObjectId(msg_id)},
                    {"$set": update_fields}
                )
            )
        if operations:
            result = await self.messages.bulk_write(operations)
            return result
            # self.logger.info(f"Bulk updated {result.modified_count} messages.")
        return None
        # return result.modified_count
    async def record_search_attempt(self, conversation_id: str, query: str, search_type: str, 
                                     success: bool, error_type: Optional[str] = None, 
                                     results_count: int = 0, metadata: Dict = None) -> str:
        """Record a search attempt."""
        if metadata is None:
            metadata = {}
        
        result = await self.search_attempts.insert_one({
            "conversation_id": conversation_id,
            "query": query,
            "search_type": search_type,
            "success": success,
            "error_type": error_type,
            "results_count": results_count,
            "metadata": metadata,
            "timestamp": datetime.utcnow()
        })
        return str(result.inserted_id)

    async def get_recent_search_attempts(self, conversation_id: str, limit: int = 5) -> List[Dict]:
        """Get recent search attempts for a conversation."""
        cursor = self.search_attempts.find(
            {"conversation_id": conversation_id}
        ).sort("timestamp", -1).limit(limit)
        return await cursor.to_list(length=limit)

    async def mark_conversation_for_consolidation(self, conversation_id: str):
        """Mark a conversation as ready for consolidation."""
        await self.conversations.update_one(
            {"_id": ObjectId(conversation_id)},
            {"$set": {"status": "ready_for_consolidation"}}
        )

    async def get_conversations_to_consolidate(self) -> List[Dict]:
        """Get conversations that are ready for consolidation."""
        cursor = self.conversations.find(
            {"status": "ready_for_consolidation"}
        ).sort("last_activity", 1)
        return await cursor.to_list(length=100)

    async def mark_conversation_consolidated(self, conversation_id: str):
        """Mark a conversation as consolidated."""
        try:
            result = await self.conversations.update_one(
                {"_id": ObjectId(conversation_id)},
                {"$set": {"status": "consolidated"}}
            )
            if result.modified_count > 0:
                self.logger.info(f"Successfully marked conversation {conversation_id} as consolidated.")
                return True
            else:
                self.logger.warning(f"Attempted to mark conversation {conversation_id} as consolidated, but no document was modified.")
                return False
        except Exception as e:
            self.logger.error(f"Failed to mark conversation {conversation_id} as consolidated. Error: {e}")
            raise
    async def get_user_by_phone(self, phone_number: str) -> Optional[Dict]:
        """Get a user by phone number."""
        return await self.users.find_one({"phone_number": phone_number})
    
    async def is_conversation_expired(self, conversation_id: str, timeout_minutes:int,payload:dict) -> bool:
        """Check if a conversation has exceeded the inactivity timeout."""
        conversation = await self.get_conversation_info(conversation_id)

        if not conversation:
            return True
        
        last_activity = conversation['last_activity']
        timeout_delta = timedelta(minutes=timeout_minutes)
        messages = await self.get_conversation_messages(conversation_id,6)
        if (datetime.utcnow() - last_activity) > timeout_delta:
            if not payload:
                return True
            ## here, we will add further intelligence.
            prompt = f"User has been inactive for {timeout_minutes} minutes."
            if messages:
                prompt += " Recent messages include: "
                for msg in messages:
                    prompt += f"{msg['role']}: {msg['content']}\n"
            prompt += f" New incoming message: {json.dumps(payload,default=str)}."

            prompt += " Based on the recent conversation context, determine if this new message is a continuation of the previous conversation or a new topic. If it's a continuation, return False. If it's a new topic, return True."
            prompt += "Consider the time, as well as the relation between the recent previous messages and the new message."
            response = await ai_service.boolean_call(prompt, False)
            return response
            
            # You can use the prompt for further processing or logging
        return False

    async def cleanup_old_conversations(self, days_old: int = 30):
        """Clean up conversations older than specified days."""
        cutoff_date = datetime.utcnow() - timedelta(days=days_old)
        
        # Find old, consolidated conversations
        old_convos_cursor = self.conversations.find({
            "last_activity": {"$lt": cutoff_date},
            "status": "consolidated"
        })
        old_convo_ids = [str(c["_id"]) async for c in old_convos_cursor]
        
        if old_convo_ids:
            # Delete associated data
            await self.search_attempts.delete_many({"conversation_id": {"$in": old_convo_ids}})
            await self.messages.delete_many({"conversation_id": {"$in": old_convo_ids}})
            
            # Delete the conversations themselves
            await self.conversations.delete_many({"_id": {"$in": [ObjectId(cid) for cid in old_convo_ids]}})

# Global conversation database instance
conversation_db = ConversationDatabase()

class DatabaseManager:
    """Handles persistent storage for system/infrastructure data using MongoDB."""
    
    def __init__(self, connection_string: str = settings.MONGO_CONNECTION_STRING, db_name: str = settings.MONGO_DB_NAME):
        self.client = motor.motor_asyncio.AsyncIOMotorClient(connection_string)
        self.db = self.client[db_name]
        self.integrations = self.db["integrations"]
        self.integration_tokens = self.db["integration_tokens"]
        self.rate_limits = self.db["rate_limits"]
        self.agent_schedules = self.db["agent_schedules"]
        self.documents = self.db["documents"]

    async def _create_index_if_not_exists(self, collection, keys, **kwargs):
        """Helper to create an index and ignore NamespaceExists error."""
        try:
            await collection.create_index(keys, **kwargs)
        except OperationFailure as e:
            # Error code 48 is NamespaceExists, which can happen in Cosmos DB
            # when the collection already exists. We can safely ignore it.
            if e.code != 48:
                raise

    async def initialize(self):
        """MongoDB is schema-less, so we just need to ensure indexes if needed."""
        await self._create_index_if_not_exists(self.integrations, [("user_id", 1), ("type", 1)], unique=True)
        await self._create_index_if_not_exists(self.integration_tokens, [("user_id", 1), ("provider", 1)], unique=True)
        await self._create_index_if_not_exists(self.rate_limits, [("user_id", 1), ("resource_type", 1), ("reset_date", 1)], unique=True)
        await self._create_index_if_not_exists(self.agent_schedules, [("user_id", 1)])
        await self._create_index_if_not_exists(self.agent_schedules, [("next_run", 1)])

    # Auth token management
    async def store_auth_token(self, user_id: str, service: str, access_token: str, 
                              refresh_token: str = None, expires_at: datetime = None):
        """Store OAuth tokens securely. This will now update integration_tokens."""
        # In a real scenario, tokens should be encrypted. The sample data shows they are.
        # This implementation will store them as-is, assuming encryption happens elsewhere.
        await self.integration_tokens.update_one(
            {"user_id": ObjectId(user_id), "provider": service},
            {
                "$set": {
                    "access_token_encrypted": access_token, # Assuming pre-encrypted
                    "refresh_token_encrypted": refresh_token, # Assuming pre-encrypted
                    "token_expiry": expires_at,
                    "updated_at": datetime.utcnow()
                },
                "$setOnInsert": {
                    "user_id": ObjectId(user_id),
                    "provider": service,
                    "created_at": datetime.utcnow()
                }
            },upsert=True
        )

    async def get_auth_token(self, user_id: str, service: str) -> Optional[Dict]:
        """Retrieve OAuth tokens."""
        token_doc = await self.integration_tokens.find_one({"user_id": ObjectId(user_id), "provider": service})
        if token_doc:
            return {
                "access_token": token_doc.get("access_token_encrypted"),
                "refresh_token": token_doc.get("refresh_token_encrypted"),
                "expires_at": token_doc.get("token_expiry")
            }
        return None

    # Sync status management
    async def update_sync_status(self, user_id: str, integration_type: str, 
                                status: str = "success", error_message: str = None):
        """Update sync timestamp and status in the integrations collection."""
        await self.integrations.update_one(
            {"user_id": ObjectId(user_id), "type": integration_type},
            {
                "$set": {
                    "last_sync": datetime.utcnow(),
                    "sync_status": status,
                    "error_message": error_message
                }
            }
        )

    async def get_last_sync(self, user_id: str, integration_type: str) -> Optional[datetime]:
        """Get last sync timestamp from the integrations collection."""
        integration_doc = await self.integrations.find_one({"user_id": ObjectId(user_id), "type": integration_type})
        if integration_doc:
            return integration_doc.get("last_sync")
        return None

    # Rate limiting
    async def get_rate_limit_count(self, user_id: str, resource_type: str, date: str) -> int:
        """Get current usage count for rate limiting."""
        rate_limit_doc = await self.rate_limits.find_one({
            "user_id": ObjectId(user_id), 
            "resource_type": resource_type, 
            "reset_date": date
        })
        return rate_limit_doc.get("count", 0) if rate_limit_doc else 0

    async def increment_rate_limit(self, user_id: str, resource_type: str, 
                                  date: str, count: int = 1):
        """Increment rate limit counter."""
        await self.rate_limits.update_one(
            {"user_id": ObjectId(user_id), "resource_type": resource_type, "reset_date": date},
            {"$inc": {"count": count}, "$setOnInsert": {"created_at": datetime.utcnow()}},
            upsert=True
        )

    # Scheduled tasks
    async def create_scheduled_task(self, task_id: str, user_id: str, task_type: str,
                                   cron_expression: str, task_data: Dict, command: str, cron_description: str,
                                   next_execution: datetime, start_time: datetime, end_time: datetime = None, run_count: int = 0, delivery_platform: str = "whatsapp", original_source:str = 'whatsapp'):
        """Create a new scheduled task in agent_schedules."""
        await self.agent_schedules.update_one(
            {"id": task_id},
            {
                "$set": {
                    "user_id": ObjectId(user_id),
                    "name": task_type, # Mapping task_type to name
                    "cron_expression": cron_expression,
                    "cron_description": cron_description,
                    "next_run": next_execution,
                    "start_time": start_time,
                    "end_time": end_time,
                    "agent_config": task_data, # Mapping task_data to agent_config
                    "is_active": True,
                    "updated_at": datetime.utcnow(),
                    "run_count": run_count,
                    'output_type': delivery_platform,
                    'original_source':original_source
                },
                "$setOnInsert": {"created_at": datetime.utcnow()}
            },
            upsert=True
        )

    async def get_pending_tasks(self, before_time: datetime = None) -> List[Dict]:
        """Get tasks that need to be executed."""
        if before_time is None:
            before_time = datetime.utcnow()
        
        cursor = self.agent_schedules.find({
            "is_active": True, 
            "next_run": {"$lte": before_time}
        }).sort("next_run")
        
        tasks = []
        async for doc in cursor:
            tasks.append({
                "task_id": doc["id"],
                "user_id": ObjectId(doc["user_id"]),
                "task_type": doc.get("name"),
                "cron_expression": doc.get("cron_expression"),
                "task_data": doc.get("agent_config", {}),
                "next_execution": doc.get("next_run")
            })
        return tasks

    async def update_task_execution(self, task_id: str, next_execution: datetime):
        """Update next execution time for a task."""
        await self.agent_schedules.update_one(
            {"id": task_id},
            {"$set": {"next_run": next_execution, "last_run": datetime.utcnow(), "updated_at": datetime.utcnow(), "run_count": {"$inc": 1}}}
        )

    async def deactivate_task(self, task_id: str):
        """Deactivate a scheduled task."""
        await self.agent_schedules.update_one(
            {"id": task_id},
            {"$set": {"is_active": False, "updated_at": datetime.utcnow()}}
        )

    async def save_execution_history(self, execution_record: Dict):
        """Saves a record of an agent execution."""
        await self.db["execution_history"].insert_one(execution_record)

    async def get_scheduled_task(self, task_id: str) -> Optional[Dict]:
        """Get a scheduled task by ID."""
        return await self.agent_schedules.find_one({"id": task_id})

    async def get_user_tasks(self, user_id: str) -> List[Dict]:
        """Gets all active scheduled tasks for a user."""
        cursor = self.agent_schedules.find({
            "user_id": ObjectId(user_id),
            "is_active": True
        }).sort("next_run")
        return await cursor.to_list(length=1000)

    async def update_task(self, task_id: str, update_data: Dict):
        """Updates a scheduled task with the given data."""
        await self.agent_schedules.update_one(
            {"id": task_id},
            {"$set": update_data}
        )

    async def add_document(self, document_record: Dict) -> str:
        """Adds a document record to the documents collection and returns the inserted _id as a string."""
        document_record['created_at'] = datetime.utcnow().isoformat()
        result = await self.documents.insert_one(document_record)
        return str(result.inserted_id)
    async def get_document_by_id(self, document_id: str) -> Optional[Dict]:
        """Get a document by its ID."""
        document = await self.documents.find_one({"_id": ObjectId(document_id)})
        if document:
            return document
        return None
    async def update_document_source_id(self, document_id: str, source_id: str):    
        """Update the source_id of a document."""
        await self.documents.update_one(
            {"_id": ObjectId(document_id)},
            {"$set": {"source_id": source_id}}
        )
# Global database instance
db_manager = DatabaseManager()
