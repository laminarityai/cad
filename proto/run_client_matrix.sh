#!/bin/sh
# THROWAWAY. Runs the scripted elicitation client in both protocol eras and all three actions.
cd "$(dirname "$0")/.." || exit 1
for mode in auto legacy; do
  for action in accept decline cancel; do
    echo "== mode=$mode action=$action"
    uv run --frozen python proto/elicit_client.py "$mode" "$action" 2>&1
  done
done
