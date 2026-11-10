# Chat and mode switcher

The person chats with our own agent. The agent runs in the `cad-http` process and reaches the MCP tools through an in-memory `mcp.Client`, with an `AgentToken` built for each turn from the person's session. The token names the account and the conversation and never leaves the process, so the agent's tool list is the registry's agent list and nothing else. The person switches between Plan, Design and Auto mode with `PUT /v1/conversations/{id}/mode`. `set_mode` is person-only, so the agent cannot call it.

Design: `docs/design/phase-4.md` §1a, §2.4 (our own chat agent needs no Clerk token) and §2.5 (modes are conversation state). Unit 8 of §4. The web page that renders the stream is a later unit. This file proves the server half.

## Routes

All three take the person's session (`__session` cookie or Bearer). An agent token gets 401. A conversation id of another account is 404, and nothing of it is read or written.

- `POST /v1/conversations` starts a conversation in Plan mode. Body `{}`, content type `application/json`. Answers 201 with `conversation_id`.
- `POST /v1/conversations/{id}/messages` takes `{"text": "..."}`, records it and starts one agent turn. 202 with the message's `seq`, 409 while the last turn still runs, 415 for any content type but `application/json`, 422 for an empty or unknown field. A turn starts only on this call.
- `GET /v1/conversations/{id}/stream` replays the transcript and then follows it as server-sent events. Each event's `id` is its `seq`. `Last-Event-ID` or `?after=N` resumes. `?follow=false` ends after what is held, for `curl`.

Events are `user`, `agent`, `tool_call`, `tool_result`, `driver` (the reminder below), `stop_report`, `turn_failed` and `turn_ended`. The transcript is `<account base>/conversations/chat/<id>.jsonl`.

## The model

`CAD_CHAT_MODEL` picks it. `scripted:<path>` replays a JSON script (see `src/cad/chat/scripted.py`), and any other value is an Anthropic model id. Unset, it is `claude-sonnet-5-5`, and the server needs `ANTHROPIC_API_KEY` only when a turn runs. Every live lane sets `CAD_CHAT_MODEL=claude-haiku-4-5-20251001`. Load the key with `set -a; . ~/.config/cad/anthropic.env; set +a`, and never print it.

## How to get to it

Start the server the way [Hosted MCP](../hosted-mcp.md) does, with the script in the environment, and mint tokens for two accounts:

```
export CAD_CHAT_MODEL="scripted:$EVIDENCE/script.json"
uv run cad-http --root "$ROOT" --opener true
export PERSON_A=$(uv run cad-token --root "$ROOT" person user_alice)
export PERSON_B=$(uv run cad-token --root "$ROOT" person user_bob)
```

- **One turn.** `CID=$(curl -s -X POST localhost:8765/v1/conversations -H "cookie: __session=$PERSON_A" -H "content-type: application/json" -d '{}' | jq -r .conversation_id)`, then post `{"text": "hi"}` to `/messages` and read `/stream?follow=false`. With a script whose one step calls `server_info`, the stream shows the call, a result holding the head SHA, and the reply.
- **Plan refuses a build.** A script that calls `build_variant` in a new conversation gets a `tool_result` with `is_error` true and `build_variant is refused in Plan mode`. `docker ps -aq --filter label=cad.sandbox` is the same before and after.
- **Another account.** Post to alice's conversation with `PERSON_B`. 404, and alice's stream gains no event.
- **No `set_mode` for the agent.** A script that calls `set_mode` gets an unknown-tool result.
- **The agent cannot answer a confirmation.** A script that calls `ask_to_confirm` shows the call and no `tool_result` until the person answers on the page, and no answer file is written by the agent.

## Proof the tests give

`uv run pytest tests/chat -q`: a turn with a tool call, a refused tool, the token built from the session, the agent tool list equal to the registry's agent list, 401, 404, 409, 415 and 422, a stream that resumes, a transcript that survives a restart, and a model that fails ending the turn with a message.

## Not built yet

A Playwright check that a change asked for in chat becomes the slot's next revision and the viewer and scorecard update without a reload. It waits for the web page and `build_variant`'s `slot`.
