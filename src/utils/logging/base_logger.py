import logging
import sys
from datetime import datetime
from typing import Dict, Any, Optional
import json

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

def setup_logger(name: str, level: int = logging.INFO) -> logging.Logger:
    """Setup a logger with colored output and proper formatting"""
    logger = logging.getLogger(name)
    logger.setLevel(level)
    
    # Avoid adding handlers multiple times
    if not logger.handlers:
        handler = logging.StreamHandler(sys.stdout)
        handler.setLevel(level)
        
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