# Knowledge

The `search_knowledge(query, k)` tool returns the k sections of the cited sources in `knowledge/` that best match the query's words, best first. Each hit has its `id`, `subject`, source `title`, `url`, `page`, `section`, `retrieved` date and quoted `text`. The ranking is BM25F over four fields of the unit: its name (subject and aliases), its source's title, its heading and keys, and its text (`src/cad/knowledge/search.py`). A hit is a possible match, not checked for identity: the agent reads the subject and quote and chooses. No check reads a number from it.

## Sub-features

- `knowledge-scripted` returns ranked hits through `cad-call`, and an empty `hits` list when no word matches.
- `knowledge-k` refuses a `k` below 1 or above 20.
- `knowledge-claude` shows a Claude Code session calling `search_knowledge`, choosing the hit about the material asked for over a near miss, and citing its source and page.

## Driving it

- **Scripted.** Run `HOME="$CAD_HOME" uv run cad-call search_knowledge '{"query": "PolyTerra PLA+ density", "k": 3}'`. Exit code `0`. The first hit's `id` is `kb:polymaker-polyterra-pla-plus#density`, and `kb:polymaker-polyterra-pla#density` is also listed. Run it with `"query": "quantum chromodynamics"` and `hits` is `[]`. Run it with `"k": 0` and the exit code is `1`.
- **Live.** Run `uv run python .claude/skills/verify/scripts/claude_session.py "<prompt>" "$EVIDENCE/claude-knowledge.json"`, where the prompt asks for a density the corpus has next to a near miss, such as PolyTerra PLA+ next to PolyTerra PLA, or one it lacks, such as Bambu PLA Basic. The transcript has a `mcp__cad__search_knowledge` call. The reply uses the hit whose `subject` is the material asked for, cites its title and page, or says the knowledge base has no source for it.
