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

## The web half

The set view's chat column (`web/src/chat/`) follows the stream with `fetch` (so it can send the cookie and resume with `?after=N`), posts messages, and shows each tool call. A Radix dropdown under the input switches Plan, Design and Auto, and Shift+Tab in the input cycles them. The Auto run shows above the variants (`web/src/mode/`): `Running`, with a red Stop button, or `Stopped`, with the reason and the server's report. Every stop moves the picker to Design, and a new run starts only when the person picks Auto. A `tool_result` of `build_variant` or `auto_revise` makes the page read the set at once, and the 2 s re-read stays as the fallback.

The conversation id is in the page's `?chat=` query, with a copy in `localStorage` as the fallback. The server has no read route for a conversation's mode or run, so the page keeps its last known mode and run in `localStorage` under the conversation id, and the server's answer to each `PUT` and the stream's stop reports win over it.

Seed a server with a brief, three scored variants and a script, then drive it. The brief holds a `max_deflection` requirement on `polymaker-polylite-abs`, which has a Poisson's ratio, so `fea` runs and a card shows pending for a while. Start `cad-http` with the browser daemon's opener first, run `chat_seed.py <run> <account> <port>` (it prints the project and brief ids and writes `<run>/seed/script/script.json`), restart `cad-http` with `CAD_CHAT_MODEL=scripted:<run>/seed/script/script.json`, then:

```
uv run python .claude/skills/verify/scripts/browser.py web chat "$RUN" /projects/<project_id>/briefs/<brief_id> name --url http://127.0.0.1:8791 --account <account> --video "$RUN/vid" [--width 400] [--scheme dark]
```

The script for the model runs one conversation: step 0 and 1 are a `build_variant` the Plan mode refuses and a reply, steps 2 to 4 rebuild slot 1 with `build_variant` and `score_variant`, and the steps after start an Auto run (`auto_start`, then `auto_revise` with `slot` 2). `chat` picks Plan and types the change, picks Design and types it again, and times slot 1: revision 2, all pending, then verdicts, with no navigation. It then picks Auto, waits for `Running`, presses Stop, and waits for `Stopped` with the picker on Design. It writes `<name>-plan.png`, `-before.png`, `-after.png`, `-auto.png`, `-stopped.png`, `<name>.webm`, `<name>.aria.yml` and `<name>.chat.json`, and exits 1 when a step did not happen.

- **Plan refuses.** The transcript shows `build_variant` in red with `refused in Plan mode`, and slot 1 still reads revision 1.
- **Rebuild without a reload.** `<name>.chat.json` has `no_reload` true, `seconds_to_revision`, `seconds_to_pending` and `seconds_to_verdicts` for slot 1, and `seconds_to_mesh` for the new mesh.
- **Stop.** The picker reads Design and the run status reads `Stopped · you stopped it`.
- **Live model.** Run the same drive with `CAD_CHAT_MODEL=claude-haiku-4-5-20251001` and the key loaded as above, typing a change in words and not the script's.

Free proofs: `npm run test` in `web/` (`chat/Chat.test.tsx`, `mode/Mode.test.tsx`).
