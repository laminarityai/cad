# Chat and mode switcher

The person chats with our own agent. The agent runs in the `cad-http` process and reaches the MCP tools through an in-memory `mcp.Client`, with an `AgentToken` built for each turn from the person's session. The token names the account and the conversation and never leaves the process, so the agent's tool list is the registry's agent list and nothing else. The person switches between Plan, Design and Auto mode with `PUT /v1/conversations/{id}/mode`. `set_mode` is person-only, so the agent cannot call it.

Design: `docs/design/phase-4.md` §1a, §2.4 (our own chat agent needs no Clerk token) and §2.5 (modes are conversation state). Unit 8 of §4. The web page that renders the stream is a later unit. This file proves the server half.

## Routes

All three take the person's session (`__session` cookie or Bearer). An agent token gets 401. A conversation id of another account is 404, and nothing of it is read or written.

- `POST /v1/conversations` starts a conversation in Plan mode. Body `{}`, content type `application/json`. Answers 201 with `conversation_id`.
- `POST /v1/conversations/{id}/messages` takes `{"text": "..."}`, records it and starts one agent turn. 202 with the message's `seq`, 409 while the last turn still runs, 415 for any content type but `application/json`, 422 for an empty or unknown field. A turn starts on this call, or on a page answer the conversation waits on (below).
- `GET /v1/conversations/{id}/stream` replays the transcript and then follows it as server-sent events. Each event's `id` is its `seq`. `Last-Event-ID` or `?after=N` resumes. `?follow=false` ends after what is held, for `curl`.

Events are `user`, `agent`, `tool_call`, `tool_result`, `driver` (the Auto reminder, or a page answer with `answered`), `stop_report`, `turn_failed` and `turn_ended`. The transcript is `<account base>/conversations/chat/<id>.jsonl`.

## A page answer starts the next turn

A conversation waits on a project when its last `ask_to_confirm` result is `pending`. Each result carries `answers_recorded`, the count of the project's page answers. When the person answers the page (`POST /projects/{pid}/confirm` answers 200), each open conversation of the account that waits on that project gets a `driver` event with `answered: {"project_id", "through"}` and starts a turn, with no `user` event. The text counts what was confirmed and declined and quotes the note, and holds no URL or token. If a turn is running, the follow-up turn starts when it ends, unless that turn's own `ask_to_confirm` returned the answer. A replayed POST is 409 and starts nothing. A conversation not opened since a restart is told when its stream opens, and a `driver` with `answered` that no turn followed runs then.

An answer that confirms a requirements item moves the conversation from Plan to Design, once: a switch back to Plan stands through later asks. A declined answer wakes the agent and stays in Plan. A first `pending` ask in a project whose older briefs are confirmed stays in Plan.

- **Wake.** Run a script that creates a brief, proposes, calls `ask_to_confirm` and ends. Open the page with `--opener` and confirm. `/stream?follow=false` shows `driver`, the next step's reply and `turn_ended` after the first `turn_ended`, and `GET /v1/conversations/$CID` shows `"mode": "design"`.

## The model

`CAD_CHAT_MODEL` picks it. `scripted:<path>` replays a JSON script (see `src/cad/chat/scripted.py`), and any other value is an Anthropic model id. Unset, it is `claude-sonnet-5-5`, and the server needs `ANTHROPIC_API_KEY` only when a turn runs. Live lanes set `CAD_CHAT_MODEL=claude-haiku-4-5-20251001`, except the exit 1 lane, which sets `claude-sonnet-5-5`. Haiku rebuilds the slot but skips `score_variant`, so its card stays pending. Load the key with `set -a; . ~/.config/cad/anthropic.env; set +a`, and never print it.

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

`uv run pytest tests/chat -q`: a turn with a tool call, a refused tool, the token built from the session, the agent tool list equal to the registry's agent list, 401, 404, 409, 415 and 422, a stream that resumes, a transcript that survives a restart, and a model that fails ending the turn with a message. `tests/chat/test_answer_wakes.py` covers the page answer: one turn per answer, a replay, an answer during a turn, a switch back to Plan, a decline, and restarts.

## The web half

The set view's chat column (`web/src/chat/`) follows the stream with `fetch` (so it can send the cookie and resume with `?after=N`), posts messages, and shows each tool call. A Radix dropdown under the input switches Plan, Design and Auto, and Shift+Tab in the input cycles them. The Auto run shows above the variants (`web/src/mode/`): `Running`, with a red Stop button, or `Stopped`, with the reason and the server's report. Every stop moves the picker to Design, and a new run starts only when the person picks Auto. A `tool_result` of `build_variant` or `auto_revise` makes the page read the set at once, and the 2 s re-read stays as the fallback.

The conversation id is in the page's `?chat=` query, with a copy in `localStorage` as the fallback. The page creates a conversation with `{"project_id", "brief_id"}` of the brief it shows, and the agent's system prompt then names them, so it reads the set with `variant_set` and a slot's code with `variant_code` and never asks the person for either. Mode and run live only on the server: the page reads `GET /v1/conversations/{id}` (mode, project, brief, and the latest run, kept after it stops) on load, when the tab becomes visible, every 3 s while visible, and after each turn, Auto tool result, stop report, mode change and stop. A stop pressed in another tab shows within one read. A hidden tab closes its chat stream and its scorecard streams, and reopens them when it is shown, the chat stream from the last event it saw. Over HTTP/1.1 a browser opens 6 connections per host, and two visible set tabs hold 8 streams, so a Stop in either waits for a stream to close.

Seed a server with a brief, three scored variants and a script, then drive it. The brief holds a `max_deflection` requirement on `polymaker-polylite-abs`, which has a Poisson's ratio, so `fea` runs and a card shows pending for a while. Start `cad-http` with the browser daemon's opener first, run `chat_seed.py <run> <account> <port>` (it prints the project and brief ids and writes `<run>/seed/script/script.json`), restart `cad-http` with `CAD_CHAT_MODEL=scripted:<run>/seed/script/script.json`, then:

```
uv run python .claude/skills/verify/scripts/browser.py web chat "$RUN" /projects/<project_id>/briefs/<brief_id> name --url http://127.0.0.1:8791 --account <account> --video "$RUN/vid" [--width 400] [--scheme dark]
```

The script for the model runs one conversation: step 0 and 1 are a `build_variant` the Plan mode refuses and a reply, steps 2 to 4 rebuild slot 1 with `build_variant` and `score_variant`, and the steps after start an Auto run (`auto_start`, then `auto_revise` with `slot` 2). `chat` picks Plan and types the change, picks Design and types it again, and times slot 1: revision 2, all pending, then verdicts, with no navigation. It then picks Auto, waits for `Running`, presses Stop, and waits for `Stopped` with the picker on Design. It writes `<name>-plan.png`, `-before.png`, `-after.png`, `-auto.png`, `-stopped.png`, `<name>.webm`, `<name>.aria.yml` and `<name>.chat.json`, and exits 1 when a step did not happen.

- **Plan refuses.** The transcript shows `build_variant` in red with `refused in Plan mode`, and slot 1 still reads revision 1.
- **Rebuild without a reload.** `<name>.chat.json` has `no_reload` true, `seconds_to_revision`, `seconds_to_pending` and `seconds_to_verdicts` for slot 1, `seconds_to_mesh` for the new mesh, and `seconds_pending_to_mesh` from the pending card to the new mesh on screen. The old mesh stays drawn, under a `Making the new mesh…` line, until the new one replaces it in the same viewer.
- **Stop.** The picker reads Design and the run status reads `Stopped · you stopped it`.
- **Stop from another tab.** Open the page in two tabs in Auto with a run going, press Stop in tab B, and tab A reads `Stopped · you stopped it` with the picker on Design within a few seconds, with no reload. `--stop elsewhere` drives this; Playwright keeps every page visible, so it sets `visibilityState` and fires `visibilitychange` on each switch, as a real tab switch does. `curl -s localhost:8765/v1/conversations/$CID -H "cookie: __session=$PERSON_A"` shows `"mode": "design"`, `"auto_run": null` and the stopped run.
- **Live model.** Run the same drive with `CAD_CHAT_MODEL=claude-haiku-4-5-20251001` and the key loaded as above, typing a change in words and not the script's.

Free proofs: `npm run test` in `web/` (`chat/Chat.test.tsx`, `mode/Mode.test.tsx`).
