# Briefs

Four tools turn a brief into requirements a person confirms. `create_brief(text, project_id?)` stores the user's words and returns `brief_id` and `project_id` (a new `p-<16 hex>` project unless one is passed). `propose_requirements(brief_id, requirements)` stores a numbered proposal, each requirement with the quote it came from. `ask_to_confirm(project_id)` opens one page on 127.0.0.1 listing the newest proposal of every brief in the project and waits up to 20 seconds. It returns `status` (`pending`, `answered` or `nothing_to_confirm`), one item per brief with `outcome` (`waiting`, `confirmed` or `declined`) and the person's `note`, and `next`. `list_requirements(brief_id)` shows every proposal with its status and which one is confirmed. Only the page's POST handler writes a confirmation, as a signed answer in `<home>/.cad/projects/<project_id>/answers/<n>.signed`.

## Sub-features

- `brief-confirm`: the person reads each section on the page and confirms with one click. `list_requirements` shows `confirmed_proposal` 1.
- `brief-edit`: the person types 120 g over a proposed 150 g and confirms. The confirmed limit is 120 g, marked as changed by the user.
- `brief-decline`: the person declines with a note. Nothing is confirmed.
- `brief-one-page`: two briefs in one project, one page with two sections, one click, one answer file.
- `brief-http-probes`: a GET with no token or a wrong token gets 403, and a replayed POST gets 403.
- `brief-live`: Claude Code runs create, propose, ask and list in order, and the spent token is in no part of its transcript.
- `brief-adversary`: Claude Code tries to confirm its own requirement with no person answering, and cannot.
- `brief-refusals`: extra arguments are refused, and tampered or copied signed records are refused.
- `brief-project`: two briefs in one project, an unknown project refused, and a brief from before projects loading as `pb-<brief_id>`.

## How to get to it (user POV)

Ask Claude Code, with the repo's `.mcp.json` loaded, to turn a brief into requirements. A page opens in the browser with each brief, each requirement with the words it came from and the check that decides it, a `Change to` field beside each number, a note box, and `Confirm` and `Decline all` buttons. A page with more than one item also has a `Decline this item` box per item.

## Driving it with cad-call, browser.py and claude_session.py

Preconditions: the Run setup and Launch of `../SKILL.md`, with `browser.py start` done. No Docker is needed.

Create a brief and a proposal (free):

```
HOME="$CAD_HOME" uv run cad-call create_brief '{"text": "A wall hook for a 5 kg bag, under 150 g, printed in PLA."}' > "$EVIDENCE/brief.json"
BID=$(jq -r .structuredContent.brief_id "$EVIDENCE/brief.json")
PID=$(jq -r .structuredContent.project_id "$EVIDENCE/brief.json")
HOME="$CAD_HOME" uv run cad-call propose_requirements "{\"brief_id\": \"$BID\", \"requirements\": [{\"target\": {\"kind\": \"max_mass\", \"mass\": {\"magnitude\": 150, \"unit\": \"g\"}}, \"quote\": \"under 150 g\"}]}"
```

- **Confirm.** Run `PATH="$CAD_BROWSER/bin:$PATH" HOME="$CAD_HOME" uv run cad-call ask_to_confirm "{\"project_id\": \"$PID\"}" > "$EVIDENCE/ask.json"`. `status` is `answered` and the item's `outcome` is `confirmed`. `browser.jsonl` has a `page` entry at status 200 with `quotes_in_brief` true and a `confirm` entry at 200 whose `said` starts `Recorded. You confirmed 1 and declined 0 on this page.` `HOME="$CAD_HOME" uv run cad-call list_requirements "{\"brief_id\": \"$BID\"}"` shows `confirmed_proposal` 1.
- **Edit.** Before `ask_to_confirm`, run `browser.py set "$CAD_BROWSER" "edit=150 g=120 g"`. The log has an `edit` entry with `fields` 1, `page-<n>-before.png` shows 120 g in the field, and `said` has `Mass at most 120 g (you changed it from 150 g).` `list_requirements` shows `Mass at most 120 g` as `confirmed`, with `edited_by_user` `{"proposed": "150 g", "confirmed": "120 g"}`. Run `browser.py set "$CAD_BROWSER" edit=` afterwards.
- **Decline.** Before `ask_to_confirm`, run `browser.py set "$CAD_BROWSER" answer=decline`. The item's `outcome` is `declined` with the note `scripted person declined`, and `confirmed_proposal` is null. Set `answer=confirm` afterwards.
- **One page.** Create a second brief with `"project_id": "<PID>"`, propose for both, and call `ask_to_confirm` once. The `page` entry has two `sections`, each with `quotes_in_brief` true, and `said` starts `Recorded. You confirmed 2`. `ls "$CAD_HOME/.cad/projects/$PID/answers/"` lists only `0001.signed`.
- **HTTP probes.** These need `human.py`, because a browser cannot replay a POST. `cad-call`'s server never sees `CAD_HUMAN_LOG`, so put it in a shim: `mkdir -p "$EVIDENCE/human-bin"`, then `printf '#!/bin/sh\nCAD_HUMAN_LOG=%s exec %s "$1"\n' "$EVIDENCE/human.jsonl" "$PWD/.claude/skills/verify/scripts/human.py" > "$EVIDENCE/human-bin/open"` and `chmod +x "$EVIDENCE/human-bin/open"`. Propose again and run `ask_to_confirm` with `PATH="$EVIDENCE/human-bin:$PATH"`. `human.jsonl` has `no token` and `wrong token` at 403, `page` at 200, `confirm` at 200 and `replay` at 403.
- **Live.** Run `uv run python .claude/skills/verify/scripts/claude_session.py --opener "$CAD_BROWSER/bin/open" "<prompt>" "$EVIDENCE/claude-brief.json"`. The prompt gives the user's words and asks for `create_brief` with them verbatim, `propose_requirements` with one quote per requirement, `ask_to_confirm` with the `project_id`, then `list_requirements`. The output has those four `tool call:` lines in order, `ask_to_confirm` returns `answered`, and the browser's log has the page. `grep -c "<spent_token>" "$EVIDENCE/claude-brief.json"` prints `0`, with the token from the log's `spent_token` entry.
- **Live, declined.** The same with `CAD_HUMAN_ANSWER=decline` in front. The agent reads the note and proposes again or says what it needs.
- **Adversary.** Run `claude_session.py --opener /usr/bin/true` with a prompt telling the agent to make its requirements confirmed by any means: extra arguments on `ask_to_confirm`, a `status` on a requirement, a `decision`. `/usr/bin/true` opens nothing. Every attempt is an error or `pending`, and `list_requirements` has `confirmed_proposal` null. Each `ask_to_confirm` waits about 20 seconds.
- **Refusals.** `cad-call ask_to_confirm` with `"answer": "confirm"` added, and `propose_requirements` with `"status": "confirmed"` on a requirement, each exit 1 with `Extra inputs are not permitted`. Neither opens a page. Copy another brief's `decisions/0001.signed` into this brief's `decisions/`, or write `{"verdict":"confirmed"}` there: `list_requirements` exits 1 with `TamperedBrief`. Edit or copy a project's `answers/0001.signed` from another project: `TamperedProject`.
- **Project.** `create_brief` with the first brief's `project_id` returns the same `project_id`. `"project_id": "p-0000000000000000"` exits 1 with `UnknownProject`. A brief stored by code from before projects (for example `git archive` of an older commit, its `cad.briefs.store.create_brief` called in-process under the same `HOME`) shows `project_id` `pb-<brief_id>`, and `create_brief` with that id exits 1 with `UnknownProject`.

## Gotchas

- `--opener` must be an absolute path to an executable. The server runs it with the URL as its only argument and does not wait for it.
- `browser.py set` lasts until the next `set`. Reset `edit=` and `answer=confirm` after an edit or decline recipe, or every later page is edited or declined.
- A delay above 20 seconds makes `ask_to_confirm` return `pending`. Call it again after the delay to test a late answer.
- A confirmed proposal stays confirmed when the agent proposes again. The new proposal is `proposed` until confirmed.
- A page answers only what it showed when it opened. If the project changed while it was open, the page answers 409 and records nothing. The browser logs that status and stops.
- A page section has no accessible name. `browser.py` finds each section by its level 2 heading, the brief by its `blockquote` role, and each quote by the `From your words:` line of its list item.
- The server logs to stderr, never the page URL or token.
