from typing import Dict, Any, Optional, List
from datetime import datetime
import json
from .base_logger import setup_logger, log_error, log_timing, truncate_text, format_user_id

# Setup assistant logger
assistant_logger = setup_logger("assistant")

def log_message_processing_started(user_id: str, message: str, source: str, message_id: str = None):
    """Log when message processing begins"""
    formatted_user = format_user_id(user_id)
    assistant_logger.info(f"🎯 Message Processing Started")
    assistant_logger.info(f"   User: {formatted_user}")
    assistant_logger.info(f"   Source: {source}")
    assistant_logger.info(f"   Message ID: {message_id}")
    assistant_logger.info(f"   Content: {truncate_text(message, 200)}")
    assistant_logger.info(f"   Started at: {datetime.utcnow().isoformat()}")

def log_message_processing_completed(user_id: str, message: str, response: str, duration: float, source: str):
    """Log when message processing completes"""
    formatted_user = format_user_id(user_id)
    assistant_logger.info(f"✅ Message Processing Completed")
    assistant_logger.info(f"   User: {formatted_user}")
    assistant_logger.info(f"   Source: {source}")
    assistant_logger.info(f"   Duration: {duration:.2f}s")
    assistant_logger.info(f"   Original: {truncate_text(message, 100)}")
    assistant_logger.info(f"   Response: {truncate_text(response, 200)}")

def log_message_processing_failed(user_id: str, message: str, error: Exception, duration: float, source: str):
    """Log when message processing fails"""
    formatted_user = format_user_id(user_id)
    assistant_logger.error(f"❌ Message Processing Failed")
    assistant_logger.error(f"   User: {formatted_user}")
    assistant_logger.error(f"   Source: {source}")
    assistant_logger.error(f"   Duration: {duration:.2f}s")
    assistant_logger.error(f"   Message: {truncate_text(message, 100)}")
    log_error(assistant_logger, error, "Message processing")

def log_rate_limit_triggered(user_id: str, source: str, limit_type: str, remaining: int):
    """Log when rate limit is triggered"""
    formatted_user = format_user_id(user_id)
    assistant_logger.warning(f"🚫 Rate Limit Triggered")
    assistant_logger.warning(f"   User: {formatted_user}")
    assistant_logger.warning(f"   Source: {source}")
    assistant_logger.warning(f"   Limit Type: {limit_type}")
    assistant_logger.warning(f"   Remaining: {remaining}")

def log_praxos_operation(operation: str, user_id: str, success: bool, details: Dict[str, Any] = None):
    """Log Praxos operations"""
    formatted_user = format_user_id(user_id)
    status = "✅ SUCCESS" if success else "❌ FAILED"
    assistant_logger.info(f"🧠 Praxos Operation: {operation} - {status}")
    assistant_logger.info(f"   User: {formatted_user}")
    
    if details:
        for key, value in details.items():
            if isinstance(value, str) and len(value) > 100:
                value = truncate_text(value, 100)
            assistant_logger.info(f"   {key}: {value}")

def log_intent_processing(user_id: str, message: str, intent_result: Dict[str, Any]):
    """Log intent processing results"""
    formatted_user = format_user_id(user_id)
    assistant_logger.info(f"🧠 Intent Processing")
    assistant_logger.info(f"   User: {formatted_user}")
    assistant_logger.info(f"   Message: {truncate_text(message, 100)}")
    assistant_logger.info(f"   Intent: {intent_result.get('intent', 'unknown')}")
    assistant_logger.info(f"   Urgency: {intent_result.get('urgency', 'unknown')}")
    
    integrations_needed = intent_result.get('integration_needed', [])
    if integrations_needed:
        assistant_logger.info(f"   Integrations Needed: {', '.join(integrations_needed)}")

def log_sync_decision(user_id: str, integration: str, needs_sync: bool, last_sync: datetime = None):
    """Log sync decision making"""
    formatted_user = format_user_id(user_id)
    decision = "SYNC" if needs_sync else "SKIP"
    assistant_logger.info(f"🔄 Sync Decision: {decision}")
    assistant_logger.info(f"   User: {formatted_user}")
    assistant_logger.info(f"   Integration: {integration}")
    if last_sync:
        assistant_logger.info(f"   Last Sync: {last_sync.isoformat()}")
        time_since = datetime.utcnow() - last_sync
        assistant_logger.info(f"   Time Since: {time_since.total_seconds():.0f}s")

def log_response_generation(user_id: str, intent: str, response: str, context_size: int = None):
    """Log response generation"""
    formatted_user = format_user_id(user_id)
    assistant_logger.info(f"💬 Response Generation")
    assistant_logger.info(f"   User: {formatted_user}")
    assistant_logger.info(f"   Intent: {intent}")
    assistant_logger.info(f"   Response Length: {len(response)} chars")
    assistant_logger.info(f"   Response: {truncate_text(response, 200)}")
    if context_size:
        assistant_logger.info(f"   Context Size: {context_size} chars")

def log_response_sent(user_id: str, source: str, response: str, success: bool):
    """Log response sending"""
    formatted_user = format_user_id(user_id)
    status = "✅ SUCCESS" if success else "❌ FAILED"
    emoji_map = {
        'whatsapp': '📱',
        'telegram': '📧',
        'email': '✉️',
        'sms': '📲'
    }
    
    emoji = emoji_map.get(source.lower(), '💬')
    assistant_logger.info(f"{emoji} Response Sent: {status}")
    assistant_logger.info(f"   User: {formatted_user}")
    assistant_logger.info(f"   Source: {source}")
    assistant_logger.info(f"   Response: {truncate_text(response, 150)}")

def log_context_retrieval(user_id: str, query: str, results_count: int, sources: List[str] = None):
    """Log context retrieval from Praxos"""
    formatted_user = format_user_id(user_id)
    assistant_logger.info(f"📚 Context Retrieval")
    assistant_logger.info(f"   User: {formatted_user}")
    assistant_logger.info(f"   Query: {truncate_text(query, 100)}")
    assistant_logger.info(f"   Results: {results_count}")
    if sources:
        assistant_logger.info(f"   Sources: {', '.join(sources)}")

def log_integration_search(user_id: str, query: str, integrations_found: List[str]):
    """Log integration capability search"""
    formatted_user = format_user_id(user_id)
    assistant_logger.info(f"🔍 Integration Search")
    assistant_logger.info(f"   User: {formatted_user}")
    assistant_logger.info(f"   Query: {truncate_text(query, 100)}")
    assistant_logger.info(f"   Integrations Found: {', '.join(integrations_found) if integrations_found else 'None'}")

def log_session_stats(user_id: str, messages_processed: int, avg_response_time: float, errors: int):
    """Log session statistics"""
    formatted_user = format_user_id(user_id)
    assistant_logger.info(f"📊 Session Stats")
    assistant_logger.info(f"   User: {formatted_user}")
    assistant_logger.info(f"   Messages Processed: {messages_processed}")
    assistant_logger.info(f"   Avg Response Time: {avg_response_time:.2f}s")
    assistant_logger.info(f"   Errors: {errors}")
    assistant_logger.info(f"   Success Rate: {((messages_processed - errors) / max(messages_processed, 1)) * 100:.1f}%")

def log_capability_check(user_id: str, capability: str, available: bool, integrations: List[str]):
    """Log capability availability checks"""
    formatted_user = format_user_id(user_id)
    status = "✅ AVAILABLE" if available else "❌ NOT AVAILABLE"
    assistant_logger.info(f"🔧 Capability Check: {status}")
    assistant_logger.info(f"   User: {formatted_user}")
    assistant_logger.info(f"   Capability: {capability}")
    assistant_logger.info(f"   Supporting Integrations: {', '.join(integrations) if integrations else 'None'}")

def log_assistant_error(user_id: str, operation: str, error: Exception, context: Dict[str, Any] = None):
    """Log assistant-specific errors"""
    formatted_user = format_user_id(user_id)
    assistant_logger.error(f"❌ Assistant Error: {operation}")
    assistant_logger.error(f"   User: {formatted_user}")
    if context:
        for key, value in context.items():
            if isinstance(value, str) and len(value) > 100:
                value = truncate_text(value, 100)
            assistant_logger.error(f"   {key}: {value}")
    log_error(assistant_logger, error)

def log_media_ingestion_started(user_id: str, media_info: Dict, conversation_id: int):
    """Log when media ingestion begins"""
    media_type = media_info.get("type", "unknown")
    filename = media_info.get("filename", "unknown")
    formatted_user = format_user_id(user_id)
    
    # Media type emojis
    emoji_map = {
        'document': '📄',
        'image': '🖼️', 
        'audio': '🎵',
        'video': '🎥'
    }
    
    media_emoji = emoji_map.get(media_type, '📎')
    assistant_logger.info(f"{media_emoji} Media Ingestion Started")
    assistant_logger.info(f"   User: {formatted_user}")
    assistant_logger.info(f"   Conversation ID: {conversation_id}")
    assistant_logger.info(f"   Media Type: {media_type}")
    assistant_logger.info(f"   Filename: {filename}")
    assistant_logger.info(f"   Started at: {datetime.utcnow().isoformat()}")

def log_media_ingestion_completed(user_id: str, media_info: Dict, duration: float, success: bool, details: Dict = None):
    """Log when media ingestion completes"""
    media_type = media_info.get("type", "unknown")
    filename = media_info.get("filename", "unknown")
    formatted_user = format_user_id(user_id)
    
    status = "✅ SUCCESS" if success else "❌ FAILED"
    assistant_logger.info(f"📎 Media Ingestion Completed: {status}")
    assistant_logger.info(f"   User: {formatted_user}")
    assistant_logger.info(f"   File: {filename} ({media_type})")
    assistant_logger.info(f"   Duration: {duration:.2f}s")
    
    if details:
        for key, value in details.items():
            assistant_logger.info(f"   {key}: {value}")

def log_media_download_attempt(user_id: str, media_id: str, media_type: str):
    """Log media download attempts"""
    formatted_user = format_user_id(user_id)
    assistant_logger.info(f"⬇️  Media Download Attempt")
    assistant_logger.info(f"   User: {formatted_user}")
    assistant_logger.info(f"   Media ID: {media_id}")
    assistant_logger.info(f"   Media Type: {media_type}")

def log_media_acknowledgment_sent(user_id: str, media_info: Dict, source: str):
    """Log when media acknowledgment is sent to user"""
    media_type = media_info.get("type", "unknown")
    filename = media_info.get("filename", "unknown")
    formatted_user = format_user_id(user_id)
    
    assistant_logger.info(f"📱 Media Acknowledgment Sent")
    assistant_logger.info(f"   User: {formatted_user}")
    assistant_logger.info(f"   Source: {source}")
    assistant_logger.info(f"   File: {filename} ({media_type})")