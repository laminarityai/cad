# AGENTS.md

## Read first

- [SPEC.md](SPEC.md) says what we are building, for whom, and what "good" looks like.
- [GLOSSARY.md](GLOSSARY.md) defines the domain terms. Use them in code, tests and issues. Write "brief", not "spec" or "prompt", for what the user asks for.
- [docs/adr/](docs/adr/) records decisions that are hard to reverse. If your change contradicts one, say so in the PR instead of overriding it.

## Rules that protect the core claim

- The agent never decides whether a design is good. Checks do. Code that lets the agent change a check, its inputs, or a table it reads is a bug.
- Numbers a check reads come from the parts and materials tables by exact key, never from vector search or model output.
- Agent-written Python runs only inside the sandbox.

## Conventions

- Python, fully typed. Strict type checking, the linter and the formatter run in pre-commit and in CI.
- One directory per feature. There is one obvious way to do each common thing; if you find two, delete one.
- A file-size lint rule fails the build when a file grows too large. Split the file instead of raising the limit.

## Verify your work

Phase 1 of the build plan adds a single `verify` command that runs type checking, lint, tests, and the app itself. A change is done when `verify` passes and you have exercised the change through the MCP server or the app, not only through unit tests.

Until `verify` exists, the only code in the repo is the throwaway bake-off on branch `proto/kernel-bakeoff`.
