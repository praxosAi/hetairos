
from datetime import datetime, timedelta
from typing import Dict, List, Optional,Union
from src.utils.database import *
from src.services.integration_service import IntegrationService
class ConversationManager:
    """Manages conversation lifecycle, context, and search attempts"""
    
    def __init__(self, db_manager: ConversationDatabase, integration_manager: IntegrationService):
        self.db = conversation_db
        self.integration_manager = integration_manager
        self.INACTIVITY_TIMEOUT = 15 * 60 
    ### TODO: This should be smarter. just randomly finding and consolidating conversations is not the best idea. it should be using praxos memory to find relevant conversations, me thinks.
    async def get_or_create_conversation(self, user_id: str, platform: str,payload) -> str:
        """Get existing active conversation or create new one"""
        
        conversation_id = await self.db.get_active_conversation(user_id)
        conversation_info = await self.db.get_conversation_info(conversation_id)
        
        if conversation_id and not platform == 'benchmark':
            if await self.is_conversation_active(conversation_id,payload) and conversation_info.get('platform') == platform:
                return conversation_id
            else:
                await self.db.mark_conversation_for_consolidation(conversation_id)
        
        return await self.db.create_conversation(user_id, platform)

    async def is_conversation_active(self, conversation_id: str, payload: dict = None) -> bool:
        """Check if conversation is still within the inactivity timeout"""
        return not await self.db.is_conversation_expired(conversation_id, self.INACTIVITY_TIMEOUT // 60,payload)
    
    async def add_user_message(self, conversation_id: str, content: str, metadata: Dict = None) -> str:
        """Add user message to conversation"""
        return await self.db.add_message(conversation_id, 'user', content, 'text', metadata)

    async def add_user_media_message(self, conversation_id: str, content: str, inserted_id: str, message_type: str = 'media', metadata: Dict = None) -> str:
        """Add user media message to conversation"""
        return await self.db.add_message(conversation_id, 'user', content + f" PLACEHOLDER FOR {inserted_id}", message_type, metadata)
    async def add_assistant_message(self, conversation_id: str, content: str, 
                             message_type: str = 'text', metadata: Dict = None) -> str:
        """Add assistant message to conversation"""
        if not content or content.replace(' ', '').lower() == '':
            content = "No response from the assistant."
        return await self.db.add_message(conversation_id, 'assistant', content, message_type, metadata)
    
    async def add_system_message(self, conversation_id: str, content: str, metadata: Dict = None) -> str:
        """Add system message to conversation"""
        return await self.db.add_message(conversation_id, 'system', content, 'system', metadata)
    
    async def get_conversation_context(self, conversation_id: str) -> Dict:
        """Get comprehensive conversation context for processing"""
        
        conversation = await self.db.get_conversation_info(conversation_id)
        if not conversation:
            return {}
        
        messages = await self.db.get_conversation_messages(conversation_id)
        search_history = await self.db.get_recent_search_attempts(conversation_id)
        available_sources = await self.integration_manager.get_user_integrations(conversation['user_id'])
        
        context = {
            'conversation_id': conversation_id,
            'user_id': str(conversation['user_id']),
            'platform': conversation['platform'],
            'start_time': conversation['start_time'],
            'last_activity': conversation['last_activity'],
            'messages': messages,
            'search_history': search_history,
            'available_sources': available_sources,
            'message_count': len(messages),
            'is_active': await self.is_conversation_active(conversation_id)
        }
        
        return context
    
    async def get_conversation_summary(self, conversation_id: str) -> Dict:
        """Get a summary of the conversation without full message history"""
        
        conversation = await self.db.get_conversation_info(conversation_id)
        if not conversation:
            return {}
        
        messages = await self.db.get_conversation_messages(conversation_id, limit=3)
        search_attempts = await self.db.get_recent_search_attempts(conversation_id)
        
        successful_searches = sum(1 for attempt in search_attempts if attempt['success'])
        failed_searches = len(search_attempts) - successful_searches
        
        return {
            'conversation_id': conversation_id,
            'user_id': conversation['user_id'],
            'platform': conversation['platform'],
            'start_time': conversation['start_time'],
            'last_activity': conversation['last_activity'],
            'status': conversation['status'],
            'recent_messages': messages,
            'total_searches': len(search_attempts),
            'successful_searches': successful_searches,
            'failed_searches': failed_searches,
            'is_active': await self.is_conversation_active(conversation_id)
        }
    
    async def record_search_attempt(self, conversation_id: str, query: str, search_type: str, 
                             success: bool, error_type: Optional[str] = None, 
                             results_count: int = 0, metadata: Dict = None) -> str:
        """Record a search attempt with context"""
        return await self.db.record_search_attempt(
            conversation_id, query, search_type, success, error_type, results_count, metadata
        )
    
    async def get_recent_queries(self, conversation_id: str, limit: int = 5) -> List[str]:
        """Get recent user queries from messages"""
        messages = await self.db.get_conversation_messages(conversation_id, limit=limit*2)
        user_messages = [msg for msg in messages if msg['role'] == 'user']
        return [msg['content'] for msg in user_messages[-limit:]]
    
    async def get_conversation_themes(self, conversation_id: str) -> List[str]:
        """Extract themes/topics from conversation for better context"""
        messages = await self.db.get_conversation_messages(conversation_id)
        search_attempts = await self.db.get_recent_search_attempts(conversation_id)
        
        themes = set()
        
        for msg in messages:
            if msg['role'] == 'user':
                words = msg['content'].lower().split()
                important_words = [word for word in words if len(word) > 3]
                themes.update(important_words[:3])
        
        for attempt in search_attempts:
            words = attempt['query'].lower().split()
            important_words = [word for word in words if len(word) > 3]
            themes.update(important_words[:2])
        
        return list(themes)[:10]
    
    async def should_consolidate_conversation(self, conversation_id: str) -> bool:
        """Check if conversation should be consolidated to long-term memory"""
        return not await self.is_conversation_active(conversation_id)
    
    async def get_conversations_ready_for_consolidation(self) -> List[Dict]:
        """Get conversations that need to be consolidated"""
        conversations = await self.db.get_conversations_to_consolidate()
        
        for conv in conversations:
            conv_summary = await self.get_conversation_summary(str(conv['_id']))
            conv.update(conv_summary)
        
        return conversations
    
    async def mark_conversation_for_consolidation(self, conversation_id: str):
        """Mark conversation as ready for consolidation"""
        await self.db.mark_conversation_for_consolidation(conversation_id)
    
    async def get_user_conversations(self, user_id: str, limit: int = 10) -> List[Dict]:
        """Get recent conversations for a user"""
        cursor = self.db.conversations.find(
            {'user_id': ObjectId(user_id)}
        ).sort('last_activity', -1).limit(limit)
        return await cursor.to_list(length=limit)
    
    async def get_conversation_statistics(self, conversation_id: str) -> Dict:
        """Get statistics about a conversation"""
        messages = await self.db.get_conversation_messages(conversation_id)
        search_attempts = await self.db.get_recent_search_attempts(conversation_id, limit=100)
        
        if not messages:
            return {}
        
        user_messages = [msg for msg in messages if msg['role'] == 'user']
        assistant_messages = [msg for msg in messages if msg['role'] == 'assistant']
        
        successful_searches = sum(1 for attempt in search_attempts if attempt['success'])
        failed_searches = len(search_attempts) - successful_searches
        
        start_time = messages[0]['timestamp']
        end_time = messages[-1]['timestamp']
        duration = end_time - start_time
        
        return {
            'conversation_id': conversation_id,
            'total_messages': len(messages),
            'user_messages': len(user_messages),
            'assistant_messages': len(assistant_messages),
            'total_searches': len(search_attempts),
            'successful_searches': successful_searches,
            'failed_searches': failed_searches,
            'search_success_rate': successful_searches / len(search_attempts) if search_attempts else 0,
            'duration_seconds': duration.total_seconds(),
            'start_time': start_time.isoformat(),
            'end_time': end_time.isoformat(),
            'themes': await self.get_conversation_themes(conversation_id)
        }
    
    async def cleanup_old_conversations(self, days_old: int = 30):
        """Clean up old consolidated conversations"""
        await self.db.cleanup_old_conversations(days_old)
