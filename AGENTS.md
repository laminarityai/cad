# AGENTS.md

## Read first

- [SPEC.md](SPEC.md) says what we are building, for whom, and what "good" looks like.
- [GLOSSARY.md](GLOSSARY.md) defines the domain terms. Use them in code, tests and issues. Write "brief", not "spec" or "prompt", for what the user asks for.
- [docs/adr/](docs/adr/) records decisions that are hard to reverse. If your change contradicts one, say so in the PR instead of overriding it.

## Rules that protect the core claim

- The agent never decides whether a design is good. Checks do. Code that lets the agent change a check, its inputs, or a table it reads is a bug. The one exception is research ([ADR-0009](docs/adr/0009-an-unknown-value-is-researched-not-left-unknown.md)). The agent may fill a value that is unknown, by reading it from a page the server fetches, checks and cites. It may never replace a value that is already known, and every verdict that rests on research is labelled and counted apart.
- Numbers a check reads come from the parts and materials tables by exact key, never from vector search or model output. The one exception is research: when a value is unknown, it is researched ([ADR-0009](docs/adr/0009-an-unknown-value-is-researched-not-left-unknown.md)). The agent reads the value from a page and supplies it with its unit, the page's URL and the quote it read it from. The server fetches the page, checks that the quote is on it and that the number is written in the quote, cites the page, and the scorecard labels the value as researched. A requirement verdict compares a check's measure with a target a person confirmed.
- Agent-written Python runs only inside the sandbox.

## Conventions

- Python, fully typed. Strict type checking, the linter and the formatter run in pre-commit and in CI.
- One directory per feature. There is one obvious way to do each common thing; if you find two, delete one.
- Layers. The packages under `src/cad` sit in this order, top to bottom: `server` `verify` > `chat` > `operations` > `confirmations` `selections` `agent_measurements` > `auto` `accounts` > `scorecard` > `context_parts` > `variant_sets` > `research` > `briefs` > `projects` > `conversations` > `loads` `geometry` > `checks` > `variants` > `records` > `sandbox` > `tables` `knowledge` `web` > `errors`. A module imports only from layers below its own, and packages that share a layer do not import each other. The `layers` step checks this against the contract in `pyproject.toml`, and a new package fails it until you give the package a place. The contract's `ignore_imports` list counts the upward imports still left. It only shrinks: fix a new upward import instead of adding a line.
- Every `quote` in `tables/materials.yaml` is word for word in its cited datasheet. The `materials table` step checks it offline against `tables/datasheet_text/`. After you add or change a row, run `uv run python tools/regen_datasheet_text.py` and commit what it writes.
- A file-size lint rule fails the build when a file grows too large. Split the file instead of raising the limit.

## Verify your work

`uv run verify` runs the fast steps side by side in about 15 seconds: type checking, lint, the format check, the file-size check, the layers check, the materials table, the API types and the web lint, tests and build. `uv run verify --all` adds the slow steps: protocol models, the sandbox image, pytest and the app step. The app step starts the MCP server and fails unless `server_info` reports the SHA that `git rev-parse HEAD` gives.

CI runs every step on every PR in about 3 minutes, and CI is the gate. Locally, run the tests for what you changed and `uv run verify`, then push and watch CI. Do not run `--all` on this laptop. It takes about 10 minutes. Do one live walk per PR, at the end, and never wait on another agent's PR. [.claude/skills/run-tests/SKILL.md](.claude/skills/run-tests/SKILL.md) says how.

A change is done when CI passes and you have exercised the change through the MCP server or the app, not only through unit tests.

The `protocol models` step model-checks the job queue and the confirmation answer flow with TLC, so it needs Java 11 or later on PATH (macOS: `brew install --cask temurin`). It downloads the TLA+ tools to `~/.cache/cad` on its first run. See [.claude/skills/protocol-models/SKILL.md](.claude/skills/protocol-models/SKILL.md).

After `uv sync`, run `uvx pre-commit install` once. Each commit then runs the fast steps through `verify --only <step>`, and `protocol models` when its files change. The other slow steps run in CI.
