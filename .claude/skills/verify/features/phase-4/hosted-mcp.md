# Hosted MCP and accounts (NOT YET BUILT)

The server serves MCP over streamable HTTP at `/mcp` as well as stdio. A person in Claude Code signs in once with `claude mcp login cad` through Clerk's Google sign-in and consent screen, and every store is partitioned per account.

Design: `docs/design/phase-4.md` §2.4 (sign-in is MCP authorization, with Clerk as the authorization server), §2.6 (the route table, `/.well-known/oauth-protected-resource`, `POST /mcp`) and §2.7 (tenancy, the lease, `AccountMeter`). Unit 3 of §4.

## The check §4 gives unit 3

- Claude Code signs in with `claude mcp login` through Clerk's Google sign-in and consent screen.
- A Clerk session token on `/mcp` and a Clerk OAuth token on a web route each get 401.
- The unit records whether Clerk binds the token's audience to `/mcp` from the `resource` indicator, and the server checks the audience if it does.
- Tenant B gets `UnknownVariant` for tenant A's id.
- A second process on the same root refuses to start.
- A capped account is refused before any container starts.
- The app step reports the SHA over HTTP.

## Proof to write when it lands

- A recipe that starts the HTTP server locally and reads `/.well-known/oauth-protected-resource`, then sends each kind of token to the other kind's route with `curl` and records the 401s. Cost: free.
- A `cad-call` equivalent over HTTP, or `claude_session.py` with an HTTP entry in its MCP config, for one tool call per tenant. The tenant B call on tenant A's `variant_id` is the proof of isolation. `claude_session.py` builds its config from `.mcp.json`'s stdio entry today, so it needs an HTTP mode.
- The Clerk sign-in needs a real Google account and an interactive `claude mcp login`. It cannot run headless, so it stays an operator step with a screenshot. Say so in the report instead of substituting a local token.
- Update [Server info](../server-info.md): the `app` step reads the SHA over HTTP.

## Until then

The stdio recipes in [Server info](../server-info.md) and every other feature file stay the proof. There is no account, so `CAD_HOME` is the only isolation.
