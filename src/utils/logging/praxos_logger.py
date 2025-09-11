import logging
from typing import Dict, List, Optional, Any
from datetime import datetime
from .base_logger import setup_logger, log_error, log_json_data, log_timing, truncate_text, format_user_id

praxos_logger = setup_logger("praxos", logging.INFO)

def log_praxos_connection_start(environment_name: str, api_key_prefix: str = None):
    """Log Praxos connection initialization"""
    key_info = f"API Key: {api_key_prefix}***" if api_key_prefix else "API Key: [hidden]"
    praxos_logger.info(f"🔌 Praxos connection starting - Environment: {environment_name}, {key_info}")

def log_praxos_connection_success(environment_name: str, environment_id: str = None):
    """Log successful Praxos connection"""
    env_info = f"(ID: {environment_id})" if environment_id else ""
    praxos_logger.info(f"✅ Praxos connected to environment: {environment_name} {env_info}")

def log_praxos_connection_failed(environment_name: str, error: Exception, duration: float = None):
    """Log failed Praxos connection"""
    timing_info = f" (took {duration:.2f}s)" if duration else ""
    praxos_logger.error(f"❌ Praxos connection failed to {environment_name}{timing_info}")
    log_error(praxos_logger, error, f"Environment: {environment_name}")

def log_praxos_environment_created(environment_name: str, environment_id: str = None):
    """Log when a new Praxos environment is created"""
    env_info = f"(ID: {environment_id})" if environment_id else ""
    praxos_logger.info(f"🆕 Created new Praxos environment: {environment_name} {env_info}")

def log_praxos_query_started(user_id: str, query: str, operation: str = "query_memory"):
    """Log when a Praxos query starts"""
    user_info = format_user_id(user_id)
    query_preview = truncate_text(query, 100)
    praxos_logger.info(f"🔍 Praxos {operation} started - User: {user_info}, Query: \"{query_preview}\"")

def log_praxos_query_completed(user_id: str, query: str, results_count: int, duration: float, operation: str = "query_memory"):
    """Log successful Praxos query completion"""
    user_info = format_user_id(user_id)
    query_preview = truncate_text(query, 100)
    praxos_logger.info(f"✅ Praxos {operation} completed - User: {user_info}, Query: \"{query_preview}\", Results: {results_count}, Duration: {duration:.2f}s")

def log_praxos_query_failed(user_id: str, query: str, error: Exception, duration: float = None, operation: str = "query_memory"):
    """Log failed Praxos query"""
    user_info = format_user_id(user_id)
    query_preview = truncate_text(query, 100)
    timing_info = f", Duration: {duration:.2f}s" if duration else ""
    praxos_logger.error(f"❌ Praxos {operation} failed - User: {user_info}, Query: \"{query_preview}\"{timing_info}")
    log_error(praxos_logger, error, f"Query: {query_preview}")

def log_praxos_search_anchors_started(user_id: str, query: str, anchors: List[Dict], max_hops: int = 3, top_k: int = 3, node_types: List[str] = None):
    """Log when anchor-based search starts"""
    user_info = format_user_id(user_id)
    query_preview = truncate_text(query, 100)
    anchor_values = [anchor.get('value', 'unknown') for anchor in anchors if anchor.get('value')]
    anchor_info = f"Anchors: {anchor_values}"
    node_info = f"Node types: {node_types}" if node_types else "Node types: [default]"
    praxos_logger.info(f"🎯 Praxos anchor search started - User: {user_info}, Query: \"{query_preview}\", {anchor_info}, Max hops: {max_hops}, Top K: {top_k}, {node_info}")

def log_praxos_search_anchors_completed(user_id: str, query: str, results_count: int, duration: float, anchors_used: int):
    """Log successful anchor-based search completion"""
    user_info = format_user_id(user_id)
    query_preview = truncate_text(query, 100)
    praxos_logger.info(f"✅ Praxos anchor search completed - User: {user_info}, Query: \"{query_preview}\", Results: {results_count}, Anchors used: {anchors_used}, Duration: {duration:.2f}s")

def log_praxos_search_anchors_failed(user_id: str, query: str, error: Exception, duration: float = None):
    """Log failed anchor-based search"""
    user_info = format_user_id(user_id)
    query_preview = truncate_text(query, 100)
    timing_info = f", Duration: {duration:.2f}s" if duration else ""
    praxos_logger.error(f"❌ Praxos anchor search failed - User: {user_info}, Query: \"{query_preview}\"{timing_info}")
    log_error(praxos_logger, error, f"Query: {query_preview}")

def log_praxos_add_message_started(user_id: str, content: str, source: str, metadata: Dict = None):
    """Log when adding a message to Praxos starts"""
    user_info = format_user_id(user_id)
    content_preview = truncate_text(content, 150)
    metadata_info = f"Metadata keys: {list(metadata.keys())}" if metadata else "No metadata"
    praxos_logger.info(f"📝 Praxos add message started - User: {user_info}, Source: {source}, Content: \"{content_preview}\", {metadata_info}")

def log_praxos_add_message_completed(user_id: str, content: str, message_id: str = None, duration: float = None):
    """Log successful message addition to Praxos"""
    user_info = format_user_id(user_id)
    content_preview = truncate_text(content, 150)
    msg_info = f"Message ID: {message_id}" if message_id else "No message ID"
    timing_info = f", Duration: {duration:.2f}s" if duration else ""
    praxos_logger.info(f"✅ Praxos add message completed - User: {user_info}, Content: \"{content_preview}\", {msg_info}{timing_info}")

def log_praxos_add_message_failed(user_id: str, content: str, error: Exception, duration: float = None):
    """Log failed message addition to Praxos"""
    user_info = format_user_id(user_id)
    content_preview = truncate_text(content, 150)
    timing_info = f", Duration: {duration:.2f}s" if duration else ""
    praxos_logger.error(f"❌ Praxos add message failed - User: {user_info}, Content: \"{content_preview}\"{timing_info}")
    log_error(praxos_logger, error, f"Content: {content_preview}")

def log_praxos_add_integration_started(user_id: str, integration_type: str, capabilities: List[str]):
    """Log when adding integration capability starts"""
    user_info = format_user_id(user_id)
    cap_info = f"Capabilities: {capabilities}"
    praxos_logger.info(f"🔗 Praxos add integration started - User: {user_info}, Type: {integration_type}, {cap_info}")

def log_praxos_add_integration_completed(user_id: str, integration_type: str, integration_id: str = None, duration: float = None):
    """Log successful integration addition to Praxos"""
    user_info = format_user_id(user_id)
    int_info = f"Integration ID: {integration_id}" if integration_id else "No integration ID"
    timing_info = f", Duration: {duration:.2f}s" if duration else ""
    praxos_logger.info(f"✅ Praxos add integration completed - User: {user_info}, Type: {integration_type}, {int_info}{timing_info}")

def log_praxos_add_integration_failed(user_id: str, integration_type: str, error: Exception, duration: float = None):
    """Log failed integration addition to Praxos"""
    user_info = format_user_id(user_id)
    timing_info = f", Duration: {duration:.2f}s" if duration else ""
    praxos_logger.error(f"❌ Praxos add integration failed - User: {user_info}, Type: {integration_type}{timing_info}")
    log_error(praxos_logger, error, f"Integration: {integration_type}")

def log_praxos_file_upload_started(file_path: str, name: str, description: str = None):
    """Log when file upload to Praxos starts"""
    desc_info = f"Description: \"{description}\"" if description else "No description"
    praxos_logger.info(f"📁 Praxos file upload started - File: {name}, Path: {file_path}, {desc_info}")

def log_praxos_file_upload_completed(file_path: str, name: str, file_id: str = None, duration: float = None):
    """Log successful file upload to Praxos"""
    file_info = f"File ID: {file_id}" if file_id else "No file ID"
    timing_info = f", Duration: {duration:.2f}s" if duration else ""
    praxos_logger.info(f"✅ Praxos file upload completed - File: {name}, {file_info}{timing_info}")

def log_praxos_file_upload_failed(file_path: str, name: str, error: Exception, duration: float = None):
    """Log failed file upload to Praxos"""
    timing_info = f", Duration: {duration:.2f}s" if duration else ""
    praxos_logger.error(f"❌ Praxos file upload failed - File: {name}, Path: {file_path}{timing_info}")
    log_error(praxos_logger, error, f"File: {name}")

def log_praxos_get_integrations_started(user_id: str):
    """Log when getting user integrations starts"""
    user_info = format_user_id(user_id)
    praxos_logger.info(f"🔍 Praxos get integrations started - User: {user_info}")

def log_praxos_get_integrations_completed(user_id: str, integrations_found: int, duration: float):
    """Log successful integration retrieval"""
    user_info = format_user_id(user_id)
    praxos_logger.info(f"✅ Praxos get integrations completed - User: {user_info}, Found: {integrations_found}, Duration: {duration:.2f}s")

def log_praxos_get_integrations_failed(user_id: str, error: Exception, duration: float = None):
    """Log failed integration retrieval"""
    user_info = format_user_id(user_id)
    timing_info = f", Duration: {duration:.2f}s" if duration else ""
    praxos_logger.error(f"❌ Praxos get integrations failed - User: {user_info}{timing_info}")
    log_error(praxos_logger, error, f"User: {user_info}")

def log_praxos_api_error(operation: str, status_code: int, error_message: str, details: Dict = None):
    """Log Praxos API errors with full context"""
    details_info = f"Details: {details}" if details else "No details"
    praxos_logger.error(f"🚨 Praxos API Error - Operation: {operation}, Status: {status_code}, Message: \"{error_message}\", {details_info}")

def log_praxos_rate_limit(operation: str, wait_time: float, retry_count: int):
    """Log Praxos rate limit encounters"""
    praxos_logger.warning(f"⏱️ Praxos rate limit hit - Operation: {operation}, Wait time: {wait_time:.2f}s, Retry count: {retry_count}")

def log_praxos_timeout(operation: str, timeout_duration: float, user_id: str = None):
    """Log Praxos operation timeouts"""
    user_info = f"User: {format_user_id(user_id)}, " if user_id else ""
    praxos_logger.warning(f"⏰ Praxos timeout - Operation: {operation}, {user_info}Timeout: {timeout_duration:.2f}s")

def log_praxos_fallback_used(operation: str, fallback_type: str, reason: str):
    """Log when fallback logic is used due to Praxos issues"""
    praxos_logger.warning(f"🔄 Praxos fallback used - Operation: {operation}, Fallback: {fallback_type}, Reason: \"{reason}\"")

def log_praxos_daily_usage(operations_today: int, queries_today: int, uploads_today: int, errors_today: int):
    """Log daily Praxos usage statistics"""
    praxos_logger.info(f"📊 Praxos daily usage - Operations: {operations_today}, Queries: {queries_today}, Uploads: {uploads_today}, Errors: {errors_today}")

def log_praxos_performance_warning(operation: str, duration: float, threshold: float):
    """Log performance warnings for slow Praxos operations"""
    praxos_logger.warning(f"⚠️ Praxos performance warning - Operation: {operation}, Duration: {duration:.2f}s (threshold: {threshold:.2f}s)")

def log_praxos_context_details(user_id: str, query: str, results: Dict, local_fallback: bool = False):
    """Log detailed context about Praxos search results"""
    user_info = format_user_id(user_id)
    query_preview = truncate_text(query, 100)
    results_count = len(results.get('results', [])) if results else 0
    fallback_info = " (using local fallback)" if local_fallback else ""
    praxos_logger.info(f"📋 Praxos context - User: {user_info}, Query: \"{query_preview}\", Results: {results_count}{fallback_info}")
    
    # Log results structure if present
    if results and praxos_logger.isEnabledFor(logging.DEBUG):
        log_json_data(praxos_logger, results, "Praxos Results", max_length=500)