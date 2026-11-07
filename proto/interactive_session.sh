#!/bin/sh
# THROWAWAY. Starts an interactive Claude Code in tmux, asks it to call proto_confirm_elicit, and
# captures the screen so we can see whether the form reaches the human and not the model.
# Usage: proto/interactive_session.sh <evidence dir>
REPO=$(cd "$(dirname "$0")/.." && pwd)
EV=$1
EMPTY=$(mktemp -d)
CONFIG="{\"mcpServers\":{\"cad\":{\"command\":\"uv\",\"args\":[\"--directory\",\"$REPO\",\"run\",\"--frozen\",\"cad-server\"]}}}"
tmux kill-session -t protoelicit 2>/dev/null
tmux new-session -d -s protoelicit -x 160 -y 50 -c "$EMPTY" \
  claude --mcp-config "$CONFIG" --strict-mcp-config --tools "" --allowedTools 'mcp__cad__*' --setting-sources project
sleep 8
tmux capture-pane -p -t protoelicit > "$EV/tui-0-start.txt"
tmux send-keys -t protoelicit Down Enter
sleep 3
tmux send-keys -t protoelicit "Call the proto_confirm_elicit tool with requirements ['max mass 50 g']. Then print its raw result." Enter
sleep 25
tmux capture-pane -p -t protoelicit > "$EV/tui-1-form.txt"
cat "$EV/tui-1-form.txt"
