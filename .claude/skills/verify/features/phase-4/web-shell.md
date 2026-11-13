# Web shell: viewer and live scorecards

A React app in `web/`, served by `src/cad/web/static.py` under `/app`. `web/src/App.tsx` has three routes. `/app/projects/<project_id>` is the project workspace. `/app/new` is the chat start. Any other path opens the newest project, or the chat start when there is none. The workspace shows each option of a brief in a three-cad-viewer, with its scorecard as one line per check. A check that has not finished is drawn as `Checking`, with no verdict colour, until its result arrives. The chat half of the workspace is in [Chat](chat.md).

Design: `docs/design/phase-4.md` §2.3 (tessellation), §2.6 (reads and streaming) and §3.

## Sub-features

- `web-shell-static` serves `web/dist` at `/app`. A path with a file extension is an asset or 404, any other path is the page, assets are cached for good and the page is not, `/` serves `landing.html` with no session, `/app` redirects to `/app/`, and an unbuilt app or landing page answers 503 with the command that builds it. `tests/web/` covers it.
- `web-shell-workspace` is `/app/projects/<project_id>` (`web/src/features/workspace/`). Three panes on a wide screen (Explorer, Design and Chat), and the same three as tabs in the `Panes` navigation at 860 px and under.
- `web-shell-live-card` polls `GET /v1/variants/<id>/scorecard` every 1.5 s for each option shown (`web/src/features/workspace/cards.ts`) and replaces the card on each read. It polls instead of streaming, because a browser holds six connections per host and the chat stream and the meshes need theirs. Each check line carries `data-line` with its status, `running` while it is checking.
- `web-shell-follow` reads the project, its confirmation, its conversation and each confirmed brief's set again every 3 s, and after each chat turn that changes the page (`web/src/features/workspace/Workspace.tsx`). A slot rebuilt to a new variant id moves its viewer and its card to the new id with no reload.
- `web-shell-viewer` reads the mesh (`web/src/features/viewer/useMesh.ts`): the `view` route says whether it is stored, then the `geometry` route starts the tessellation and answers pending until it is done, and the immutable mesh URL serves a stored one.
- `web-shell-one-way` has one way to call the server and one way to load: every request goes through `web/src/api/client.ts` (`request`, typed by the generated `paths`, and `openStream`; the chat's calls are `web/src/api/chat.ts`), and every GET the page shows loads through `useResource` or `useResources` (`web/src/state/resource.ts`). `npm run lint` in `web/` fails on `fetch`, `EventSource` or a `/v1/` path outside `web/src/api/`.
- `web-shell-signed-out` shows a Sign in link to the confirmation page's sign-in (`web/src/api/confirmation.ts` is the one file that knows its URL) when a route answers 401.

The page's own tests are `npm run test` in `web/`: Vitest with fakes for the API, the chat stream and the viewer. `uv run verify` runs `web lint`, `web test` and `web build`.

## How to get to it (person POV)

1. Build the page once: `cd web && npm ci && npm run build`.
2. Start a local server on its own port and data root, with the browser daemon as the person for confirmation pages:

   ```
   export RUN=$(mktemp -d)
   uv run python .claude/skills/verify/scripts/browser.py start $RUN
   uv run cad-http --port 8791 --root $RUN/home --opener $RUN/bin/open
   ```

3. Make a confirmed brief with three built variants, as an agent would, through `/mcp` with `cad-token agent <account> --url http://127.0.0.1:8791 --root $RUN/home` (`create_brief`, `propose_requirements`, `ask_to_confirm`, then `build_variant` three times with the `brief_id`). A `max_deflection` requirement makes the `fea` check run for a few seconds, which is the checking state. The material must have an elastic modulus and a Poisson's ratio in `tables/materials.yaml` (`polymaker-polylite-abs` has both) or `fea` is unknown at once.
4. Open the workspace as that account: `uv run python .claude/skills/verify/scripts/browser.py web shot $RUN /projects/<project_id> name --url http://127.0.0.1:8791 --account <account> [--width 400 --tab Design] [--scheme dark] [--slot 2]`. It waits for the slot tabs and the viewers, opens option `--slot` when it is given, and writes `$RUN/name.png` and `$RUN/name.aria.yml`.
5. Watch a card go from checking to done: start `uv run python .claude/skills/verify/scripts/browser.py web watch $RUN /projects/<project_id> watch --url http://127.0.0.1:8791 --account <account> --seconds 240` in the background, then call `score_variant` for each variant with that `material_key` and the `brief_id`. `watch` follows the `[data-line]` check lines of the option on screen, writes `watch-running.png`, `watch-done.png` and `watch.lines.jsonl`, and prints the lines it saw running and settled. It exits 0 when a line went from `running` to a verdict, no running line showed anything but `Checking`, and the page did not navigate. Here the `max_deflection` line was `Checking` for about 78 s and then `Pass`.

## Checks

- `npm run test` in `web/` (`features/workspace/workspace.test.tsx`) covers the workspace with fake services.
- The page signs in with the `__session` cookie that `cad-token person` mints, so the local drive needs no Clerk and no confirmation-page sign-in.

## Gotchas

- Headless Chromium needs `--enable-unsafe-swiftshader` for WebGL, which `web_drive.py` passes. Without it the viewers fail to start.
- The server leaves an empty `reads`, an empty `instance`, an empty `research`, an empty `not_verified` and a null `research_problem` out of a scorecard, and `web/src/api/types.ts` marks them optional. `restore` in `web/src/api/snapshot.ts` puts them back where a scorecard enters the page, so the check lines never test for a missing field.
- `view` never starts a tessellation. Only the `geometry` route does, so a page that read `view` alone would wait for ever.
