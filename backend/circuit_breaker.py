import time


class CircuitOpenError(Exception):
    """Raised when a call is rejected because the circuit is open."""


class CircuitBreaker:
    """Implements a circuit breaker pattern for external service calls with retry logic."""

    def __init__(self, failure_threshold: int = 3, recovery_timeout: int = 30, max_retries: int = 3, initial_backoff: float = 1.0):
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.max_retries = max_retries
        self.initial_backoff = initial_backoff
        self.failure_count = 0
        self.state = "closed"
        self.last_failure_time = 0

    def call(self, func, *args, **kwargs):
        """Execute a function with circuit breaker protection and retry logic.

        Fails fast with ``CircuitOpenError`` while the circuit is open and the
        recovery timeout has not elapsed. Once it elapses, a single trial call
        is allowed (half-open); success closes the circuit, failure re-opens it.
        """
        # Fail fast if the circuit is open and we are still within the cooldown.
        if self.state == "open":
            if time.time() - self.last_failure_time > self.recovery_timeout:
                self.state = "half-open"
            else:
                raise CircuitOpenError("Circuit is open")

        # In half-open we allow exactly ONE trial call (no retries); otherwise the
        # retries that belong to a single logical request all share one failure.
        max_attempts = 1 if self.state == "half-open" else self.max_retries + 1
        last_exception = None
        for attempt in range(max_attempts):
            try:
                result = func(*args, **kwargs)
                self.reset()
                return result
            except Exception as e:
                last_exception = e
                if attempt < max_attempts - 1:
                    time.sleep(self.initial_backoff * (2 ** attempt))  # Exponential backoff

        # Count ONE failure for the whole call (not one per retry). A failed
        # half-open trial reopens immediately; otherwise we open at the threshold.
        self.failure_count += 1
        if self.state == "half-open" or self.failure_count >= self.failure_threshold:
            self.state = "open"
            self.last_failure_time = time.time()
        raise last_exception

    def record_failure(self):
        """Record a failed operation and update the circuit state."""
        self.failure_count += 1
        if self.failure_count >= self.failure_threshold:
            self.state = "open"
            self.last_failure_time = time.time()

    def reset(self):
        """Reset the circuit after a successful operation."""
        self.failure_count = 0
        self.state = "closed"