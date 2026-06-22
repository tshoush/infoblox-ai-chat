import json
import os
from typing import Any, Dict, List

import requests

from backend.config import InfobloxConfig
from backend.vocabulary import Vocabulary

class ToolGenerator:
    """Dynamically generates WAPI tools from Infoblox schemas."""

    def __init__(self, config: InfobloxConfig):
        self.config = config
        self.base_url = f"https://{config.grid_ip}/wapi/{config.wapi_version}/"
        self.auth = (config.admin_user, config.admin_pass)
        self.schema_dir = "backend/schemas"
        os.makedirs(self.schema_dir, exist_ok=True)
        self.vocabulary = Vocabulary()

    def fetch_schema(self, object_name: str = "") -> Dict[str, Any]:
        """Fetches the WAPI schema for a given object or the main schema.

        WAPI exposes a schema for an object at ``<base>/<object>?_schema``. The
        previous implementation used ``<base>/?_schema=<object>``; WAPI ignores
        that query value and returns the *main* schema for every object, which is
        why every cached per-object schema ended up identical.
        """
        if object_name:
            schema_url = f"{self.base_url}{object_name}?_schema"
        else:
            schema_url = f"{self.base_url}?_schema"

        try:
            response = requests.get(
                schema_url, 
                auth=self.auth, 
                verify=False, 
                timeout=self.config.connection_timeout
            )
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            print(f"Error fetching schema for '{object_name}': {e}")
            return {}

    # Default CRUD capabilities used when a per-object schema does not declare
    # its "supports" string (e.g. when generating offline from a cached main
    # schema). WAPI objects generally support read/write/update/delete.
    DEFAULT_SUPPORTS = ["r", "w", "u", "d"]

    def _load_main_schema(self, offline_schema_path: str = None) -> Dict[str, Any]:
        """Returns the main schema, preferring a live fetch and falling back to
        a local cached schema file (so tools can be regenerated offline)."""
        main_schema = {} if offline_schema_path else self.fetch_schema()
        if main_schema.get("supported_objects"):
            return main_schema

        for candidate in filter(None, [offline_schema_path, "schema.json", "network_schema.json"]):
            if os.path.exists(candidate):
                with open(candidate, "r") as f:
                    schema = json.load(f)
                if schema.get("supported_objects"):
                    print(f"Using local schema '{candidate}' for tool generation.")
                    return schema
        return main_schema

    def generate_tools(self, offline_schema_path: str = None) -> None:
        """Generates Python functions for each WAPI object and saves them to a file."""
        main_schema = self._load_main_schema(offline_schema_path)
        if not main_schema:
            print("Could not fetch main schema. Tool generation aborted.")
            return

        supported_objects = main_schema.get("supported_objects", [])
        self.vocabulary.add_terms(supported_objects, "wapi_objects")

        tools_code = self._generate_header()

        for obj in supported_objects:
            obj_schema_path = os.path.join(self.schema_dir, f"{obj.replace(':', '_')}.json")
            obj_schema = {}
            if os.path.exists(obj_schema_path):
                with open(obj_schema_path, 'r') as f:
                    cached = json.load(f)
                # Guard against corrupt caches that hold the *main* schema dump
                # (an earlier URL bug wrote the main schema to every object file).
                if "supported_objects" not in cached:
                    obj_schema = cached
            elif not offline_schema_path:
                obj_schema = self.fetch_schema(obj)
                if obj_schema:
                    with open(obj_schema_path, 'w') as f:
                        json.dump(obj_schema, f, indent=2)

            # Extract field names and enum values for vocabulary
            field_names = []
            enum_values = []
            for field in obj_schema.get("fields", []):
                if field.get("name"):
                    field_names.append(field.get("name"))
                if "enum_values" in field:
                    enum_values.extend(field["enum_values"])
            if field_names:
                self.vocabulary.add_terms(field_names, "wapi_fields")
            if enum_values:
                self.vocabulary.add_terms(enum_values, "wapi_enum_values")

            tools_code += self._generate_crud_functions(obj, obj_schema)

        with open("backend/tools.py", "w") as f:
            f.write(tools_code)
        print("Successfully generated WAPI tools.")

    def _generate_header(self) -> str:
        # NOTE: this is an f-string, so ``{{ }}`` emits literal braces (the
        # generated file's own runtime f-string) while ``{self...}`` is
        # interpolated now. The previous version used a plain string, so the
        # output contained an undefined ``{self.config.verify_ssl}`` set literal
        # and broke on import.
        return f'''"""
Autogenerated WAPI tools for Infoblox.

This file is automatically generated by the ToolGenerator. Do not edit manually.
"""
import requests
from backend.config import load_config

config = load_config().infoblox
BASE_URL = f"https://{{config.grid_ip}}/wapi/{{config.wapi_version}}/"
AUTH = (config.admin_user, config.admin_pass)
VERIFY_SSL = {bool(self.config.verify_ssl)}


'''

    def _generate_crud_functions(self, object_name: str, schema: Dict[str, Any]) -> str:
        """Generates the CRUD function strings for a given WAPI object."""
        func_name = object_name.replace(":", "_").replace("-", "_")
        
        functions = []
        supports = schema.get("supports") or self.DEFAULT_SUPPORTS

        # GET/Search Function
        if "r" in supports or "s" in supports:
            functions.append(f'''
def search_{func_name}(**kwargs) -> dict:
    """Search for {object_name} objects."""
    url = f"{{BASE_URL}}{object_name}"
    try:
        response = requests.get(url, auth=AUTH, params=kwargs, verify=VERIFY_SSL)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        return {{\"error\": str(e)}}
''')

        # CREATE Function
        if "w" in supports:
            functions.append(f'''
def create_{func_name}(data: dict) -> dict:
    """Create a new {object_name} object."""
    url = f"{{BASE_URL}}{object_name}"
    try:
        response = requests.post(url, auth=AUTH, json=data, verify=VERIFY_SSL)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        return {{\"error\": str(e)}}
''')

        # UPDATE Function
        if "u" in supports:
            functions.append(f'''
def update_{func_name}(ref: str, data: dict) -> dict:
    """Update a {object_name} object."""
    url = f"{{BASE_URL}}{{ref}}"
    try:
        response = requests.put(url, auth=AUTH, json=data, verify=VERIFY_SSL)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        return {{\"error\": str(e)}}
''')

        # DELETE Function
        if "d" in supports:
            functions.append(f'''
def delete_{func_name}(ref: str) -> dict:
    """Delete a {object_name} object."""
    url = f"{{BASE_URL}}{{ref}}"
    try:
        response = requests.delete(url, auth=AUTH, verify=VERIFY_SSL)
        response.raise_for_status()
        return response.json() if response.content else {{\"success\": True}}
    except requests.exceptions.RequestException as e:
        return {{\"error\": str(e)}}
''')

        return "\n".join(functions) + "\n"