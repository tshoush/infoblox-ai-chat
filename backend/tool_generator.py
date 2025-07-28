"""
Dynamic WAPI tool generation system.
Replaces basic setup.sh generation with comprehensive schema-based tool creation.
"""

import json
import requests
from typing import Dict, List, Any, Optional
from pathlib import Path
import logging
from dataclasses import dataclass

from config import config_manager


@dataclass
class WAPIObject:
    """Represents a WAPI object with its schema information."""
    name: str
    fields: Dict[str, Any]
    supports: List[str]
    base_url: str


@dataclass
class FieldDefinition:
    """Represents a field definition from WAPI schema."""
    name: str
    type: str
    required: bool
    searchable: bool
    description: str
    enum_values: Optional[List[str]] = None


class ToolGenerator:
    """Generates Python tools for WAPI objects based on schemas."""
    
    def __init__(self):
        self.config = config_manager.get_infoblox_config()
        self.logger = logging.getLogger(__name__)
        self.base_url = f"https://{self.config.grid_ip}/wapi/{self.config.wapi_version}/"
        self.session = requests.Session()
        self.session.verify = self.config.verify_ssl
        self.session.auth = (self.config.admin_user, self.config.admin_pass)
        self.session.timeout = self.config.connection_timeout
        
    def fetch_schema(self) -> Dict[str, Any]:
        """Retrieve WAPI schema from Grid Master."""
        try:
            response = self.session.get(f"{self.base_url}?_schema")
            response.raise_for_status()
            schema = response.json()
            
            # Save schema for reference
            schema_path = Path("schema.json")
            with open(schema_path, 'w') as f:
                json.dump(schema, f, indent=2)
            
            self.logger.info(f"Successfully fetched WAPI schema with {len(schema.get('supported_objects', []))} objects")
            return schema
            
        except requests.exceptions.RequestException as e:
            self.logger.error(f"Failed to fetch WAPI schema: {e}")
            # Return mock schema for development
            return self._get_mock_schema()
    
    def _get_mock_schema(self) -> Dict[str, Any]:
        """Return mock schema for development when Infoblox is not available."""
        return {
            "supported_objects": [
                "record:a", "record:aaaa", "record:cname", "record:mx", "record:ptr",
                "network", "range", "host", "zone_auth", "zone_forward",
                "member", "grid", "networkview"
            ],
            "supported_versions": ["2.13.1"]
        }
    
    def fetch_object_schema(self, object_name: str) -> Dict[str, Any]:
        """Fetch detailed schema for a specific WAPI object."""
        try:
            response = self.session.get(f"{self.base_url}?_schema={object_name}")
            response.raise_for_status()
            schema = response.json()
            
            # Save object-specific schema
            schema_path = Path(f"schema_{object_name.replace(':', '_')}.json")
            with open(schema_path, 'w') as f:
                json.dump(schema, f, indent=2)
            
            return schema
            
        except requests.exceptions.RequestException as e:
            self.logger.warning(f"Failed to fetch schema for {object_name}: {e}")
            return self._get_mock_object_schema(object_name)
    
    def _get_mock_object_schema(self, object_name: str) -> Dict[str, Any]:
        """Return mock object schema for development."""
        base_fields = {
            "fields": {
                "_ref": {"type": "string", "required": False, "searchable": False},
                "comment": {"type": "string", "required": False, "searchable": True},
                "extattrs": {"type": "object", "required": False, "searchable": False}
            },
            "supports": ["r", "w", "u", "d", "s"]
        }
        
        # Add object-specific fields
        if object_name.startswith("record:"):
            base_fields["fields"].update({
                "name": {"type": "string", "required": True, "searchable": True},
                "view": {"type": "string", "required": False, "searchable": True},
                "zone": {"type": "string", "required": False, "searchable": True}
            })
            
            if object_name in ["record:a", "record:aaaa"]:
                base_fields["fields"]["ipv4addr" if object_name == "record:a" else "ipv6addr"] = {
                    "type": "string", "required": True, "searchable": True
                }
            elif object_name == "record:cname":
                base_fields["fields"]["canonical"] = {"type": "string", "required": True, "searchable": True}
        
        elif object_name == "network":
            base_fields["fields"].update({
                "network": {"type": "string", "required": True, "searchable": True},
                "network_view": {"type": "string", "required": False, "searchable": True}
            })
        
        return base_fields
    
    def generate_tools(self) -> str:
        """Generate comprehensive WAPI tools file."""
        schema = self.fetch_schema()
        supported_objects = schema.get("supported_objects", [])
        
        tools_content = self._generate_header()
        
        for obj_name in supported_objects:
            obj_schema = self.fetch_object_schema(obj_name)
            wapi_object = WAPIObject(
                name=obj_name,
                fields=obj_schema.get("fields", {}),
                supports=obj_schema.get("supports", []),
                base_url=self.base_url
            )
            
            tools_content += self._generate_object_functions(wapi_object)
        
        tools_content += self._generate_utility_functions()
        
        # Write tools file
        tools_path = Path("backend/tools.py")
        with open(tools_path, 'w') as f:
            f.write(tools_content)
        
        self.logger.info(f"Generated tools for {len(supported_objects)} WAPI objects")
        return str(tools_path)
    
    def _generate_header(self) -> str:
        """Generate the header section of the tools file."""
        return f'''"""
Auto-generated WAPI tools for Infoblox AI Chat Interface.
Generated from WAPI schema version {self.config.wapi_version}.

This file contains Python functions for all supported WAPI objects.
Each object has CRUD operations (Create, Read, Update, Delete) where supported.
"""

import requests
import json
import logging
from typing import Dict, List, Any, Optional, Union
from functools import wraps

from config import config_manager

# Configuration
config = config_manager.get_infoblox_config()
GRID_IP = config.grid_ip
ADMIN_USER = config.admin_user
ADMIN_PASS = config.admin_pass
WAPI_VERSION = config.wapi_version
BASE_URL = f"https://{{GRID_IP}}/wapi/{{WAPI_VERSION}}/"
VERIFY_SSL = config.verify_ssl
TIMEOUT = config.connection_timeout
MAX_RETRIES = config.max_retries

# Setup logging
logger = logging.getLogger(__name__)

# Session for connection pooling
session = requests.Session()
session.verify = VERIFY_SSL
session.auth = (ADMIN_USER, ADMIN_PASS)
session.timeout = TIMEOUT


def handle_wapi_errors(func):
    """Decorator to handle WAPI errors consistently."""
    @wraps(func)
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except requests.exceptions.ConnectionError as e:
            logger.error(f"Connection error in {{func.__name__}}: {{e}}")
            raise WAPIConnectionError(f"Failed to connect to Infoblox Grid Master: {{e}}")
        except requests.exceptions.HTTPError as e:
            logger.error(f"HTTP error in {{func.__name__}}: {{e}}")
            if e.response.status_code == 401:
                raise WAPIAuthenticationError("Authentication failed - check credentials")
            elif e.response.status_code == 400:
                raise WAPIValidationError(f"Invalid request parameters: {{e.response.text}}")
            else:
                raise WAPIError(f"HTTP {{e.response.status_code}}: {{e.response.text}}")
        except requests.exceptions.Timeout as e:
            logger.error(f"Timeout error in {{func.__name__}}: {{e}}")
            raise WAPITimeoutError(f"Request timed out after {{TIMEOUT}} seconds")
        except Exception as e:
            logger.error(f"Unexpected error in {{func.__name__}}: {{e}}")
            raise WAPIError(f"Unexpected error: {{e}}")
    return wrapper


class WAPIError(Exception):
    """Base exception for WAPI operations."""
    pass


class WAPIConnectionError(WAPIError):
    """Raised when connection to Grid Master fails."""
    pass


class WAPIAuthenticationError(WAPIError):
    """Raised when authentication fails."""
    pass


class WAPIValidationError(WAPIError):
    """Raised when request validation fails."""
    pass


class WAPITimeoutError(WAPIError):
    """Raised when request times out."""
    pass


def validate_parameters(params: Dict[str, Any], required_fields: List[str]) -> None:
    """Validate that required parameters are present."""
    missing_fields = [field for field in required_fields if field not in params or params[field] is None]
    if missing_fields:
        raise WAPIValidationError(f"Missing required fields: {{', '.join(missing_fields)}}")


'''
    
    def _generate_object_functions(self, wapi_object: WAPIObject) -> str:
        """Generate CRUD functions for a WAPI object."""
        obj_name = wapi_object.name
        safe_name = obj_name.replace(':', '_').replace('-', '_')
        
        functions = f"\n# Functions for {obj_name}\n"
        
        # Get required fields
        required_fields = [name for name, field in wapi_object.fields.items() 
                          if field.get('required', False)]
        
        # Generate GET function (if supported)
        if 'r' in wapi_object.supports:
            functions += f'''
@handle_wapi_errors
def get_{safe_name}(ref: str = None, **kwargs) -> Union[Dict[str, Any], List[Dict[str, Any]]]:
    """
    Retrieve {obj_name} object(s).
    
    Args:
        ref: Object reference for specific object retrieval
        **kwargs: Search parameters
    
    Returns:
        Single object dict if ref provided, list of objects otherwise
    """
    if ref:
        url = f"{{BASE_URL}}{{ref}}"
        response = session.get(url, params=kwargs)
    else:
        url = f"{{BASE_URL}}{obj_name}"
        response = session.get(url, params=kwargs)
    
    response.raise_for_status()
    return response.json()
'''

        # Generate SEARCH function (if supported)
        if 's' in wapi_object.supports:
            functions += f'''
@handle_wapi_errors
def search_{safe_name}(**kwargs) -> List[Dict[str, Any]]:
    """
    Search for {obj_name} objects.
    
    Args:
        **kwargs: Search parameters
    
    Returns:
        List of matching objects
    """
    url = f"{{BASE_URL}}{obj_name}"
    response = session.get(url, params=kwargs)
    response.raise_for_status()
    return response.json()
'''

        # Generate CREATE function (if supported)
        if 'w' in wapi_object.supports:
            functions += f'''
@handle_wapi_errors
def create_{safe_name}(data: Dict[str, Any]) -> str:
    """
    Create a new {obj_name} object.
    
    Args:
        data: Object data dictionary
    
    Returns:
        Reference of created object
    """
    required_fields = {required_fields}
    validate_parameters(data, required_fields)
    
    url = f"{{BASE_URL}}{obj_name}"
    response = session.post(url, json=data)
    response.raise_for_status()
    return response.json()
'''

        # Generate UPDATE function (if supported)
        if 'u' in wapi_object.supports:
            functions += f'''
@handle_wapi_errors
def update_{safe_name}(ref: str, data: Dict[str, Any]) -> str:
    """
    Update an existing {obj_name} object.
    
    Args:
        ref: Object reference
        data: Updated object data
    
    Returns:
        Reference of updated object
    """
    if not ref:
        raise WAPIValidationError("Object reference is required for update")
    
    url = f"{{BASE_URL}}{{ref}}"
    response = session.put(url, json=data)
    response.raise_for_status()
    return response.json()
'''

        # Generate DELETE function (if supported)
        if 'd' in wapi_object.supports:
            functions += f'''
@handle_wapi_errors
def delete_{safe_name}(ref: str) -> str:
    """
    Delete a {obj_name} object.
    
    Args:
        ref: Object reference
    
    Returns:
        Reference of deleted object
    """
    if not ref:
        raise WAPIValidationError("Object reference is required for delete")
    
    url = f"{{BASE_URL}}{{ref}}"
    response = session.delete(url)
    response.raise_for_status()
    return response.json()
'''

        return functions
    
    def _generate_utility_functions(self) -> str:
        """Generate utility functions for WAPI operations."""
        return '''

# Utility Functions

@handle_wapi_errors
def get_schema(object_name: str = None) -> Dict[str, Any]:
    """
    Get WAPI schema information.
    
    Args:
        object_name: Specific object name for detailed schema
    
    Returns:
        Schema information
    """
    if object_name:
        url = f"{BASE_URL}?_schema={object_name}"
    else:
        url = f"{BASE_URL}?_schema"
    
    response = session.get(url)
    response.raise_for_status()
    return response.json()


@handle_wapi_errors
def test_connection() -> bool:
    """
    Test connection to Infoblox Grid Master.
    
    Returns:
        True if connection successful, raises exception otherwise
    """
    url = f"{BASE_URL}?_schema"
    response = session.get(url)
    response.raise_for_status()
    return True


def get_supported_objects() -> List[str]:
    """
    Get list of supported WAPI objects.
    
    Returns:
        List of supported object names
    """
    try:
        schema = get_schema()
        return schema.get('supported_objects', [])
    except Exception as e:
        logger.error(f"Failed to get supported objects: {e}")
        return []


def validate_ip_address(ip: str) -> bool:
    """
    Validate IP address format.
    
    Args:
        ip: IP address string
    
    Returns:
        True if valid IP address
    """
    import ipaddress
    try:
        ipaddress.ip_address(ip)
        return True
    except ValueError:
        return False


def validate_network(network: str) -> bool:
    """
    Validate network CIDR format.
    
    Args:
        network: Network in CIDR notation
    
    Returns:
        True if valid network
    """
    import ipaddress
    try:
        ipaddress.ip_network(network, strict=False)
        return True
    except ValueError:
        return False
'''


def generate_wapi_tools() -> str:
    """Main function to generate WAPI tools."""
    generator = ToolGenerator()
    return generator.generate_tools()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    tools_path = generate_wapi_tools()
    print(f"Generated WAPI tools at: {tools_path}")