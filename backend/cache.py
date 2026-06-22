import redis
import uuid
import json
from typing import Any
from backend.config import CacheConfig

class CacheManager:
    """Manages the Redis cache for the application."""

    def __init__(self, config: CacheConfig):
        self.config = config
        if config.enable_cache and config.redis_url:
            try:
                self.redis_client = redis.from_url(config.redis_url)
                self.redis_client.ping()
                print("Successfully connected to Redis.")
            except redis.exceptions.ConnectionError as e:
                print(f"Could not connect to Redis: {e}")
                self.redis_client = None
        else:
            self.redis_client = None

    def get(self, key: str):
        """Get a value from the cache. Never raises on a Redis/JSON failure."""
        if not self.redis_client:
            return None
        try:
            value = self.redis_client.get(key)
            return json.loads(value) if value else None
        except (redis.exceptions.RedisError, json.JSONDecodeError) as e:
            print(f"Cache get failed for '{key}': {e}")
            return None

    def set(self, key: str, value: Any, ttl: int = None):
        """Set a value in the cache with an optional TTL. Never raises."""
        if not self.redis_client:
            return
        try:
            ttl = ttl or self.config.llm_cache_ttl
            self.redis_client.set(key, json.dumps(value), ex=ttl)
        except (redis.exceptions.RedisError, TypeError) as e:
            print(f"Cache set failed for '{key}': {e}")

    def delete(self, key: str):
        """Delete a value from the cache. Never raises."""
        if not self.redis_client:
            return
        try:
            self.redis_client.delete(key)
        except redis.exceptions.RedisError as e:
            print(f"Cache delete failed for '{key}': {e}")

    def generate_session_id(self) -> str:
        """Generates a unique session ID."""
        return str(uuid.uuid4())

    def get_session_data(self, session_id: str) -> dict:
        """Retrieves session data from the cache."""
        return self.get(f"session:{session_id}") or {}

    def set_session_data(self, session_id: str, data: dict, ttl: int = None):
        """Stores session data in the cache."""
        self.set(f"session:{session_id}", data, ttl)

    def invalidate_session(self, session_id: str):
        """Invalidates a session by deleting its data from the cache."""
        self.delete(f"session:{session_id}")

    def clear_all_cache(self):
        """Clears all data from the cache. Use with caution."""
        if self.redis_client:
            self.redis_client.flushdb()
            print("All cache data cleared.")