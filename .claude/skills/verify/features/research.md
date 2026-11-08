# Research

ADR-0009: a material value the table lacks is researched, not left unknown. When a check reads a material field the table marks `unknown`, the result's `reads` has a `missing` entry and the scorecard's `research` holds a request: brief id, key, field, unit and the accepted range. `submit_research(brief_id, key, field, url, quote)` never takes a number. The server fetches the page (https on port 443 only, public addresses only, checked again after every redirect, 4 MiB and 15 s caps, no credentials), checks that the quote is on the page word for word, and reads the value with the quote reader in `cad.sources`. An accepted value is a signed record in `~/.cad/projects/<project_id>/research/<n>.signed` and fills the field for that project only. It never replaces a value git cites. A result that reads it has a `researched` read with the url, quote and page hash, and a requirement it decides has `basis` `researched`.

## Sub-features

- `research-request` makes `score_variant` with a brief return a `research` request for each missing material value a check read. Missing geometry never asks.
- `research-accept` stores a value read from a quote on a fetched page, and the next `score_variant` reads it, with table version `<git>+<project_id>@r<n>`.
- `research-refuse` refuses a quote that is not on the page, a quote the reader refuses, a failed or guarded fetch, and a value that breaks the table's rules. Each gives a reason and a new request. A field git cites is refused with no request.

## Driving it with cad-call

Run every call with `HOME` set to a fresh directory, so nothing writes to the operator's `~/.cad` (issue #81). Create a brief for a PLA cantilever (100 x 20 x 10 mm box, `flat_end` support, 10 N `far_end` load across the long axis) with a `max_deflection` 2 mm requirement, and confirm it with the scripted person as [Briefs](./briefs.md) says, through a server started with `--opener .claude/skills/verify/scripts/human.py`. Build the box with the `brief_id`, then score it with `material_key` `prusament-pla` until nothing is pending:

- `fea` is `unknown`, its `reads` lists `poisson_ratio` as `missing`, and `research` has one request for `poisson_ratio` with `low` 0 and `high` 0.5.
- `uv run cad-call submit_research '{"brief_id": "<brief_id>", "key": "prusament-pla", "field": "poisson_ratio", "url": "https://pmc.ncbi.nlm.nih.gov/articles/PMC11312661/", "quote": "Poisson’s ratio 0.30"}'` returns `refused` with "does not appear word for word" and a new request.
- The same call with `"Poisson’s ratio 0.35"` (Table 1, the PLA core) returns `accepted` with `value` 0.35 and `record` 1.
- Score again: `fea` decides, its `reads` has `researched` for `poisson_ratio` with the url and quote, the requirement has `basis` `researched`, and `research` is gone.

## Gotchas

- The quote reader reads a datasheet line, a label and one value, such as "Poisson's ratio 0.35". Prose such as "Poisson's ratio of pure PLA equals 0.35" is refused. Pick a table row.
- Many datasheet sites answer the server's fetch with HTTP 403, and PDFs are refused. The request then asks for another page.
