# Hosted confirmation (NOT YET BUILT)

The confirmation page moves into the signed-in web app, rendered by Starlette. An outside MCP client opens it for the person through URL-mode elicitation. A headless client gets `waiting in the web app`. The stdlib page server, the URL token and the in-memory `Desk` are deleted.

Design: `docs/design/phase-4.md` §2.4 (amends ADR-0004, resolves #47). Unit 4 of §4. Unit 0, the ADR-0004 amendment, needs the operator's approval first.

## The check §4 gives unit 4

- Playwright signs in and confirms with one click.
- An agent-token POST, a POST with a stale snapshot, a replay and a session from another account are each refused and write no record.
- `ask_to_confirm` returns no link in its result.
- In an interactive Claude Code session the URL dialog opens the page, and under `claude -p` the tool returns `waiting in the web app`.
- The scripted-person eval still passes through `--opener` with the local verifier.

## Proof to write when it lands

- Keep `browser.py` as the person. With `--opener PROGRAM`, the server hands that program a local sign-in link instead of a page URL (§2.4, local dev), so `browser.py`'s drive gains a sign-in step before the page. Read the new page for its handles. Do not assume today's `Confirm` and `Decline all` names or the `Change to` fields survive.
- The refusals (agent token, stale snapshot, replay, another account) are HTTP probes. Move them from `human.py` to `curl` or a test, and record each status and that no answer file was written.
- `claude_session.py` under `claude -p`: `ask_to_confirm` returns `waiting in the web app`, and the transcript contains no URL.
- The interactive URL dialog cannot run headless. It stays an operator step with a screenshot.
- `human.py` parses today's HTML with regular expressions and posts to `/confirm/<token>`. Rewrite or delete it with this unit, and update `evals/briefs/session.py`, which points at it.

## Until then

[Briefs](../briefs.md) drives today's 127.0.0.1 page with `browser.py`.
