"""
Configuration management system for Infoblox AI Chat Interface.
Handles system configuration with environment variable overrides and validation.
"""

import os
import json
from dataclasses import dataclass, asdict
from typing import Optional, Dict, Any
from pathlib import Path


@dataclass
class InfobloxConfig:
    """Configuration for Infoblox Grid Master connection."""
    grid_ip: str
    admin_user: str
    admin_pass: str
    network_view: str = "default"
    wapi_version: str = "v2.13.1"
    verify_ssl: bool = False
    connection_timeout: int = 30
    max_retries: int = 3


@dataclass
class LLMConfig:
    """Configuration for Language Model providers."""
    provider: str
    api_key: str
    base_url: Optional[str] = None
    model: Optional[str] = None
    temperature: float = 0.7
    max_tokens: int = 4000
    timeout: int = 30
    fallback_enabled: bool = True


@dataclass
class PerformanceConfig:
    """Performance and scaling configuration."""
    max_concurrent_users: int = 50
    response_timeout: int = 30
    batch_size: int = 10
    enable_metrics: bool = True


@dataclass
class CacheConfig:
    """Caching configuration."""
    redis_url: Optional[str] = None
    llm_cache_ttl: int = 3600
    schema_cache_ttl: int = 86400
    enable_cache: bool = True


@dataclass
class SystemConfig:
    """Complete system configuration."""
    infoblox: InfobloxConfig
    llm: LLMConfig
    performance: PerformanceConfig
    cache: CacheConfig


class ConfigManager:
    """Manages system configuration with validation and environment overrides."""
    
    def __init__(self, config_path: str = "backend/config.json"):
        self.config_path = Path(config_path)
        self._config: Optional[SystemConfig] = None
    
    def load_config(self) -> SystemConfig:
        """Load configuration from file and environment variables."""
        if self._config is None:
            self._config = self._load_from_sources()
        return self._config
    
    def _load_from_sources(self) -> SystemConfig:
        """Load configuration from JSON file and environment variables."""
        # Load from JSON file if it exists
        config_data = {}
        if self.config_path.exists():
            with open(self.config_path, 'r') as f:
                config_data = json.load(f)
        
        # Apply environment variable overrides
        config_data = self._apply_env_overrides(config_data)
        
        # Create configuration objects
        infoblox_config = InfobloxConfig(
            grid_ip=config_data.get('infoblox', {}).get('grid_ip', 'localhost'),
            admin_user=config_data.get('infoblox', {}).get('admin_user', 'admin'),
            admin_pass=config_data.get('infoblox', {}).get('admin_pass', 'infoblox'),
            network_view=config_data.get('infoblox', {}).get('network_view', 'default'),
            wapi_version=config_data.get('infoblox', {}).get('wapi_version', 'v2.13.1'),
            verify_ssl=config_data.get('infoblox', {}).get('verify_ssl', False),
            connection_timeout=config_data.get('infoblox', {}).get('connection_timeout', 30),
            max_retries=config_data.get('infoblox', {}).get('max_retries', 3)
        )
        
        llm_config = LLMConfig(
            provider=config_data.get('llm', {}).get('provider', 'openai'),
            api_key=config_data.get('llm', {}).get('api_key', ''),
            base_url=config_data.get('llm', {}).get('base_url'),
            model=config_data.get('llm', {}).get('model'),
            temperature=config_data.get('llm', {}).get('temperature', 0.7),
            max_tokens=config_data.get('llm', {}).get('max_tokens', 4000),
            timeout=config_data.get('llm', {}).get('timeout', 30),
            fallback_enabled=config_data.get('llm', {}).get('fallback_enabled', True)
        )
        
        performance_config = PerformanceConfig(
            max_concurrent_users=config_data.get('performance', {}).get('max_concurrent_users', 50),
            response_timeout=config_data.get('performance', {}).get('response_timeout', 30),
            batch_size=config_data.get('performance', {}).get('batch_size', 10),
            enable_metrics=config_data.get('performance', {}).get('enable_metrics', True)
        )
        
        cache_config = CacheConfig(
            redis_url=config_data.get('cache', {}).get('redis_url'),
            llm_cache_ttl=config_data.get('cache', {}).get('llm_cache_ttl', 3600),
            schema_cache_ttl=config_data.get('cache', {}).get('schema_cache_ttl', 86400),
            enable_cache=config_data.get('cache', {}).get('enable_cache', True)
        )
        
        return SystemConfig(
            infoblox=infoblox_config,
            llm=llm_config,
            performance=performance_config,
            cache=cache_config
        )
    
    def _apply_env_overrides(self, config_data: Dict[str, Any]) -> Dict[str, Any]:
        """Apply environment variable overrides to configuration."""
        env_mappings = {
            'INFOBLOX_GRID_IP': ['infoblox', 'grid_ip'],
            'INFOBLOX_ADMIN_USER': ['infoblox', 'admin_user'],
            'INFOBLOX_ADMIN_PASS': ['infoblox', 'admin_pass'],
            'INFOBLOX_NETWORK_VIEW': ['infoblox', 'network_view'],
            'LLM_PROVIDER': ['llm', 'provider'],
            'LLM_API_KEY': ['llm', 'api_key'],
            'LLM_BASE_URL': ['llm', 'base_url'],
            'LLM_MODEL': ['llm', 'model'],
            'REDIS_URL': ['cache', 'redis_url'],
        }
        
        for env_var, config_path in env_mappings.items():
            value = os.getenv(env_var)
            if value is not None:
                # Ensure nested dict structure exists
                current = config_data
                for key in config_path[:-1]:
                    if key not in current:
                        current[key] = {}
                    current = current[key]
                current[config_path[-1]] = value
        
        return config_data
    
    def get_infoblox_config(self) -> InfobloxConfig:
        """Get Infoblox configuration."""
        return self.load_config().infoblox
    
    def get_llm_config(self) -> LLMConfig:
        """Get LLM configuration."""
        return self.load_config().llm
    
    def get_performance_config(self) -> PerformanceConfig:
        """Get performance configuration."""
        return self.load_config().performance
    
    def get_cache_config(self) -> CacheConfig:
        """Get cache configuration."""
        return self.load_config().cache
    
    def validate_config(self) -> Dict[str, str]:
        """Validate configuration completeness and return any errors."""
        errors = {}
        config = self.load_config()
        
        # Validate Infoblox configuration
        if not config.infoblox.grid_ip:
            errors['infoblox.grid_ip'] = 'Grid Master IP address is required'
        if not config.infoblox.admin_user:
            errors['infoblox.admin_user'] = 'Admin username is required'
        if not config.infoblox.admin_pass:
            errors['infoblox.admin_pass'] = 'Admin password is required'
        
        # Validate LLM configuration
        if not config.llm.provider:
            errors['llm.provider'] = 'LLM provider is required'
        if not config.llm.api_key and config.llm.provider != 'local':
            errors['llm.api_key'] = 'LLM API key is required for cloud providers'
        
        return errors
    
    def save_config(self, config: SystemConfig) -> None:
        """Save configuration to file."""
        self.config_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.config_path, 'w') as f:
            json.dump(asdict(config), f, indent=2)
        self._config = config


# Global configuration manager instance
config_manager = ConfigManager()