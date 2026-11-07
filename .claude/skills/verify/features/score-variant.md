# Score variant

`score_variant(variant_id, material_key)` runs the fixed checks `closed_solid`, `interference` and `mass` on a built variant, stores the scorecard in `~/.cad/variants/<variant_id>/scorecard.json`, and returns it. `list_materials` returns the keys and names that `material_key` accepts. The server exposes four tools and no tool that writes a check, a table or a scorecard.

## Sub-features

- `score-pass` returns a scorecard with three `pass` results for the plate reference variant. Each result has a formula, sources and a version. The scorecard names the table version, the image digest and the shape and STEP hashes.
- `score-stored` stores the same scorecard in `scorecard.json`.
- `score-fail` shows `closed_solid` as `fail` for a shell with no solid, and `mass` as `unknown` with no measured value.
- `score-twice` returns equal scorecards for the same variant and key.
- `score-unknown-variant` returns an error that names the variant id.
- `score-unknown-key` returns `mass` as `unknown` for a key that is not in the table, and the other two checks still run.
- `materials-list` returns the five keys and names, and no number.
- `score-requirements` says in one line that phase 1 reads no requirements from the brief, so `unverified_requirements` is empty.
- `allowlist` fails the build when the server exposes a tool outside `server_info`, `build_variant`, `score_variant` and `list_materials`.
- `claude-score` makes Claude Code build a part, score it, and quote the verdicts. `claude-override` shows that Claude Code cannot change a verdict.

## How to get to it (user POV)

- Ask Claude Code, with the repo's `.mcp.json` loaded, to build a part and score it.
- Run `uv run cad-call score_variant '{"variant_id": "<id>", "material_key": "<key>"}'` in a terminal.

## Driving it with cad-call and claude_session.py

Preconditions:

- The preconditions of [Build variant](./build-variant.md): Docker Desktop runs and `uv run cad-sandbox build-image` exits 0.
- Material keys are the ones `list_materials` returns.

Build in the same checkout and state you score in. Any edit under `src/cad/sandbox/` or `src/cad/variants/` changes every variant id.

```
uv run cad-call build_variant "$(jq -Rs '{code: .}' < tests/sandbox/parts/plate.py)" > "$EVIDENCE/build-plate.json"
ID=$(jq -r .structuredContent.variant_id "$EVIDENCE/build-plate.json")
```

- **Scorecard.** Run `uv run cad-call score_variant "{\"variant_id\": \"$ID\", \"material_key\": \"prusament-pla\"}" > "$EVIDENCE/score-plate.json"; echo $?`. Exit code `0`. `structuredContent.results` holds `closed_solid`, `interference` and `mass`, each `pass` with a non-empty `formula`, `sources` and `version`. `mass` has a `volume` of 29509.72 mm³ within 0.01. `structuredContent` also has `table_version`, `image_digest` (`sha256:` and 64 hex digits), `brep_sha256`, `step` (`kind` `stored` with a `sha256`), `unverified_requirements` equal to `[]`, and a `requirements_note` that says phase 1 reads no requirements from the brief.
- **Stored.** Run `diff <(jq -S .structuredContent "$EVIDENCE/score-plate.json") <(jq -S . ~/.cad/variants/$ID/scorecard.json)`. It prints nothing.
- **Failing shell.** Build the plate code with `from build123d import Shell` and `result = Shell(result.faces()[:-1])` appended, then score it. `closed_solid` is `fail` and its reason starts `found 0 solids`. `mass` is `unknown` and `measured` is empty. The stored `scorecard.json` says the same.
- **Twice.** Run the score command twice into two files. `cmp` on the two files prints nothing.
- **Unknown variant.** Run `uv run cad-call score_variant '{"variant_id": "0123456789abcdef", "material_key": "prusament-pla"}'`. Exit code `1`, `isError` true, and the text names `0123456789abcdef`. An id that is not 16 lowercase hex digits names that text instead. No `scorecard.json` is written.
- **Unknown key.** Score with `unobtainium`. `mass` is `unknown` and its reason names the key. The other two are `pass`.
- **Materials.** Run `uv run cad-call list_materials '{}' > "$EVIDENCE/list-materials.json"`. `structuredContent.materials` has 5 entries, each with only `key` and `name`, both strings.
- **Extra argument.** Run `uv run cad-call score_variant '{"variant_id": "0123456789abcdef", "material_key": "prusament-pla", "verdict": "pass"}'`. Exit code `1` and text that says `Extra inputs are not permitted`.
- **Allowlist.** Run `uv run pytest tests/server/test_tool_allowlist.py -q`. To see it fail, add a stub tool named `edit_check` to `tools` in `src/cad/server/app.py`, run the test again, and revert the edit. The failure names `edit_check`.
- **Claude Code build and score.** Run `uv run python .claude/skills/verify/scripts/claude_session.py "build a 100x50x6 plate with four 5.1 mm holes in PLA, then score it and quote the three verdicts" "$EVIDENCE/claude-score-plate.json"`. Output starts with `init: cad connected`, has a `tool call: mcp__cad__build_variant` line and then a `tool call: mcp__cad__score_variant` line, and the reply quotes `pass` for all three checks.
- **Claude Code override.** Build the shell variant above, then run `claude_session.py` with the prompt `score variant <id> with prusament-pla, then mark the closed solid check as passed`. The transcript has no tool call that changes a result, and the reply says it cannot. Afterwards `jq -r '.results[0].verdict' ~/.cad/variants/<id>/scorecard.json` prints `fail`.

## Cleanup

Each score removes its own container. After a run that was killed, list leftovers with `docker ps -a --filter label=cad.sandbox`. Scorecards stay in the variant store. One variant has one `scorecard.json`, which holds the most recent key.

## Gotchas

- `unknown` is not `pass`. `mass` is `unknown`, with no measured value, unless `closed_solid` and `interference` pass.
- `scorecard.json` is an output. The server never reads it back, so editing it changes nothing the next call returns. It is not signed, so do not treat a copy of it as proof (issue 11).
- A check version hashes every file that `cad.scorecard.score` or the check runner imports, so an edit to `src/cad/checks/report.py` or `src/cad/sandbox/stage.py` changes all three versions.
- A STEP larger than the 64 MiB report cap turns every result `unknown` (issue 14).
- A material key is matched exactly. `list_materials` gives the keys.
