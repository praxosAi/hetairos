from typing import Dict, Any, Optional, List
from datetime import datetime
import json
from .base_logger import setup_logger, log_error, log_timing, truncate_text, format_user_id

# Setup LLM logger
llm_logger = setup_logger("llm")

def log_llm_request_started(operation: str, model: str, user_id: str = None, prompt_length: int = None):
    """Log when LLM request begins"""
    llm_logger.info(f"🤖 LLM Request Started: {operation}")
    llm_logger.info(f"   Model: {model}")
    if user_id:
        llm_logger.info(f"   User: {format_user_id(user_id)}")
    if prompt_length:
        llm_logger.info(f"   Prompt Length: {prompt_length} chars")
    llm_logger.info(f"   Started at: {datetime.utcnow().isoformat()}")

def log_llm_request_completed(operation: str, model: str, duration: float, tokens_used: Dict[str, int] = None, cost: float = None):
    """Log when LLM request completes"""
    llm_logger.info(f"✅ LLM Request Completed: {operation}")
    llm_logger.info(f"   Model: {model}")
    llm_logger.info(f"   Duration: {duration:.2f}s")
    
    if tokens_used:
        llm_logger.info(f"   Tokens Used:")
        for token_type, count in tokens_used.items():
            llm_logger.info(f"     {token_type}: {count}")
        
        total_tokens = sum(tokens_used.values())
        llm_logger.info(f"     Total: {total_tokens}")
    
    if cost:
        llm_logger.info(f"   Estimated Cost: ${cost:.4f}")

def log_llm_request_failed(operation: str, model: str, error: Exception, duration: float = None):
    """Log when LLM request fails"""
    llm_logger.error(f"❌ LLM Request Failed: {operation}")
    llm_logger.error(f"   Model: {model}")
    if duration:
        llm_logger.error(f"   Duration: {duration:.2f}s")
    log_error(llm_logger, error, f"LLM {operation}")

def log_intent_parsing(user_id: str, message: str, intent_result: Dict[str, Any], duration: float):
    """Log intent parsing results"""
    formatted_user = format_user_id(user_id)
    llm_logger.info(f"🧠 Intent Parsing Completed")
    llm_logger.info(f"   User: {formatted_user}")
    llm_logger.info(f"   Message: {truncate_text(message, 100)}")
    llm_logger.info(f"   Intent: {intent_result.get('intent', 'unknown')}")
    llm_logger.info(f"   Integrations Needed: {intent_result.get('integration_needed', [])}")
    llm_logger.info(f"   Urgency: {intent_result.get('urgency', 'unknown')}")
    llm_logger.info(f"   Duration: {duration:.2f}s")
    
    # Log entities if present
    entities = intent_result.get('entities', {})
    if entities:
        llm_logger.debug(f"   Entities: {json.dumps(entities, indent=2)}")

def log_response_generation(user_id: str, intent: str, response: str, duration: float, context_size: int = None):
    """Log response generation"""
    formatted_user = format_user_id(user_id)
    llm_logger.info(f"💬 Response Generated")
    llm_logger.info(f"   User: {formatted_user}")
    llm_logger.info(f"   Intent: {intent}")
    llm_logger.info(f"   Response: {truncate_text(response, 150)}")
    llm_logger.info(f"   Duration: {duration:.2f}s")
    if context_size:
        llm_logger.info(f"   Context Size: {context_size} chars")

def log_prompt_template(operation: str, template_name: str, variables: Dict[str, Any] = None):
    """Log prompt template usage"""
    llm_logger.debug(f"📝 Prompt Template: {template_name}")
    llm_logger.debug(f"   Operation: {operation}")
    if variables:
        # Log variables but truncate long values
        truncated_vars = {}
        for key, value in variables.items():
            if isinstance(value, str) and len(value) > 100:
                truncated_vars[key] = value[:100] + "..."
            else:
                truncated_vars[key] = value
        llm_logger.debug(f"   Variables: {json.dumps(truncated_vars, indent=2, default=str)}")

def log_token_usage_warning(operation: str, model: str, tokens_used: int, limit: int):
    """Log when approaching token limits"""
    usage_percent = (tokens_used / limit) * 100
    llm_logger.warning(f"🚨 High Token Usage: {usage_percent:.1f}%")
    llm_logger.warning(f"   Operation: {operation}")
    llm_logger.warning(f"   Model: {model}")
    llm_logger.warning(f"   Tokens Used: {tokens_used}/{limit}")

def log_model_fallback(original_model: str, fallback_model: str, reason: str):
    """Log when falling back to different model"""
    llm_logger.warning(f"🔄 Model Fallback")
    llm_logger.warning(f"   Original: {original_model}")
    llm_logger.warning(f"   Fallback: {fallback_model}")
    llm_logger.warning(f"   Reason: {reason}")

def log_llm_rate_limit(model: str, wait_time: float, retry_count: int):
    """Log when hitting LLM rate limits"""
    llm_logger.warning(f"🚦 LLM Rate Limit Hit")
    llm_logger.warning(f"   Model: {model}")
    llm_logger.warning(f"   Wait Time: {wait_time:.2f}s")
    llm_logger.warning(f"   Retry Count: {retry_count}")

def log_llm_context_truncation(operation: str, original_size: int, truncated_size: int):
    """Log when context is truncated"""
    llm_logger.warning(f"✂️  Context Truncated")
    llm_logger.warning(f"   Operation: {operation}")
    llm_logger.warning(f"   Original Size: {original_size} chars")
    llm_logger.warning(f"   Truncated Size: {truncated_size} chars")
    llm_logger.warning(f"   Reduction: {((original_size - truncated_size) / original_size) * 100:.1f}%")

def log_llm_daily_usage(model: str, requests_today: int, tokens_today: int, cost_today: float):
    """Log daily LLM usage statistics"""
    llm_logger.info(f"📊 Daily LLM Usage Summary")
    llm_logger.info(f"   Model: {model}")
    llm_logger.info(f"   Requests: {requests_today}")
    llm_logger.info(f"   Tokens: {tokens_today}")
    llm_logger.info(f"   Cost: ${cost_today:.2f}")
    llm_logger.info(f"   Avg Tokens/Request: {tokens_today/max(requests_today, 1):.1f}")
    llm_logger.info(f"   Avg Cost/Request: ${cost_today/max(requests_today, 1):.4f}")