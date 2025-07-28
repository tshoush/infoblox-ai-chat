"""
LLM client with multi-provider support and circuit breaker protection.
Handles communication with various LLM providers with fallback strategies.
"""

import json
import logging
import time
from typing import Dict, List, Any, Optional, Union
from dataclasses import dataclass
from abc import ABC, abstractmethod
import requests

from config import config_manager
from circuit_breaker import call_llm_with_breaker, CircuitBreakerError
from cache import llm_cache

logger = logging.getLogger(__name__)


@dataclass
class LLMRequest:
    """Represents an LLM request."""
    prompt: str
    context: Optional[Dict[str, Any]] = None
    temperature: float = 0.7
    max_tokens: int = 4000
    system_message: Optional[str] = None


@dataclass
class LLMResponse:
    """Represents an LLM response."""
    content: str
    provider: str
    model: Optional[str] = None
    usage: Optional[Dict[str, Any]] = None
    confidence: float = 1.0
    cached: bool = False
    response_time: float = 0.0


class LLMProvider(ABC):
    """Abstract base class for LLM providers."""
    
    @abstractmethod
    def send_request(self, request: LLMRequest) -> LLMResponse:
        """Send request to LLM provider."""
        pass
    
    @abstractmethod
    def is_available(self) -> bool:
        """Check if provider is available."""
        pass


class OpenAIProvider(LLMProvider):
    """OpenAI API provider."""
    
    def __init__(self, api_key: str, base_url: Optional[str] = None, model: str = "gpt-3.5-turbo"):
        self.api_key = api_key
        self.base_url = base_url or "https://api.openai.com/v1"
        self.model = model
        self.session = requests.Session()
        self.session.headers.update({
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        })
    
    def send_request(self, request: LLMRequest) -> LLMResponse:
        """Send request to OpenAI API."""
        start_time = time.time()
        
        messages = []
        if request.system_message:
            messages.append({"role": "system", "content": request.system_message})
        
        messages.append({"role": "user", "content": request.prompt})
        
        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": request.temperature,
            "max_tokens": request.max_tokens
        }
        
        response = self.session.post(
            f"{self.base_url}/chat/completions",
            json=payload,
            timeout=30
        )
        response.raise_for_status()
        
        data = response.json()
        response_time = time.time() - start_time
        
        return LLMResponse(
            content=data["choices"][0]["message"]["content"],
            provider="openai",
            model=self.model,
            usage=data.get("usage"),
            response_time=response_time
        )
    
    def is_available(self) -> bool:
        """Check if OpenAI API is available."""
        try:
            response = self.session.get(f"{self.base_url}/models", timeout=5)
            return response.status_code == 200
        except Exception:
            return False


class ClaudeProvider(LLMProvider):
    """Anthropic Claude API provider."""
    
    def __init__(self, api_key: str, model: str = "claude-3-sonnet-20240229"):
        self.api_key = api_key
        self.model = model
        self.base_url = "https://api.anthropic.com/v1"
        self.session = requests.Session()
        self.session.headers.update({
            "x-api-key": api_key,
            "Content-Type": "application/json",
            "anthropic-version": "2023-06-01"
        })
    
    def send_request(self, request: LLMRequest) -> LLMResponse:
        """Send request to Claude API."""
        start_time = time.time()
        
        payload = {
            "model": self.model,
            "max_tokens": request.max_tokens,
            "temperature": request.temperature,
            "messages": [
                {"role": "user", "content": request.prompt}
            ]
        }
        
        if request.system_message:
            payload["system"] = request.system_message
        
        response = self.session.post(
            f"{self.base_url}/messages",
            json=payload,
            timeout=30
        )
        response.raise_for_status()
        
        data = response.json()
        response_time = time.time() - start_time
        
        return LLMResponse(
            content=data["content"][0]["text"],
            provider="claude",
            model=self.model,
            usage=data.get("usage"),
            response_time=response_time
        )
    
    def is_available(self) -> bool:
        """Check if Claude API is available."""
        try:
            # Claude doesn't have a simple health check, so we'll assume it's available if we have an API key
            return bool(self.api_key)
        except Exception:
            return False


class LocalProvider(LLMProvider):
    """Local LLM provider (e.g., Ollama, local OpenAI-compatible API)."""
    
    def __init__(self, base_url: str, model: str = "llama2"):
        self.base_url = base_url.rstrip('/')
        self.model = model
        self.session = requests.Session()
        self.session.headers.update({
            "Content-Type": "application/json"
        })
    
    def send_request(self, request: LLMRequest) -> LLMResponse:
        """Send request to local LLM API."""
        start_time = time.time()
        
        # Try OpenAI-compatible format first
        try:
            messages = []
            if request.system_message:
                messages.append({"role": "system", "content": request.system_message})
            messages.append({"role": "user", "content": request.prompt})
            
            payload = {
                "model": self.model,
                "messages": messages,
                "temperature": request.temperature,
                "max_tokens": request.max_tokens
            }
            
            response = self.session.post(
                f"{self.base_url}/v1/chat/completions",
                json=payload,
                timeout=60  # Local models might be slower
            )
            
            if response.status_code == 200:
                data = response.json()
                response_time = time.time() - start_time
                
                return LLMResponse(
                    content=data["choices"][0]["message"]["content"],
                    provider="local",
                    model=self.model,
                    usage=data.get("usage"),
                    response_time=response_time
                )
        except Exception as e:
            logger.warning(f"OpenAI-compatible format failed: {e}")
        
        # Try Ollama format
        try:
            payload = {
                "model": self.model,
                "prompt": request.prompt,
                "temperature": request.temperature,
                "options": {
                    "num_predict": request.max_tokens
                }
            }
            
            response = self.session.post(
                f"{self.base_url}/api/generate",
                json=payload,
                timeout=60
            )
            response.raise_for_status()
            
            data = response.json()
            response_time = time.time() - start_time
            
            return LLMResponse(
                content=data["response"],
                provider="local",
                model=self.model,
                response_time=response_time
            )
            
        except Exception as e:
            logger.error(f"Local LLM request failed: {e}")
            raise
    
    def is_available(self) -> bool:
        """Check if local LLM is available."""
        try:
            # Try to get model list
            response = self.session.get(f"{self.base_url}/api/tags", timeout=5)
            return response.status_code == 200
        except Exception:
            try:
                # Try OpenAI-compatible health check
                response = self.session.get(f"{self.base_url}/v1/models", timeout=5)
                return response.status_code == 200
            except Exception:
                return False


class LLMClient:
    """Main LLM client with multi-provider support and fallback."""
    
    def __init__(self):
        self.config = config_manager.get_llm_config()
        self.providers: Dict[str, LLMProvider] = {}
        self.primary_provider = None
        self.fallback_providers: List[LLMProvider] = []
        
        self._initialize_providers()
    
    def _initialize_providers(self):
        """Initialize LLM providers based on configuration."""
        provider_name = self.config.provider.lower()
        
        try:
            if provider_name == "openai":
                self.primary_provider = OpenAIProvider(
                    api_key=self.config.api_key,
                    base_url=self.config.base_url,
                    model=self.config.model or "gpt-3.5-turbo"
                )
                self.providers["openai"] = self.primary_provider
                
            elif provider_name == "claude":
                self.primary_provider = ClaudeProvider(
                    api_key=self.config.api_key,
                    model=self.config.model or "claude-3-sonnet-20240229"
                )
                self.providers["claude"] = self.primary_provider
                
            elif provider_name in ["local", "ollama", "llama"]:
                if not self.config.base_url:
                    raise ValueError("Base URL required for local LLM provider")
                
                self.primary_provider = LocalProvider(
                    base_url=self.config.base_url,
                    model=self.config.model or "llama2"
                )
                self.providers["local"] = self.primary_provider
                
            else:
                raise ValueError(f"Unsupported LLM provider: {provider_name}")
            
            logger.info(f"Initialized primary LLM provider: {provider_name}")
            
            # Initialize fallback providers if enabled
            if self.config.fallback_enabled:
                self._initialize_fallback_providers()
                
        except Exception as e:
            logger.error(f"Failed to initialize LLM provider {provider_name}: {e}")
            raise
    
    def _initialize_fallback_providers(self):
        """Initialize fallback providers."""
        # For now, we'll use a simple keyword-based fallback
        # In a production system, you might want multiple LLM providers
        logger.info("Fallback processing enabled for LLM failures")
    
    def send_request(self, request: LLMRequest) -> LLMResponse:
        """Send request with caching and circuit breaker protection."""
        # Check cache first
        cached_response = llm_cache.get_cached_response(request.prompt, request.context)
        if cached_response:
            return LLMResponse(
                content=cached_response['response']['content'],
                provider=cached_response['response']['provider'],
                model=cached_response['response'].get('model'),
                cached=True,
                response_time=0.0
            )
        
        # Try primary provider with circuit breaker
        try:
            response = call_llm_with_breaker(self._send_to_provider, self.primary_provider, request)
            
            # Cache successful response
            llm_cache.cache_response(
                request.prompt,
                {
                    'content': response.content,
                    'provider': response.provider,
                    'model': response.model,
                    'confidence': response.confidence
                },
                request.context
            )
            
            return response
            
        except CircuitBreakerError as e:
            logger.warning(f"Circuit breaker open for LLM: {e}")
            if self.config.fallback_enabled:
                return self._fallback_processing(request)
            raise
            
        except Exception as e:
            logger.error(f"LLM request failed: {e}")
            if self.config.fallback_enabled:
                return self._fallback_processing(request)
            raise
    
    def _send_to_provider(self, provider: LLMProvider, request: LLMRequest) -> LLMResponse:
        """Send request to specific provider."""
        if not provider.is_available():
            raise Exception(f"Provider {provider.__class__.__name__} is not available")
        
        return provider.send_request(request)
    
    def _fallback_processing(self, request: LLMRequest) -> LLMResponse:
        """Fallback processing when LLM is unavailable."""
        logger.info("Using fallback processing for LLM request")
        
        # Simple keyword-based intent recognition
        prompt_lower = request.prompt.lower()
        
        if any(word in prompt_lower for word in ['show', 'list', 'get', 'find', 'search']):
            intent = "search"
        elif any(word in prompt_lower for word in ['create', 'add', 'new']):
            intent = "create"
        elif any(word in prompt_lower for word in ['update', 'modify', 'change']):
            intent = "update"
        elif any(word in prompt_lower for word in ['delete', 'remove']):
            intent = "delete"
        else:
            intent = "unknown"
        
        fallback_response = (
            f"I'm currently operating in fallback mode due to LLM service unavailability. "
            f"Based on your request, I detected a '{intent}' intent. "
            f"Please try again later for full AI processing, or use specific WAPI commands."
        )
        
        return LLMResponse(
            content=fallback_response,
            provider="fallback",
            confidence=0.3,
            response_time=0.1
        )
    
    def format_prompt_for_wapi(self, user_query: str, context: Dict[str, Any] = None) -> str:
        """Format prompt for WAPI operation generation."""
        system_context = """You are an expert Infoblox NIOS administrator. Your job is to translate natural language queries into specific WAPI operations.

Available WAPI objects include:
- record:a (A records)
- record:aaaa (AAAA records) 
- record:cname (CNAME records)
- record:mx (MX records)
- record:ptr (PTR records)
- network (Network objects)
- range (DHCP ranges)
- host (Host records)
- zone_auth (Authoritative zones)
- zone_forward (Forward zones)

For each query, provide:
1. The intent (search, create, update, delete)
2. The WAPI object type
3. Required parameters
4. Optional parameters
5. Confidence level (0.0-1.0)

Respond in JSON format with this structure:
{
  "intent": "search|create|update|delete",
  "object_type": "wapi_object_name",
  "parameters": {"key": "value"},
  "confidence": 0.95,
  "explanation": "Brief explanation of the operation"
}"""
        
        prompt = f"""User Query: {user_query}

Context: {json.dumps(context) if context else 'None'}

Please analyze this query and provide the appropriate WAPI operation."""
        
        return system_context + "\n\n" + prompt
    
    def parse_wapi_response(self, response: str) -> Dict[str, Any]:
        """Parse LLM response for WAPI operations."""
        try:
            # Try to extract JSON from response
            import re
            json_match = re.search(r'\{.*\}', response, re.DOTALL)
            if json_match:
                return json.loads(json_match.group())
            else:
                # Fallback parsing
                return {
                    "intent": "unknown",
                    "object_type": "unknown",
                    "parameters": {},
                    "confidence": 0.1,
                    "explanation": "Could not parse LLM response"
                }
        except Exception as e:
            logger.error(f"Failed to parse LLM response: {e}")
            return {
                "intent": "error",
                "object_type": "unknown", 
                "parameters": {},
                "confidence": 0.0,
                "explanation": f"Parse error: {e}"
            }
    
    def get_provider_status(self) -> Dict[str, Any]:
        """Get status of all providers."""
        status = {
            "primary_provider": self.primary_provider.__class__.__name__ if self.primary_provider else None,
            "fallback_enabled": self.config.fallback_enabled,
            "providers": {}
        }
        
        for name, provider in self.providers.items():
            try:
                available = provider.is_available()
                status["providers"][name] = {
                    "available": available,
                    "type": provider.__class__.__name__
                }
            except Exception as e:
                status["providers"][name] = {
                    "available": False,
                    "error": str(e),
                    "type": provider.__class__.__name__
                }
        
        return status


# Global LLM client instance
llm_client = LLMClient()