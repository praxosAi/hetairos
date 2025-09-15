import asyncio
from datetime import datetime
from typing import Dict, List, Optional
from src.utils.database import ConversationDatabase
from src.core.praxos_client import PraxosClient
from src.services.user_service import user_service
from src.services.ai_service.ai_service import ai_service
from src.utils.logging import setup_logger
logger = setup_logger(__name__)
class ConversationConsolidator:
    """Consolidates conversations from short-term to long-term memory"""
    def __init__(self, db_manager: ConversationDatabase):
        self.db = db_manager

    
    async def consolidate_conversation(self, conversation_id: int) -> bool:
        """Consolidate a single conversation to Praxos"""
        try:
            conversation = await self.db.get_conversation_info(conversation_id)
            ### now that we have this, we can 
            if not conversation:
                logger.warning(f"Conversation {conversation_id} not found")
                return False
            logger.info(f"Found conversation {conversation_id}")
            # Get all messages and search attempts
            message_dict = {} 
            messages = await self.db.get_conversation_messages(conversation_id)
            try:
                file_message_idx = []
                tasks = []
                for idx, message in enumerate(messages):
                    if message.get('metadata', {}).get('inserted_id'):
                        file_message_idx.append(idx)
                        tasks.append(asyncio.create_task(ai_service.multi_modal_by_doc_id('provide a full description of this media. prefix it with "description of media type: , where media type is the type of the media, for example, audio, video, etc."', message['metadata']['inserted_id'])))
                descriptions = await asyncio.gather(*tasks)
                for i, idx in enumerate(file_message_idx):
                    message_idx = file_message_idx[i]
                    message = messages[message_idx]
                    description = descriptions[i]
                    message['content'] = f'Description of media type with id: {message["metadata"]["inserted_id"]}: {description}'
                    message_dict[str(message['_id'])] = {'content': message['content']}

            except Exception as e:
                logger.error(f"Error generating media descriptions: {e}", exc_info=True)

            ### now, let's update messages
            update_messages = await self.db.bulk_update_messages(message_dict)
            logger.info(f"Updated {update_messages} messages with media descriptions")
            search_attempts = await self.db.get_recent_search_attempts(conversation_id, limit=100)
            logger.info(f"Found {len(search_attempts)} search attempts")
            if not messages:
                logger.warning(f"No messages found for conversation {conversation_id}")
                await self.db.mark_conversation_consolidated(conversation_id)
                return True
            # summary = self.create_conversation_summary(conversation, messages, search_attempts)
            
            new_consolidation = await self.db.mark_conversation_consolidated(conversation_id)
            if not new_consolidation:
                logger.info(f"Conversation {conversation_id} already consolidated")
                return True
            # Send to Praxos
            conversation_user_id = conversation['user_id']
            user_record = user_service.get_user_by_id(conversation_user_id)
            user_email = user_record['email']
            env_name = f"env_for_{user_email}"

            from src.config.settings import settings
            if settings.OPERATING_MODE == "local":
                praxos_api_key = settings.PRAXOS_API_KEY
            else:
                praxos_api_key = user_record.get("praxos_api_key")

            if not praxos_api_key:
                raise ValueError("Praxos API key not found.")

            praxos_client = PraxosClient(env_name, api_key=praxos_api_key)
            source_data = await praxos_client.add_conversation(
                    user_id=conversation_user_id,
                    source='conversation_summary',
                    messages=messages,
                    metadata={
                        'conversation_id': conversation_id,
                        'message_count': len(messages),
                        'search_attempts': len(search_attempts),
                        'platform': conversation['platform'],
                        'start_time': conversation['start_time'],
                        'end_time': conversation['last_activity']
                    },
                    user_record=user_record,
                    conversation_id=conversation_id
                )
            source_id = source_data.get('id', '')
            await self.db.update_conversation_praxos_source_id(conversation_id, source_id)
            # Mark as consolidated


            logger.info(f"Successfully consolidated conversation {conversation_id} with {len(messages)} messages")
            return True
            
        except Exception as e:
            logger.error(f"Error consolidating conversation {conversation_id}: {e}")
            # Optionally, mark the conversation as failed to prevent retries
            # await self.db.mark_conversation_failed(conversation_id, str(e))
            return False
    
    def create_conversation_summary(self, conversation: Dict, messages: List[Dict], 
                                   search_attempts: List[Dict]) -> str:
        """Create a comprehensive conversation summary for Praxos"""
        
        # Basic conversation info
        start_time = conversation['start_time']
        end_time = conversation['last_activity']
        platform = conversation['platform']
        user_id = conversation['user_id']
        
        # Message analysis
        user_messages = [msg for msg in messages if msg['role'] == 'user']
        assistant_messages = [msg for msg in messages if msg['role'] == 'assistant']
        
        # Search analysis
        successful_searches = [attempt for attempt in search_attempts if attempt['success']]
        failed_searches = [attempt for attempt in search_attempts if not attempt['success']]
        
        # Extract key topics/themes
        themes = self.extract_conversation_themes(messages, search_attempts)
        
        # Build summary
        summary = f"""Conversation Summary - {start_time} to {end_time}
        User: {user_id}
        Platform: {platform}
        Duration: {self.calculate_duration(start_time, end_time)}

        === CONVERSATION OVERVIEW ===
        Total Messages: {len(messages)} ({len(user_messages)} user, {len(assistant_messages)} assistant)
        Search Attempts: {len(search_attempts)} ({len(successful_searches)} successful, {len(failed_searches)} failed)
        Main Topics: {', '.join(themes[:5])}

        === CONVERSATION FLOW ===
        """
        
        # Add conversation flow (simplified)
        for i, message in enumerate(messages):
            role_indicator = "👤" if message['role'] == 'user' else "🤖"
            timestamp = message['timestamp']
            content = message['content'][:100] + "..." if len(message['content']) > 100 else message['content']
            
            summary += f"{role_indicator} [{timestamp}] {content}\n"
        
        # Add search attempts summary
        if search_attempts:
            summary += "\n=== SEARCH ATTEMPTS ===\n"
            for attempt in search_attempts:
                status = "✅" if attempt['success'] else "❌"
                summary += f"{status} {attempt['query']} ({attempt['search_type']})\n"
        
        # Add key outcomes/results
        if successful_searches:
            summary += "\n=== SUCCESSFUL SEARCHES ===\n"
            for search in successful_searches:
                summary += f"- {search['query']} (found {search['results_count']} results)\n"
        
        if failed_searches:
            summary += "\n=== FAILED SEARCHES ===\n"
            for search in failed_searches:
                error_info = f" - {search['error_type']}" if search['error_type'] else ""
                summary += f"- {search['query']}{error_info}\n"
        
        # Add conversation insights
        summary += f"\n=== CONVERSATION INSIGHTS ===\n"
        summary += f"- User engagement: {len(user_messages)} messages\n"
        summary += f"- Search success rate: {len(successful_searches)}/{len(search_attempts)} ({len(successful_searches)/len(search_attempts)*100:.1f}%)\n" if search_attempts else "- No searches performed\n"
        summary += f"- Primary topics: {', '.join(themes[:3])}\n"
        summary += f"- Platform: {platform}\n"
        
        return summary
    
    def extract_conversation_themes(self, messages: List[Dict], search_attempts: List[Dict]) -> List[str]:
        """Extract key themes from conversation"""
        themes = set()
        
        # Extract from user messages
        for msg in messages:
            if msg['role'] == 'user':
                # Simple keyword extraction
                words = msg['content'].lower().split()
                # Filter out common words and keep meaningful ones
                meaningful_words = [
                    word for word in words 
                    if len(word) > 3 and word not in ['what', 'when', 'where', 'how', 'why', 'the', 'and', 'or', 'but', 'with', 'have', 'this', 'that', 'they', 'them', 'from', 'your', 'you', 'are', 'was', 'were', 'been', 'being', 'have', 'has', 'had', 'do', 'does', 'did', 'will', 'would', 'could', 'should', 'may', 'might', 'must', 'can', 'shall']
                ]
                themes.update(meaningful_words[:3])  # Top 3 words per message
        
        # Extract from search queries
        for attempt in search_attempts:
            words = attempt['query'].lower().split()
            meaningful_words = [word for word in words if len(word) > 3]
            themes.update(meaningful_words[:2])  # Top 2 words per search
        
        return list(themes)[:10]  # Return top 10 themes
    
    def calculate_duration(self, start_time: str, end_time: str) -> str:
        """Calculate human-readable duration"""
        try:
            start = datetime.fromisoformat(start_time.replace('Z', '+00:00'))
            end = datetime.fromisoformat(end_time.replace('Z', '+00:00'))
            duration = end - start
            
            if duration.days > 0:
                return f"{duration.days} days, {duration.seconds // 3600} hours"
            elif duration.seconds > 3600:
                return f"{duration.seconds // 3600} hours, {(duration.seconds % 3600) // 60} minutes"
            else:
                return f"{duration.seconds // 60} minutes"
        except:
            return "Unknown duration"
    
    async def consolidate_all_ready_conversations(self) -> Dict:
        """Consolidate all conversations ready for consolidation"""
        conversations = await self.db.get_conversations_to_consolidate()
        
        results = {
            'total': len(conversations),
            'successful': 0,
            'failed': 0,
            'errors': []
        }
        self.db.logger.info(f"Consolidating {len(conversations)} conversations")
        for conversation in conversations:
            conversation_id = str(conversation['_id'])
            try:
                success = await self.consolidate_conversation(conversation_id)
                if success:
                    results['successful'] += 1
                else:
                    results['failed'] += 1
                    results['errors'].append(f"Conversation {conversation_id}: Unknown error")
            except Exception as e:
                results['failed'] += 1
                results['errors'].append(f"Conversation {conversation_id}: {str(e)}")
        
        return results
    
    async def consolidate_user_conversations(self, user_id: str) -> Dict:
        """Consolidate all ready conversations for a specific user"""
        conversations = await self.db.get_conversations_to_consolidate()
        user_conversations = [conv for conv in conversations if conv['user_id'] == user_id]
        
        results = {
            'user_id': user_id,
            'total': len(user_conversations),
            'successful': 0,
            'failed': 0,
            'errors': []
        }
        
        for conversation in user_conversations:
            conversation_id = str(conversation['_id'])
            try:
                success = await self.consolidate_conversation(conversation_id)
                if success:
                    results['successful'] += 1
                else:
                    results['failed'] += 1
                    results['errors'].append(f"Conversation {conversation_id}: Unknown error")
            except Exception as e:
                results['failed'] += 1
                results['errors'].append(f"Conversation {conversation_id}: {str(e)}")
        
        return results
    
    async def get_consolidation_statistics(self) -> Dict:
        """Get statistics about conversations ready for consolidation"""
        conversations = await self.db.get_conversations_to_consolidate()
        
        # Group by user
        user_counts = {}
        platform_counts = {}
        
        for conv in conversations:
            user_id = conv['user_id']
            platform = conv['platform']
            
            user_counts[user_id] = user_counts.get(user_id, 0) + 1
            platform_counts[platform] = platform_counts.get(platform, 0) + 1
        
        return {
            'total_conversations': len(conversations),
            'unique_users': len(user_counts),
            'conversations_by_user': user_counts,
            'conversations_by_platform': platform_counts,
            'oldest_conversation': min(conversations, key=lambda x: x['start_time'])['start_time'] if conversations else None,
            'newest_conversation': max(conversations, key=lambda x: x['start_time'])['start_time'] if conversations else None
        }