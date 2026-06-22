import requests
import json
from backend.config import load_config

config = load_config().infoblox

try:
    response = requests.get(f"https://{config.grid_ip}/wapi/", auth=(config.admin_user, config.admin_pass), verify=False)
    response.raise_for_status()
    data = response.json()
    if 'supported_versions' in data:
        print(json.dumps(data['supported_versions'], indent=2))
    else:
        print("Could not find 'supported_versions' in the response.")
except requests.exceptions.RequestException as e:
    print(f"Error: {e}")
