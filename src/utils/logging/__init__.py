# Logging utilities for AI Personal Assistant
# Import all logging functions for easy access

from .base_logger import setup_logger, log_error, log_json_data, log_timing, truncate_text, format_user_id
from .webhook_logger import (
    log_webhook_received,
    log_webhook_verification,
    log_message_extracted,
    log_message_processing_started,
    log_user_filtered,
    log_webhook_error,
    log_webhook_response,
    log_rate_limit_check,
    log_webhook_stats,
    log_media_message_detected,
    log_media_processing_started,
    log_media_processing_error
)
from .integration_logger import (
    log_sync_started,
    log_sync_completed,
    log_sync_failed,
    log_authentication_started,
    log_authentication_result,
    log_data_fetched,
    log_data_processed,
    log_praxos_upload,
    log_rate_limit_hit,
    log_capability_added,
    log_integration_health,
    log_integration_error
)
from .llm_logger import (
    log_llm_request_started,
    log_llm_request_completed,
    log_llm_request_failed,
    log_intent_parsing,
    log_response_generation,
    log_prompt_template,
    log_token_usage_warning,
    log_model_fallback,
    log_llm_rate_limit,
    log_llm_context_truncation,
    log_llm_daily_usage
)
from .assistant_logger import (
    log_message_processing_started as log_assistant_processing_started,
    log_message_processing_completed as log_assistant_processing_completed,
    log_message_processing_failed as log_assistant_processing_failed,
    log_rate_limit_triggered,
    log_praxos_operation,
    log_intent_processing,
    log_sync_decision,
    log_response_generation as log_assistant_response_generation,
    log_response_sent,
    log_context_retrieval,
    log_integration_search,
    log_session_stats,
    log_capability_check,
    log_assistant_error,
    log_media_ingestion_started,
    log_media_ingestion_completed,
    log_media_download_attempt,
    log_media_acknowledgment_sent
)
from .praxos_logger import (
    log_praxos_connection_start,
    log_praxos_connection_success,
    log_praxos_connection_failed,
    log_praxos_environment_created,
    log_praxos_query_started,
    log_praxos_query_completed,
    log_praxos_query_failed,
    log_praxos_search_anchors_started,
    log_praxos_search_anchors_completed,
    log_praxos_search_anchors_failed,
    log_praxos_add_message_started,
    log_praxos_add_message_completed,
    log_praxos_add_message_failed,
    log_praxos_add_integration_started,
    log_praxos_add_integration_completed,
    log_praxos_add_integration_failed,
    log_praxos_file_upload_started,
    log_praxos_file_upload_completed,
    log_praxos_file_upload_failed,
    log_praxos_get_integrations_started,
    log_praxos_get_integrations_completed,
    log_praxos_get_integrations_failed,
    log_praxos_api_error,
    log_praxos_rate_limit,
    log_praxos_timeout,
    log_praxos_fallback_used,
    log_praxos_daily_usage,
    log_praxos_performance_warning,
    log_praxos_context_details
)
from .voice_logger import (
    log_voice_message_received,
    log_voice_message_detection,
    log_voice_transcription_started,
    log_voice_transcription_completed,
    log_voice_transcription_failed,
    log_voice_file_processing,
    log_voice_format_conversion,
    log_voice_service_health,
    log_voice_job_queued,
    log_voice_usage_stats,
    log_voice_worker_status,
    log_voice_model_loaded,
    log_voice_assistant_integration,
    log_voice_error
)

# Export loggers for direct use
from .webhook_logger import webhook_logger
from .integration_logger import integration_logger
from .llm_logger import llm_logger
from .assistant_logger import assistant_logger
from .praxos_logger import praxos_logger
from .voice_logger import voice_logger

__all__ = [
    # Base utilities
    'setup_logger', 'log_error', 'log_json_data', 'log_timing', 'truncate_text', 'format_user_id',
    
    # Webhook logging
    'log_webhook_received', 'log_webhook_verification', 'log_message_extracted',
    'log_message_processing_started', 'log_user_filtered', 'log_webhook_error',
    'log_webhook_response', 'log_rate_limit_check', 'log_webhook_stats',
    'log_media_message_detected', 'log_media_processing_started', 'log_media_processing_error',
    
    # Integration logging
    'log_sync_started', 'log_sync_completed', 'log_sync_failed',
    'log_authentication_started', 'log_authentication_result',
    'log_data_fetched', 'log_data_processed', 'log_praxos_upload',
    'log_rate_limit_hit', 'log_capability_added', 'log_integration_health',
    'log_integration_error',
    
    # LLM logging
    'log_llm_request_started', 'log_llm_request_completed', 'log_llm_request_failed',
    'log_intent_parsing', 'log_response_generation', 'log_prompt_template',
    'log_token_usage_warning', 'log_model_fallback', 'log_llm_rate_limit',
    'log_llm_context_truncation', 'log_llm_daily_usage',
    
    # Assistant logging
    'log_assistant_processing_started', 'log_assistant_processing_completed',
    'log_assistant_processing_failed', 'log_rate_limit_triggered',
    'log_praxos_operation', 'log_intent_processing', 'log_sync_decision',
    'log_assistant_response_generation', 'log_response_sent',
    'log_context_retrieval', 'log_integration_search', 'log_session_stats',
    'log_capability_check', 'log_assistant_error', 'log_media_ingestion_started',
    'log_media_ingestion_completed', 'log_media_download_attempt', 'log_media_acknowledgment_sent',
    
    # Praxos logging
    'log_praxos_connection_start', 'log_praxos_connection_success', 'log_praxos_connection_failed',
    'log_praxos_environment_created', 'log_praxos_query_started', 'log_praxos_query_completed',
    'log_praxos_query_failed', 'log_praxos_search_anchors_started', 'log_praxos_search_anchors_completed',
    'log_praxos_search_anchors_failed', 'log_praxos_add_message_started', 'log_praxos_add_message_completed',
    'log_praxos_add_message_failed', 'log_praxos_add_integration_started', 'log_praxos_add_integration_completed',
    'log_praxos_add_integration_failed', 'log_praxos_file_upload_started', 'log_praxos_file_upload_completed',
    'log_praxos_file_upload_failed', 'log_praxos_get_integrations_started', 'log_praxos_get_integrations_completed',
    'log_praxos_get_integrations_failed', 'log_praxos_api_error', 'log_praxos_rate_limit',
    'log_praxos_timeout', 'log_praxos_fallback_used', 'log_praxos_daily_usage',
    'log_praxos_performance_warning', 'log_praxos_context_details',
    
    # Voice logging
    'log_voice_message_received', 'log_voice_message_detection', 'log_voice_transcription_started',
    'log_voice_transcription_completed', 'log_voice_transcription_failed', 'log_voice_file_processing',
    'log_voice_format_conversion', 'log_voice_service_health', 'log_voice_job_queued',
    'log_voice_usage_stats', 'log_voice_worker_status', 'log_voice_model_loaded',
    'log_voice_assistant_integration', 'log_voice_error',
    
    # Logger instances
    'webhook_logger', 'integration_logger', 'llm_logger', 'assistant_logger', 'praxos_logger', 'voice_logger'
]