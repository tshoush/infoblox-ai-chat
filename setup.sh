#!/bin/bash

# Setup script for Infoblox AI Chat Interface (IACI)
# Prompts for Infoblox credentials, fetches WAPI schema, generates tools for all WAPI objects,
# downloads docs for RAG, and configures LLM.

# Create project directory
PROJECT_DIR="iaci"
mkdir -p "$PROJECT_DIR/backend/tests" "$PROJECT_DIR/frontend/src/components" "$PROJECT_DIR/rag_docs"

cd "$PROJECT_DIR" || exit

# Git init
git init

# Prompt for Infoblox details
read -p "Enter Infoblox Grid Master IP address: " GRID_IP
read -p "Enter admin username: " ADMIN_USER
read -s -p "Enter password: " ADMIN_PASS
echo
read -p "Enter Network View (default: default): " NETWORK_VIEW
NETWORK_VIEW=${NETWORK_VIEW:-default}

# WAPI version
WAPI_VERSION="v2.13.1"

# Fetch main schema to get supported objects
curl -k -u "$ADMIN_USER:$ADMIN_PASS" "https://$GRID_IP/wapi/$WAPI_VERSION/?_schema" -o schema.json

# Parse supported objects using jq (assume jq installed; if not, install via package manager)
SUPPORTED_OBJECTS=$(jq -r '.supported_objects[]' schema.json)

# Generate tools.py with functions for each object
TOOLS_FILE="backend/tools.py"
echo "import requests" > "$TOOLS_FILE"
echo "" >> "$TOOLS_FILE"
echo "GRID_IP = '$GRID_IP'" >> "$TOOLS_FILE"
echo "ADMIN_USER = '$ADMIN_USER'" >> "$TOOLS_FILE"
echo "ADMIN_PASS = '$ADMIN_PASS'" >> "$TOOLS_FILE"
echo "WAPI_VERSION = '$WAPI_VERSION'" >> "$TOOLS_FILE"
echo "BASE_URL = f'https://{GRID_IP}/wapi/{WAPI_VERSION}/'" >> "$TOOLS_FILE"
echo "" >> "$TOOLS_FILE"

for OBJ in $SUPPORTED_OBJECTS; do
  # Fetch object-specific schema
  curl -k -u "$ADMIN_USER:$ADMIN_PASS" "https://$GRID_IP/wapi/$WAPI_VERSION/?_schema=$OBJ" -o "schema_$OBJ.json"

  # Parse fields and supports (simplified; assume jq extracts)
  # For real, parse 'fields' array for supports like 'r', 'w', 'u', 's'

  # Generate functions
  echo "def get_${OBJ}(**kwargs):" >> "$TOOLS_FILE"
  echo "    url = f'{BASE_URL}${OBJ}'" >> "$TOOLS_FILE"
  echo "    return requests.get(url, auth=(ADMIN_USER, ADMIN_PASS), params=kwargs, verify=False).json()" >> "$TOOLS_FILE"
  echo "" >> "$TOOLS_FILE"

  echo "def search_${OBJ}(**kwargs):" >> "$TOOLS_FILE"
  echo "    url = f'{BASE_URL}${OBJ}'" >> "$TOOLS_FILE"
  echo "    return requests.get(url, auth=(ADMIN_USER, ADMIN_PASS), params=kwargs, verify=False).json()" >> "$TOOLS_FILE"
  echo "" >> "$TOOLS_FILE"

  echo "def create_${OBJ}(data):" >> "$TOOLS_FILE"
  echo "    url = f'{BASE_URL}${OBJ}'" >> "$TOOLS_FILE"
  echo "    return requests.post(url, auth=(ADMIN_USER, ADMIN_PASS), json=data, verify=False).json()" >> "$TOOLS_FILE"
  echo "" >> "$TOOLS_FILE"

  echo "def update_${OBJ}(ref, data):" >> "$TOOLS_FILE"
  echo "    url = f'{BASE_URL}{ref}'" >> "$TOOLS_FILE"
  echo "    return requests.put(url, auth=(ADMIN_USER, ADMIN_PASS), json=data, verify=False).json()" >> "$TOOLS_FILE"
  echo "" >> "$TOOLS_FILE"

  echo "def delete_${OBJ}(ref):" >> "$TOOLS_FILE"
  echo "    url = f'{BASE_URL}{ref}'" >> "$TOOLS_FILE"
  echo "    return requests.delete(url, auth=(ADMIN_USER, ADMIN_PASS), verify=False).json()" >> "$TOOLS_FILE"
  echo "" >> "$TOOLS_FILE"
done

# Download docs for RAG
curl -o rag_docs/wapi_guide.pdf "https://docs.infoblox.com/download/attachments/15433773/Infoblox%2520NIOS%2520WAPI%25209.x%2520Reference%2520Guide.pdf"
curl -o rag_docs/swagger.yaml "https://raw.githubusercontent.com/infobloxopen/infoblox-swagger-wapi/master/swagger.yaml"
curl -o rag_docs/wapi_doc.html "https://ipam.illinois.edu/wapidoc/"

# Note: In the app, use these files for RAG (e.g., via LangChain load_pdf, load_yaml for context in LLM prompts)

# Configure LLM
echo "Configure LLM provider:"
echo "Options: Grok, Llama, OpenAI, Claude, Gemini, etc."
read -p "Enter LLM provider: " LLM_PROVIDER
read -s -p "Enter API Key: " LLM_API_KEY
echo
read -p "Enter Base URL (if custom, e.g., for Llama local): " LLM_BASE_URL

# Save to config.json
cat << EOF > backend/config.json
{
  "infoblox": {
    "grid_ip": "$GRID_IP",
    "admin_user": "$ADMIN_USER",
    "network_view": "$NETWORK_VIEW"
  },
  "llm": {
    "provider": "$LLM_PROVIDER",
    "api_key": "$LLM_API_KEY",
    "base_url": "$LLM_BASE_URL"
  }
}
EOF

# Create other files as in previous setup (abbreviated)
echo "Flask==3.0.3\nrequests==2.32.3\ntabulate==0.9.0" > backend/requirements.txt
echo "{}" > vocabulary.json  # To be updated later
echo "FROM python:3.12\nCOPY . /app\nRUN pip install -r /app/backend/requirements.txt\nCMD ['python', '/app/backend/app.py']" > Dockerfile

# Frontend
echo "{\"name\": \"iaci-frontend\", \"dependencies\": {\"react\": \"^18.3.1\", \"react-autosuggest\": \"^10.1.0\"}}" > frontend/package.json
echo "<!DOCTYPE html><html><body><div id=\"root\"></div></body></html>" > frontend/public/index.html
echo "import React from 'react';" > frontend/src/components/Chat.js  # Stub

# Tests stub (comprehensive tests to be added in app.py etc.)
echo "import unittest" > backend/tests/test_tools.py
echo "class TestTools(unittest.TestCase): pass" >> backend/tests/test_tools.py  # Add tests

# Execute basic test
python -m unittest discover backend/tests

echo "Setup complete. Tools generated in backend/tools.py. Use config.json in your app."