"""
Voice processing logging utilities for AI Personal Assistant
Provides structured logging for voice message transcription and processing
"""

import json
from datetime import datetime
from typing import Dict, Any, Optional
from .base_logger import setup_logger, log_json_data, truncate_text, format_user_id

# Setup dedicated voice logger
voice_logger = setup_logger("voice")

def log_voice_message_received(integration: str, user_id: str, media_info: Dict[str, Any], message_id: str):
    """Log when a voice message is received"""
    voice_logger.info(
        f"🎤 VOICE_MESSAGE_RECEIVED | Integration: {integration} | User: {format_user_id(user_id)} | "
        f"MessageID: {message_id} | MIME: {media_info.get('mime_type', 'unknown')} | "
        f"MediaID: {media_info.get('id', 'unknown')} | "
        f"Filename: {media_info.get('filename', 'none')} | "
        f"Duration: {media_info.get('duration', 'unknown')}s"
    )
    
    # Log detailed media info
    log_json_data(voice_logger, "voice_message_metadata", {
        "event": "voice_message_received",
        "integration": integration,
        "user_id": format_user_id(user_id),
        "message_id": message_id,
        "media_info": media_info,
        "timestamp": datetime.utcnow().isoformat()
    })

def log_voice_message_detection(integration: str, user_id: str, media_info: Dict[str, Any], 
                               is_voice: bool, detection_reason: str):
    """Log voice message detection logic"""
    status = "DETECTED" if is_voice else "NOT_VOICE"
    voice_logger.info(
        f"🔍 VOICE_DETECTION | Integration: {integration} | User: {format_user_id(user_id)} | "
        f"Status: {status} | Reason: {detection_reason} | "
        f"Type: {media_info.get('type', 'unknown')} | MIME: {media_info.get('mime_type', 'unknown')}"
    )

def log_voice_transcription_started(user_id: str, job_id: str, media_info: Dict[str, Any], 
                                  service: str, model: str):
    """Log when voice transcription starts"""
    voice_logger.info(
        f"🎯 TRANSCRIPTION_STARTED | User: {format_user_id(user_id)} | JobID: {job_id} | "
        f"Service: {service} | Model: {model} | "
        f"MediaID: {media_info.get('id', 'unknown')} | "
        f"MIME: {media_info.get('mime_type', 'unknown')}"
    )
    
    log_json_data(voice_logger, "transcription_job_started", {
        "event": "transcription_started",
        "user_id": format_user_id(user_id),
        "job_id": job_id,
        "service": service,
        "model": model,
        "media_info": media_info,
        "timestamp": datetime.utcnow().isoformat()
    })

def log_voice_transcription_completed(user_id: str, job_id: str, transcription_text: str,
                                    confidence: float, language: str, processing_time: float,
                                    service: str, success: bool):
    """Log when voice transcription completes"""
    status = "SUCCESS" if success else "FAILED"
    text_preview = truncate_text(transcription_text, 100) if transcription_text else "empty"
    
    voice_logger.info(
        f"✅ TRANSCRIPTION_COMPLETED | User: {format_user_id(user_id)} | JobID: {job_id} | "
        f"Status: {status} | Service: {service} | "
        f"Language: {language} | Confidence: {confidence:.2f} | "
        f"Time: {processing_time:.2f}s | Length: {len(transcription_text)} chars | "
        f"Text: '{text_preview}'"
    )
    
    log_json_data(voice_logger, "transcription_completed", {
        "event": "transcription_completed",
        "user_id": format_user_id(user_id),
        "job_id": job_id,
        "success": success,
        "service": service,
        "language": language,
        "confidence": confidence,
        "processing_time": processing_time,
        "text_length": len(transcription_text),
        "text_preview": text_preview,
        "timestamp": datetime.utcnow().isoformat()
    })

def log_voice_transcription_failed(user_id: str, job_id: str, error: str, service: str,
                                 retry_count: int, max_retries: int):
    """Log when voice transcription fails"""
    voice_logger.error(
        f"❌ TRANSCRIPTION_FAILED | User: {format_user_id(user_id)} | JobID: {job_id} | "
        f"Service: {service} | Retry: {retry_count}/{max_retries} | "
        f"Error: {truncate_text(error, 200)}"
    )
    
    log_json_data(voice_logger, "transcription_failed", {
        "event": "transcription_failed",
        "user_id": format_user_id(user_id),
        "job_id": job_id,
        "service": service,
        "error": error,
        "retry_count": retry_count,
        "max_retries": max_retries,
        "timestamp": datetime.utcnow().isoformat()
    })

def log_voice_file_processing(user_id: str, job_id: str, operation: str, 
                            file_path: str, success: bool, details: Optional[Dict] = None):
    """Log voice file processing operations (download, conversion, cleanup)"""
    status = "SUCCESS" if success else "FAILED"
    voice_logger.info(
        f"📁 FILE_PROCESSING | User: {format_user_id(user_id)} | JobID: {job_id} | "
        f"Operation: {operation} | Status: {status} | File: {file_path}"
    )
    
    log_data = {
        "event": "file_processing",
        "user_id": format_user_id(user_id),
        "job_id": job_id,
        "operation": operation,
        "file_path": file_path,
        "success": success,
        "timestamp": datetime.utcnow().isoformat()
    }
    
    if details:
        log_data.update(details)
    
    log_json_data(voice_logger, "file_processing", log_data)

def log_voice_format_conversion(user_id: str, job_id: str, input_format: str, 
                              output_format: str, input_size: int, output_size: int,
                              conversion_time: float, success: bool):
    """Log audio format conversion"""
    status = "SUCCESS" if success else "FAILED"
    voice_logger.info(
        f"🔄 FORMAT_CONVERSION | User: {format_user_id(user_id)} | JobID: {job_id} | "
        f"Status: {status} | {input_format} → {output_format} | "
        f"Size: {input_size} → {output_size} bytes | Time: {conversion_time:.2f}s"
    )
    
    log_json_data(voice_logger, "format_conversion", {
        "event": "format_conversion",
        "user_id": format_user_id(user_id),
        "job_id": job_id,
        "input_format": input_format,
        "output_format": output_format,
        "input_size": input_size,
        "output_size": output_size,
        "conversion_time": conversion_time,
        "success": success,
        "timestamp": datetime.utcnow().isoformat()
    })

def log_voice_service_health(service: str, available: bool, details: Optional[Dict] = None):
    """Log voice service health checks"""
    status = "AVAILABLE" if available else "UNAVAILABLE"
    voice_logger.info(f"🏥 SERVICE_HEALTH | Service: {service} | Status: {status}")
    
    log_data = {
        "event": "service_health_check",
        "service": service,
        "available": available,
        "timestamp": datetime.utcnow().isoformat()
    }
    
    if details:
        log_data.update(details)
    
    log_json_data(voice_logger, "service_health", log_data)

def log_voice_job_queued(user_id: str, job_id: str, queue_size: int, estimated_wait_time: Optional[float] = None):
    """Log when a voice transcription job is queued"""
    voice_logger.info(
        f"📥 JOB_QUEUED | User: {format_user_id(user_id)} | JobID: {job_id} | "
        f"QueueSize: {queue_size} | EstimatedWait: {estimated_wait_time or 'unknown'}s"
    )
    
    log_json_data(voice_logger, "job_queued", {
        "event": "job_queued",
        "user_id": format_user_id(user_id),
        "job_id": job_id,
        "queue_size": queue_size,
        "estimated_wait_time": estimated_wait_time,
        "timestamp": datetime.utcnow().isoformat()
    })

def log_voice_usage_stats(daily_minutes_used: int, daily_limit: int, cost_estimate: float,
                        service: str, user_count: int):
    """Log voice transcription usage statistics"""
    usage_percentage = (daily_minutes_used / daily_limit * 100) if daily_limit > 0 else 0
    
    voice_logger.info(
        f"📊 USAGE_STATS | Service: {service} | Usage: {daily_minutes_used}/{daily_limit} min ({usage_percentage:.1f}%) | "
        f"Cost: ${cost_estimate:.2f} | Users: {user_count}"
    )
    
    log_json_data(voice_logger, "usage_stats", {
        "event": "usage_stats",
        "service": service,
        "daily_minutes_used": daily_minutes_used,
        "daily_limit": daily_limit,
        "usage_percentage": usage_percentage,
        "cost_estimate": cost_estimate,
        "user_count": user_count,
        "timestamp": datetime.utcnow().isoformat()
    })

def log_voice_worker_status(status: str, active_jobs: int, queue_size: int, 
                          processing_jobs: int, completed_today: int, failed_today: int):
    """Log voice transcription worker status"""
    voice_logger.info(
        f"⚙️ WORKER_STATUS | Status: {status} | Active: {active_jobs} | Queue: {queue_size} | "
        f"Processing: {processing_jobs} | Completed: {completed_today} | Failed: {failed_today}"
    )
    
    log_json_data(voice_logger, "worker_status", {
        "event": "worker_status",
        "status": status,
        "active_jobs": active_jobs,
        "queue_size": queue_size,
        "processing_jobs": processing_jobs,
        "completed_today": completed_today,
        "failed_today": failed_today,
        "timestamp": datetime.utcnow().isoformat()
    })

def log_voice_model_loaded(service: str, model_name: str, model_size: str, 
                         load_time: float, memory_usage: Optional[int] = None):
    """Log when a voice model is loaded"""
    voice_logger.info(
        f"🧠 MODEL_LOADED | Service: {service} | Model: {model_name} ({model_size}) | "
        f"LoadTime: {load_time:.2f}s | Memory: {memory_usage or 'unknown'} MB"
    )
    
    log_json_data(voice_logger, "model_loaded", {
        "event": "model_loaded",
        "service": service,
        "model_name": model_name,
        "model_size": model_size,
        "load_time": load_time,
        "memory_usage": memory_usage,
        "timestamp": datetime.utcnow().isoformat()
    })

def log_voice_assistant_integration(user_id: str, job_id: str, transcribed_text: str,
                                  assistant_response: str, processing_time: float):
    """Log when transcribed voice is passed to assistant"""
    voice_logger.info(
        f"🤖 ASSISTANT_INTEGRATION | User: {format_user_id(user_id)} | JobID: {job_id} | "
        f"TranscribedLength: {len(transcribed_text)} chars | "
        f"ResponseLength: {len(assistant_response)} chars | Time: {processing_time:.2f}s"
    )
    
    log_json_data(voice_logger, "assistant_integration", {
        "event": "assistant_integration",
        "user_id": format_user_id(user_id),
        "job_id": job_id,
        "transcribed_text_preview": truncate_text(transcribed_text, 100),
        "transcribed_length": len(transcribed_text),
        "response_length": len(assistant_response),
        "processing_time": processing_time,
        "timestamp": datetime.utcnow().isoformat()
    })

def log_voice_error(user_id: str, job_id: str, error_type: str, error_message: str, 
                   context: Optional[Dict] = None):
    """Log voice processing errors with context"""
    voice_logger.error(
        f"💥 VOICE_ERROR | User: {format_user_id(user_id)} | JobID: {job_id} | "
        f"Type: {error_type} | Error: {truncate_text(error_message, 200)}"
    )
    
    log_data = {
        "event": "voice_error",
        "user_id": format_user_id(user_id),
        "job_id": job_id,
        "error_type": error_type,
        "error_message": error_message,
        "timestamp": datetime.utcnow().isoformat()
    }
    
    if context:
        log_data["context"] = context
    
    log_json_data(voice_logger, "voice_error", log_data)