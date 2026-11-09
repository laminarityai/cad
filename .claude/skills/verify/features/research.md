# Research

ADR-0009: a material value the table lacks is researched, not left unknown. When a check reads a material field the table marks `unknown`, the result's `reads` has a `missing` entry and the scorecard's `research` holds a request: brief id, key, field, unit and the accepted range. `submit_research(brief_id, key, field, url, quote)` never takes a number. The server fetches the page (https on port 443 only, public addresses only, checked again after every redirect, a 4 MiB cap, one 15 s deadline over the whole fetch, no credentials), checks that the quote is on the page word for word, starting and ending on a boundary of the page's text so it is never cut from a longer number, and reads the value with the quote reader in `cad.sources`. An accepted value is a signed record in `~/.cad/projects/<project_id>/research/<n>.signed` and fills the field for that project only. It never replaces a value git cites. A result that reads it has a `researched` read with the url, quote and page hash, and a requirement it decides has `basis` `researched`.

## Sub-features

- `research-request` makes `score_variant` with a brief return a `research` request for each missing material value a check read. Missing geometry never asks.
- `research-accept` stores a value read from a quote on a fetched page, and the next `score_variant` reads it, with table version `<git>+<project_id>@r<n>`.
- `research-refuse` refuses a quote that is not on the page or is cut from a longer number, a quote the reader refuses, a failed or guarded fetch, and a value that breaks the table's rules. Each gives a reason and a new request. The reader refuses a value outside the request's range before any fetch. A field git cites is refused with no request.
- `research-current` keeps a card current when a later record fills a value the card never read. Two variants in one project: variant A reads a researched `poisson_ratio` for `prusament-pla` (record 1), then a record for `bambu-pla-basic` lands (record 2). `evals/briefs/trace_store.py --root <home>/.cad/variants --briefs-root <home>/.cad/briefs --projects-root <home>/.cad/projects` reports `stale: 0` for both cards. It rebuilds each card's table from the first `n` records its version names.
- `research-prose` reads a short sentence that names the field, such as "the Poisson ratio = 0.36" on `https://pmc.ncbi.nlm.nih.gov/articles/PMC8123144/`, which returns `accepted` with `value` 0.36. The same quote with the page's trailing ", was used" is refused, because the comma touches the digits.
- `research-unreadable` covers a project ledger the store cannot read. `submit_research` refuses before the fetch with no new request, and `score_variant` puts the problem in `research_problem` and asks for no research.

## Driving it with cad-call

Run every call with `HOME` set to a fresh directory, so nothing writes to the operator's `~/.cad` (issue #81). Create a brief for a PLA cantilever (100 x 20 x 10 mm box, `flat_end` support, 10 N `far_end` load across the long axis) with a `max_deflection` 2 mm requirement, and confirm it with the scripted person as [Briefs](./briefs.md) says, through a server started with `--opener .claude/skills/verify/scripts/human.py`. Build the box with the `brief_id`, then score it with `material_key` `prusament-pla` until nothing is pending:

- `fea` is `unknown`, its `reads` lists `poisson_ratio` as `missing`, and `research` has one request for `poisson_ratio` with `low` 0, `high` 0.5 and `exclusive` true.
- `uv run cad-call submit_research '{"brief_id": "<brief_id>", "key": "prusament-pla", "field": "poisson_ratio", "url": "https://pmc.ncbi.nlm.nih.gov/articles/PMC11312661/", "quote": "Poisson’s ratio 0.30"}'` returns `refused` with "does not appear word for word" and a new request.
- The same call with `"Poisson’s ratio 0.3"`, cut from 0.35 on the page, is refused the same way.
- The same call with `"Poisson’s ratio 0.35"` (Table 1, the PLA core) returns `accepted` with `value` 0.35 and `record` 1.
- Score again: `fea` decides, its `reads` has `researched` for `poisson_ratio` with the url and quote, the requirement has `basis` `researched`, and `research` is gone.

## Gotchas

- The quote reader reads a datasheet line, such as "Poisson's ratio 0.35", or a short sentence that names the field and joins it to one value with words from `PROSE` in `cad.sources.tokens`, such as "a Poisson's ratio of 0.35 was used". Any other word refuses the quote, so "Poisson's ratio of pure PLA equals 0.35" is refused. Cut the quote to the label and the value.
- Many sites answer the server's fetch with HTTP 403, and PDFs are refused. The request then asks for another page. On 2026-11-08, 11 of 40 likely research sites answered 403 (matweb, makeitfrom, specialchem, mdpi, sciencedirect, researchgate, wiley, acs, tandfonline, curbell, ulprospector). A browser-like Accept header and a `Mozilla/5.0 (compatible; ...)` User-Agent changed none of them. PMC, Wikipedia, engineeringtoolbox, azom, simplify3d and the Prusa and Bambu wikis answer 200.
