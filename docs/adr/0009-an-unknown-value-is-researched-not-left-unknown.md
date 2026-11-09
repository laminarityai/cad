# An unknown value is researched, not left unknown

Status: Accepted. The operator approved this ADR on 2026-11-08, with researched verdicts labelled and counted apart and no confirmation-page item.

A check that needs a number the tables lack used to report `unknown`. Examples are a Poisson's ratio that no source gives for PLA by name, and the density of a filament with no row. The person then had to find and confirm the number. That is friction, and SPEC calls friction a defect. This ADR records the operator's decision of 2026-11-08: when a value a check reads is unknown, it is researched. That applies to every value, not only material constants. The person sees which values were researched and which come from the reviewed tables, so a researched value does not need their confirmation.

## The decision

Nothing is refused, and nothing is marked unknown, only because a table lacks it. That covers a field marked `unknown` in a git row, a material, part or profile with no row at all, and a key that matches no row.

The server asks for research through MCP. When a tool hits a missing value, it returns a research request instead of refusing the call. The same applies when a check result is incomplete because of one. The tool's reply lists each missing item with a plain instruction to the agent, such as "research poisson_ratio for bambu-pla-basic: find a source and quote the words that state it". It also lists the key and field the answer fills. The server instructions tell the agent to answer every research request before it reports results, and to call the same tool again afterwards. The work that does not depend on the value still runs, and the card shows the affected results as waiting on research.

The agent answers each request with one tool call. That call gives the key, the field, a source URL and a quote copied from the source. It never gives the number itself. A material or part with no row gets a new row in the project overlay, built from researched fields. Its key is the agent's name for it, prefixed `project-` as ADR-0006 requires.

The server opens the URL itself and checks that the quote appears in the source word for word. It then reads the quantity out of the quote with the quote reader that confirmations already use (SPEC, PDF extraction). A quote the server cannot find gives no value, and neither does a number the reader cannot parse. The field then stays `unknown`, and the agent may try another source. The agent never types a number that a check reads.

A source does not have to name the exact material or part. A handbook value for plain PLA can stand in for a PLA blend. The record keeps the source's own words, so the card shows what the source actually covers.

A researched value lands in the project's overlay (ADR-0006) as a signed record with the kind `researched`. It carries the URL, the quote, the date it was fetched and a hash of the fetched source. Unlike a confirmed value, a researched value may fill an `unknown` field of a git row, in that project only. It never replaces a value that git cites. A value the person confirms replaces a researched one.

Checks still read through the one `get_material` lookup. The lookup returns each value with its provenance, which is `cited` (git), `confirmed` (the person, ADR-0006) or `researched`. Every check result that reads a researched value says so: it names the field and the source and quotes the source's words. So does every requirement verdict that rests on such a result. The table version records the overlay as ADR-0006 describes, so the tracer can rebuild the exact table that was used.

A researched value never enters `tables/` in git by itself. Moving one into git is a reviewed change, like any other row.

A researched value that fails the table's validation rules goes back to the agent with its problems, as a new research request. That covers values like an implausible density or a yield above tensile. It never makes the table or a tool fail. One bad answer must not take down the tools that read the table.

## Where this applies

An audit on 2026-11-08 found these places. Issue #113 tracks them.

- **Refusals.** A `made_of` material that is not in the table rejects the whole `propose_requirements` call. It becomes a research request for a new row. Phase 3's planned refusals become research requests too: a `printed_on` process with no row, and a cost in a currency other than USD. When `max_print_time` or `max_cost` comes with no process, the server asks the agent to research and propose one.
- **Unknown results.** Each of these leaves a check result unknown today, and each becomes a research request:
  - a `score_variant` key with no row;
  - a field marked `unknown` that `mass` or `fea` reads (density, E, ν, yield);
  - a missing printed-specimen yield;
  - phase 3's process fields, slicer profiles and filament prices.
- **Instructions.** These tell the agent to stop or to say "not checked" when data is missing: the server instructions, `score_variant`, `list_materials`, `propose_requirements` and `search_knowledge`. They now tell the agent to research the value. The ban on the agent's own arithmetic stays.
- **Quote reader.** It reads only density today. It gains E, ν, yield, tensile strength and price.

Unknowns that come from geometry are out of scope. Examples are a load anchor that does not resolve, a part that is not a closed solid, and a mesh that does not converge. These are not missing data. Research cannot fix them, and they stay `unknown`.

## Keeping a researched verdict honest

The agent that is graded chooses the source. It could pick a data sheet with a low density to pass a mass limit, or a high yield strength to pass a safety factor. The quote check proves the number is on the page. It does not prove that it is the right number for this material. This ADR therefore departs from ADR-0008 on purpose, and says so. An agent measurement never decides a requirement. A researched value does feed a verdict, because otherwise FEA would say nothing about most printed parts. Four rules keep that verdict honest without asking the person anything:

- **Labelled.** A verdict that rests on a researched value has the basis `researched`. It names each researched field, its source and the quote. The server tells the agent to report it as "passes on researched data", never as a plain pass.
- **Counted apart.** The tracer counts researched verdicts on their own line, as ADR-0008 does for agent measurements. Requirement coverage reports team-backed and researched passes separately, so research can never inflate the claim that checks decide.
- **Bounded.** A researched value must pass the same validation as a git row: a plausible range for its quantity, and yield no higher than tensile strength. It can only fill a gap. It never replaces a value that git cites or that the person confirmed.
- **Replaceable.** A reviewer who promotes a better value into git, or a person who confirms one, replaces the researched value. The card then moves to the stronger basis.

If evals show the agent choosing sources that flatter its own designs, the next step is to require two sources and keep the more conservative value. That costs the agent more work, and the person nothing.

## Fetching

The server fetches only `https` URLs. It resolves the host itself and refuses private, loopback, link-local and metadata addresses, including after a redirect. It caps the response size and the request time, and it sends no cookies or credentials. A fetch that fails any of these gives no value, and the agent is asked to try another source.

## Tracing

A researched value counts as traced. The scorecard records its URL, the quote and the hash of the fetched source, so SPEC's phase 2 exit, "every number on every scorecard traces to a source", holds without a new exception. The tracer reports it as `researched`, never as `confirmed`.

## What does not change

- Checks decide, and a requirement's target is still one a person confirmed. Research fills a value that a check reads. It never sets a target and never grades a result.
- The agent still never decides whether a design is good. It chooses where to look, but the server reads the number from the source, and "Keeping a researched verdict honest" limits what that choice can do.
- Requirements are still confirmed on the page (ADR-0004).

## Considered options

- **Leave it unknown until a reviewed source names the exact material.** This was the old rule. Rejected because FEA said nothing about most printed parts, since no data sheet gives ν for PLA or PETG. Most of the time, the person's only next step was to go and find the number themselves.
- **Ask the person to confirm each value the agent found.** Rejected for values. It costs one confirmation for each number, while research that is labelled and traceable shows the person the same facts at no cost. Confirmation stays for requirements.
- **Let the agent pass the number with a citation.** Rejected. Model output would then reach a check. Making the server read the number from a quote it fetched itself keeps the number path mechanical.
- **Have the server run its own web search.** Not chosen for now. It needs a search API and a ranking rule, and the agent already has search tools. Asking the agent through the tool reply is the simplest path, and the server's job is to verify, not to find.
- **Refuse a key that is not in the table, and let the agent pick another.** Rejected. That pushes the agent toward whatever happens to be in the table rather than what the person asked for.

## Consequences

AGENTS.md and SPEC change. "Numbers a check reads come from the tables by exact key" becomes "come from the tables by exact key, or from a source the server fetched and quoted, labelled as researched." "Missing data is unknown, never a guess" becomes "missing data is researched and labelled, and stays unknown only when no source can be verified."

A researched value can be wrong for the specific grade. For example, a handbook ν for plain PC is not quite right for an impact-modified PC. The card shows this, because it quotes what the source names. It does not stop the verdict. Reviewers can promote good values into git and replace weak ones.

The server makes outbound requests to URLs the agent chooses. They are read-only GETs, with a size cap and a timeout. Pages behind a login, or that block bots, give no value. The data policy in SPEC still applies: opening a specific vendor page and citing it is allowed, and building a catalog from a vendor's site is not.

A source page can change or vanish. The record keeps the quote and a hash of what was fetched, so the scorecard still shows what the check read.

## Amendment (2026-11-08): the agent reads the number, the server cites and checks it

The operator decided on 2026-11-08 that the server stops reading the number out of the quote. In the operator's words: "LLMs are pretty good at reading from a page and extracting the correct numbers. Just retrieving a webpage and the value is good enough, we do not need to create a parser that has to work for every single page. however, the page that was used must be cited." A hand-written quote reader overfits to the few pages it was built from, and it refused ordinary sentences such as "the Poisson ratio = 0.36, was used" (#120). Each refusal sent the agent to look for another page, which is friction.

This replaces the parts of this ADR that say the server reads the quantity with the quote reader and that the agent never gives the number:

- The agent's `submit_research` call gives the key, the field, the value and its unit as the page writes them, the page's URL, and the quote it read the value from.
- The server still fetches the page itself, under the rules in "Fetching". On 2026-11-09 the operator chose to keep exactly two checks, and neither reads a unit, a label or prose:
  - The quote is on the fetched page. The comparison uses only the letters and numbers of each, in order and case folded, so whitespace, punctuation, markup and case may differ. A quote may not start or end inside a number, so "960 kg/m3" is not on a page that says "8960 kg/m3".
  - The value is written in the quote as one number. "." or "," may be a decimal mark or digit grouping, so 1.24 is written in "1.24" and "1,24", but not in "124" or "1.245". Digits that follow a letter, as in "D638" or "cm3", are not a number.
- The server trusts the agent's unit. It converts it by an exact table of spellings, and a spelling that differs from a key only in case, such as "Mpa", names that key. It applies the field's range and the table's rules, as before. Measured on 23 quotes an agent copied from 19 real pages, the two checks accept 22. The one refusal is a quote that left out the symbol "ν" between the label and the number.
- The record cites the page: the URL, the page title, the quote, the date it was fetched and the hash of the fetched page. A value that is already known, cited or researched, is never replaced.
- The verdict is still labelled `researched` and counted apart. "Keeping a researched verdict honest" still holds. The two checks prove that the page states the quote and that the quote writes the agent's number. They do not prove that the agent picked the right number or the right unit. They accept 75 ksi from "Tensile Strength (MPa) 55-75", 0.3 from "-0.3", 2.1 from "2.1 × 10⁵", 960 from "8 960", and 1.337 or 1337 from "1,337". The labelled, cited verdict lets a reviewer see each of these.

- A table value is `cited` or `researched`. The `confirmed` kind this ADR lists is dropped, as the ADR-0006 amendment records, so a researched value is replaced only by a reviewed value in git.

The quote reader in `cad.sources` is deleted, because research was its only user.
