# Web shell: viewer and live scorecards (NOT YET BUILT)

A React app (`web/`) served by `src/cad/web/`. The person sees each variant of a set in three-cad-viewer and its scorecard, which updates over SSE as check jobs finish, with no reload. Each SSE event carries a whole `ScorecardSnapshot`. The mesh comes from the person-only `geometry` operation, which unit 5 built: see [Geometry](../geometry.md).

Design: `docs/design/phase-4.md` §2.3 (tessellation as an analysis-image job), §2.6 (reads and streaming, the route table, `GET /v1/variants/{vid}/events`, `GET /v1/geometry/{version}/{brep_sha256}.json`) and §3 (`src/cad/web/`, `src/cad/geometry/`, `web/`). Units 5 and 6 of §4. Unit 2 deletes `scorecard.json`, so the [Score variant](../score-variant.md) recipes that diff it change then.

## The checks §4 gives units 5 and 6

- Unit 5, geometry: the mesh volume is within 0.5% of the mass check's volume, and a bake-off part renders in three-cad-viewer (screenshot attached).
- Unit 6, web shell: Playwright watches a card go from pending to done without a reload, and no pending row ever has a verdict colour.

## Proof to write when it lands

- Geometry: mount the `geometry` operation as a route, and point [Geometry](../geometry.md)'s script at the route in place of the registry call.
- Web shell: a Playwright recipe that opens the set view, triggers a score, and waits for the card's rows to change from pending to a verdict on the same page, with no navigation. Record the before and after screenshots and the SSE events from the network log. Assert from the page that no pending row has a verdict colour. Cost: docker + browser.
- Reuse `browser.py`'s one-Chromium-per-run daemon rather than launching a browser per recipe. Add a drive for the web app next to the confirmation page drive.
- Write the selectors from the built app's ARIA roles and names. None exist yet.

## Until then

Scorecards are proved through `cad-call` and `claude_session.py` in [Score variant](../score-variant.md). Nothing renders geometry.
