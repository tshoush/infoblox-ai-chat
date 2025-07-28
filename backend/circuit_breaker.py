"""
Circuit breaker pattern implementation for external service protection.
Provides resilience against service failures with automatic recovery.
"""

import time
import logging
from typing import Callable, Any, Dict, Optional
from enum import Enum
from dataclasses import dataclass
from functools import wraps
import threading

logger = logging.getLogger(__name__)


class CircuitState(Enum):
    """Circuit breaker states."""
    CLOSED = "closed"      # Normal operation
    OPEN = "open"          # Failing, blocking requests
    HALF_OPEN = "half_open"  # Testing if service recovered


@dataclass
class CircuitBreakerConfig:
    """Configuration for circuit breaker."""
    failure_threshold: int = 5          # Failures before opening
    recovery_timeout: int = 60          # Seconds before trying half-open
    success_threshold: int = 3          # Successes to close from half-open
    timeout: int = 30                   # Request timeout in seconds


class CircuitBreakerError(Exception):
    """Raised when circuit breaker is open."""
    pass


class CircuitBreaker:
    """Circuit breaker implementation for external service calls."""
    
    def __init__(self, name: str, config: CircuitBreakerConfig = None):
        self.name = name
        self.config = config or CircuitBreakerConfig()
        self.state = CircuitState.CLOSED
        self.failure_count = 0
        self.success_count = 0
        self.last_failure_time = 0
        self.lock = threading.RLock()
        
        logger.info(f"Initialized circuit breaker '{name}' with config: {self.config}")
    
    def call(self, func: Callable, *args, **kwargs) -> Any:
        """Execute function with circuit breaker protection."""
        with self.lock:
            if self.state == CircuitState.OPEN:
                if self._should_attempt_reset():
                    self.state = CircuitState.HALF_OPEN
                    self.success_count = 0
                    logger.info(f"Circuit breaker '{self.name}' moved to HALF_OPEN")
                else:
                    raise CircuitBreakerError(
                        f"Circuit breaker '{self.name}' is OPEN. "
                        f"Service unavailable. Next attempt in "
                        f"{self._time_until_next_attempt():.1f} seconds."
                    )
            
            try:
                # Execute the function with timeout
                start_time = time.time()
                result = func(*args, **kwargs)
                execution_time = time.time() - start_time
                
                # Record success
                self._record_success(execution_time)
                return result
                
            except Exception as e:
                # Record failure
                self._record_failure(e)
                raise
    
    def _should_attempt_reset(self) -> bool:
        """Check if enough time has passed to attempt reset."""
        return time.time() - self.last_failure_time >= self.config.recovery_timeout
    
    def _time_until_next_attempt(self) -> float:
        """Calculate time until next attempt is allowed."""
        return max(0, self.config.recovery_timeout - (time.time() - self.last_failure_time))
    
    def _record_success(self, execution_time: float):
        """Record successful execution."""
        if self.state == CircuitState.HALF_OPEN:
            self.success_count += 1
            logger.debug(f"Circuit breaker '{self.name}' success {self.success_count}/{self.config.success_threshold}")
            
            if self.success_count >= self.config.success_threshold:
                self.state = CircuitState.CLOSED
                self.failure_count = 0
                self.success_count = 0
                logger.info(f"Circuit breaker '{self.name}' moved to CLOSED after recovery")
        
        elif self.state == CircuitState.CLOSED:
            # Reset failure count on success
            if self.failure_count > 0:
                self.failure_count = 0
                logger.debug(f"Circuit breaker '{self.name}' reset failure count")
        
        logger.debug(f"Circuit breaker '{self.name}' successful call in {execution_time:.3f}s")
    
    def _record_failure(self, exception: Exception):
        """Record failed execution."""
        self.failure_count += 1
        self.last_failure_time = time.time()
        
        logger.warning(f"Circuit breaker '{self.name}' failure {self.failure_count}/{self.config.failure_threshold}: {exception}")
        
        if self.state == CircuitState.HALF_OPEN:
            # Failure during half-open immediately opens circuit
            self.state = CircuitState.OPEN
            self.success_count = 0
            logger.warning(f"Circuit breaker '{self.name}' moved to OPEN (failed during half-open)")
        
        elif self.state == CircuitState.CLOSED and self.failure_count >= self.config.failure_threshold:
            # Too many failures, open the circuit
            self.state = CircuitState.OPEN
            logger.warning(f"Circuit breaker '{self.name}' moved to OPEN (threshold reached)")
    
    def get_state(self) -> Dict[str, Any]:
        """Get current circuit breaker state."""
        with self.lock:
            return {
                'name': self.name,
                'state': self.state.value,
                'failure_count': self.failure_count,
                'success_count': self.success_count,
                'last_failure_time': self.last_failure_time,
                'time_until_next_attempt': self._time_until_next_attempt() if self.state == CircuitState.OPEN else 0,
                'config': {
                    'failure_threshold': self.config.failure_threshold,
                    'recovery_timeout': self.config.recovery_timeout,
                    'success_threshold': self.config.success_threshold,
                    'timeout': self.config.timeout
                }
            }
    
    def reset(self):
        """Manually reset circuit breaker to closed state."""
        with self.lock:
            self.state = CircuitState.CLOSED
            self.failure_count = 0
            self.success_count = 0
            self.last_failure_time = 0
            logger.info(f"Circuit breaker '{self.name}' manually reset to CLOSED")


class CircuitBreakerManager:
    """Manages multiple circuit breakers."""
    
    def __init__(self):
        self.breakers: Dict[str, CircuitBreaker] = {}
        self.lock = threading.RLock()
    
    def get_breaker(self, name: str, config: CircuitBreakerConfig = None) -> CircuitBreaker:
        """Get or create a circuit breaker."""
        with self.lock:
            if name not in self.breakers:
                self.breakers[name] = CircuitBreaker(name, config)
            return self.breakers[name]
    
    def call_with_breaker(self, name: str, func: Callable, *args, config: CircuitBreakerConfig = None, **kwargs) -> Any:
        """Execute function with named circuit breaker."""
        breaker = self.get_breaker(name, config)
        return breaker.call(func, *args, **kwargs)
    
    def get_all_states(self) -> Dict[str, Dict[str, Any]]:
        """Get states of all circuit breakers."""
        with self.lock:
            return {name: breaker.get_state() for name, breaker in self.breakers.items()}
    
    def reset_breaker(self, name: str) -> bool:
        """Reset a specific circuit breaker."""
        with self.lock:
            if name in self.breakers:
                self.breakers[name].reset()
                return True
            return False
    
    def reset_all(self):
        """Reset all circuit breakers."""
        with self.lock:
            for breaker in self.breakers.values():
                breaker.reset()
            logger.info("All circuit breakers reset")


# Global circuit breaker manager
circuit_breaker_manager = CircuitBreakerManager()


def circuit_breaker(name: str, config: CircuitBreakerConfig = None):
    """Decorator for circuit breaker protection."""
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs):
            return circuit_breaker_manager.call_with_breaker(name, func, *args, config=config, **kwargs)
        return wrapper
    return decorator


# Retry logic with exponential backoff
def retry_with_backoff(max_retries: int = 3, base_delay: float = 1.0, max_delay: float = 60.0, backoff_factor: float = 2.0):
    """Decorator for retry logic with exponential backoff."""
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs):
            last_exception = None
            
            for attempt in range(max_retries + 1):
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    last_exception = e
                    
                    if attempt == max_retries:
                        # Last attempt failed
                        logger.error(f"Function {func.__name__} failed after {max_retries + 1} attempts: {e}")
                        raise
                    
                    # Calculate delay with exponential backoff
                    delay = min(base_delay * (backoff_factor ** attempt), max_delay)
                    logger.warning(f"Function {func.__name__} attempt {attempt + 1} failed: {e}. Retrying in {delay:.1f}s")
                    time.sleep(delay)
            
            # This should never be reached, but just in case
            raise last_exception
        return wrapper
    return decorator


# Predefined circuit breaker configurations
INFOBLOX_BREAKER_CONFIG = CircuitBreakerConfig(
    failure_threshold=3,
    recovery_timeout=30,
    success_threshold=2,
    timeout=30
)

LLM_BREAKER_CONFIG = CircuitBreakerConfig(
    failure_threshold=5,
    recovery_timeout=60,
    success_threshold=3,
    timeout=30
)

# Convenience functions for common services
def call_infoblox_with_breaker(func: Callable, *args, **kwargs) -> Any:
    """Call Infoblox API with circuit breaker protection."""
    return circuit_breaker_manager.call_with_breaker('infoblox', func, *args, config=INFOBLOX_BREAKER_CONFIG, **kwargs)

def call_llm_with_breaker(func: Callable, *args, **kwargs) -> Any:
    """Call LLM API with circuit breaker protection."""
    return circuit_breaker_manager.call_with_breaker('llm', func, *args, config=LLM_BREAKER_CONFIG, **kwargs)