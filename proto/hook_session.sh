#!/bin/sh
# THROWAWAY. Runs headless Claude Code from a project dir whose .claude/settings.json has an
# Elicitation hook, to see whether a hook (a file an agent can write) answers the elicitation.
# Usage: proto/hook_session.sh <project dir with .claude/settings.json> <transcript.json>
REPO=$(cd "$(dirname "$0")/.." && pwd)
cd "$1" || exit 1
claude -p "Call the proto_confirm_elicit tool with requirements ['max mass 50 g']. Print its raw result verbatim." \
  --mcp-config "{\"mcpServers\":{\"cad\":{\"command\":\"uv\",\"args\":[\"--directory\",\"$REPO\",\"run\",\"--frozen\",\"cad-server\"]}}}" \
  --strict-mcp-config --tools "" --allowedTools 'mcp__cad__*' --setting-sources project \
  --output-format json --verbose > "$2"
echo "claude exit=$?"
jq -c '.[] | select(.type=="user") | .message.content[0].content' "$2"
