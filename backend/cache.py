"""
Caching and session management system for Infoblox AI Chat Interface.
Provides Redis-based caching with fallback to in-memory storage.
"""

import json
import time
import logging
from typing import Any, Dict, List, Optional, Union
from datetime import datetime, timedelta
import hashlib
import uuid

try:
    import redis
    REDIS_AVAILABLE = True
except ImportError:
    REDIS_AVAILABLE = False

from config import config_manager

logger = logging.getLogger(__name__)


class CacheManager:
    """Manages caching with Redis backend and in-memory fallback."""
    
    def __init__(self):
        self.config = config_manager.get_cache_config()
        self.redis_client = None
        self.memory_cache = {}
        self.memory_cache_timestamps = {}
        
        if self.config.enable_cache and REDIS_AVAILABLE and self.config.redis_url:
            try:
                self.redis_client = redis.from_url(
                    self.config.redis_url,
                    decode_responses=True,
                    socket_timeout=5,
                    socket_connect_timeout=5
                )
                # Test connection
                self.redis_client.ping()
                logger.info("Connected to Redis cache")
            except Exception as e:
                logger.warning(f"Failed to connect to Redis: {e}. Using in-memory cache.")
                self.redis_client = None
        else:
            logger.info("Using in-memory cache (Redis not available or disabled)")
    
    def _generate_key(self, prefix: str, identifier: str) -> str:
        """Generate a cache key with prefix."""
        return f"iaci:{prefix}:{identifier}"
    
    def _hash_content(self, content: str) -> str:
        """Generate hash for content-based caching."""
        return hashlib.md5(content.encode()).hexdigest()
    
    def set(self, key: str, value: Any, ttl: int = 3600) -> bool:
        """Set a value in cache with TTL."""
        try:
            serialized_value = json.dumps(value, default=str)
            
            if self.redis_client:
                return self.redis_client.setex(key, ttl, serialized_value)
            else:
                # In-memory fallback
                self.memory_cache[key] = serialized_value
                self.memory_cache_timestamps[key] = time.time() + ttl
                return True
                
        except Exception as e:
            logger.error(f"Failed to set cache key {key}: {e}")
            return False
    
    def get(self, key: str) -> Optional[Any]:
        """Get a value from cache."""
        try:
            if self.redis_client:
                value = self.redis_client.get(key)
                if value:
                    return json.loads(value)
            else:
                # In-memory fallback
                if key in self.memory_cache:
                    if time.time() < self.memory_cache_timestamps.get(key, 0):
                        return json.loads(self.memory_cache[key])
                    else:
                        # Expired
                        self.delete(key)
            
            return None
            
        except Exception as e:
            logger.error(f"Failed to get cache key {key}: {e}")
            return None
    
    def delete(self, key: str) -> bool:
        """Delete a key from cache."""
        try:
            if self.redis_client:
                return bool(self.redis_client.delete(key))
            else:
                # In-memory fallback
                self.memory_cache.pop(key, None)
                self.memory_cache_timestamps.pop(key, None)
                return True
                
        except Exception as e:
            logger.error(f"Failed to delete cache key {key}: {e}")
            return False
    
    def exists(self, key: str) -> bool:
        """Check if key exists in cache."""
        try:
            if self.redis_client:
                return bool(self.redis_client.exists(key))
            else:
                # In-memory fallback
                if key in self.memory_cache:
                    if time.time() < self.memory_cache_timestamps.get(key, 0):
                        return True
                    else:
                        self.delete(key)
                return False
                
        except Exception as e:
            logger.error(f"Failed to check cache key {key}: {e}")
            return False
    
    def clear_expired(self) -> int:
        """Clear expired entries from in-memory cache."""
        if self.redis_client:
            return 0  # Redis handles expiration automatically
        
        current_time = time.time()
        expired_keys = [
            key for key, expiry in self.memory_cache_timestamps.items()
            if current_time >= expiry
        ]
        
        for key in expired_keys:
            self.delete(key)
        
        return len(expired_keys)


class SessionManager:
    """Manages user sessions with caching backend."""
    
    def __init__(self, cache_manager: CacheManager):
        self.cache = cache_manager
        self.session_ttl = 3600  # 1 hour
    
    def create_session(self, user_id: Optional[str] = None) -> str:
        """Create a new session."""
        session_id = str(uuid.uuid4())
        session_data = {
            'id': session_id,
            'user_id': user_id,
            'created_at': datetime.utcnow().isoformat(),
            'last_activity': datetime.utcnow().isoformat(),
            'message_count': 0,
            'context': {}
        }
        
        key = self.cache._generate_key('session', session_id)
        self.cache.set(key, session_data, self.session_ttl)
        
        logger.info(f"Created session {session_id}")
        return session_id
    
    def get_session(self, session_id: str) -> Optional[Dict[str, Any]]:
        """Get session data."""
        key = self.cache._generate_key('session', session_id)
        return self.cache.get(key)
    
    def update_session(self, session_id: str, updates: Dict[str, Any]) -> bool:
        """Update session data."""
        session_data = self.get_session(session_id)
        if not session_data:
            return False
        
        session_data.update(updates)
        session_data['last_activity'] = datetime.utcnow().isoformat()
        
        key = self.cache._generate_key('session', session_id)
        return self.cache.set(key, session_data, self.session_ttl)
    
    def delete_session(self, session_id: str) -> bool:
        """Delete a session."""
        key = self.cache._generate_key('session', session_id)
        return self.cache.delete(key)
    
    def extend_session(self, session_id: str) -> bool:
        """Extend session TTL."""
        session_data = self.get_session(session_id)
        if not session_data:
            return False
        
        key = self.cache._generate_key('session', session_id)
        return self.cache.set(key, session_data, self.session_ttl)


class LLMResponseCache:
    """Caches LLM responses to improve performance and reduce costs."""
    
    def __init__(self, cache_manager: CacheManager):
        self.cache = cache_manager
        self.config = config_manager.get_cache_config()
    
    def _generate_query_hash(self, query: str, context: Dict[str, Any] = None) -> str:
        """Generate hash for query and context."""
        content = query
        if context:
            content += json.dumps(context, sort_keys=True)
        return self.cache._hash_content(content)
    
    def get_cached_response(self, query: str, context: Dict[str, Any] = None) -> Optional[Dict[str, Any]]:
        """Get cached LLM response."""
        query_hash = self._generate_query_hash(query, context)
        key = self.cache._generate_key('llm_response', query_hash)
        
        cached_response = self.cache.get(key)
        if cached_response:
            logger.info(f"Cache hit for query hash {query_hash}")
            return cached_response
        
        return None
    
    def cache_response(self, query: str, response: Dict[str, Any], context: Dict[str, Any] = None) -> bool:
        """Cache LLM response."""
        query_hash = self._generate_query_hash(query, context)
        key = self.cache._generate_key('llm_response', query_hash)
        
        cache_data = {
            'query': query,
            'response': response,
            'context': context,
            'cached_at': datetime.utcnow().isoformat(),
            'query_hash': query_hash
        }
        
        success = self.cache.set(key, cache_data, self.config.llm_cache_ttl)
        if success:
            logger.info(f"Cached LLM response for query hash {query_hash}")
        
        return success


class SchemaCache:
    """Caches WAPI schema information."""
    
    def __init__(self, cache_manager: CacheManager):
        self.cache = cache_manager
        self.config = config_manager.get_cache_config()
    
    def get_schema(self, object_name: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """Get cached schema."""
        key_suffix = object_name if object_name else 'main'
        key = self.cache._generate_key('schema', key_suffix)
        
        cached_schema = self.cache.get(key)
        if cached_schema:
            logger.debug(f"Schema cache hit for {key_suffix}")
            return cached_schema
        
        return None
    
    def cache_schema(self, schema: Dict[str, Any], object_name: Optional[str] = None) -> bool:
        """Cache schema information."""
        key_suffix = object_name if object_name else 'main'
        key = self.cache._generate_key('schema', key_suffix)
        
        cache_data = {
            'schema': schema,
            'object_name': object_name,
            'cached_at': datetime.utcnow().isoformat()
        }
        
        success = self.cache.set(key, cache_data, self.config.schema_cache_ttl)
        if success:
            logger.debug(f"Cached schema for {key_suffix}")
        
        return success


# Global cache instances
cache_manager = CacheManager()
session_manager = SessionManager(cache_manager)
llm_cache = LLMResponseCache(cache_manager)
schema_cache = SchemaCache(cache_manager)


def cleanup_cache():
    """Cleanup expired cache entries."""
    try:
        expired_count = cache_manager.clear_expired()
        if expired_count > 0:
            logger.info(f"Cleaned up {expired_count} expired cache entries")
    except Exception as e:
        logger.error(f"Cache cleanup failed: {e}")


# Schedule periodic cleanup for in-memory cache
import threading
import atexit

def periodic_cleanup():
    """Periodic cleanup function."""
    while True:
        time.sleep(300)  # Run every 5 minutes
        cleanup_cache()

# Start cleanup thread
cleanup_thread = threading.Thread(target=periodic_cleanup, daemon=True)
cleanup_thread.start()

# Cleanup on exit
atexit.register(cleanup_cache)