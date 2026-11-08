# An unknown value is researched, not left unknown

A check that needs a number the tables lack used to report `unknown`. Examples are a Poisson's ratio that no source gives for PLA by name, and the density of a filament with no row. The person then had to find and confirm the number. That is friction, and SPEC calls friction a defect. This ADR records the operator's decision of 2026-11-08: when a value a check reads is unknown, it is researched. That applies to every value, not only material constants. The person sees which values were researched and which come from the reviewed tables, so a researched value does not need their confirmation.

## The decision

When a check would read an unknown value, the agent researches it. That covers a field marked `unknown` in a git row, and a key with no row at all. The agent hands the server a source URL and a quote copied from that source. It never hands over the number itself.

The server opens the URL itself and checks that the quote appears in the source word for word. It then reads the quantity out of the quote with the quote reader that confirmations already use (SPEC, PDF extraction). A quote the server cannot find gives no value, and neither does a number the reader cannot parse. The field then stays `unknown`, and the agent may try another source. The agent never types a number that a check reads.

A source does not have to name the exact material or part. A handbook value for plain PLA can stand in for a PLA blend. The record keeps the source's own words, so the card shows what the source actually covers.

A researched value lands in the project's overlay (ADR-0006) as a signed record with the kind `researched`. It carries the URL, the quote, the date it was fetched and a hash of the fetched source. Unlike a confirmed value, a researched value may fill an `unknown` field of a git row, in that project only. It never replaces a value that git cites. A value the person confirms replaces a researched one.

Checks still read through the one `get_material` lookup. The lookup returns each value with its provenance, which is `cited` (git), `confirmed` (the person, ADR-0006) or `researched`. Every check result that reads a researched value says so: it names the field and the source and quotes the source's words. So does every requirement verdict that rests on such a result. The table version records the overlay as ADR-0006 describes, so the tracer can rebuild the exact table that was used.

A researched value never enters `tables/` in git by itself. Moving one into git is a reviewed change, like any other row.

## What does not change

- Checks decide, and a requirement's target is still one a person confirmed. Research fills a value that a check reads. It never sets a target and never grades a result.
- The agent still never decides whether a design is good. It chooses where to look, but the server reads the number from the source.
- Requirements are still confirmed on the page (ADR-0004).

## Considered options

- **Leave it unknown until a reviewed source names the exact material.** This was the old rule. Rejected because FEA said nothing about most printed parts, since no data sheet gives ν for PLA or PETG. Most of the time, the person's only next step was to go and find the number themselves.
- **Ask the person to confirm each value the agent found.** Rejected for values. It costs one confirmation for each number, while research that is labelled and traceable shows the person the same facts at no cost. Confirmation stays for requirements.
- **Let the agent pass the number with a citation.** Rejected. Model output would then reach a check. Making the server read the number from a quote it fetched itself keeps the number path mechanical.
- **Have the server run its own web search.** Not chosen for now. It needs a search API and a ranking rule, and the agent already has search tools. The server's job is to verify, not to find.

## Consequences

AGENTS.md and SPEC change. "Numbers a check reads come from the tables by exact key" becomes "come from the tables by exact key, or from a source the server fetched and quoted, labelled as researched." "Missing data is unknown, never a guess" becomes "missing data is researched and labelled, and stays unknown only when no source can be verified."

A researched value can be wrong for the specific grade. For example, a handbook ν for plain PC is not quite right for an impact-modified PC. The card shows this, because it quotes what the source names. It does not stop the verdict. Reviewers can promote good values into git and replace weak ones.

The server makes outbound requests to URLs the agent chooses. They are read-only GETs, with a size cap and a timeout. Pages behind a login, or that block bots, give no value. The data policy in SPEC still applies: opening a specific vendor page and citing it is allowed, and building a catalog from a vendor's site is not.

A source page can change or vanish. The record keeps the quote and a hash of what was fetched, so the scorecard still shows what the check read.
