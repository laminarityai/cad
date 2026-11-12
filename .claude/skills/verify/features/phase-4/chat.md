# Chat

The person chats with our own agent. The agent runs in the `cad-http` process and reaches the MCP tools through an in-memory `mcp.Client`, with an `AgentToken` built for each turn from the person's session. The token names the account and the conversation and never leaves the process, so the agent's tool list is the registry's agent list and nothing else. A conversation has no mode. It records its running Auto run and the stopped run that holds it, and only the person's message or page answer lifts the hold ([Auto](auto.md)).

Design: `docs/design/phase-4.md` §1a, §2.4 (our own chat agent needs no Clerk token) and §2.5 (the Auto run, ADR-0010). Unit 8 of §4. The project workspace in the web app renders the stream: see The web half below.

## Routes

All three take the person's session (`__session` cookie or Bearer). An agent token gets 401. A conversation id of another account is 404, and nothing of it is read or written.

- `POST /v1/conversations` starts a conversation. Body `{}`, content type `application/json`. Answers 201 with `conversation_id`.
- `POST /v1/conversations/{id}/messages` takes `{"text": "..."}`, records it and starts one agent turn. 202 with the message's `seq`, 409 while the last turn still runs, 415 for any content type but `application/json`, 422 for an empty or unknown field. A turn starts on this call, or on a page answer the conversation waits on (below).
- `GET /v1/conversations/{id}/stream` replays the transcript and then follows it as server-sent events. Each event's `id` is its `seq`. `Last-Event-ID` or `?after=N` resumes. `?follow=false` ends after what is held, for `curl`.

Events are `user`, `agent`, `tool_call`, `tool_result`, `driver` (the Auto reminder, or a page answer with `answered`), `stop_report`, `turn_failed` and `turn_ended`. The transcript is `<account base>/conversations/chat/<id>.jsonl`.

## A page answer starts the next turn

A conversation waits on a project when its last `ask_to_confirm` result is `pending`. Each result carries `answers_recorded`, the count of the project's page answers. When the person answers the page (`POST /projects/{pid}/confirm` answers 200), each open conversation of the account that waits on that project gets a `driver` event with `answered: {"project_id", "through"}` and starts a turn, with no `user` event. The text counts what was confirmed and declined and quotes the note, and holds no URL or token. If a turn is running, the follow-up turn starts when it ends, unless that turn's own `ask_to_confirm` returned the answer. A replayed POST is 409 and starts nothing. A conversation not opened since a restart is told when its stream opens, and a `driver` with `answered` that no turn followed runs then.

An answer, confirmed or declined, deletes nothing built: a brief builds at once, so the options already stand when the card appears.

- **Wake.** Run a script that creates a brief, proposes a stated target, builds and scores an option, calls `ask_to_confirm` and ends. Open the page with `--opener` and confirm. `/stream?follow=false` shows `driver`, the next step's reply and `turn_ended` after the first `turn_ended`, and `GET /v1/conversations/$CID` shows `"stopped_run": null` after.

## The model

`CAD_CHAT_MODEL` picks it. `scripted:<path>` replays a JSON script (see `src/cad/chat/scripted.py`), and any other value is an Anthropic model id. Unset, it is `claude-sonnet-5-5`, and the server needs `ANTHROPIC_API_KEY` only when a turn runs. Live lanes set `CAD_CHAT_MODEL=claude-haiku-4-5-20251001`, except the exit 1 lane, which sets `claude-sonnet-5-5`. Haiku rebuilds the slot but skips `score_variant`, so its card stays pending. `cad-http` reads the key from `~/.config/cad/anthropic.env` (one line, `ANTHROPIC_API_KEY=...`) when it starts and the variable is not already set; a key already in the environment wins. With neither, it prints one line on stdout that names the file. Never print the key.

## How to get to it

Start the server the way [Hosted MCP](../hosted-mcp.md) does, with the script in the environment, and mint tokens for two accounts:

```
export CAD_CHAT_MODEL="scripted:$EVIDENCE/script.json"
uv run cad-http --root "$ROOT" --opener true
export PERSON_A=$(uv run cad-token --root "$ROOT" person user_alice)
export PERSON_B=$(uv run cad-token --root "$ROOT" person user_bob)
```

- **One turn.** `CID=$(curl -s -X POST localhost:8765/v1/conversations -H "cookie: __session=$PERSON_A" -H "content-type: application/json" -d '{}' | jq -r .conversation_id)`, then post `{"text": "hi"}` to `/messages` and read `/stream?follow=false`. With a script whose one step calls `server_info`, the stream shows the call, a result holding the head SHA, and the reply.
- **A fresh brief builds at once.** A script that calls `create_brief`, `propose_requirements` and `build_variant` in a new conversation, with no `ask_to_confirm` before it, gets a `tool_result` with no error and a variant id.
- **Another account.** Post to alice's conversation with `PERSON_B`. 404, and alice's stream gains no event.
- **No `auto_stop` for the agent.** A script that calls `auto_stop` gets an unknown-tool result.
- **The agent cannot answer a confirmation.** A script that calls `ask_to_confirm` shows the call and no `tool_result` until the person answers on the page, and no answer file is written by the agent.

## Proof the tests give

`uv run pytest tests/chat -q`: a turn with a tool call, a refused tool, the token built from the session, the agent tool list equal to the registry's agent list, 401, 404, 409, 415 and 422, a stream that resumes, a transcript that survives a restart, and a model that fails ending the turn with a message. `tests/chat/test_answer_wakes.py` covers the page answer: one turn per answer, a replay, an answer during a turn, a decline that keeps the built options, and restarts.

## The web half

The project workspace (`web/src/features/workspace/`) is one page per project at `/projects/{id}`. The empty `/app` is a chat start: the first message makes the conversation, the agent's `create_brief` binds it to the new project, and the page moves to the project. `GET /v1/projects/{id}/conversation` returns the project's one conversation, made on the first read, so every part of the project opens the same chat. The chat follows the stream with `fetch` and resumes with `?after=N`; the chat section carries `aria-busy` while a turn runs. A confirmation waiting on the person shows as a card in the chat titled "Confirm your targets" (`data-confirm-card`), and only when a target the person stated waits. A brief with no stated number shows no card. The card is read from `GET /v1/projects/{id}/confirmation` and posted to the same person-only handler as `/projects/{id}/confirm`, with the snapshot the server sealed. The Checks pane groups what the person asked for, what awaits their Confirm (a waiting row with the measure beside it, no verdict) and what the agent assumed. There is no mode picker. While the conversation has a running run, or a stopped run that holds it, the chat shows an `Auto run` section above the input (`web/src/features/auto/`) with the run's status and, while it runs, a Stop button (`POST /v1/auto/{run_id}/stop`). A `stop_report` line names why the run stopped. The section disappears when the person's next message lifts the hold, and the stop report stays in the chat.

Drive it with a live model. Start `cad-http` on a fresh root with the key loaded and `CAD_CHAT_MODEL` set (Sonnet by default), then:

```
uv run python .claude/skills/verify/scripts/browser.py web walk "$RUN" "$RUN/shots" --url http://127.0.0.1:8765
```

`walk` (`web_walk.py`) starts on the empty `/app`, types a box brief, waits for the options and their checks (the box brief states a number, so a Confirm card shows too, and the walk confirms it with no rebuild), asks for a change and steps back to the earlier revision, asks for a lid, waits for its options, confirms the card when one shows, and turns the fit ghost on. It shoots each step in dark mode at 1440 px and the last at 400 px, and exits 1 at the first step that did not happen, with `missed.png`. `--brief`, `--change` and `--lid` replace the words it types.

Free proofs: `npm run test` in `web/` (`features/workspace/workspace.test.tsx`).
