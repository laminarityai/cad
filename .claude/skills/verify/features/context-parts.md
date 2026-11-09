# Context parts

A context part is a part the new part must fit with. Today it is a variant the agent built. `propose_context_part(brief_id, quote, name, variant_id)` opens the stored variant, has the analysis container read its BREP, and stores a signed record with the part's facts: the number of solids, the volume in mm^3 and the bounding box in the part's own frame. It returns `part_id` (`part-` and the first 16 hex digits of the BREP's SHA-256), `status` and `facts`. The person confirms the part on the `ask_to_confirm` page, in a section titled "A part your design must fit with", and the same click confirms the requirements. `ask_to_confirm` then lists one item per part, `{kind: "context_part", part_id, name, outcome, box_min, box_max, note}`, after the requirements items. No check reads a context part yet. The fit check is the next delivery step in `docs/design/context-parts.md`.

Records live in `~/.cad/projects/<project_id>/context_parts/<n>.signed`, signed by the projects key. The geometry is `~/.cad/projects/<project_id>/parts/<brep_sha256>.brep`.

## Sub-features

- `part-live` makes Claude Code build a plate, store a brief that names it, propose requirements and the plate as a context part, and call `ask_to_confirm` while the scripted person confirms.
- `part-idempotent` proposes the same BREP twice. One record is stored and one item is listed.
- `part-declined` declines the part on the page. Proposing it again stores a second record that waits on a new page.
- `part-refusals` shows a quote that is not in the brief (`BadContextPart`), an unknown variant (`UnknownVariant`), a variant whose build failed (`NotBuilt`) and a shape the container refuses (`BadContextPart: variant <id> cannot be a context part: <reason>`). Nothing is stored for any of them.

## How to get to it (user POV)

Tell Claude Code that the new part must fit with a part it built earlier. The confirmation page shows that part, with the brief words it came from, its box and volume, and what the fit check will decide against it.

## Driving it

Preconditions are those of [Briefs](./briefs.md) and [Build variant](./build-variant.md): Docker runs and both sandbox images are current, because the analysis container reads the part.

- **Live.** Run `CAD_HUMAN_LOG="$EVIDENCE/human-part.jsonl" uv run python .claude/skills/verify/scripts/claude_session.py --opener "$PWD/.claude/skills/verify/scripts/human.py" "<prompt>" "$EVIDENCE/claude-context-part.json"`. The prompt gives the code of `tests/sandbox/parts/plate.py` for `build_variant` with no brief_id, then the brief "A cover that sits on top of the mounting plate, at least 0.5 mm clear of it, under 80 g", and asks for `create_brief`, `propose_requirements`, `propose_context_part` for the plate, then one `ask_to_confirm`. The transcript has those calls in that order. `propose_context_part` returns `status` `waiting` and a box from (-50, -25, -3) to (50, 25, 3). `human-part.jsonl` has one `page` entry with two sections: the requirements, then `Item 2. A part your design must fit with` whose headline reads `Mounting plate, from variant <id>: a box of 100 by 50 by 6 mm, volume 29509.7 mm³` and whose quote is in the brief. `ask_to_confirm` returns `answered`, and both items are `confirmed`. Under the printed server home, `projects/<project_id>/` holds `answers/0001.signed`, `context_parts/0001.signed` and `parts/<sha256>.brep`.
- **Idempotent, declined, refusals and tampering.** These run without Docker through `tests/context_parts/`, with a fake ingest that the `s` fixture in `tests/conftest.py` passes to `build_server`: `uv run python -m pytest -q tests/context_parts tests/confirmations/test_no_tool_decides.py`.

## Gotchas

- The part is identified by its BREP, not by its variant id. Two variants with the same geometry are the same part, and a rebuild under a new sandbox image keeps the part.
- A part has no number to change. A forged `edit-<i>-<row>` field for a part's item gets 400 and records nothing.
- A record or BREP edited on disk makes every call that reads the project's parts fail with `TamperedProject`. Only the operator can fix it, by deleting the project's context parts.
