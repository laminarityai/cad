# Web shell: viewer and live scorecards

A React app in `web/`, served by `src/cad/web/static.py` under `/app`. The signed-in person sees their projects, and for a brief the set of variants: one three-cad-viewer per member, and a scorecard that updates over server-sent events with no reload. A row that is waiting on a check is drawn as pending, with no verdict colour, until its result arrives.

Design: `docs/design/phase-4.md` §2.3 (tessellation), §2.6 (reads and streaming) and §3.

## Sub-features

- `web-shell-static` serves `web/dist` at `/app`. A path with a file extension is an asset or 404, any other path is the page, assets are cached for good and the page is not, `/` redirects to `/app/`, and an unbuilt app answers 503 with the command that builds it. `tests/web/` covers it.
- `web-shell-set` is the set view at `/app/projects/<project_id>/briefs/<brief_id>`. Three panes on a wide screen (waiting and scorecard, the viewers, the chat placeholder), and tabs (chat, model, scorecard) at 860 px and under.
- `web-shell-live-card` opens one `GET /v1/variants/<id>/events` stream per member and replaces the card on every event.
- `web-shell-follow` reads the set again two seconds after each read. A slot rebuilt to a new variant id moves its viewer and its stream to the new id with no reload, and its card shows every row of the revision before as pending, with that revision's numbers as `before:` text, until the new revision is scored. The events stream of the old id never hears of the rebuild, so only the set says it happened.
- `web-shell-waiting` is the Waiting on you panel. It reads `GET /v1/projects/<project_id>/waiting`, the same pending list the confirmation page and `ask_to_confirm` use, so it lists what every brief of the project waits on, each under its brief, and shows Review and confirm whenever anything waits. It is read with the set, so a proposal on another brief appears within two seconds with no reload.
- `web-shell-viewer` reads the mesh: the `view` route says whether it is stored, then the `geometry` route starts the tessellation and answers pending until it is done, and the immutable mesh URL serves a stored one.
- `web-shell-signed-out` shows a Sign in link to the confirmation page's sign-in (`web/src/api/confirmation.ts` is the one file that knows its URL) when a route answers 401.

The page's own tests are `npm run test` in `web/`: Vitest with fakes for the API, the event stream and the viewer. `uv run verify` runs `web lint`, `web test` and `web build`.

## How to get to it (person POV)

1. Build the page once: `cd web && npm ci && npm run build`.
2. Start a local server on its own port and data root, with the browser daemon as the person for confirmation pages:

   ```
   export RUN=$(mktemp -d)
   uv run python .claude/skills/verify/scripts/browser.py start $RUN
   uv run cad-http --port 8791 --root $RUN/home --opener $RUN/bin/open
   ```

3. Make a confirmed brief with three built variants, as an agent would, through `/mcp` with `cad-token agent <account> --url http://127.0.0.1:8791 --root $RUN/home` (`create_brief`, `propose_requirements`, `ask_to_confirm`, then `build_variant` three times with the `brief_id`). A `max_deflection` requirement makes the `fea` check run for a few seconds, which is the pending state. The material must have an elastic modulus and a Poisson's ratio in `tables/materials.yaml` (`polymaker-polylite-abs` has both) or `fea` is unknown at once.
4. Open the set view as that account: `uv run python .claude/skills/verify/scripts/browser.py web shot $RUN /projects/<project_id>/briefs/<brief_id> name --url http://127.0.0.1:8791 --account <account> [--width 400] [--scheme dark]`. It writes `$RUN/name.png` and `$RUN/name.aria.yml`.
5. Watch a card go from pending to done: start `browser.py web watch $RUN <path> name --url ... --account ... --material polymaker-polylite-abs` in the background, then call `score_variant` for each variant with that `material_key` and the `brief_id`. It writes `name-pending.png`, `name-done.png`, `name.sse.jsonl` (each event the page received) and `name.rows.jsonl`, and exits 1 when a pending row ever wore a verdict, when no row went from pending to a verdict, or when the page navigated.

6. Watch a slot follow a rebuild: open the set view, call `build_variant` with the `brief_id` and `"slot": <n>`, then `score_variant` on the new `variant_id`. Within two seconds the tile reads revision 2, a new events stream and geometry route for the new id appear in the network log, and the card turns from all pending to verdicts with no navigation.

## Checks

- Every pending row has only the `pending` tone: `watch` asserts it on every poll.
- The card changes without a navigation: `watch` records `framenavigated` after the first load and fails on any.
- The page signs in with the `__session` cookie that `cad-token person` mints, so the local drive needs no Clerk and no confirmation-page sign-in.

## Gotchas

- Headless Chromium needs `--enable-unsafe-swiftshader` for WebGL, which `web_drive.py` passes. Without it the viewers fail to start.
- The server leaves an empty `reads`, an empty `instance`, an empty `research`, an empty `not_verified` and a null `research_problem` out of a scorecard, and `web/src/api/types.ts` marks them optional. `web/src/api/snapshot.ts` puts them back at the one place an event enters the page, so the rows never test for a missing field.
- `view` never starts a tessellation. Only the `geometry` route does, so a page that read `view` alone would wait for ever.
- A browser allows six connections per host on HTTP/1.1, and the set view holds one event stream per member, five at most.
