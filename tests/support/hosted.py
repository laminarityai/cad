"""Where the hosted app thinks it is served from, for tests that build it in process."""

from typing import Final

BASE: Final = "http://127.0.0.1:8765"
MCP: Final = f"{BASE}/mcp"
