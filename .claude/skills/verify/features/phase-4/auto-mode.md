# Auto mode

The server holds an Auto run. The agent calls `auto_start`, then `auto_revise` with each new revision of the code, until the server returns `Stopped`. A run stops when every checked requirement passes, when a call proposes requirements or a row waits on a confirmation, when the agent calls `auto_ask`, when the account's usage cap refuses a build (`AccountLimit`), or when the person presses Stop. `bounds_conflicts` stops a run before any build and warns on the Plan mode confirmation page.

Design: `docs/design/phase-4.md` §1b, §2.5 (ADR-0010) and §2.7 (`AccountMeter`). Units 7 and 9 of §4.

## The chat's part

The chat agent runs the loop ([Chat](chat.md)). The server holds the rule, and the chat holds none:

- After every tool call it reads the run's signed log. When the run has stopped, whoever stopped it, it posts a `stop_report` event, with the server's reason and report, and ends the turn. The person's Stop while a turn runs is reported the same way, and the agent's next call is refused by the server.
- When the agent ends a message with the run still running, it posts a `driver` reminder to call `auto_revise` or `auto_ask`, at most three times in a turn. Then the turn ends and the run stays Running.
- A message that continues a run is watched too. A run that stopped before the message was reported by the turn that stopped it.

## The checks §4 gives units 7 and 9

- Unit 7, Auto core: table tests for all pass, pending not counting toward all pass, proposing requirements stopping the run, `auto_ask` stopping it with the agent's note, and a cap refusal stopping it with `AccountLimit`. A scripted driver that keeps calling after `Stopped` is refused with no container started. An agent measurement cannot change `step`.
- Unit 9, conflict exit eval: on "fits in a 20 mm cube, PLA, at least 50 g" the confirmation page warns of the conflict, and the run stops with `NeedsPerson(conflict)` and its `Bounds` before any build. On a stiffness-versus-mass brief the agent stops and reports within 6 revisions, with a note that names both requirements.

## How to get to it

- **Through the chat, scripted.** Start `cad-http` as in [Chat](chat.md), put the conversation in Auto with `curl -X PUT localhost:8765/v1/conversations/$CID/mode -H "cookie: __session=$PERSON_A" -H "content-type: application/json" -d '{"mode": "auto"}'`, and post one message to a script that calls `create_brief`, `propose_requirements`, `ask_to_confirm`, `auto_start`, then `auto_revise` with the plate code. The stream ends with `stop_report` (reason `all_pass`) then `turn_ended`. The run log under `<account base>/projects/` shows `auto_start`, at least one `auto_revise` and `Stopped`.
- **The person's Stop.** While the script's turn runs, `PUT` the mode to `design`. The stream shows the next call refused and a `stop_report` with reason `stopped_by_person`.
- **With a headless client.** Confirm a brief (browser as the person), `auto_start`, `auto_revise` with the plate code, then call `auto_revise` again after `Stopped` and show the refusal with no new container (`docker ps -a --filter label=cad.sandbox` before and after). Cost: docker + browser.
- The conflict warning is on the confirmation page, so `browser.py` reads it from the ARIA snapshot of that page. The 20 mm cube brief stops before any build: the variant store under `$CAD_HOME` stays empty.
- The stiffness-versus-mass eval is a live run through the brief-set driver ([Brief set](../brief-set.md)). Cost: live.

`uv run pytest tests/chat/test_auto_driver.py -q` runs a run to all pass, a run stopped by `auto_ask`, a call refused after `Stopped`, the person's Stop in a turn, and the reminders.
