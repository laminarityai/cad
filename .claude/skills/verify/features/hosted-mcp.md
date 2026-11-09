# Hosted MCP and accounts

`cad-http` serves MCP over streamable HTTP at `/mcp`, beside the stdio server. Clerk is the authorization server: `/mcp` takes a Clerk OAuth access token whose `aud` holds the `/mcp` URL, and a web route such as `GET /v1/variants/{variant_id}/scorecard` takes a Clerk session token. Each account gets its own stores under `<root>/accounts/<account>/`, one server leases a data root, and every container is charged to the caller's account against a daily cap before it starts.

With no Clerk configuration, `cad-http` trusts a local issuer instead, and only on a loopback address. `cad-token` mints its tokens. That is how every recipe here runs. Design: `docs/design/phase-4.md` §2.4, §2.6 and §2.7, unit 3 of §4.

## Sub-features

- `http-metadata` serves the Protected Resource Metadata (RFC 9728) at `/.well-known/oauth-protected-resource/mcp`, naming the issuer.
- `http-cross-route` refuses a session token on `/mcp` and an OAuth token on a web route, each with 401.
- `http-tenancy` gives tenant B `UnknownVariant` for tenant A's `variant_id`.
- `http-lease` refuses a second server on the same data root.
- `http-cap` refuses a capped account before any container starts.
- `http-app-step` reads the SHA over HTTP inside `uv run verify`.
- `http-clerk-login` signs Claude Code in with `claude mcp login cad` through Clerk. It needs a Clerk instance and a real Google account, so it is an operator step.

## How to get to it (user POV)

- An operator runs `uv run cad-http --root <data root>` and points a client at `http://127.0.0.1:8765/mcp`.
- Hosted, the operator sets `CLERK_PUBLISHABLE_KEY` and `CAD_PUBLIC_URL` (https), and a person runs `claude mcp login cad`.

## Driving it with curl and cad-call

Preconditions: `uv sync --frozen` has run. Set a data root and start the server in its own terminal. `--cap-seconds 0` makes the cap recipe refuse at once, and `--opener true` keeps confirmation pages off the screen.

```
export ROOT="$EVIDENCE/root"
uv run cad-http --root "$ROOT" --cap-seconds 0 --opener true
```

In another terminal, mint one token of each kind for two accounts:

```
export AGENT_A=$(uv run cad-token --root "$ROOT" agent user_alice)
export PERSON_A=$(uv run cad-token --root "$ROOT" person user_alice)
export AGENT_B=$(uv run cad-token --root "$ROOT" agent user_bob)
```

- **Metadata.** Run `curl -s http://127.0.0.1:8765/.well-known/oauth-protected-resource/mcp`. The JSON has `resource` `http://127.0.0.1:8765/mcp` and `authorization_servers` `["http://127.0.0.1/cad-local-issuer"]`. Hosted, it names the Clerk Frontend API URL.
- **No token.** Run `curl -s -i -X POST http://127.0.0.1:8765/mcp -d '{}'`. Status `401` and a `www-authenticate` header whose `resource_metadata` names the metadata URL.
- **Session token on /mcp.** Run `curl -s -i -X POST http://127.0.0.1:8765/mcp -H "authorization: Bearer $PERSON_A" -d '{}'`. Status `401`.
- **OAuth token on a web route.** Run `curl -s -i "http://127.0.0.1:8765/v1/variants/0123456789abcdef/scorecard?material_key=prusament-pla" -H "authorization: Bearer $AGENT_A"`. Status `401` and `{"error":"sign in: this route takes a Clerk session token"}`. The same request with `-H "cookie: __session=$PERSON_A"` gets past sign-in: status `400`, `UnknownVariant`.
- **Agent call.** Run `uv run cad-call --url http://127.0.0.1:8765/mcp --token "$AGENT_A" server_info '{}'`. Exit code `0` and the head SHA.
- **Tenancy.** Build a variant as user_alice on a server started without `--cap-seconds 0`, then run `uv run cad-call --url http://127.0.0.1:8765/mcp --token "$AGENT_B" scorecard '{"variant_id": "<alice variant_id>", "material_key": "prusament-pla"}'`. Exit code `1` and `UnknownVariant`. `tests/server/test_hosted.py` proves the same without Docker.
- **Lease.** While the server runs, run `uv run cad-http --root "$ROOT" --port 8766`. Exit code `1` and `cad-http: <root>/accounts/lease is held by pid <pid>: one server serves a data root, so this one did not start`.
- **Cap.** Count `docker ps -aq --filter label=cad.sandbox`, then run `uv run cad-call --url http://127.0.0.1:8765/mcp --token "$AGENT_A" build_variant '{"code": "result = None"}'`. Exit code `1` and `the account limit is reached: 0 of 0 container-seconds used today, so nothing was started; it resets at <tomorrow> 00:00 UTC`. The container count is unchanged.
- **App step.** Run `uv run verify --only app`. Prints `server_info over stdio sha <head>` and `server_info over http sha <head>`.

## Gotchas

- The metadata path is the SDK's path-suffixed form, `/.well-known/oauth-protected-resource/mcp`, as RFC 9728 §3.1 gives for a resource at `/mcp`.
- Without `CLERK_PUBLISHABLE_KEY`, `cad-http --host 0.0.0.0` exits and names the two variables. The local issuer's key is `<root>/local-issuer.pem`.
- The Clerk docs say Clerk turns on `aud` when the first MCP server is added, and that the server must check that `aud` includes the `/mcp` URL. They do not say Clerk takes `aud` from the RFC 8707 `resource` parameter. The verifier requires `aud` to include the `/mcp` URL either way. Record what the live login shows when a Clerk instance exists.
