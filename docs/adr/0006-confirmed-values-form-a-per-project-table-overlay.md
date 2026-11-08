# A confirmed value lands in a per-project table overlay that the store signs

A check reads its numbers from the parts and materials tables by exact key. A person can also confirm a value that the tables lack, such as the density of a filament with no row, and SPEC says that the value is then reused for the rest of the project. This ADR records where that value lives and how a check reads it. The operator approved it on 2026-11-07.

A confirmed value lands in a per-project overlay. Only the confirmation page's request handler writes the answer that confirms the value, and the project store signs that answer with its key, as ADR-0003 and ADR-0004 do for their records. The overlay is derived on read from the signed answers. No tool writes it, and it is never stored as a file that the agent can edit.

The overlay only adds rows. Every overlay key starts with `project-`, and the table loader refuses a row in git whose key has that prefix. So an overlay row can never shadow a git row, including a row that a later commit adds to git. The overlay never fills an `unknown` field of a git row. Overlay rows obey the same validation rules as git rows, such as a plausible density.

Checks read through one lookup over the git table plus the project's overlay. `get_material` stays the only lookup, so the checks and the overlay go through one function. If git rows gain `same_as` aliases, the lookup resolves the alias in the git table before it reads the overlay.

The table version that a scorecard records is `<git>+<pid>@<n>`. `<git>` is the version of the git table, `<pid>` is the project id, and `<n>` is the number of page answers that the overlay was built from. The overlay is a pure function of the first `n` answers, so the tracer rebuilds exactly the table that the scorecard read. A scorecard scored against an older overlay traces as stale, not as unresolved.

## Considered options

- **Write the confirmed value into `tables/` in git.** Rejected. A row in git is shared by every project, and one person's confirmation covers only their project. A commit for each confirmation would also make the value wait for review and a merge, while SPEC says that mass fills in as soon as you confirm a density. And a path from the running server to `tables/` is a way to change a table that a check reads, which AGENTS.md calls a bug.
- **Store the overlay as a YAML file in each project.** Rejected. An agent with file tools could edit the file. The store refuses an answer whose signature does not match, and only the page writes answers.
- **Let the overlay fill an `unknown` field of a git row.** Rejected. One key would then read different values in different projects, and the key would no longer say whether a value came from git or from a person.
- **A second lookup for overlay rows.** Rejected. With two lookups, a check could read one table and miss the other, and an alias could resolve in one lookup but not the other.
- **A table version that hashes the overlay's answers.** Rejected. A hash says that the table changed but does not tell the tracer which answers to rebuild it from. `@<n>` does.

## Consequences

SPEC says that the parts and materials tables are files in git. Shared rows still are. The overlay adds rows for one project only, and those rows carry the `project-` prefix, so a reader can tell the two apart from the key.

Any page answer in a project changes the table version. So every variant in the project is scored again on its next comparison, even if the answer was not a value. We accept this cost because the tracer can then rebuild the exact table.

The overlay inherits the guarantee of ADR-0004 and its gap. An agent that reaches the server only through MCP cannot add an overlay row. An agent with shell tools that runs as the same user can read the store key and sign a forged answer.
