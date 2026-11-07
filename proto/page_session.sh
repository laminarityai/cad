#!/bin/sh
# THROWAWAY. Headless Claude calls proto_confirm_page; this script plays the human by reading the
# one-time URL from a file the agent is not told about and clicking Confirm with curl.
# Usage: proto/page_session.sh <evidence dir>
REPO=$(cd "$(dirname "$0")/.." && pwd)
EV=$1
URLFILE=$(mktemp -u "$EV/page-url.XXXX")
EMPTY=$(mktemp -d)
cd "$EMPTY" || exit 1
claude -p "Call the proto_confirm_page tool with requirements ['max mass 50 g', 'fits 60x40 mm']. Print its raw result verbatim." \
  --mcp-config "{\"mcpServers\":{\"cad\":{\"command\":\"uv\",\"args\":[\"--directory\",\"$REPO\",\"run\",\"--frozen\",\"cad-server\"],\"env\":{\"CAD_PROTO_URL_FILE\":\"$URLFILE\"}}}}" \
  --strict-mcp-config --tools "" --allowedTools 'mcp__cad__*' --setting-sources project \
  --output-format json --verbose > "$EV/claude-page.json" &
CLAUDE=$!
while [ ! -s "$URLFILE" ]; do sleep 0.5; done
URL=$(cat "$URLFILE")
TOKEN=${URL#*t=}
BASE=${URL%%/?t=*}
echo "human: page GET without token -> $(curl -s -o /dev/null -w '%{http_code}' "$BASE/")"
echo "human: page GET with token -> $(curl -s -o /dev/null -w '%{http_code}' "$URL")"
sleep 3
echo "human: click Confirm -> $(curl -s "$BASE/answer?t=$TOKEN&a=accept")"
echo "replay: second click -> $(curl -s -o /dev/null -w '%{http_code}' "$BASE/answer?t=$TOKEN&a=decline")"
wait $CLAUDE
echo "claude exit=$?"
echo "agent-facing tool_result:"
jq -c '.[] | select(.type=="user") | .message.content[0].content' "$EV/claude-page.json"
if grep -q "$TOKEN" "$EV/claude-page.json"; then echo "TOKEN FOUND in transcript"; else echo "token absent from transcript"; fi
