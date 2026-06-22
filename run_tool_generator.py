"""Regenerate backend/tools.py from WAPI schemas.

Usage:
    python run_tool_generator.py             # live: fetch schemas from the Grid
    python run_tool_generator.py --offline   # offline: use local schema.json
"""
import sys

from backend.config import load_config
from backend.tool_generator import ToolGenerator

if __name__ == "__main__":
    offline = "--offline" in sys.argv
    config = load_config()
    generator = ToolGenerator(config.infoblox)
    generator.generate_tools(offline_schema_path="schema.json" if offline else None)
