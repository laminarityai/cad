# Hosted confirmation

The confirmation page lives in the signed-in web app, at `/projects/<project_id>/confirm`. Only a person session can read or answer it, so the agent never answers its own confirmation. `ask_to_confirm` hands nothing to the agent: a client that declared URL elicitation is asked to open the page, a local server's `--opener PROGRAM` is handed a sign-in link, and any other client gets the result `pending` with `next` saying the confirmation is waiting in the web app.

Design: `docs/design/phase-4.md` §2.4 (amends ADR-0004, resolves #47). Unit 4 of §4. Code: `src/cad/confirmations/web.py` (the routes), `page.py` (the form), `snapshot.py` (what the page showed), `src/cad/operations/confirmation.py` (`answer_page`).

## Sub-features

- `confirm-sign-in`: `GET /local/sign-in?token=<person JWT>&project=<project_id>` answers 303 to the page and sets `__session`. Only on a server that trusts the local issuer.
- `confirm-page`: the page needs a person session. No cookie or an agent token is 401, another account's cookie is 404, and nothing waiting is 200 with `Nothing in this project waits on you.`
- `confirm-answer`: one POST answers every item on the page and records one signed answer.
- `confirm-refusals`: an agent token, a missing or foreign `Origin`, a snapshot that is not this session's, a stale snapshot and a replay each record nothing.
- `confirm-waiting`: `ask_to_confirm` over HTTP returns `pending`, says the confirmation is waiting in the web app, and holds no link.
- `confirm-clerk-session`: hosted, the page loads Clerk's pinned `clerk-js@5.128.1` from the Frontend API, takes a fresh session token before it posts, and keeps the person's fields in the tab's sessionStorage under the snapshot's items. A token that expires while the person reads still records, and a POST that meets an ended session goes through sign-in and back to the page with the edits in place. The local page loads no script.
- `confirm-browser`: `browser.py` as the person, through `--opener`, with the page's real buttons.
- Not built: the interactive Claude Code URL dialog. It cannot run headless, so it stays an operator step with a screenshot.

## How to get to it (user POV)

Hosted, a person signs in with Clerk, and Claude Code opens the project's confirmation page from the URL dialog. The page lists each brief with its requirements and the words each came from, a `Change to` field beside each number, a note box, and `Confirm` and `Decline all` buttons. Locally, `cad-http --opener PROGRAM` (or `cad-server --opener PROGRAM`) runs `PROGRAM <link>` with `http://127.0.0.1:<port>/local/sign-in?token=<person JWT>&project=<project_id>`.

## Driving it with cad-http, curl and browser.py

Preconditions: the Run setup and Launch of `../../SKILL.md`, and `browser.py start` for the browser recipe. No Docker is needed. Set a data root and a port:

```
export ROOT="$EVIDENCE/root"
export PORT=8791
```

Boot the server in its own terminal, with the browser as the person:

```
HOME="$CAD_HOME" uv run cad-http --root "$ROOT" --port "$PORT" --opener "$CAD_BROWSER/bin/open"
```

Mint tokens (each `person` call is a new session, and a page answers only the session that opened it):

```
export AGENT_A=$(uv run cad-token --root "$ROOT" --url http://127.0.0.1:$PORT agent user_alice)
export PERSON_A=$(uv run cad-token --root "$ROOT" --url http://127.0.0.1:$PORT person user_alice)
export PERSON_A2=$(uv run cad-token --root "$ROOT" --url http://127.0.0.1:$PORT person user_alice)
export PERSON_B=$(uv run cad-token --root "$ROOT" --url http://127.0.0.1:$PORT person user_bob)
```

Create a brief and a proposal as the agent. `propose_requirements` with the same arguments twice is one proposal, so change the number to make a new one:

```
export U=http://127.0.0.1:$PORT
CALL() { HOME="$CAD_HOME" uv run cad-call --url $U/mcp --token "$AGENT_A" "$@"; }
CALL create_brief '{"text": "A wall hook for a 5 kg bag, under 150 g, printed in PLA."}' > "$EVIDENCE/hbrief.json"
export BID=$(jq -r .structuredContent.brief_id "$EVIDENCE/hbrief.json")
export PID=$(jq -r .structuredContent.project_id "$EVIDENCE/hbrief.json")
propose() { CALL propose_requirements "{\"brief_id\": \"$BID\", \"requirements\": [{\"target\": {\"kind\": \"max_mass\", \"mass\": {\"magnitude\": $1, \"unit\": \"g\"}}, \"quote\": \"under 150 g\"}]}"; }
propose 150
```

- **Browser.** With the server above, run `CALL ask_to_confirm "{\"project_id\": \"$PID\"}"`. `status` is `answered`. `browser.jsonl` has a `page` entry at 200 with `path` `/projects/<PID>/confirm` and a `confirm` entry at 200 whose `said` starts `Recorded. You confirmed 1 and declined 0 on this page.` `CALL list_requirements "{\"brief_id\": \"$BID\"}"` shows `confirmed_proposal` 1. The cad-http log has no JWT: `grep -c eyJ <server log>` prints `0`.
- **Sign-in link.** Run `curl -s -i "$U/local/sign-in?token=$PERSON_A&project=$PID"`. Status `303`, `location: /projects/<PID>/confirm` and `set-cookie: __session=...; HttpOnly; Path=/; SameSite=lax`. An agent token or `token=junk` is `401`, and `project=nope` is `400`.
- **Waiting, with no link.** Stop the server and boot it again without `--opener`, so nothing answers. Propose, then run `CALL ask_to_confirm "{\"project_id\": \"$PID\"}"`. After about 20 seconds `status` is `pending`, the item's `outcome` is `waiting`, and `next` starts `The confirmation is waiting in the web app and has no answer yet.` The result has no `http` anywhere in it.
- **Page and snapshot.** With no opener, a page is open to curl. `curl -s -o /dev/null -w "%{http_code}\n" $U/projects/$PID/confirm` is `401`, and the same with `-H "authorization: Bearer $AGENT_A"` is `401`. `-H "cookie: __session=$PERSON_B"` is `404` (`There is no such project in your account.`). With `-H "cookie: __session=$PERSON_A"` it is `200`. Save the page and read its seal: `SNAP=$(curl -s -H "cookie: __session=$PERSON_A" $U/projects/$PID/confirm | grep -o 'name="snapshot" value="[^"]*"' | sed 's/.*value="//;s/"$//')`.
- **Refusals.** Define `post() { curl -s -w " %{http_code}\n" -X POST -H "content-type: application/x-www-form-urlencoded" -d "snapshot=$SNAP&answer=confirm&note=" "$@" $U/projects/$PID/confirm; }` and `ls "$ROOT/accounts/user_alice/projects/$PID/answers"` for the count. Each of these records nothing, so the listing stays empty:
  - Agent Bearer token: `post -H "authorization: Bearer $AGENT_A" -H "origin: $U"` is `401`. No cookie is `401`.
  - No `Origin`: `post -H "cookie: __session=$PERSON_A"` is `403` (`This answer did not come from this page.`). `-H "origin: http://evil.example"` is `403`.
  - Another account's cookie: `post -H "cookie: __session=$PERSON_B" -H "origin: $U"` is `403` (`This page is not yours to answer.`).
  - Another session of the same account: `post -H "cookie: __session=$PERSON_A2" -H "origin: $U"` is `403`. A made-up snapshot is `403` too.
  - Stale snapshot: take `SNAP` from the page, run `propose 140`, then `post -H "cookie: __session=$PERSON_A" -H "origin: $U"`. Status `409`, `The agent added or changed something since this page opened. Nothing was recorded.`
- **Answer and replay.** Take a new `SNAP` from the page, then run `post -H "cookie: __session=$PERSON_A" -H "origin: $U"`. Status `200`, `Recorded. You confirmed 1 and declined 0 on this page.`, and the answers directory lists `0001.signed`. Run the same command again: `409`, `This page was already answered.`, and still one file. The page now reads `Nothing in this project waits on you.` `CALL list_requirements` shows `confirmed_proposal` 2.
- **Scripted person over HTTP.** `human.py` does the sign-in, the page, the POST and the replay in one run. Boot with `--opener "$PWD/.claude/skills/verify/scripts/human.py"` and `CAD_HUMAN_LOG="$EVIDENCE/human.jsonl"` in front of the command (`cad-http` passes its environment on), propose, and run `ask_to_confirm`. The log has `no session` 401, `page` 200, `confirm` 200, `replay` 409 and `spent_token`. Add `CAD_HUMAN_EDIT="150 g=120 g"` for the edit: `list_requirements` shows `Mass at most 120 g` with `edited_by_user` `{"proposed": "150 g", "confirmed": "120 g"}`.
- **Clerk session expiry.** `uv run python .claude/skills/verify/scripts/clerk_session.py "$EVIDENCE/clerk" expired`, then the same with `signed-out`. A stand-in Clerk Frontend API mints 10 s person tokens under one session id and never refreshes on its own. Each case prints `said` starting `Recorded. You confirmed 1 and declined 0 on this page.`, `Mass at most 120 g (you changed it from 150 g).` and `answers` `["0001.signed"]`. `signed-out.json` logs POST 401, then GET 200 and `restored` with `120 g` and the note, then POST 200. With `PYTHONPATH=<checkout of 91186d5>/src` the `expired` case records nothing: the POST meets 401 and the sign-in page's reload sends it again under a new session, 403.
- **Claude Code.** Run the Live recipe of [Briefs](../briefs.md) with `claude_session.py --opener "$CAD_BROWSER/bin/open"`. `grep -c` of the log's `spent_token` in the transcript must print `0`. Without `--opener` the session's `ask_to_confirm` waits 20 seconds and returns `pending`, and nobody answers.

## Gotchas

- A snapshot is sealed to the session that opened the page. Every `cad-token person` call is a new session, so mint each token once and reuse it, or a valid POST answers 403.
- The 401 body for a local server says to sign in with the link the server handed its opener, even on a `cad-http` that has no opener. Sign in with `/local/sign-in?token=<person JWT>&project=<project_id>` and a token from `cad-token person`.
- A GET answers 404 for another account's cookie, but a POST with it answers 403: the POST is refused by the snapshot, not by the route.
- The person JWT in the sign-in link is good for about an hour and more than once. `spent_token` in `browser.jsonl` and `human.jsonl` is that JWT: grep every transcript for it.
- `cad-http` takes `--opener` only with the local issuer. With Clerk configured it exits, because Clerk signs people in.
- A page's `Origin` must be the server's own origin, `http://127.0.0.1:<port>`, as `cad-token --url` and the sign-in link say it. A request through `localhost` is a different origin and answers 403.
- Kill only the pid you started: `pgrep -fl "cad-http --root $ROOT"`. Never `pkill` by name.
