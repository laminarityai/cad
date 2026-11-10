# A person confirms requirements on a local page, not through MCP elicitation

A check reads only requirements that a person confirmed. The agent makes every MCP call, so the server cannot accept a confirmation that arrives as a tool call. We need a channel that only the person can answer. We tried two on branch `proto/elicitation` (commit `719ae37`), measured on Claude Code 2.1.287 with mcp 2.3.0.

MCP elicitation failed. The server sent the form and the model never saw it. But an `Elicitation` hook in `.claude/settings.json` answered the form with no person present, and an agent with the Edit tool can write that file. Headless `claude -p` cancelled every elicitation, so evals could never use the channel.

A local page passed. The server served it on 127.0.0.1 with a one-time token that the agent never received. The page returned 403 without the token, accepted one click, and refused a replay. The token did not appear in the transcript.

We chose the local page. `confirm_requirements` opens it with the operating system's `open` command. The page shows the brief, each proposed requirement with the words it was taken from, and the check that decides it. The person confirms or declines the whole set. Only the page's request handler writes a decision record, and the store signs it with the brief store's key (ADR-0003). Status is never stored. The store derives it from the signed decision records, so there is no `confirmed` field to edit.

## Consequences

The guarantee is this. An agent that reaches the server only through MCP cannot confirm a requirement, and every confirmation is signed. No tool returns or logs the token, the port or the URL. No tool takes a path, a program or a URL as an argument.

The guarantee does not cover an agent with shell or browser tools that runs as the same user. That agent can read the URL from the `open` process's arguments or from the browser, and it can read the store key, as ADR-0003 already states. The operator approved this level of guarantee on 2026-11-07. Closing the gap needs a channel that the operating system keeps from same-user processes, and it is out of scope for phase 2.

A person can take longer than a client allows for one tool call. Claude Code 2.1.287 completed a 70-second and a 330-second tool call, so it did not time out in our measurement. Other clients can have shorter limits. So `confirm_requirements` waits at most 20 seconds and then returns `pending`. The page stays open for 30 minutes or until the server stops. A later call reports the answer from the signed record on disk, not from memory, so an answer that arrives after a call returns is not lost.

Tests and evals need a scripted person. `cad-server --opener PROGRAM` runs that program with the page URL instead of `open`. The flag is part of the server's command line, which the operator sets when they start the server. No MCP tool can change it. An agent that can edit the MCP client's configuration can set the flag, but that agent can already read the store key, so the flag adds no new reach.

A newer proposal ends the open page for the older one. A confirmed proposal stays in force until the person confirms a newer one, so the agent cannot weaken what the person confirmed by proposing again.

## Amendment (2026-11-08)

SPEC says that everything waiting on the person in a project appears on one page, and that one visit answers it. PR #78 builds that page, and this amendment records three facts that changed. The decision does not change. The page is local, its token never reaches the agent, only the page's request handler writes the answer, and status is derived from signed records.

The tool is `ask_to_confirm(project_id)`. It replaces `confirm_requirements`. It opens the project's page, waits as `confirm_requirements` did, and reports each brief's newest proposal as `waiting`, `confirmed` or `declined`. It cannot answer.

The answer is a `PageAnswer` in the project store. It is no longer a decision record in the brief store. The handler writes one signed record per answered page to a zero-padded numbered file such as `~/.cad/projects/<project_id>/answers/0001.signed`, and the projects key, `~/.cad/projects.key`, signs it under ADR-0003's scheme. A decision record that the brief store holds from before this change is still read, and it wins over a page answer for the same proposal. Nothing rewrites it.

One click answers the whole page. The page lists every brief in the project whose newest proposal is still waiting, and later kinds of item join the same page. The person can tick Decline on single items, and the same click confirms the rest and declines those. The page snapshots its items when it opens. If an item is added or replaced after that, the page records nothing and closes, and the next `ask_to_confirm` opens a new page.

The guarantee and its gap are unchanged. An agent that reaches the server only through MCP cannot answer the page. An agent with shell tools that runs as the same user can read the projects key, as it could read the brief store's key before.

The operator approved this amendment on 2026-11-08.

## Amendment (2026-11-08): the hosted web app

Phase 4 hosts the server, and a hosted server cannot open a page on the person's 127.0.0.1. Putting a link in a tool result would let the agent open the page and confirm for itself (#47). This amendment records how a person confirms on the hosted server. It follows the operator's direction in #47 of 2026-11-07, and the operator's approval of URL-mode elicitation on 2026-11-08. The design is in `docs/design/phase-4.md` §2.4 and §2.7.

The rules of this ADR do not change. Only the person can answer. Only the page's request handler writes the answer. The projects key signs each `PageAnswer`, and status is derived from signed records.

### The person presses Confirm in the signed-in web app

The page becomes part of the web app, and only a signed-in person can press Confirm. The page keeps its items, its sections and its one-click answer. Its form carries a CSRF token bound to the page's snapshot, so an item added after the page opened still records nothing. `PageAnswer` gains the account and the session that answered. The page checks that the signed-in account is the account of the agent that asked. The stdlib page server, the in-memory `Desk` and the one-time token in the URL are deleted.

People sign in through Clerk with Google. Clerk is the authorization server, and our server only verifies the tokens that Clerk issues. The web routes accept only a Clerk session token. The `/mcp` endpoint accepts only a Clerk OAuth access token. Answering the page is a person-only operation with no MCP tool, so no agent token can answer it.

### An outside client opens the page through URL-mode elicitation

A person in Claude Code, or in any MCP client, signs in once with MCP authorization through Clerk. Nobody pastes a token. When `ask_to_confirm` runs and the client declared `elicitation.url`, the server asks the client to open the page's address, `https://<app>/projects/<pid>/confirm`. The MCP spec requires the client to show the full URL, ask the person's consent and open the page so that neither the client nor the model can read it. `ask_to_confirm` then waits at most 20 seconds for a signed `PageAnswer`, as it does today, and returns `waiting` if none arrives.

The URL carries no token and no answer. It is the page's ordinary address, and it grants nothing without the person's session cookie. The server never treats the client's `accept`, `decline` or `cancel` as an answer. `accept` means only that the person agreed to open the page. Whatever the client returns, the tool reports what the signed records say.

This ADR rejected form-mode elicitation because an `Elicitation` hook could answer the form, and the form's answer was the decision. In URL mode a hook can only accept or decline opening a page. The decision still comes only from the page. On 2026-11-08, with Claude Code 2.1.287, mcp 2.3.0 and the 2026-07-28 protocol, an interactive session showed the full URL with Accept and Decline. The URL was not in the model's transcript. `claude -p` returned `cancel`. An `Elicitation` hook did receive the URL, which is harmless because the URL grants nothing.

### Every other client gets "waiting in the web app"

A client that does not declare `elicitation.url`, a headless run, and a person who declines all get the same result. `ask_to_confirm` returns `waiting in the web app`, with no link and no token. The person opens the web app, where the page lists every waiting item in the project. The agent's next call reads the signed answer.

Onshape users confirm in the web app too. The Onshape Confirm button from #47 needs the Onshape extension panel, which SPEC lists as out of scope.

### Local development keeps a scripted person

Local development and the eval driver run the same web app on 127.0.0.1 with no Clerk. A local verifier takes Clerk's place and produces the same kind of signed-in person and agent token, so nothing past the sign-in check knows which one ran. The server uses the local verifier only when it listens on 127.0.0.1 and has no Clerk keys. `--opener PROGRAM` still gives the scripted person its sign-in link and the page URL, and no MCP tool can change it.

### The guarantee and its gap

An agent that reaches the server only through MCP cannot answer the page. No tool result carries the page's URL or a token. The client and its hooks do receive the URL, so the sentence "No tool returns or logs the token, the port or the URL" now covers tool results and server logs, not the client.

A process that can drive the person's signed-in browser could still press Confirm. This is the gap that ADR-0003 and this ADR already accept, and the operator accepted it again for the web app in #47. The operator declined a passkey touch for each confirmation on 2026-11-08.

The title of this ADR records the phase 2 decision. The file keeps its name so that links to it stay valid.

### Considered options

- **A link to the page in the tool result.** Rejected in #47. The agent could open the link.
- **A notification to the signed-in account, by email or in the app's inbox, with a link that requires sign-in.** It works with any client, but it is a scheme of our own. URL-mode elicitation is the standard way a remote MCP server sends a person to a page.
- **A passkey touch for each confirmation.** Declined by the operator on 2026-11-08. It closes the signed-in-browser gap, but it adds WebAuthn, enrolment and recovery for a gap the operator already accepted.

The operator approved this amendment on 2026-11-09.
