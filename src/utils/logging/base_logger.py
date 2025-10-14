import logging
import sys
from datetime import datetime
from typing import Dict, Any, Optional
import json
from contextvars import ContextVar
import platform
# Context variables for request-specific data
request_id_var: ContextVar[Optional[str]] = ContextVar("request_id", default='SYSTEM_LEVEL')
user_id_var: ContextVar[Optional[str]] = ContextVar("user_id", default='SYSTEM_LEVEL')
modality_var: ContextVar[Optional[str]] = ContextVar("modality", default='SYSTEM_LEVEL')


if platform.system() == "Darwin" or platform.system() == "Windows":
    # If local, use colored logging for better readability
    json_logging = False
else:
    # If in production (Linux), use JSON logging for better integration with log management system.
    json_logging = True
# Flag to ensure noisy loggers are only suppressed once
_loggers_suppressed = False

def _suppress_noisy_loggers():
    """Suppress verbose third-party library loggers globally."""
    global _loggers_suppressed
    if _loggers_suppressed:
        return

    # Azure SDK - extremely verbose AMQP protocol logs
    logging.getLogger("azure.servicebus").setLevel(logging.WARNING)
    logging.getLogger("azure.core").setLevel(logging.WARNING)
    logging.getLogger("azure.servicebus._pyamqp").setLevel(logging.WARNING)

    # Playwright - can be verbose with browser interactions
    logging.getLogger("playwright").setLevel(logging.WARNING)

    # Browser-use - only warnings and errors
    logging.getLogger("browser_use").setLevel(logging.WARNING)

    _loggers_suppressed = True

class ContextFilter(logging.Filter):
    """
    A logging filter that injects context variables (request_id, user_id, modality) into log records.
    """
    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = request_id_var.get()
        record.user_id = user_id_var.get()
        record.modality = modality_var.get()
        return True

class ColoredFormatter(logging.Formatter):
    """Custom formatter with colors for different log levels"""
    
    COLORS = {
        'DEBUG': '\033[36m',    # Cyan
        'INFO': '\033[32m',     # Green
        'WARNING': '\033[33m',  # Yellow
        'ERROR': '\033[31m',    # Red
        'CRITICAL': '\033[35m', # Magenta
    }
    RESET = '\033[0m'
    
    def format(self, record):
        log_color = self.COLORS.get(record.levelname, self.RESET)
        record.levelname = f"{log_color}{record.levelname}{self.RESET}"
        return super().format(record)

class JsonFormatter(logging.Formatter):
    """Custom formatter to output log records as JSON."""
    def format(self, record: logging.LogRecord) -> str:
        log_entry = {
            "timestamp": self.formatTime(record, self.datefmt),
            "level": record.levelname,
            "logger_name": record.name,
            "message": record.getMessage(),
            "context": {
                "request_id": getattr(record, "request_id", None),
                "user_id": getattr(record, "user_id", None),
                "modality": getattr(record, "modality", None),
            }
        }

        # Add any other extra attributes passed to the logger
        extra_attrs = {
            key: value for key, value in record.__dict__.items()
            if key not in logging.LogRecord.__dict__ and key not in log_entry and key not in ['request_id', 'user_id', 'modality']
        }
        if extra_attrs:
            log_entry['extra'] = extra_attrs

        if record.exc_info:
            log_entry["exception"] = self.formatException(record.exc_info)
        
        # Use separators for compact output and default=str for robustness
        return json.dumps(log_entry, separators=(',', ':'), default=str)

def setup_logger(name: str, level: int = logging.INFO, json_format: bool = json_logging) -> logging.Logger:
    """Setup a logger with colored output or JSON formatting with context."""
    logger = logging.getLogger(name)
    logger.setLevel(level)

    # Avoid adding handlers multiple times
    if not logger.handlers:
        handler = logging.StreamHandler(sys.stdout)
        handler.setLevel(level)
        
        if json_format:
            formatter = JsonFormatter(datefmt='%Y-%m-%d %H:%M:%S')
            handler.addFilter(ContextFilter()) # Add the context filter
        else:
            formatter = ColoredFormatter(
                '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
                datefmt='%Y-%m-%d %H:%M:%S'
            )
        handler.setFormatter(formatter)
        logger.addHandler(handler)
    
    return logger

def log_error(logger: logging.Logger, error: Exception, context: str = None):
    """Log errors with context - common utility"""
    logger.error(f"❌ Error occurred: {str(error)}")
    if context:
        logger.error(f"   Context: {context}")
    logger.error(f"   Error Type: {type(error).__name__}")

def log_json_data(logger: logging.Logger, data: Dict[str, Any], title: str = "Data", max_length: int = 1000):
    """Log JSON data with truncation for readability"""
    json_str = json.dumps(data, indent=2)
    if len(json_str) > max_length:
        json_str = json_str[:max_length] + "... (truncated)"
    logger.debug(f"{title}:")
    logger.debug(json_str)

def log_timing(logger: logging.Logger, operation: str, start_time: datetime, end_time: datetime = None):
    """Log operation timing"""
    if end_time is None:
        end_time = datetime.utcnow()
    duration = (end_time - start_time).total_seconds()
    logger.info(f"⏱️  {operation} completed in {duration:.2f} seconds")

def truncate_text(text: str, max_length: int = 200) -> str:
    """Truncate text for logging with ellipsis"""
    if len(text) > max_length:
        return text[:max_length] + "..."
    return text

def format_user_id(user_id: str) -> str:
    """Format user ID for consistent logging"""
    # # Mask phone numbers for privacy: +1234567890 -> +123***7890
    # if user_id.startswith('+') and len(user_id) > 6:
    #     return user_id[:4] + "***" + user_id[-4:]
    return user_id