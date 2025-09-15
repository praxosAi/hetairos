"""
Circuit breaker pattern implementation for Gmail webhook resilience.
Prevents cascade failures and provides graceful degradation.
"""
import time
import asyncio
import logging
from typing import Callable, Any, Dict, Optional
from enum import Enum
from dataclasses import dataclass

from src.utils.logging.base_logger import setup_logger
logger = setup_logger(__name__)

class CircuitState(Enum):
    CLOSED = "closed"      # Normal operation
    OPEN = "open"          # Failing, requests blocked
    HALF_OPEN = "half_open"  # Testing if service recovered

@dataclass
class CircuitBreakerConfig:
    failure_threshold: int = 5          # Failures before opening
    timeout: float = 60.0               # Seconds to wait before half-open
    success_threshold: int = 2          # Successes to close from half-open
    reset_timeout: float = 300.0        # Seconds to reset failure count

class CircuitBreaker:
    """
    Circuit breaker for Gmail API operations.
    Prevents repeated calls to failing services and provides graceful degradation.
    """
    
    def __init__(self, name: str, config: CircuitBreakerConfig = None):
        self.name = name
        self.config = config or CircuitBreakerConfig()
        
        # State tracking
        self.state = CircuitState.CLOSED
        self.failure_count = 0
        self.success_count = 0
        self.last_failure_time = 0
        self.last_success_time = 0
        
        # Statistics
        self.stats = {
            'total_requests': 0,
            'successful_requests': 0,
            'failed_requests': 0,
            'circuit_opens': 0,
            'circuit_closes': 0
        }
    
    async def call(self, func: Callable, *args, **kwargs) -> Any:
        """
        Execute a function with circuit breaker protection.
        
        Args:
            func: Function to execute
            *args, **kwargs: Arguments for the function
            
        Returns:
            Function result or raises CircuitBreakerError
            
        Raises:
            CircuitBreakerOpenError: When circuit is open
        """
        self.stats['total_requests'] += 1
        
        # Check if circuit should transition states
        await self._check_state_transition()
        
        if self.state == CircuitState.OPEN:
            logger.warning(f"Circuit breaker {self.name} is OPEN, request blocked")
            raise CircuitBreakerOpenError(f"Circuit breaker {self.name} is open")
        
        try:
            # Execute the function
            if asyncio.iscoroutinefunction(func):
                result = await func(*args, **kwargs)
            else:
                result = func(*args, **kwargs)
            
            # Record success
            await self._record_success()
            return result
            
        except Exception as e:
            # Record failure
            await self._record_failure(e)
            raise
    
    async def _check_state_transition(self):
        """Check if circuit breaker should change state"""
        current_time = time.time()
        
        if self.state == CircuitState.OPEN:
            # Check if timeout has passed to try half-open
            if current_time - self.last_failure_time >= self.config.timeout:
                logger.info(f"Circuit breaker {self.name} transitioning to HALF_OPEN")
                self.state = CircuitState.HALF_OPEN
                self.success_count = 0
        
        elif self.state == CircuitState.CLOSED:
            # Reset failure count if enough time has passed since last failure
            if (self.last_failure_time > 0 and 
                current_time - self.last_failure_time >= self.config.reset_timeout):
                logger.debug(f"Circuit breaker {self.name} resetting failure count")
                self.failure_count = 0
    
    async def _record_success(self):
        """Record successful operation"""
        self.stats['successful_requests'] += 1
        self.last_success_time = time.time()
        
        if self.state == CircuitState.HALF_OPEN:
            self.success_count += 1
            logger.debug(f"Circuit breaker {self.name} half-open success: {self.success_count}")
            
            if self.success_count >= self.config.success_threshold:
                logger.info(f"Circuit breaker {self.name} transitioning to CLOSED")
                self.state = CircuitState.CLOSED
                self.failure_count = 0
                self.success_count = 0
                self.stats['circuit_closes'] += 1
    
    async def _record_failure(self, exception: Exception):
        """Record failed operation"""
        self.stats['failed_requests'] += 1
        self.failure_count += 1
        self.last_failure_time = time.time()
        
        logger.warning(f"Circuit breaker {self.name} recorded failure: {exception}")
        
        if self.state == CircuitState.CLOSED:
            if self.failure_count >= self.config.failure_threshold:
                logger.error(f"Circuit breaker {self.name} transitioning to OPEN")
                self.state = CircuitState.OPEN
                self.stats['circuit_opens'] += 1
        
        elif self.state == CircuitState.HALF_OPEN:
            logger.warning(f"Circuit breaker {self.name} transitioning back to OPEN")
            self.state = CircuitState.OPEN
            self.success_count = 0
            self.stats['circuit_opens'] += 1
    
    def get_state(self) -> Dict[str, Any]:
        """Get current circuit breaker state"""
        return {
            'name': self.name,
            'state': self.state.value,
            'failure_count': self.failure_count,
            'success_count': self.success_count,
            'last_failure_time': self.last_failure_time,
            'last_success_time': self.last_success_time,
            'config': {
                'failure_threshold': self.config.failure_threshold,
                'timeout': self.config.timeout,
                'success_threshold': self.config.success_threshold,
                'reset_timeout': self.config.reset_timeout
            },
            'stats': self.stats.copy()
        }
    
    def reset(self):
        """Reset circuit breaker to initial state"""
        logger.info(f"Circuit breaker {self.name} manually reset")
        self.state = CircuitState.CLOSED
        self.failure_count = 0
        self.success_count = 0
        self.last_failure_time = 0
        self.last_success_time = 0

class CircuitBreakerOpenError(Exception):
    """Raised when circuit breaker is open and blocks requests"""
    pass

# Gmail-specific circuit breakers
gmail_auth_breaker = CircuitBreaker(
    "gmail_auth",
    CircuitBreakerConfig(
        failure_threshold=3,    # Auth failures are serious
        timeout=120.0,          # Wait 2 minutes before retry
        success_threshold=1,    # Only need one success to close
        reset_timeout=600.0     # Reset failures after 10 minutes
    )
)

gmail_api_breaker = CircuitBreaker(
    "gmail_api",
    CircuitBreakerConfig(
        failure_threshold=5,    # Allow more API failures
        timeout=60.0,           # Wait 1 minute before retry
        success_threshold=2,    # Need 2 successes to close
        reset_timeout=300.0     # Reset failures after 5 minutes
    )
)

pubsub_breaker = CircuitBreaker(
    "pubsub",
    CircuitBreakerConfig(
        failure_threshold=3,    # Pub/Sub should be reliable
        timeout=90.0,           # Wait 1.5 minutes before retry
        success_threshold=1,    # Only need one success to close
        reset_timeout=300.0     # Reset failures after 5 minutes
    )
)

def get_all_circuit_breakers() -> Dict[str, CircuitBreaker]:
    """Get all circuit breakers for monitoring"""
    return {
        'gmail_auth': gmail_auth_breaker,
        'gmail_api': gmail_api_breaker,
        'pubsub': pubsub_breaker
    }

async def test_circuit_breaker():
    """Test circuit breaker functionality"""
    logger.info("🔧 Testing Circuit Breaker...")
    
    # Create test breaker
    test_breaker = CircuitBreaker("test", CircuitBreakerConfig(failure_threshold=2, timeout=1.0))
    
    # Test successful operation
    async def success_func():
        return "success"
    
    result = await test_breaker.call(success_func)
    assert result == "success"
    logger.info("   ✅ Successful operation works")
    
    # Test failing operation
    async def failing_func():
        raise Exception("Test failure")
    
    # Should succeed initially
    try:
        await test_breaker.call(failing_func)
        assert False, "Should have raised exception"
    except Exception as e:
        assert str(e) == "Test failure"
    
    try:
        await test_breaker.call(failing_func)
        assert False, "Should have raised exception"
    except Exception as e:
        assert str(e) == "Test failure"
    
    # Circuit should now be open
    try:
        await test_breaker.call(failing_func)
        assert False, "Should have raised CircuitBreakerOpenError"
    except CircuitBreakerOpenError:
        logger.info("   ✅ Circuit breaker opens after failures")
    
    # Wait for timeout
    await asyncio.sleep(1.1)
    
    # Should now be half-open and allow one request
    result = await test_breaker.call(success_func)
    assert result == "success"
    logger.info("   ✅ Circuit breaker transitions to half-open and closes")
    
    logger.info("   🎉 Circuit breaker test passed!")

if __name__ == "__main__":
    asyncio.run(test_circuit_breaker())