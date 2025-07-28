"""
Auto-generated WAPI tools for Infoblox AI Chat Interface.
Generated from WAPI schema version v2.13.1.

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
BASE_URL = f"https://{GRID_IP}/wapi/{WAPI_VERSION}/"
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
            logger.error(f"Connection error in {func.__name__}: {e}")
            raise WAPIConnectionError(f"Failed to connect to Infoblox Grid Master: {e}")
        except requests.exceptions.HTTPError as e:
            logger.error(f"HTTP error in {func.__name__}: {e}")
            if e.response.status_code == 401:
                raise WAPIAuthenticationError("Authentication failed - check credentials")
            elif e.response.status_code == 400:
                raise WAPIValidationError(f"Invalid request parameters: {e.response.text}")
            else:
                raise WAPIError(f"HTTP {e.response.status_code}: {e.response.text}")
        except requests.exceptions.Timeout as e:
            logger.error(f"Timeout error in {func.__name__}: {e}")
            raise WAPITimeoutError(f"Request timed out after {TIMEOUT} seconds")
        except Exception as e:
            logger.error(f"Unexpected error in {func.__name__}: {e}")
            raise WAPIError(f"Unexpected error: {e}")
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
        raise WAPIValidationError(f"Missing required fields: {', '.join(missing_fields)}")



# Functions for record:a

@handle_wapi_errors
def get_record_a(ref: str = None, **kwargs) -> Union[Dict[str, Any], List[Dict[str, Any]]]:
    """
    Retrieve record:a object(s).
    
    Args:
        ref: Object reference for specific object retrieval
        **kwargs: Search parameters
    
    Returns:
        Single object dict if ref provided, list of objects otherwise
    """
    if ref:
        url = f"{BASE_URL}{ref}"
        response = session.get(url, params=kwargs)
    else:
        url = f"{BASE_URL}record:a"
        response = session.get(url, params=kwargs)
    
    response.raise_for_status()
    return response.json()

@handle_wapi_errors
def search_record_a(**kwargs) -> List[Dict[str, Any]]:
    """
    Search for record:a objects.
    
    Args:
        **kwargs: Search parameters
    
    Returns:
        List of matching objects
    """
    url = f"{BASE_URL}record:a"
    response = session.get(url, params=kwargs)
    response.raise_for_status()
    return response.json()

@handle_wapi_errors
def create_record_a(data: Dict[str, Any]) -> str:
    """
    Create a new record:a object.
    
    Args:
        data: Object data dictionary
    
    Returns:
        Reference of created object
    """
    required_fields = ['name', 'ipv4addr']
    validate_parameters(data, required_fields)
    
    url = f"{BASE_URL}record:a"
    response = session.post(url, json=data)
    response.raise_for_status()
    return response.json()

@handle_wapi_errors
def update_record_a(ref: str, data: Dict[str, Any]) -> str:
    """
    Update an existing record:a object.
    
    Args:
        ref: Object reference
        data: Updated object data
    
    Returns:
        Reference of updated object
    """
    if not ref:
        raise WAPIValidationError("Object reference is required for update")
    
    url = f"{BASE_URL}{ref}"
    response = session.put(url, json=data)
    response.raise_for_status()
    return response.json()

@handle_wapi_errors
def delete_record_a(ref: str) -> str:
    """
    Delete a record:a object.
    
    Args:
        ref: Object reference
    
    Returns:
        Reference of deleted object
    """
    if not ref:
        raise WAPIValidationError("Object reference is required for delete")
    
    url = f"{BASE_URL}{ref}"
    response = session.delete(url)
    response.raise_for_status()
    return response.json()

# Functions for record:aaaa

@handle_wapi_errors
def get_record_aaaa(ref: str = None, **kwargs) -> Union[Dict[str, Any], List[Dict[str, Any]]]:
    """
    Retrieve record:aaaa object(s).
    
    Args:
        ref: Object reference for specific object retrieval
        **kwargs: Search parameters
    
    Returns:
        Single object dict if ref provided, list of objects otherwise
    """
    if ref:
        url = f"{BASE_URL}{ref}"
        response = session.get(url, params=kwargs)
    else:
        url = f"{BASE_URL}record:aaaa"
        response = session.get(url, params=kwargs)
    
    response.raise_for_status()
    return response.json()

@handle_wapi_errors
def search_record_aaaa(**kwargs) -> List[Dict[str, Any]]:
    """
    Search for record:aaaa objects.
    
    Args:
        **kwargs: Search parameters
    
    Returns:
        List of matching objects
    """
    url = f"{BASE_URL}record:aaaa"
    response = session.get(url, params=kwargs)
    response.raise_for_status()
    return response.json()

@handle_wapi_errors
def create_record_aaaa(data: Dict[str, Any]) -> str:
    """
    Create a new record:aaaa object.
    
    Args:
        data: Object data dictionary
    
    Returns:
        Reference of created object
    """
    required_fields = ['name', 'ipv6addr']
    validate_parameters(data, required_fields)
    
    url = f"{BASE_URL}record:aaaa"
    response = session.post(url, json=data)
    response.raise_for_status()
    return response.json()

@handle_wapi_errors
def update_record_aaaa(ref: str, data: Dict[str, Any]) -> str:
    """
    Update an existing record:aaaa object.
    
    Args:
        ref: Object reference
        data: Updated object data
    
    Returns:
        Reference of updated object
    """
    if not ref:
        raise WAPIValidationError("Object reference is required for update")
    
    url = f"{BASE_URL}{ref}"
    response = session.put(url, json=data)
    response.raise_for_status()
    return response.json()

@handle_wapi_errors
def delete_record_aaaa(ref: str) -> str:
    """
    Delete a record:aaaa object.
    
    Args:
        ref: Object reference
    
    Returns:
        Reference of deleted object
    """
    if not ref:
        raise WAPIValidationError("Object reference is required for delete")
    
    url = f"{BASE_URL}{ref}"
    response = session.delete(url)
    response.raise_for_status()
    return response.json()

# Functions for record:cname

@handle_wapi_errors
def get_record_cname(ref: str = None, **kwargs) -> Union[Dict[str, Any], List[Dict[str, Any]]]:
    """
    Retrieve record:cname object(s).
    
    Args:
        ref: Object reference for specific object retrieval
        **kwargs: Search parameters
    
    Returns:
        Single object dict if ref provided, list of objects otherwise
    """
    if ref:
        url = f"{BASE_URL}{ref}"
        response = session.get(url, params=kwargs)
    else:
        url = f"{BASE_URL}record:cname"
        response = session.get(url, params=kwargs)
    
    response.raise_for_status()
    return response.json()

@handle_wapi_errors
def search_record_cname(**kwargs) -> List[Dict[str, Any]]:
    """
    Search for record:cname objects.
    
    Args:
        **kwargs: Search parameters
    
    Returns:
        List of matching objects
    """
    url = f"{BASE_URL}record:cname"
    response = session.get(url, params=kwargs)
    response.raise_for_status()
    return response.json()

@handle_wapi_errors
def create_record_cname(data: Dict[str, Any]) -> str:
    """
    Create a new record:cname object.
    
    Args:
        data: Object data dictionary
    
    Returns:
        Reference of created object
    """
    required_fields = ['name', 'canonical']
    validate_parameters(data, required_fields)
    
    url = f"{BASE_URL}record:cname"
    response = session.post(url, json=data)
    response.raise_for_status()
    return response.json()

@handle_wapi_errors
def update_record_cname(ref: str, data: Dict[str, Any]) -> str:
    """
    Update an existing record:cname object.
    
    Args:
        ref: Object reference
        data: Updated object data
    
    Returns:
        Reference of updated object
    """
    if not ref:
        raise WAPIValidationError("Object reference is required for update")
    
    url = f"{BASE_URL}{ref}"
    response = session.put(url, json=data)
    response.raise_for_status()
    return response.json()

@handle_wapi_errors
def delete_record_cname(ref: str) -> str:
    """
    Delete a record:cname object.
    
    Args:
        ref: Object reference
    
    Returns:
        Reference of deleted object
    """
    if not ref:
        raise WAPIValidationError("Object reference is required for delete")
    
    url = f"{BASE_URL}{ref}"
    response = session.delete(url)
    response.raise_for_status()
    return response.json()

# Functions for record:mx

@handle_wapi_errors
def get_record_mx(ref: str = None, **kwargs) -> Union[Dict[str, Any], List[Dict[str, Any]]]:
    """
    Retrieve record:mx object(s).
    
    Args:
        ref: Object reference for specific object retrieval
        **kwargs: Search parameters
    
    Returns:
        Single object dict if ref provided, list of objects otherwise
    """
    if ref:
        url = f"{BASE_URL}{ref}"
        response = session.get(url, params=kwargs)
    else:
        url = f"{BASE_URL}record:mx"
        response = session.get(url, params=kwargs)
    
    response.raise_for_status()
    return response.json()

@handle_wapi_errors
def search_record_mx(**kwargs) -> List[Dict[str, Any]]:
    """
    Search for record:mx objects.
    
    Args:
        **kwargs: Search parameters
    
    Returns:
        List of matching objects
    """
    url = f"{BASE_URL}record:mx"
    response = session.get(url, params=kwargs)
    response.raise_for_status()
    return response.json()

@handle_wapi_errors
def create_record_mx(data: Dict[str, Any]) -> str:
    """
    Create a new record:mx object.
    
    Args:
        data: Object data dictionary
    
    Returns:
        Reference of created object
    """
    required_fields = ['name']
    validate_parameters(data, required_fields)
    
    url = f"{BASE_URL}record:mx"
    response = session.post(url, json=data)
    response.raise_for_status()
    return response.json()

@handle_wapi_errors
def update_record_mx(ref: str, data: Dict[str, Any]) -> str:
    """
    Update an existing record:mx object.
    
    Args:
        ref: Object reference
        data: Updated object data
    
    Returns:
        Reference of updated object
    """
    if not ref:
        raise WAPIValidationError("Object reference is required for update")
    
    url = f"{BASE_URL}{ref}"
    response = session.put(url, json=data)
    response.raise_for_status()
    return response.json()

@handle_wapi_errors
def delete_record_mx(ref: str) -> str:
    """
    Delete a record:mx object.
    
    Args:
        ref: Object reference
    
    Returns:
        Reference of deleted object
    """
    if not ref:
        raise WAPIValidationError("Object reference is required for delete")
    
    url = f"{BASE_URL}{ref}"
    response = session.delete(url)
    response.raise_for_status()
    return response.json()

# Functions for record:ptr

@handle_wapi_errors
def get_record_ptr(ref: str = None, **kwargs) -> Union[Dict[str, Any], List[Dict[str, Any]]]:
    """
    Retrieve record:ptr object(s).
    
    Args:
        ref: Object reference for specific object retrieval
        **kwargs: Search parameters
    
    Returns:
        Single object dict if ref provided, list of objects otherwise
    """
    if ref:
        url = f"{BASE_URL}{ref}"
        response = session.get(url, params=kwargs)
    else:
        url = f"{BASE_URL}record:ptr"
        response = session.get(url, params=kwargs)
    
    response.raise_for_status()
    return response.json()

@handle_wapi_errors
def search_record_ptr(**kwargs) -> List[Dict[str, Any]]:
    """
    Search for record:ptr objects.
    
    Args:
        **kwargs: Search parameters
    
    Returns:
        List of matching objects
    """
    url = f"{BASE_URL}record:ptr"
    response = session.get(url, params=kwargs)
    response.raise_for_status()
    return response.json()

@handle_wapi_errors
def create_record_ptr(data: Dict[str, Any]) -> str:
    """
    Create a new record:ptr object.
    
    Args:
        data: Object data dictionary
    
    Returns:
        Reference of created object
    """
    required_fields = ['name']
    validate_parameters(data, required_fields)
    
    url = f"{BASE_URL}record:ptr"
    response = session.post(url, json=data)
    response.raise_for_status()
    return response.json()

@handle_wapi_errors
def update_record_ptr(ref: str, data: Dict[str, Any]) -> str:
    """
    Update an existing record:ptr object.
    
    Args:
        ref: Object reference
        data: Updated object data
    
    Returns:
        Reference of updated object
    """
    if not ref:
        raise WAPIValidationError("Object reference is required for update")
    
    url = f"{BASE_URL}{ref}"
    response = session.put(url, json=data)
    response.raise_for_status()
    return response.json()

@handle_wapi_errors
def delete_record_ptr(ref: str) -> str:
    """
    Delete a record:ptr object.
    
    Args:
        ref: Object reference
    
    Returns:
        Reference of deleted object
    """
    if not ref:
        raise WAPIValidationError("Object reference is required for delete")
    
    url = f"{BASE_URL}{ref}"
    response = session.delete(url)
    response.raise_for_status()
    return response.json()

# Functions for network

@handle_wapi_errors
def get_network(ref: str = None, **kwargs) -> Union[Dict[str, Any], List[Dict[str, Any]]]:
    """
    Retrieve network object(s).
    
    Args:
        ref: Object reference for specific object retrieval
        **kwargs: Search parameters
    
    Returns:
        Single object dict if ref provided, list of objects otherwise
    """
    if ref:
        url = f"{BASE_URL}{ref}"
        response = session.get(url, params=kwargs)
    else:
        url = f"{BASE_URL}network"
        response = session.get(url, params=kwargs)
    
    response.raise_for_status()
    return response.json()

@handle_wapi_errors
def search_network(**kwargs) -> List[Dict[str, Any]]:
    """
    Search for network objects.
    
    Args:
        **kwargs: Search parameters
    
    Returns:
        List of matching objects
    """
    url = f"{BASE_URL}network"
    response = session.get(url, params=kwargs)
    response.raise_for_status()
    return response.json()

@handle_wapi_errors
def create_network(data: Dict[str, Any]) -> str:
    """
    Create a new network object.
    
    Args:
        data: Object data dictionary
    
    Returns:
        Reference of created object
    """
    required_fields = ['network']
    validate_parameters(data, required_fields)
    
    url = f"{BASE_URL}network"
    response = session.post(url, json=data)
    response.raise_for_status()
    return response.json()

@handle_wapi_errors
def update_network(ref: str, data: Dict[str, Any]) -> str:
    """
    Update an existing network object.
    
    Args:
        ref: Object reference
        data: Updated object data
    
    Returns:
        Reference of updated object
    """
    if not ref:
        raise WAPIValidationError("Object reference is required for update")
    
    url = f"{BASE_URL}{ref}"
    response = session.put(url, json=data)
    response.raise_for_status()
    return response.json()

@handle_wapi_errors
def delete_network(ref: str) -> str:
    """
    Delete a network object.
    
    Args:
        ref: Object reference
    
    Returns:
        Reference of deleted object
    """
    if not ref:
        raise WAPIValidationError("Object reference is required for delete")
    
    url = f"{BASE_URL}{ref}"
    response = session.delete(url)
    response.raise_for_status()
    return response.json()

# Functions for range

@handle_wapi_errors
def get_range(ref: str = None, **kwargs) -> Union[Dict[str, Any], List[Dict[str, Any]]]:
    """
    Retrieve range object(s).
    
    Args:
        ref: Object reference for specific object retrieval
        **kwargs: Search parameters
    
    Returns:
        Single object dict if ref provided, list of objects otherwise
    """
    if ref:
        url = f"{BASE_URL}{ref}"
        response = session.get(url, params=kwargs)
    else:
        url = f"{BASE_URL}range"
        response = session.get(url, params=kwargs)
    
    response.raise_for_status()
    return response.json()

@handle_wapi_errors
def search_range(**kwargs) -> List[Dict[str, Any]]:
    """
    Search for range objects.
    
    Args:
        **kwargs: Search parameters
    
    Returns:
        List of matching objects
    """
    url = f"{BASE_URL}range"
    response = session.get(url, params=kwargs)
    response.raise_for_status()
    return response.json()

@handle_wapi_errors
def create_range(data: Dict[str, Any]) -> str:
    """
    Create a new range object.
    
    Args:
        data: Object data dictionary
    
    Returns:
        Reference of created object
    """
    required_fields = []
    validate_parameters(data, required_fields)
    
    url = f"{BASE_URL}range"
    response = session.post(url, json=data)
    response.raise_for_status()
    return response.json()

@handle_wapi_errors
def update_range(ref: str, data: Dict[str, Any]) -> str:
    """
    Update an existing range object.
    
    Args:
        ref: Object reference
        data: Updated object data
    
    Returns:
        Reference of updated object
    """
    if not ref:
        raise WAPIValidationError("Object reference is required for update")
    
    url = f"{BASE_URL}{ref}"
    response = session.put(url, json=data)
    response.raise_for_status()
    return response.json()

@handle_wapi_errors
def delete_range(ref: str) -> str:
    """
    Delete a range object.
    
    Args:
        ref: Object reference
    
    Returns:
        Reference of deleted object
    """
    if not ref:
        raise WAPIValidationError("Object reference is required for delete")
    
    url = f"{BASE_URL}{ref}"
    response = session.delete(url)
    response.raise_for_status()
    return response.json()

# Functions for host

@handle_wapi_errors
def get_host(ref: str = None, **kwargs) -> Union[Dict[str, Any], List[Dict[str, Any]]]:
    """
    Retrieve host object(s).
    
    Args:
        ref: Object reference for specific object retrieval
        **kwargs: Search parameters
    
    Returns:
        Single object dict if ref provided, list of objects otherwise
    """
    if ref:
        url = f"{BASE_URL}{ref}"
        response = session.get(url, params=kwargs)
    else:
        url = f"{BASE_URL}host"
        response = session.get(url, params=kwargs)
    
    response.raise_for_status()
    return response.json()

@handle_wapi_errors
def search_host(**kwargs) -> List[Dict[str, Any]]:
    """
    Search for host objects.
    
    Args:
        **kwargs: Search parameters
    
    Returns:
        List of matching objects
    """
    url = f"{BASE_URL}host"
    response = session.get(url, params=kwargs)
    response.raise_for_status()
    return response.json()

@handle_wapi_errors
def create_host(data: Dict[str, Any]) -> str:
    """
    Create a new host object.
    
    Args:
        data: Object data dictionary
    
    Returns:
        Reference of created object
    """
    required_fields = []
    validate_parameters(data, required_fields)
    
    url = f"{BASE_URL}host"
    response = session.post(url, json=data)
    response.raise_for_status()
    return response.json()

@handle_wapi_errors
def update_host(ref: str, data: Dict[str, Any]) -> str:
    """
    Update an existing host object.
    
    Args:
        ref: Object reference
        data: Updated object data
    
    Returns:
        Reference of updated object
    """
    if not ref:
        raise WAPIValidationError("Object reference is required for update")
    
    url = f"{BASE_URL}{ref}"
    response = session.put(url, json=data)
    response.raise_for_status()
    return response.json()

@handle_wapi_errors
def delete_host(ref: str) -> str:
    """
    Delete a host object.
    
    Args:
        ref: Object reference
    
    Returns:
        Reference of deleted object
    """
    if not ref:
        raise WAPIValidationError("Object reference is required for delete")
    
    url = f"{BASE_URL}{ref}"
    response = session.delete(url)
    response.raise_for_status()
    return response.json()

# Functions for zone_auth

@handle_wapi_errors
def get_zone_auth(ref: str = None, **kwargs) -> Union[Dict[str, Any], List[Dict[str, Any]]]:
    """
    Retrieve zone_auth object(s).
    
    Args:
        ref: Object reference for specific object retrieval
        **kwargs: Search parameters
    
    Returns:
        Single object dict if ref provided, list of objects otherwise
    """
    if ref:
        url = f"{BASE_URL}{ref}"
        response = session.get(url, params=kwargs)
    else:
        url = f"{BASE_URL}zone_auth"
        response = session.get(url, params=kwargs)
    
    response.raise_for_status()
    return response.json()

@handle_wapi_errors
def search_zone_auth(**kwargs) -> List[Dict[str, Any]]:
    """
    Search for zone_auth objects.
    
    Args:
        **kwargs: Search parameters
    
    Returns:
        List of matching objects
    """
    url = f"{BASE_URL}zone_auth"
    response = session.get(url, params=kwargs)
    response.raise_for_status()
    return response.json()

@handle_wapi_errors
def create_zone_auth(data: Dict[str, Any]) -> str:
    """
    Create a new zone_auth object.
    
    Args:
        data: Object data dictionary
    
    Returns:
        Reference of created object
    """
    required_fields = []
    validate_parameters(data, required_fields)
    
    url = f"{BASE_URL}zone_auth"
    response = session.post(url, json=data)
    response.raise_for_status()
    return response.json()

@handle_wapi_errors
def update_zone_auth(ref: str, data: Dict[str, Any]) -> str:
    """
    Update an existing zone_auth object.
    
    Args:
        ref: Object reference
        data: Updated object data
    
    Returns:
        Reference of updated object
    """
    if not ref:
        raise WAPIValidationError("Object reference is required for update")
    
    url = f"{BASE_URL}{ref}"
    response = session.put(url, json=data)
    response.raise_for_status()
    return response.json()

@handle_wapi_errors
def delete_zone_auth(ref: str) -> str:
    """
    Delete a zone_auth object.
    
    Args:
        ref: Object reference
    
    Returns:
        Reference of deleted object
    """
    if not ref:
        raise WAPIValidationError("Object reference is required for delete")
    
    url = f"{BASE_URL}{ref}"
    response = session.delete(url)
    response.raise_for_status()
    return response.json()

# Functions for zone_forward

@handle_wapi_errors
def get_zone_forward(ref: str = None, **kwargs) -> Union[Dict[str, Any], List[Dict[str, Any]]]:
    """
    Retrieve zone_forward object(s).
    
    Args:
        ref: Object reference for specific object retrieval
        **kwargs: Search parameters
    
    Returns:
        Single object dict if ref provided, list of objects otherwise
    """
    if ref:
        url = f"{BASE_URL}{ref}"
        response = session.get(url, params=kwargs)
    else:
        url = f"{BASE_URL}zone_forward"
        response = session.get(url, params=kwargs)
    
    response.raise_for_status()
    return response.json()

@handle_wapi_errors
def search_zone_forward(**kwargs) -> List[Dict[str, Any]]:
    """
    Search for zone_forward objects.
    
    Args:
        **kwargs: Search parameters
    
    Returns:
        List of matching objects
    """
    url = f"{BASE_URL}zone_forward"
    response = session.get(url, params=kwargs)
    response.raise_for_status()
    return response.json()

@handle_wapi_errors
def create_zone_forward(data: Dict[str, Any]) -> str:
    """
    Create a new zone_forward object.
    
    Args:
        data: Object data dictionary
    
    Returns:
        Reference of created object
    """
    required_fields = []
    validate_parameters(data, required_fields)
    
    url = f"{BASE_URL}zone_forward"
    response = session.post(url, json=data)
    response.raise_for_status()
    return response.json()

@handle_wapi_errors
def update_zone_forward(ref: str, data: Dict[str, Any]) -> str:
    """
    Update an existing zone_forward object.
    
    Args:
        ref: Object reference
        data: Updated object data
    
    Returns:
        Reference of updated object
    """
    if not ref:
        raise WAPIValidationError("Object reference is required for update")
    
    url = f"{BASE_URL}{ref}"
    response = session.put(url, json=data)
    response.raise_for_status()
    return response.json()

@handle_wapi_errors
def delete_zone_forward(ref: str) -> str:
    """
    Delete a zone_forward object.
    
    Args:
        ref: Object reference
    
    Returns:
        Reference of deleted object
    """
    if not ref:
        raise WAPIValidationError("Object reference is required for delete")
    
    url = f"{BASE_URL}{ref}"
    response = session.delete(url)
    response.raise_for_status()
    return response.json()

# Functions for member

@handle_wapi_errors
def get_member(ref: str = None, **kwargs) -> Union[Dict[str, Any], List[Dict[str, Any]]]:
    """
    Retrieve member object(s).
    
    Args:
        ref: Object reference for specific object retrieval
        **kwargs: Search parameters
    
    Returns:
        Single object dict if ref provided, list of objects otherwise
    """
    if ref:
        url = f"{BASE_URL}{ref}"
        response = session.get(url, params=kwargs)
    else:
        url = f"{BASE_URL}member"
        response = session.get(url, params=kwargs)
    
    response.raise_for_status()
    return response.json()

@handle_wapi_errors
def search_member(**kwargs) -> List[Dict[str, Any]]:
    """
    Search for member objects.
    
    Args:
        **kwargs: Search parameters
    
    Returns:
        List of matching objects
    """
    url = f"{BASE_URL}member"
    response = session.get(url, params=kwargs)
    response.raise_for_status()
    return response.json()

@handle_wapi_errors
def create_member(data: Dict[str, Any]) -> str:
    """
    Create a new member object.
    
    Args:
        data: Object data dictionary
    
    Returns:
        Reference of created object
    """
    required_fields = []
    validate_parameters(data, required_fields)
    
    url = f"{BASE_URL}member"
    response = session.post(url, json=data)
    response.raise_for_status()
    return response.json()

@handle_wapi_errors
def update_member(ref: str, data: Dict[str, Any]) -> str:
    """
    Update an existing member object.
    
    Args:
        ref: Object reference
        data: Updated object data
    
    Returns:
        Reference of updated object
    """
    if not ref:
        raise WAPIValidationError("Object reference is required for update")
    
    url = f"{BASE_URL}{ref}"
    response = session.put(url, json=data)
    response.raise_for_status()
    return response.json()

@handle_wapi_errors
def delete_member(ref: str) -> str:
    """
    Delete a member object.
    
    Args:
        ref: Object reference
    
    Returns:
        Reference of deleted object
    """
    if not ref:
        raise WAPIValidationError("Object reference is required for delete")
    
    url = f"{BASE_URL}{ref}"
    response = session.delete(url)
    response.raise_for_status()
    return response.json()

# Functions for grid

@handle_wapi_errors
def get_grid(ref: str = None, **kwargs) -> Union[Dict[str, Any], List[Dict[str, Any]]]:
    """
    Retrieve grid object(s).
    
    Args:
        ref: Object reference for specific object retrieval
        **kwargs: Search parameters
    
    Returns:
        Single object dict if ref provided, list of objects otherwise
    """
    if ref:
        url = f"{BASE_URL}{ref}"
        response = session.get(url, params=kwargs)
    else:
        url = f"{BASE_URL}grid"
        response = session.get(url, params=kwargs)
    
    response.raise_for_status()
    return response.json()

@handle_wapi_errors
def search_grid(**kwargs) -> List[Dict[str, Any]]:
    """
    Search for grid objects.
    
    Args:
        **kwargs: Search parameters
    
    Returns:
        List of matching objects
    """
    url = f"{BASE_URL}grid"
    response = session.get(url, params=kwargs)
    response.raise_for_status()
    return response.json()

@handle_wapi_errors
def create_grid(data: Dict[str, Any]) -> str:
    """
    Create a new grid object.
    
    Args:
        data: Object data dictionary
    
    Returns:
        Reference of created object
    """
    required_fields = []
    validate_parameters(data, required_fields)
    
    url = f"{BASE_URL}grid"
    response = session.post(url, json=data)
    response.raise_for_status()
    return response.json()

@handle_wapi_errors
def update_grid(ref: str, data: Dict[str, Any]) -> str:
    """
    Update an existing grid object.
    
    Args:
        ref: Object reference
        data: Updated object data
    
    Returns:
        Reference of updated object
    """
    if not ref:
        raise WAPIValidationError("Object reference is required for update")
    
    url = f"{BASE_URL}{ref}"
    response = session.put(url, json=data)
    response.raise_for_status()
    return response.json()

@handle_wapi_errors
def delete_grid(ref: str) -> str:
    """
    Delete a grid object.
    
    Args:
        ref: Object reference
    
    Returns:
        Reference of deleted object
    """
    if not ref:
        raise WAPIValidationError("Object reference is required for delete")
    
    url = f"{BASE_URL}{ref}"
    response = session.delete(url)
    response.raise_for_status()
    return response.json()

# Functions for networkview

@handle_wapi_errors
def get_networkview(ref: str = None, **kwargs) -> Union[Dict[str, Any], List[Dict[str, Any]]]:
    """
    Retrieve networkview object(s).
    
    Args:
        ref: Object reference for specific object retrieval
        **kwargs: Search parameters
    
    Returns:
        Single object dict if ref provided, list of objects otherwise
    """
    if ref:
        url = f"{BASE_URL}{ref}"
        response = session.get(url, params=kwargs)
    else:
        url = f"{BASE_URL}networkview"
        response = session.get(url, params=kwargs)
    
    response.raise_for_status()
    return response.json()

@handle_wapi_errors
def search_networkview(**kwargs) -> List[Dict[str, Any]]:
    """
    Search for networkview objects.
    
    Args:
        **kwargs: Search parameters
    
    Returns:
        List of matching objects
    """
    url = f"{BASE_URL}networkview"
    response = session.get(url, params=kwargs)
    response.raise_for_status()
    return response.json()

@handle_wapi_errors
def create_networkview(data: Dict[str, Any]) -> str:
    """
    Create a new networkview object.
    
    Args:
        data: Object data dictionary
    
    Returns:
        Reference of created object
    """
    required_fields = []
    validate_parameters(data, required_fields)
    
    url = f"{BASE_URL}networkview"
    response = session.post(url, json=data)
    response.raise_for_status()
    return response.json()

@handle_wapi_errors
def update_networkview(ref: str, data: Dict[str, Any]) -> str:
    """
    Update an existing networkview object.
    
    Args:
        ref: Object reference
        data: Updated object data
    
    Returns:
        Reference of updated object
    """
    if not ref:
        raise WAPIValidationError("Object reference is required for update")
    
    url = f"{BASE_URL}{ref}"
    response = session.put(url, json=data)
    response.raise_for_status()
    return response.json()

@handle_wapi_errors
def delete_networkview(ref: str) -> str:
    """
    Delete a networkview object.
    
    Args:
        ref: Object reference
    
    Returns:
        Reference of deleted object
    """
    if not ref:
        raise WAPIValidationError("Object reference is required for delete")
    
    url = f"{BASE_URL}{ref}"
    response = session.delete(url)
    response.raise_for_status()
    return response.json()


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
