# Knowledge architecture research

Nov 5, 2026. Three research passes (prior art, engineering skills, data and storage), consolidated. Links were opened by the research agents; lines marked *inference* are judgment, not findings. Not legal advice.

## Findings that shape the design

### Plain vector search is the wrong tool for engineering numbers

- DesignQA (Formula SAE rules): GPT-4 with basic vector RAG scored rule-retrieval F1 0.181 vs 0.750 with the full rules in context. Tables were flattened and figures dropped. https://arxiv.org/html/2404.07917v2
- MCERF fixed rule retrieval (F1 0.95) with page-image retrieval plus keyword search, but models still "often miss numerical values and fine detail, especially in complex tables." https://arxiv.org/html/2604.09552
- FinanceBench: GPT-4-Turbo with retrieval answered wrongly or refused 81% of questions. https://arxiv.org/abs/2311.11944
- LLaMP looked up materials data through typed API calls, no vector search: formation energy error 0.009 vs 1.680 eV for plain GPT-4. TableRAG routes table questions to SQL because chunking tables "leads to information loss." https://arxiv.org/html/2401.17244v3 , https://arxiv.org/abs/2506.10380
- Anthropic's contextual retrieval: adding keyword (BM25) search to embeddings cut retrieval failures 49%, 67% with a reranker. Keyword match catches part numbers and clause IDs that embeddings miss. https://www.anthropic.com/news/contextual-retrieval

### Agents fail on knowing which rule applies, not on arithmetic

- EngDesign (NeurIPS 2025): domain-knowledge errors and constraint violations are 55 to 67% of failures; computation errors 6 to 9%. Simulator feedback over iterations raises pass rates. https://arxiv.org/html/2509.16204v2
- CADSmith: a small curated knowledge base (API entries, worked examples, 25 error-to-fix patterns) found by keyword matching was enough for CAD code generation. https://arxiv.org/html/2603.26512v1

### Products ground on docs and execution, not calculations

- Zoo's Zookeeper searches docs, executes, reviews snapshots, measures mass. No standards or catalogs described. https://zoo.dev/research/zookeeper
- Leo claims 1M+ pages of standards and datasheets with citations and "no confident match" answers; no calculation tooling described (vendor claim). https://www.getleo.ai/blog/this-is-why-engineers-hate-gpt-and-what-they-re-using-instead
- Adam users worry about "one hallucinated miscalculation" and say vendor downloads "never have everything you need." https://news.ycombinator.com/item?id=47977694

### Little exists to build domain checks from

- Usable: python-gearbox for gear rating (ISO 6336, AGMA 2001; MIT; version 0.2 only from git, PyPI still has 2015's 0.1) https://github.com/efirvida/python-gearbox ; pint for units; Pynite (MIT) as a frame/plate solver.
- Avoid for a closed product: gearpy and anastruct (GPL-3.0).
- Must be written in-house: shaft fatigue and deflection, bearing L10 life, bolted joints (no open-source VDI 2230 exists), thread stripping, belt rating, weld sizing, FDM design rules.
- Validation oracles: KHK Gear Technical Reference worked examples (free), MechaniCalc bolted-joint validation cases, ReCalc's test files, Shigley worked examples, ISO/TR 6336-30 (paid, about $230). Rule: at least two independent oracles per check.

### Data licensing

- Formulas can be reimplemented with the clause cited (17 USC 102(b)). Tables copied verbatim from paid standards cannot; DIN also forbids AI use of its documents. https://www.din.de/en/about-standards/standards-and-the-law/reproduction-new/reproduction-faq
- Do not use: MatWeb (terms bar redistribution and AI use), NIST SRD without permission, MMPDS, McMaster-Carr scraping (robots.txt blocks AI crawlers; API for vetted customers only), CADENAS PARTcommunity (no derived databases, no AI training).
- Safe to embed: bd_warehouse tables (Apache-2.0: fasteners, bearings, o-rings, keys, drill sizes). FreeCAD material cards are CC-BY but need checking: the PLA card lists tensile strength below its yield strength, and the 6061 card cites MatWeb.
- Unknown: WCP, REV, SDP-SI, igus, Misumi, TraceParts terms. Ask for written permission.

### Storage

- Postgres + pgvector + Postgres full-text search, fused with reciprocal rank fusion in SQL. One database holds jobs, briefs, requirements, sources, chunks and scorecards with real foreign keys. https://github.com/pgvector/pgvector
- Runner-up: LanceDB (embedded, hybrid search, auto-versioning), but a second store. Chroma lacks BM25; sqlite-vec is alpha.
- Docling (MIT) for PDF table extraction; MinerU scores higher on tables but its license is unclear. https://github.com/docling-project/docling

## Recommended layout

1. **Engineering skills.** Own the mapping from requirement kind to check, not just the checks. Checks are executed, never read into context, and write-protected from the agent. Each check carries a manifest (inputs with units, validity range, status, reviewer, code hash, source IDs) and oracle cases. A changed hash reverts the check to unverified.
2. **Knowledge base.** Hybrid keyword and vector search over page- or section-sized units, each returning its source, page and section ID. It supplies reasons and pointers, never a number a check uses. Short critical documents go into context whole. No confident hit means the requirement is marked unverified.
3. **Parts and materials tables.** YAML/CSV in git as the source of truth, validated in CI (units, yield ≤ tensile strength, plausible density), loaded into Postgres. Read through typed tool calls returning value, unit, source and table version. Scorecards record the table version. Missing data is an explicit "unknown," never filled in by the agent.
4. **Tooling know-how.** build123d API notes, worked examples and error-to-fix patterns, found by keyword. Small, curated, separate from engineering knowledge.
5. **Design library, later.** Past variants with scorecards; each records the check and table versions that scored it, so old passes are not reused after a check changes. Weakest evidence of the five.

Numbers extracted from PDFs become candidate table rows that a person confirms before any check reads them.

## Evaluation

- Retrieval: 100 to 200 domain questions with a gold source and page; score recall@k and MRR by ID match, not an LLM judge.
- Extraction: about 20 fixed datasheet PDFs with hand-entered expected cells; rerun on parser upgrades.
- Near-miss: an M5 lookup when only M6 exists returns "not found"; PETG never returns PLA values.
- Provenance: every number on a scorecard resolves to a confirmed source, page and table version.
