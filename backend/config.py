import os
from dataclasses import dataclass
from typing import Optional

from dotenv import load_dotenv

# Load environment variables from a .env file
load_dotenv()

@dataclass
class InfobloxConfig:
    """Configuration for Infoblox WAPI connection."""
    grid_ip: str
    admin_user: str
    admin_pass: str
    network_view: str = "default"
    wapi_version: str = "2.12.3"
    verify_ssl: bool = False
    connection_timeout: int = 30
    max_retries: int = 3

@dataclass
class LLMConfig:
    """Configuration for the Language Model provider."""
    provider: str
    api_key: Optional[str] = None
    base_url: Optional[str] = None
    model: Optional[str] = None
    temperature: float = 0.7
    max_tokens: int = 4000
    timeout: int = 30
    fallback_enabled: bool = True

@dataclass
class PerformanceConfig:
    """Configuration for system performance and scaling."""
    max_concurrent_users: int = 50
    response_timeout: int = 30
    batch_size: int = 10
    enable_metrics: bool = True

@dataclass
class CacheConfig:
    """Configuration for caching mechanisms."""
    redis_url: Optional[str] = None
    llm_cache_ttl: int = 3600
    schema_cache_ttl: int = 86400
    enable_cache: bool = True

@dataclass
class SystemConfig:
    """Root configuration object for the entire system."""
    infoblox: InfobloxConfig
    llm: LLMConfig
    performance: PerformanceConfig
    cache: CacheConfig

def get_bool_env(var_name: str, default: bool = False) -> bool:
    """Helper to get boolean value from an environment variable."""
    return os.getenv(var_name, str(default)).lower() in ('true', '1', 't')

def load_config() -> SystemConfig:
    """
    Loads configuration from environment variables and returns a SystemConfig object.
    
    Raises:
        ValueError: If required environment variables are not set.
    """
    infoblox_config = InfobloxConfig(
        grid_ip=os.getenv("INFOBLOX_GRID_IP"),
        admin_user=os.getenv("INFOBLOX_ADMIN_USER"),
        admin_pass=os.getenv("INFOBLOX_ADMIN_PASS"),
        network_view=os.getenv("INFOBLOX_NETWORK_VIEW", "default"),
        wapi_version=os.getenv("INFOBLOX_WAPI_VERSION", "2.12.3"),
        verify_ssl=get_bool_env("INFOBLOX_VERIFY_SSL", False),
        connection_timeout=int(os.getenv("INFOBLOX_CONNECTION_TIMEOUT", 30)),
        max_retries=int(os.getenv("INFOBLOX_MAX_RETRIES", 3)),
    )

    llm_config = LLMConfig(
        provider=os.getenv("LLM_PROVIDER"),
        api_key=os.getenv("LLM_API_KEY"),
        base_url=os.getenv("LLM_BASE_URL"),
        model=os.getenv("LLM_MODEL"),
        temperature=float(os.getenv("LLM_TEMPERATURE", 0.7)),
        max_tokens=int(os.getenv("LLM_MAX_TOKENS", 4000)),
        timeout=int(os.getenv("LLM_TIMEOUT", 30)),
        fallback_enabled=get_bool_env("LLM_FALLBACK_ENABLED", True),
    )

    performance_config = PerformanceConfig(
        max_concurrent_users=int(os.getenv("MAX_CONCURRENT_USERS", 50)),
        response_timeout=int(os.getenv("RESPONSE_TIMEOUT", 30)),
        batch_size=int(os.getenv("BATCH_SIZE", 10)),
        enable_metrics=get_bool_env("ENABLE_METRICS", True),
    )

    cache_config = CacheConfig(
        redis_url=os.getenv("REDIS_URL"),
        llm_cache_ttl=int(os.getenv("LLM_CACHE_TTL", 3600)),
        schema_cache_ttl=int(os.getenv("SCHEMA_CACHE_TTL", 86400)),
        enable_cache=get_bool_env("ENABLE_CACHE", True),
    )
    
    if not all([infoblox_config.grid_ip, infoblox_config.admin_user, infoblox_config.admin_pass]):
        raise ValueError("INFOBLOX_GRID_IP, INFOBLOX_ADMIN_USER, and INFOBLOX_ADMIN_PASS must be set in your .env file.")

    if not llm_config.provider:
        raise ValueError("LLM_PROVIDER must be set in your .env file.")

    from backend.providers import get as get_provider, PROVIDER_REGISTRY, PROVIDER_ALIASES
    if get_provider(llm_config.provider) is None:
        supported = list(PROVIDER_REGISTRY) + list(PROVIDER_ALIASES)
        raise ValueError(
            f"LLM_PROVIDER='{llm_config.provider}' is not supported. "
            f"Choose one of: {', '.join(supported)}."
        )

    if not 0.0 <= llm_config.temperature <= 2.0:
        raise ValueError(f"LLM_TEMPERATURE must be between 0.0 and 2.0 (got {llm_config.temperature}).")
    if llm_config.max_tokens <= 0:
        raise ValueError(f"LLM_MAX_TOKENS must be a positive integer (got {llm_config.max_tokens}).")
    if llm_config.timeout <= 0:
        raise ValueError(f"LLM_TIMEOUT must be a positive integer (got {llm_config.timeout}).")

    return SystemConfig(
        infoblox=infoblox_config,
        llm=llm_config,
        performance=performance_config,
        cache=cache_config,
    )