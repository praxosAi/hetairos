from typing import Dict, Any, Optional, List
from datetime import datetime
import json
from .base_logger import setup_logger, log_error, log_json_data, log_timing, format_user_id

# Setup integration logger
integration_logger = setup_logger("integration")

def log_sync_started(integration_type: str, user_id: str, since: datetime = None):
    """Log when integration sync begins"""
    formatted_user = format_user_id(user_id)
    integration_logger.info(f"🔄 {integration_type.title()} Sync Started")
    integration_logger.info(f"   User: {formatted_user}")
    integration_logger.info(f"   Since: {since.isoformat() if since else 'Full sync'}")
    integration_logger.info(f"   Started at: {datetime.utcnow().isoformat()}")

def log_sync_completed(integration_type: str, user_id: str, items_synced: int, duration: float):
    """Log when integration sync completes"""
    formatted_user = format_user_id(user_id)
    integration_logger.info(f"✅ {integration_type.title()} Sync Completed")
    integration_logger.info(f"   User: {formatted_user}")
    integration_logger.info(f"   Items Synced: {items_synced}")
    integration_logger.info(f"   Duration: {duration:.2f}s")
    integration_logger.info(f"   Rate: {items_synced/max(duration, 0.001):.2f} items/sec")

def log_sync_failed(integration_type: str, user_id: str, error: Exception, duration: float = None):
    """Log when integration sync fails"""
    formatted_user = format_user_id(user_id)
    integration_logger.error(f"❌ {integration_type.title()} Sync Failed")
    integration_logger.error(f"   User: {formatted_user}")
    if duration:
        integration_logger.error(f"   Duration: {duration:.2f}s")
    log_error(integration_logger, error, f"{integration_type} sync")

def log_authentication_started(integration_type: str, user_id: str, auth_method: str = None):
    """Log authentication attempt"""
    formatted_user = format_user_id(user_id)
    integration_logger.info(f"🔐 {integration_type.title()} Authentication Started")
    integration_logger.info(f"   User: {formatted_user}")
    if auth_method:
        integration_logger.info(f"   Method: {auth_method}")

def log_authentication_result(integration_type: str, user_id: str, success: bool, error: Exception = None):
    """Log authentication result"""
    formatted_user = format_user_id(user_id)
    status = "✅ SUCCESS" if success else "❌ FAILED"
    integration_logger.info(f"🔐 {integration_type.title()} Authentication: {status}")
    integration_logger.info(f"   User: {formatted_user}")
    
    if not success and error:
        log_error(integration_logger, error, f"{integration_type} authentication")

def log_data_fetched(integration_type: str, user_id: str, data_type: str, count: int, api_calls: int = None):
    """Log data fetching from integration"""
    formatted_user = format_user_id(user_id)
    integration_logger.info(f"📥 {integration_type.title()} Data Fetched")
    integration_logger.info(f"   User: {formatted_user}")
    integration_logger.info(f"   Data Type: {data_type}")
    integration_logger.info(f"   Items: {count}")
    if api_calls:
        integration_logger.info(f"   API Calls: {api_calls}")

def log_data_processed(integration_type: str, user_id: str, data_type: str, processed: int, skipped: int = 0):
    """Log data processing results"""
    formatted_user = format_user_id(user_id)
    integration_logger.info(f"⚙️  {integration_type.title()} Data Processed")
    integration_logger.info(f"   User: {formatted_user}")
    integration_logger.info(f"   Data Type: {data_type}")
    integration_logger.info(f"   Processed: {processed}")
    if skipped > 0:
        integration_logger.info(f"   Skipped: {skipped}")

def log_praxos_upload(integration_type: str, user_id: str, items: List[Dict], success: bool):
    """Log uploading data to Praxos"""
    formatted_user = format_user_id(user_id)
    status = "✅ SUCCESS" if success else "❌ FAILED"
    integration_logger.info(f"📤 {integration_type.title()} → Praxos Upload: {status}")
    integration_logger.info(f"   User: {formatted_user}")
    integration_logger.info(f"   Items: {len(items)}")
    
    # Log sample of items being uploaded (debug level)
    if items and len(items) > 0:
        sample_item = items[0]
        integration_logger.debug(f"   Sample Item: {json.dumps(sample_item, indent=2, default=str)}")

def log_rate_limit_hit(integration_type: str, user_id: str, limit_type: str, wait_time: float):
    """Log when rate limit is hit"""
    formatted_user = format_user_id(user_id)
    integration_logger.warning(f"🚦 {integration_type.title()} Rate Limit Hit")
    integration_logger.warning(f"   User: {formatted_user}")
    integration_logger.warning(f"   Limit Type: {limit_type}")
    integration_logger.warning(f"   Wait Time: {wait_time:.2f}s")

def log_capability_added(integration_type: str, user_id: str, capabilities: List[str]):
    """Log when integration capabilities are added to Praxos"""
    formatted_user = format_user_id(user_id)
    integration_logger.info(f"🔧 {integration_type.title()} Capabilities Added")
    integration_logger.info(f"   User: {formatted_user}")
    integration_logger.info(f"   Capabilities: {', '.join(capabilities)}")

def log_integration_health(integration_type: str, user_id: str, health_status: str, last_sync: datetime = None):
    """Log integration health status"""
    formatted_user = format_user_id(user_id)
    status_emoji = {
        'healthy': '💚',
        'warning': '🟡',
        'error': '🔴',
        'unknown': '⚪'
    }
    
    emoji = status_emoji.get(health_status.lower(), '⚪')
    integration_logger.info(f"{emoji} {integration_type.title()} Health: {health_status.upper()}")
    integration_logger.info(f"   User: {formatted_user}")
    if last_sync:
        integration_logger.info(f"   Last Sync: {last_sync.isoformat()}")

def log_integration_error(integration_type: str, user_id: str, error: Exception, context: str = None):
    """Log integration-specific errors"""
    formatted_user = format_user_id(user_id)
    integration_logger.error(f"❌ {integration_type.title()} Error")
    integration_logger.error(f"   User: {formatted_user}")
    if context:
        integration_logger.error(f"   Context: {context}")
    log_error(integration_logger, error)