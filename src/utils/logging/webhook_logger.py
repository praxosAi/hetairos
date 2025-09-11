from typing import Dict, Any, Optional
from datetime import datetime
import json
from .base_logger import setup_logger, log_error, log_json_data, truncate_text, format_user_id

# Setup webhook logger
webhook_logger = setup_logger("webhook")

def log_webhook_received(source: str, payload: Dict[str, Any], endpoint: str = None):
    """Log incoming webhook payload"""
    webhook_logger.info(f"🔔 {source.title()} Webhook Received")
    if endpoint:
        webhook_logger.info(f"   Endpoint: {endpoint}")
    webhook_logger.info(f"   Timestamp: {datetime.utcnow().isoformat()}")
    
    # Log payload size and basic info
    payload_size = len(json.dumps(payload))
    webhook_logger.info(f"   Payload Size: {payload_size} bytes")
    
    # Log full payload in debug mode
    log_json_data(webhook_logger, payload, f"{source.title()} Webhook Payload")

def log_webhook_verification(source: str, success: bool, verify_token: str = None, challenge: str = None):
    """Log webhook verification attempts"""
    status = "✅ SUCCESS" if success else "❌ FAILED"
    webhook_logger.info(f"🔐 {source.title()} Webhook Verification: {status}")
    
    if verify_token:
        # Mask the token for security
        masked_token = verify_token[:4] + "***" + verify_token[-4:] if len(verify_token) > 8 else "***"
        webhook_logger.info(f"   Verify Token: {masked_token}")
    
    if challenge:
        webhook_logger.info(f"   Challenge: {challenge}")

def log_message_extracted(source: str, user_id: str, message_text: str, message_id: str, metadata: Dict = None):
    """Log message extraction from webhook"""
    emoji_map = {
        'whatsapp': '📱',
        'telegram': '📧',
        'sms': '📲',
        'email': '✉️'
    }
    
    emoji = emoji_map.get(source.lower(), '💬')
    formatted_user = format_user_id(user_id)
    
    webhook_logger.info(f"{emoji} {source.title()} Message Extracted")
    webhook_logger.info(f"   From: {formatted_user}")
    webhook_logger.info(f"   Message ID: {message_id}")
    webhook_logger.info(f"   Content: {truncate_text(message_text)}")
    
    if metadata:
        webhook_logger.debug(f"   Metadata: {json.dumps(metadata, indent=2)}")

def log_message_processing_started(source: str, user_id: str, message_text: str):
    """Log when message processing begins"""
    formatted_user = format_user_id(user_id)
    webhook_logger.info(f"⚙️  Processing {source.title()} Message")
    webhook_logger.info(f"   User: {formatted_user}")
    webhook_logger.info(f"   Message: {truncate_text(message_text, 100)}")

def log_user_filtered(source: str, user_id: str, allowed_users: list):
    """Log when a user is filtered out"""
    formatted_user = format_user_id(user_id)
    webhook_logger.warning(f"🚫 User Filtered Out")
    webhook_logger.warning(f"   Source: {source.title()}")
    webhook_logger.warning(f"   User: {formatted_user}")
    webhook_logger.warning(f"   Allowed Users: {len(allowed_users)} configured")

def log_webhook_error(source: str, error: Exception, context: str = None):
    """Log webhook processing errors"""
    webhook_logger.error(f"❌ {source.title()} Webhook Error")
    if context:
        webhook_logger.error(f"   Context: {context}")
    log_error(webhook_logger, error)

def log_webhook_response(source: str, status_code: int, response_data: Dict = None):
    """Log webhook response being sent"""
    webhook_logger.info(f"📤 {source.title()} Webhook Response")
    webhook_logger.info(f"   Status Code: {status_code}")
    
    if response_data:
        webhook_logger.debug(f"   Response Data: {json.dumps(response_data, indent=2)}")

def log_rate_limit_check(source: str, user_id: str, allowed: bool, remaining: int):
    """Log rate limit checks"""
    formatted_user = format_user_id(user_id)
    status = "✅ ALLOWED" if allowed else "❌ BLOCKED"
    
    webhook_logger.info(f"🚦 Rate Limit Check: {status}")
    webhook_logger.info(f"   Source: {source.title()}")
    webhook_logger.info(f"   User: {formatted_user}")
    webhook_logger.info(f"   Remaining: {remaining}")

def log_webhook_stats(source: str, messages_processed: int, errors: int, processing_time: float):
    """Log webhook processing statistics"""
    webhook_logger.info(f"📊 {source.title()} Webhook Stats")
    webhook_logger.info(f"   Messages Processed: {messages_processed}")
    webhook_logger.info(f"   Errors: {errors}")
    webhook_logger.info(f"   Processing Time: {processing_time:.2f}s")
    webhook_logger.info(f"   Average per Message: {processing_time/max(messages_processed, 1):.2f}s")

def log_media_message_detected(source: str, user_id: str, media_info: Dict, message_id: str):
    """Log when a media message is detected"""
    media_type = media_info.get("type", "unknown")
    filename = media_info.get("filename", "unknown")
    mime_type = media_info.get("mime_type", "unknown")
    media_id = media_info.get("id", "unknown")
    
    # Media type emojis
    emoji_map = {
        'document': '📄',
        'image': '🖼️',
        'audio': '🎵',
        'video': '🎥'
    }
    
    media_emoji = emoji_map.get(media_type, '📎')
    formatted_user = format_user_id(user_id)
    
    webhook_logger.info(f"{media_emoji} {source.title()} Media Message Detected")
    webhook_logger.info(f"   From: {formatted_user}")
    webhook_logger.info(f"   Message ID: {message_id}")
    webhook_logger.info(f"   Media Type: {media_type}")
    webhook_logger.info(f"   Filename: {filename}")
    webhook_logger.info(f"   MIME Type: {mime_type}")
    webhook_logger.info(f"   Media ID: {media_id}")
    
    if media_info.get("caption"):
        webhook_logger.info(f"   Caption: {truncate_text(media_info['caption'])}")

def log_media_processing_started(source: str, user_id: str, media_info: Dict):
    """Log when media processing begins"""
    media_type = media_info.get("type", "unknown")
    filename = media_info.get("filename", "unknown")
    formatted_user = format_user_id(user_id)
    
    webhook_logger.info(f"⚙️  Processing {source.title()} Media File")
    webhook_logger.info(f"   User: {formatted_user}")
    webhook_logger.info(f"   File: {filename} ({media_type})")

def log_media_processing_error(source: str, user_id: str, media_info: Dict, error: Exception):
    """Log media processing errors"""
    media_type = media_info.get("type", "unknown")
    filename = media_info.get("filename", "unknown")
    formatted_user = format_user_id(user_id)
    
    webhook_logger.error(f"❌ {source.title()} Media Processing Error")
    webhook_logger.error(f"   User: {formatted_user}")
    webhook_logger.error(f"   File: {filename} ({media_type})")
    log_error(webhook_logger, error)

# Gmail-specific webhook logging functions

def log_gmail_webhook_received(history_id: str, message_id: str = None, publish_time: str = None):
    """Log Gmail push notification received"""
    webhook_logger.info(f"📧 Gmail Push Notification Received")
    webhook_logger.info(f"   History ID: {history_id}")
    if message_id:
        webhook_logger.info(f"   Message ID: {message_id}")
    if publish_time:
        webhook_logger.info(f"   Publish Time: {publish_time}")
    webhook_logger.info(f"   Timestamp: {datetime.utcnow().isoformat()}")

def log_gmail_webhook_processed(history_id: str, emails_processed: int, processing_time: float):
    """Log successful Gmail webhook processing"""
    webhook_logger.info(f"✅ Gmail Webhook Processed Successfully")
    webhook_logger.info(f"   History ID: {history_id}")
    webhook_logger.info(f"   Emails Processed: {emails_processed}")
    webhook_logger.info(f"   Processing Time: {processing_time:.3f}s")

def log_gmail_webhook_failed(history_id: str, error: str, processing_time: float = 0.0):
    """Log failed Gmail webhook processing"""
    webhook_logger.error(f"❌ Gmail Webhook Processing Failed")
    webhook_logger.error(f"   History ID: {history_id}")
    webhook_logger.error(f"   Error: {error}")
    webhook_logger.error(f"   Processing Time: {processing_time:.3f}s")

def log_gmail_webhook_skipped(history_id: str, reason: str):
    """Log skipped Gmail webhook"""
    webhook_logger.info(f"⏭️  Gmail Webhook Skipped")
    webhook_logger.info(f"   History ID: {history_id}")
    webhook_logger.info(f"   Reason: {reason}")

def log_gmail_subscription_event(event_type: str, details: Dict[str, Any]):
    """Log Gmail subscription events (setup, stop, renewal)"""
    webhook_logger.info(f"🔔 Gmail Subscription {event_type.title()}")
    webhook_logger.info(f"   User: {details.get('user_id', 'unknown')}")
    if 'history_id' in details:
        webhook_logger.info(f"   History ID: {details['history_id']}")
    if 'expiration' in details:
        webhook_logger.info(f"   Expiration: {details['expiration']}")
    if 'topic_name' in details:
        webhook_logger.info(f"   Topic: {details['topic_name']}")

def log_gmail_authentication_failure(user_id: str):
    """Log Gmail authentication failures"""
    webhook_logger.error(f"🔐 Gmail Authentication Failed")
    webhook_logger.error(f"   User: {user_id}")
    webhook_logger.error(f"   Timestamp: {datetime.utcnow().isoformat()}")

def log_gmail_rate_limit_hit(resource_type: str, user_id: str, remaining: int):
    """Log Gmail rate limit encounters"""
    webhook_logger.warning(f"🚫 Gmail Rate Limit Hit")
    webhook_logger.warning(f"   Resource: {resource_type}")
    webhook_logger.warning(f"   User: {user_id}")
    webhook_logger.warning(f"   Remaining: {remaining}")

def log_gmail_history_fetch(history_id: str, items_count: int, fetch_time: float):
    """Log Gmail history API calls"""
    webhook_logger.debug(f"📊 Gmail History Fetched")
    webhook_logger.debug(f"   Since History ID: {history_id}")
    webhook_logger.debug(f"   Items Retrieved: {items_count}")
    webhook_logger.debug(f"   Fetch Time: {fetch_time:.3f}s")