# Download

`export(variant_id, brief_id, format)` and `export_file(version, brep_sha256, format)` are person-only operations in `src/cad/operations/exports.py`. A person downloads the option on screen as STEP, STL or 3MF from the Download menu in the Stage toolbar. The analysis image writes the three files from the BREP that the checks measured, in the background, once per BREP. The files are stored under `$CAD_HOME/.cad/exports/<version>/<brep_sha256>.{step,stl,3mf}`, with a `.json` record written last. The version names the analysis image and the export sources. It has no MCP tool, because an agent has no use for a file. The server's route sends it as an attachment, named `{brief name}-{option label}-rev{n}.{ext}`.

## Sub-features

- `pending` returns `preparing` while the job runs, and starts no second job for the same BREP. The menu shows `Preparing…`.
- `ready` returns a URL and a file name. The URL is content addressed, so it is immutable and answers 304 to its ETag.
- `stored` reads a stored export, or a stored failure for a BREP the kernel cannot read, with no job. A timeout is not stored.
- `step-is-the-card-step` serves a STEP whose SHA-256 is the `step` hash on the scorecard.
- `stl-box` is a binary STL whose bounding box is the `extents` check's numbers, in millimetres.
- `3mf-unit` is a 3MF whose model says `unit="millimeter"`, with the same box.
- `same-bytes` gives the same files when the same BREP is exported again.
- `checks-untouched` leaves every check version, the mesh version and every variant id as they were.
- `cost` charges a first export as one `check` container through the usual meter. A stored file costs nothing.
- `not-a-tool` is missing from the MCP tool list, because its audience is `PERSON`.

## How to get to it (user POV)

Open a project with a built option. The Stage toolbar has a `Download` button. Pick STEP, STL or 3MF. The button reads `Preparing…` until the file is ready, and the browser then saves it. The file is the revision on screen. A failed export shows its reason under the button.

## Driving it with browser.py

Preconditions: a running local `cad-http` with the opener of `browser.py start`, a built web app (`uv run python tools/web.py build`), and a confirmed brief with a built, scored option for the account ([Web shell](./phase-4/web-shell.md) builds one).

```
uv run python .claude/skills/verify/scripts/browser.py web download "$RUN" "$EVIDENCE/download" --url http://127.0.0.1:<port> --account <account>
```

The script opens the account's newest project, opens the Download menu, writes `download-menu.png`, then downloads the three formats through the menu. It reads the scorecard of that revision and exits 1 at the first claim that fails. It prints one JSON line with the three file names and sizes, the `extents` numbers, the STL and 3MF boxes, the 3MF unit and both STEP hashes. Cost: docker for the first export of each BREP, and one Chromium.

Free proofs: `tests/geometry/test_exports.py` (pending, stored, failed, the record written last, one charge, the version apart from the mesh version), `tests/operations/test_download_adapter.py` and `tests/operations/test_download.py` (the attachment header, the immutable route, the 404 cases, the file name), and `web/src/features/workspace/workspace.test.tsx` (the menu). Docker: `tests/geometry/test_export_container.py` (the real image: the STEP and its hash, the STL box and edges, the 3MF unit, the same bytes twice, a garbage BREP).

## Evidence

Look at `download-menu.png`: the menu lists STEP, STL and 3MF under the button, over the shaded part. The JSON line has equal STEP hashes, an STL and 3MF box equal to `extents`, and `"threemf_unit": "millimeter"`. The run's `cad-http` log holds the local sign-in token, so keep it out of anything shared.
