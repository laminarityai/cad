import json

from cad.server.app import REPO_ROOT

MCP_CONFIG = REPO_ROOT / ".mcp.json"


def cad_entry() -> dict[str, object]:
    config = json.loads(MCP_CONFIG.read_text())
    return config["mcpServers"]["cad"]


def test_launcher_does_not_relock_uv_lock() -> None:
    entry = cad_entry()
    assert entry["command"] == "uv"
    assert entry["args"] == ["run", "--frozen", "cad-server"]
