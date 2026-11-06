# Build variant

The `build_variant` tool runs agent-written build123d code in a sandbox container and returns the variant id, the build outcome and the tail of what the code printed. The container has no network, 2 GB of memory, 128 processes, a read-only root and a 60 second wall clock. The code must assign the final shape to `result`.

## Sub-features

- `build-built` returns `built` for a reference part and stores `result.brep` and `result.step`.
- `build-cached` returns the stored outcome and the same id for the same code, without a new container.
- `build-failed` returns `build_failed` with the error line and a traceback that starts in `/tmp/variant.py`.
- `build-no-result` returns `no_result` with a reason that names the contract.
- `build-timed-out` returns `timed_out` at the wall clock and leaves no container behind.
- `build-out-of-memory` returns `out_of_memory` for an allocation over 2 GB.
- `build-docker-down` returns an error result with one line that names the cause, for Docker stopped or not installed.
- `build-image-step` passes inside `uv run verify` as the `sandbox image` step.

## How to get to it (user POV)

- Run `uv run cad-call build_variant "$(jq -Rs '{code: .}' < <file>.py)"` in a terminal.
- Ask Claude Code, with the repo's `.mcp.json` loaded, to build a part with the `build_variant` tool.
- Run `uv run verify` and read the `sandbox image` line.

## Driving it with cad-call and claude_session.py

Preconditions:

- Docker Desktop runs. `docker version` prints a `Server` section.
- `uv run cad-sandbox build-image` prints `sandbox image cad-sandbox:<12 hex digits> is current` or `built sandbox image ...` and exits 0.

Variants live in `~/.cad/variants/<variant_id>/`, which holds `code.py` and `build.json`, plus `result.brep` and `result.step` when the outcome is `built`. A timed-out build is never stored.

- **Built.** Run `uv run cad-call build_variant "$(jq -Rs '{code: .}' < tests/sandbox/parts/plate.py)" > "$EVIDENCE/build-plate.json"`. Exit code `0`. `structuredContent.outcome` is `{"kind": "built"}`, and `~/.cad/variants/<variant_id>/result.step` exists. List that directory into the evidence.
- **Cached.** Run the same command again. `structuredContent` is the same, `variant_id` included. The call takes about a second, the time to start the server, against 3 to 4 seconds for a build.
- **Build failed.** Run `uv run cad-call build_variant '{"code": "from build123d import *\nresult = Box(1, 1, 1, align=Alignment.CENTER)\n"}'`. `outcome.kind` is `build_failed`, `outcome.error` is `NameError: name 'Alignment' is not defined`, and `outcome.traceback` names `Alignment`.
- **No result.** Run `uv run cad-call build_variant '{"code": "x = 1\n"}'`. `outcome` is `no_result` with the reason ``the code never assigned `result`; assign the final shape to `result` ``.
- **Timed out.** Run `uv run cad-call build_variant '{"code": "while True: pass\n"}'`. It returns after about 60 seconds with `outcome` equal to `{"kind": "timed_out", "limit_seconds": 60}`. Then run the cleanup check below, which must print nothing.
- **Docker missing.** Run `PATH=/usr/bin:/bin "$(command -v uv)" run cad-call build_variant '{"code": "result = 2\n"}'` with code that is not already stored. Exit code `1`, `isError` true, and one line of text: ``Error executing tool build_variant: docker is not installed: no `docker` command on PATH``.
- **Docker down.** With Docker Desktop stopped, call with code that is not already stored. Exit code `1`, `isError` true, and one line of text that starts `Error executing tool build_variant: docker is not reachable: `.
- **Claude Code call.** Run `uv run python .claude/skills/verify/scripts/claude_session.py "make a 20 mm cube with a 5 mm hole using build_variant" "$EVIDENCE/claude-build.json"`. Output has a `tool call: mcp__cad__build_variant` line, and the transcript shows the result with `"kind": "built"`.
- **Image step.** Run `uv run verify --only "sandbox image"`. Prints `ok   sandbox image` and exits 0.

## Cleanup

Each build removes its own container. After a run that was killed, list leftovers. The label marks only sandbox builds, so removing what it lists is safe.

```
docker ps -a --filter label=cad.sandbox=build
```

## Gotchas

- `cad-call` takes the arguments as one JSON object. `jq -Rs '{code: .}'` turns a file into that object, newlines and quotes included.
- The same code returns its stored outcome, so to measure a real build, change a comment in the code each time.
- With Docker down, a call for code that is already stored still succeeds, because the variant id needs no Docker.
- The MCP stdio client passes the server only `HOME`, `LOGNAME`, `PATH`, `SHELL`, `TERM` and `USER`. `DOCKER_HOST` set on `cad-call` never reaches the server, so the build uses the default Docker. `tests/sandbox/test_build.py` covers an unreachable daemon in-process.
- Editing `sandbox/Dockerfile` or `sandbox/requirements.txt` changes the image tag. The tool then answers ``sandbox image cad-sandbox:<tag> is missing; run `uv run cad-sandbox build-image` ``. Editing `src/cad/sandbox/runner.py` needs no rebuild, because the host sends the runner with each build.
