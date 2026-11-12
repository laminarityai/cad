# AGENTS.md

## Read first

- [SPEC.md](SPEC.md) says what we are building, for whom, and what "good" looks like.
- [GLOSSARY.md](GLOSSARY.md) defines the domain terms. Use them in code, tests and issues. Write "brief", not "spec" or "prompt", for what the user asks for.
- [docs/adr/](docs/adr/) records decisions that are hard to reverse. If your change contradicts one, say so in the PR instead of overriding it.

## Rules that protect the core claim

- The agent never decides whether a design is good. Checks do. Code that lets the agent change a check, its inputs, or a table it reads is a bug. The one exception is research ([ADR-0009](docs/adr/0009-an-unknown-value-is-researched-not-left-unknown.md)). The agent may fill a value that is unknown, by reading it from a web page or PDF that the server fetches, checks and cites. It may never replace a value that is already known, and every verdict that rests on research is labelled and counted apart. An assumption is not a second exception ([ADR-0004](docs/adr/0004-a-person-confirms-on-a-local-page-not-through-mcp-elicitation.md)). A check may measure under a load the agent assumed, and no verdict ever rests on it.
- Numbers a check reads come from the parts and materials tables by exact key, never from vector search or model output. The one exception is research: when a value is unknown, it is researched ([ADR-0009](docs/adr/0009-an-unknown-value-is-researched-not-left-unknown.md)). The agent reads the value from a page and supplies it with its unit, the page's URL and the quote it read it from. The server fetches the page, checks that the quote is on it and that the number is written in the quote, cites the page, and the scorecard labels the value as researched. A requirement verdict compares a check's measure with a target a person confirmed.
- Agent-written Python runs only inside the sandbox.

## Conventions

- Python, fully typed. Strict type checking, the linter and the formatter run in pre-commit and in CI.
- One directory per feature. There is one obvious way to do each common thing; if you find two, delete one.
- Layers. The packages under `src/cad` sit in this order, top to bottom: `server` `verify` > `chat` > `operations` > `confirmations` `selections` `agent_measurements` > `auto` `accounts` > `scorecard` > `context_parts` > `variant_sets` > `research` > `briefs` > `projects` > `conversations` > `loads` `geometry` > `checks` > `variants` > `records` > `sandbox` > `tables` `knowledge` `web` > `errors` `data_root` `frozen`. A module imports only from layers below its own, and packages that share a layer do not import each other. The `layers` step checks this against the contract in `pyproject.toml`, and a new package fails it until you give the package a place. The contract's `ignore_imports` list counts the upward imports still left. It only shrinks: fix a new upward import instead of adding a line.
- Every `quote` in `tables/materials.yaml` is word for word in its cited datasheet. The `materials table` step checks it offline against `tables/datasheet_text/`. After you add or change a row, run `uv run python tools/regen_datasheet_text.py` and commit what it writes.
- `tables/tolerances.yaml` is read by exact class key (`H7`, `ISO 2768-m`) and the size range that holds the hole's diameter. Each row's `quote` and `range_quote` are checked and regenerated the same way. ASME B4.1 and Y14.5 are not in it.
- `tables/fasteners.yaml` is read by exact metric size (`M5`), and the `holes` requirement judges against it. The same step checks each row's `quote` against `tables/datasheet_text/`, and the same command regenerates the text.
- A file-size lint rule fails the build when a file grows too large. Split the file instead of raising the limit.

## Adding things

Each row is the one way. Start in the named file and copy the entry beside yours. The step or test in the last column fails when the addition is done another way or left half done.

| To add | Start in | Checked by |
| --- | --- | --- |
| An MCP tool, or a `/v1` route for the page | An `operation(...)` in the feature's module under `src/cad/operations/`. `registry.py` collects them, and its `ROUTES` gives a person-facing one its path. | `api types`, `tests/operations/test_openapi.py` |
| A route that is not an operation | `HAND_DESCRIBED` in `src/cad/operations/outside.py` | `tests/operations/test_openapi.py` |
| A check | A module in `src/cad/checks/container/` with `ID`, `SOURCES`, and `run`, listed in `suite.py` `CHECKS`. Standard library only: it runs inside the sandbox. | `tests/checks/test_versions.py`, `tests/checks/test_logic.py` |
| A requirement kind | A model in `src/cad/briefs/model.py`, added to `Target` | `basedpyright`, at every `assert_never` |
| A fastener size | A row in `tables/fasteners.yaml`, then `uv run python tools/regen_datasheet_text.py` | `materials table`, `tests/tables/test_fasteners.py` |
| A tolerance class | A class in `tables/tolerances.yaml` with its standard in `origin`, then `uv run python tools/regen_datasheet_text.py` | `materials table`, `tests/tables/test_tolerances.py` |
| A material field | `FIELDS` in `src/cad/tables/fields.py` | `tests/tables/test_fields.py`, `materials table` |
| An error a tool or a route answers with | Derive from `Refused`, `NotFound`, or `Unavailable` in `src/cad/errors.py` | `tests/operations/test_error_mapping.py` |
| A record model | Derive from `Frozen` in `src/cad/frozen.py` | `tests/test_frozen.py` |
| A quantity field | `Length`, `Force`, `Mass`, or `AnyQuantity` from `src/cad/checks/units.py` | |
| A stored file | `replace` in `src/cad/records/files.py`. A file the agent must not forge goes through `records/signed.py`. | |
| Text the agent is told | A named constant in `src/cad/operations/guidance.py` | |
| A package under `src/cad` | A place in the `layers` contract in `pyproject.toml` | `layers` |
| A server read in the web app | `useResource` in `web/src/state/resource.ts`, calling `request` in `web/src/api/client.ts` | `web lint` |
| A web widget (tabs, expander, tooltip, menu, toast) | A wrapper in `web/src/components/ui/`. It is the one place that imports base-ui (`@base-ui/react`) or Sonner. | `web lint` (`no-restricted-imports`) |
| A web feature | A folder under `web/src/features/` | |
| A test | `tests/<feature>/`, mirroring `src/cad/<feature>/`. Shared helpers go in `tests/support/`, and shared fixtures in `tests/conftest.py`. | `tests/test_support_imports.py` |

## Verify your work

`uv run verify` runs the fast steps side by side in about 12 seconds, and skips one whose inputs match its last pass (`--no-cache` runs them all): type checking, lint, the format check, the file-size check, the layers check, the materials table, the API types and the web lint, tests and build. `uv run verify --all` adds the slow steps: protocol models, the sandbox image, the reader image, pytest and the app step. The app step starts the MCP server and fails unless `server_info` reports the SHA that `git rev-parse HEAD` gives.

CI runs every step on every PR in about 3 minutes, and CI is the gate. Locally, run the tests for what you changed, with `-m "not docker"` while you iterate, and `uv run verify`, then push and watch CI. Do not run `--all` on this laptop. It takes about 10 minutes. Do one live walk per PR, at the end, and never wait on another agent's PR. [.claude/skills/run-tests/SKILL.md](.claude/skills/run-tests/SKILL.md) says how.

A change is done when CI passes and you have exercised the change through the MCP server or the app, not only through unit tests.

The `protocol models` step model-checks the job queue and the confirmation answer flow with TLC, so it needs Java 11 or later on PATH (macOS: `brew install --cask temurin`). It downloads the TLA+ tools to `~/.cache/cad` on its first run. See [.claude/skills/protocol-models/SKILL.md](.claude/skills/protocol-models/SKILL.md).

After `uv sync`, run `uvx pre-commit install` once. Each commit then runs the fast steps through `verify --only <step>`, and `protocol models` when a file its coverage block lists changes. The other slow steps run in CI.
