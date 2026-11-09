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
- A file-size lint rule fails the build when a file grows too large. Split the file instead of raising the limit.

## Verify your work

`uv run verify` is the single command that runs type checking, lint, the format check, the file-size check, tests and the app step, and exits non-zero on the first failure. The app step starts the MCP server and fails unless `server_info` reports the SHA that `git rev-parse HEAD` gives. A change is done when `verify` passes and you have exercised the change through the MCP server or the app, not only through unit tests.

After `uv sync`, run `uvx pre-commit install` once. Each commit then runs the same steps through `verify --only <step>`.
