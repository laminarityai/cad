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
