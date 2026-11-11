# CAD harness product spec

Nov 5, 2026 · @Kevin · revised after a grilling session, and on Nov 7 to make friction a defect and to record phase 2 decisions; terms follow [GLOSSARY.md](GLOSSARY.md)

## Summary

We are building an AI engineer that turns what you ask for into several engineering-checked designs to choose from. Pitch: CAD at the speed of thought, with the engineering already done.

- **Who it's for:** early CADders, such as students, makers and hobbyists, who can describe what a part must do but can't yet model it fast or size it confidently. The bar is that a working engineer would trust the same output.
- **What it does:** turns a brief into 3 to 5 parametric variants, checks each one, shows every result with its math, changes the chosen one when you ask in chat, and sends it to Onshape.
- **How it should feel:** simpler, faster and easier than CAD, most of all in the slow parts of prototyping and testing. The agent does the work and asks you only for the decisions that need a person. If you have to take a step the product could have taken, we have failed.
- **How it stays honest:** the agent proposes designs, and checks it cannot change decide whether they pass. Each scorecard lists every requirement that no reviewed check covers, so a design never looks more checked than it is.
- **What it is not:** a new CAD program, a text-to-mesh generator, or a blueprint-to-CAD converter.
- **First version:** a generalist. It designs any part it can build reliably, with universal checks on everything. Engineering skills for specific domains come later, chosen by what people actually design.

## Problem and evidence

Engineers don't trust AI to design parts, and beginners can't catch AI's mistakes, so the product has to check its own work and show the math.

- **Trust is low.** 89% of engineers verify every AI result and 52% use back-of-the-envelope calculations to do it ([Omni Calculator, 2026](https://www.omnicalculator.com/reports/ai-adoption-in-engineering)). Full reliance on AI does not exceed 3% for any activity surveyed, and 61% say transparency and explainability would raise their trust ([IoT Analytics, Sep 2026](https://iot-analytics.com/the-ai-trust-gap-in-design-and-engineering-software/)).
- **What engineers want is the work around modeling.** In the [HN thread on Adam's AI CAD Harness](https://news.ycombinator.com/item?id=47977694), the strongest asks were standard and vendor parts, drafting, and checks, delivered as inspectable scripts or feature-tree edits inside tools they already use. Commenters worried about "one hallucinated miscalculation."
- **Text-to-CAD breaks on real parts.** In [Xometry's test](https://xometry.pro/en/articles/text-to-cad-tools-test/) of free tiers, most tools failed a 24-tooth, 2 mm module gear. On [Text2CAD-Bench](https://arxiv.org/html/2605.18430v1), invalid output rises from about 15% to 70 to 90% for most models at the hardest difficulty tier, where sweeps, lofts and shells appear.
- **Checks work.** Feeding FEA results back to the agent raised designs that hit their target safety factor from 22% to 59% ([Physics-in-the-Loop](https://arxiv.org/html/2605.19717)).
- **The gap.** Zoo, Adam, MecAgent and Autodesk compete on generation. In our assessment as of November 2026, none combines checks the agent cannot change, standard-part grounding, and variant comparison.

The full user research is in the report *AI CAD harness user needs*. The knowledge-layer research is in [docs/research/knowledge-architecture.md](docs/research/knowledge-architecture.md).

## Core loop

1. **Brief.** You say what you need, in your own words, and attach images, drawings or documents if you have them.
2. **Variants.** The agent builds 3 to 5 parametric variants at once. It does not wait for you.
3. **Requirements.** The agent proposes the targets you stated, each with the words it came from, and fills in the numbers you did not state as assumptions it labels. You confirm your targets with one click, and a brief with no number needs no click.
4. **Checks.** Every variant gets a scorecard. A target waits as waiting on you, with the measure beside it, until you confirm it, and then the same results are judged. This step is what sets us apart.
5. **Change and export.** You pick a variant, ask in chat for any change, and send it to Onshape. The agent edits the variant and rebuilds it, and the checks run again. You can download the option on screen as STEP, STL or 3MF from the workspace page.

Attachments are context, not input to convert. The agent reads them for intent and dimensions, and every dimension it takes from an image becomes a requirement you confirm, with the others. No verdict rests on it until you do.

Existing CAD parts can be context too. A context part is a part that the new part must fit with, such as the housing or rail it mounts to. You attach one to the project, or an earlier variant becomes one. You confirm each context part before a verdict rests on it. Reading a part directly from Onshape or Fusion through their MCP servers is a later goal, tracked in [#60](https://github.com/laminarityai/cad/issues/60).

## Asking you

Friction is a defect. The one step the agent cannot take for you is confirming what it proposed, because then it would be grading its own work. So confirmations stay, and each one costs you as little as possible.

- **One page, one click.** Everything waiting on you appears on one confirmation page: requirements, dimensions read from images, values taken from documents, context parts, and sources the agent found. Each item shows the agent's proposal and the words it came from. Confirming the whole page is one click, and editing an item is optional.
- **Only what you stated.** The agent asks you to confirm a number only when you stated it and a check will use it. A number it fills in itself is an assumption, shown apart with no verdict. What it reads for context and intent needs no confirmation.
- **Nothing waits that doesn't have to.** A new brief builds its options before you confirm anything, and what you decline later removes none of them. You never have to choose a material. When your brief names none, the agent chooses one for each variant, from our table or one it researches, and says why in a line. The page marks it as chosen by the agent, and you can change it in chat. A material you name is a requirement you confirm. If the material is not in our table, the variants are still built and the geometry checks still run. The agent researches the density, and mass fills in, labelled as researched, without a rebuild.
- **Any cited source.** A value can come from a datasheet, a handbook, a supplier's page, a standard's clause, or your own words in the brief. The citation says where the number came from. Your confirmation says that it is the number you mean.
- **Confirm once.** A confirmed value, material or source is reused for the rest of the project, so you are never asked the same thing twice.
- **Most briefs need no values confirmed.** Our materials and parts tables cover the common choices, so confirming a value is the exception, not a step in every design.

## How the agent works

### Modes

You switch modes in the chat, the way you switch modes in Claude Code.

- **Design mode** is the default. A new brief builds at once: the agent makes variants, runs checks, shows scorecards, and stops for you to pick a variant or ask for a change. It asks you only to confirm a target you stated.
- **Auto mode.** The agent revises variants against the checks without stopping. It stops in three cases. The first is that every requirement passes, which the checks decide. The second is that it needs a decision only you can make, such as relaxing one of two conflicting requirements, changing a requirement you confirmed, or using a source it found. The third is that the agent judges it is stuck, in which case it reports what it tried and asks how to proceed. There is no budget. An account's usage limit also ends a run when it refuses a build.

Deeper analysis is not a mode. When you ask whether a chosen variant will hold a load, or a requirement needs it, the agent runs slower analysis of that one variant, such as full FEA and tolerance stack-ups, in whichever mode you are in.

### Checks

A check is a fixed, deterministic piece of code that measures a variant and returns pass or fail with its formula and source. The agent cannot edit checks or their inputs. Its only move is to change the design and run the checks again.

- **Universal checks** run on every variant: builds as one closed solid, no interference, mass and center of mass from the materials table, manufacturability (wall thickness, overhangs), and FEA under the loads you state.
- **The fit check** measures each variant against the confirmed context parts of its project. It reports the volume where they overlap and the minimum clearance between them. Our team writes and reviews it, as it does the universal checks, and it ships in phase 2.
- **The holes check** measures every round hole of a variant and holds the diameters to what you confirm: a metric fastener size with a clearance or tapped fit, or a stated diameter, and a count. Fastener sizes come from our fasteners table, read by exact key and cited to ISO 273 and a tap-drill chart. A coaxial group such as a counterbore is one hole. A slot, a hexagon or any other opening that is not a round hole makes the result unknown, never a pass. Our team writes and reviews it.
- **Domain checks** come from engineering skills, such as gear tooth strength or bolted joint preload. The first version ships none. The first skill goes to whichever domain people design in most.
- **Agent-written checks** cover requirements no existing check handles, such as a snap-fit. Their results show as unreviewed. You can review one for your own project, and its results then show as user-reviewed. Only our team can add a check to an engineering skill that every user gets. Before a person reviews it, an agent-written check must pass automatic gates: consistent units, deterministic output, and at least one worked example from its cited source.
  - The first version has no agent-written checks ([ADR-0008](docs/adr/0008-the-agents-own-measurements-are-information-never-a-verdict.md)). The agent may report its own measurement for a requirement no check covers. The scorecard shows it as information only, labelled not verified, and it never passes or fails anything.
- **Unverified requirements** are listed on every scorecard. If nothing reviewed checks a requirement, the scorecard says so.

The first version does not design freeform or loft-heavy shapes reliably, and the agent says so. It offers the closest prismatic version if one exists and marks the shape requirement unverified.

### Knowledge

Knowledge lives in five places. Numbers a check uses never come from vector search, because retrieval returns near misses and a check that reads a near-miss yield strength is worse than no check.

1. **Engineering skills.** A bundle for one kind of design: its domain checks, the rules for which check applies to which requirement, its templates, its sources, and worked examples that test each check. Checks are executed, never read into the agent's context. A change to a check's code reverts it to unreviewed.
2. **Knowledge base.** Standards summaries, design guides, datasheets and the agent's own research, each stored as a source with its page and section. In phase 2 the knowledge base is source files in git, found by keyword search, with no database and no vector search. The knowledge base supplies reasons and pointers, never a number a check reads. Search returns the closest few sections, and the agent decides whether one fits. A requirement stays unverified until a check measures it against a target a person confirmed.
3. **Parts, fasteners and materials tables.** YAML and CSV files in git, validated in CI (units, yield strength no higher than tensile strength, plausible density) and read by exact key. Every value cites its source. Every scorecard records the table version it used. Missing data is researched: the agent reads the number from a page, the server fetches that page, checks that the agent's quote and number are on it, cites it, and labels the value as researched ([ADR-0009](docs/adr/0009-an-unknown-value-is-researched-not-left-unknown.md)). It stays "unknown" only when no source can be verified, and is never a guess.
4. **build123d know-how.** API notes, worked examples and common error fixes, kept small and found by keyword.
5. **Design library, later.** Past variants with their scorecards. Each records the check and table versions that scored it, so an old pass is not reused after a check changes.

A number the agent takes from a web page fills a missing value only as a researched value. The server fetches the page itself and checks that the quote and the number are on it, and the record cites the page. Every check result and verdict that reads a researched value says so and names its source, and the tracer counts those verdicts apart. A number the agent takes from anywhere else, such as a PDF or your brief, reaches a check only as a requirement you confirm.

**Data policy.** The agent may open a specific vendor page while designing and cite it as a source you confirm. Building a shared catalog from a vendor's site needs that vendor's written permission. McMaster-Carr blocks AI agents, so for its parts you paste the details or attach the STEP file. We implement formulas from paid standards and cite the clause. We never ship a standard's text or tables. You supply any copyrighted standard tables yourself. We build our own materials table from manufacturer data sheets and do not use MatWeb data.

## Architecture

The MCP server is the product ([ADR-0002](docs/adr/0002-mcp-server-is-the-product.md)). Every capability is an MCP tool: making variants, running checks, reading tables and the knowledge base, and exporting to Onshape. Our web app's agent is the first client and uses the same interface as Claude Code or any other MCP client. Because checks run on the server, any agent that connects can do the engineering but cannot grade its own work.

- **Sandbox.** Every variant is Python written by an AI. The server runs it in a locked-down container with no network access and with time and memory limits. This is a security requirement from the first release.
- **Hosted, with accounts.** The first version is hosted only. The web app and MCP clients both sign in through Clerk with Google, and accounts carry usage limits because FEA costs compute. Accounts and usage limits ship in phase 4.
- **Modes travel as guidance.** Outside clients get the tools and the same checks. They also get the modes and stopping rules as guidance, and the server does not enforce them for those clients. In a web app conversation the server enforces the mode. It also holds each Auto run and refuses to build past a stop ([ADR-0010](docs/adr/0010-the-server-holds-the-auto-run.md)). Auto mode runs only in the web app for now.
- **Long jobs stream.** FEA takes seconds to minutes, so it runs as a background job and the scorecard fills in as results arrive.

## Stack

Python on the backend, because the CAD kernel and FEA wrappers all have Python APIs. A thin web front end sits on top.

| Layer | Pick | Why | Alternatives |
| --- | --- | --- | --- |
| Code-CAD kernel | [build123d](https://pypi.org/project/build123d/0.12.0/) 0.12 (Sep 2026, Apache-2.0, OCCT) | Our bake-off tied it with CadQuery on model reliability; the parts generators and joint objects we need are native to it ([ADR-0001](docs/adr/0001-build123d-as-cad-kernel.md)) | CadQuery |
| Standard parts | [bd_warehouse](https://pypi.org/project/bd-warehouse/) 0.4 (Apache-2.0 tables for fasteners, bearings, o-rings, keys), [py_gearworks](https://pypi.org/project/py-gearworks/0.0.24/) (gear geometry) | Generators draw parts from standard tables, so the model never draws threads or gear teeth | Vendor STEP files the user attaches |
| Engineering calcs | Our own tested Python module + Pint for units | Each calc returns its formula and source, so the scorecard can show its work. Few open libraries exist; shaft, bearing, bolt and belt calcs must be written in-house | [python-gearbox](https://github.com/efirvida/python-gearbox) for gear rating once a gear skill exists (install from a pinned commit) |
| Materials | Our own YAML table in git, every value cited from manufacturer data sheets | One validated table prevents mass and strength errors | FreeCAD material cards (CC-BY) as a starting point, checked by hand |
| FEA | [gmsh](https://gmsh.info) + CalculiX, with our own input writer and result reader | CalculiX is a mature solver that engineers recognize; the writer and reader are about 150 lines we review, for the static analysis phase 3 needs ([phase 3 design](docs/design/phase-3.md)) | [pygccx](https://github.com/calculix/pygccx), not used: one maintainer, no commit since February 2025, GPL-3.0; torch-fem, which [Physics-in-the-Loop](https://arxiv.org/html/2605.19717) used |
| Print cost and time | Deferred indefinitely (2026-11-09), with printability. When it returns: PrusaSlicer CLI, from Debian, in the analysis image ([ADR-0005](docs/adr/0005-checks-run-in-an-analysis-image.md)) | A real slice gives print time, filament weight and cost. It slices headless and gives the same G-code twice | OrcaSlicer later: its Linux builds need a newer glibc than our Debian base. Volume times density as a fast first pass |
| Knowledge store | Source files in git, found by keyword search (phase 2) | The files are reviewed in git like the tables, and the knowledge base never supplies a number a check reads | Postgres + [pgvector](https://github.com/pgvector/pgvector) + Postgres full-text search, fused with reciprocal rank fusion, later; LanceDB |
| PDF extraction | None in phase 2. The agent reads a value from an HTML or text page, and the server fetches the page and checks that the quote and the number are on it | A model reads a page well; a hand-written reader overfits to the pages it was built from ([ADR-0009](docs/adr/0009-an-unknown-value-is-researched-not-left-unknown.md) amendment) | [Docling](https://github.com/docling-project/docling) (MIT) later, which keeps layout and table structure; MinerU, if table errors show up in testing |
| Agent tools | Our own MCP server (official Python MCP SDK) | [build123d-mcp](https://pypi.org/project/build123d-mcp/0.3.70/) reports render-and-measure feedback lifting GPT-5.5 from 0.360 to 0.457 on CADGenBench | Fork build123d-mcp or [mcp-build123d](https://jsr.io/@casys/mcp-build123d) as a starting point |
| LLM | Model-agnostic through MCP | Our bake-off ran Claude Sonnet and Opus at about $0.01 per generated part | Route cheap edits to a small model later |
| Viewer | three-cad-viewer (the viewer inside [OCP CAD Viewer](https://pypi.org/project/ocp-vscode/4.1.0/)) | Built for build123d B-rep: picking, measuring, part tree | [OCP.wasm](https://github.com/Yeicor/OCP.wasm) (active as of Sep 2026) for in-browser build123d later |
| App | Starlette backend, served by uvicorn and already a dependency of the MCP SDK; React front end; job queue for FEA | Long jobs run in the background and stream results. Each web route is built from a registry operation, so the app needs no framework of its own | [FastAPI](https://fastapi.tiangolo.com), not used (operator, 2026-11-09): Starlette already serves `/mcp`, and each route is built from a registry operation |
| Sign-in | [Clerk](https://clerk.com/docs/guides/ai/mcp/connect-mcp-client), with Google sign-in | Clerk is the OAuth 2.1 authorization server for MCP clients, with client registration and a consent screen, so our server only verifies its tokens | Supabase Auth (open source, newer OAuth server); Better Auth, which would need a Node service |
| Onshape link | Onshape REST API (STEP import, translated into Onshape parts) | You stay in Onshape for the rest of your design | An Onshape extension panel later; it is an iframe inside Onshape, and App Store listing needs OAuth2 |
| History | A signed log of revisions per variant slot; each chat edit adds one | Enough to show what changed and go back, with no git process per design. Git waits until someone needs a diff the log cannot give | None needed |

## Build plan

The first version is built in five phases, in this order. Each phase ends when its exit condition holds, not on a date.

1. **Server and universal checks.** Project setup ([AGENTS.md](AGENTS.md)), an MCP server that runs build123d code in the sandbox, the geometric universal checks, and the first materials table.
   - Exit: Claude Code, connected to the server, produces scorecards for the 10 bake-off parts that agree with the bake-off grader, and the sandbox blocks network access and enforces its limits.
2. **Briefs, requirements and scorecards.** A brief that builds at once, 3 to 5 variants, scorecards that list unverified requirements, sources and researched values, the knowledge base, agent-written checks with per-project review, and context parts with the fit check.
   - Exit: on the private brief set, across at least five domains, every number on every scorecard traces to a confirmed source. The one exception is an agent's own measurement, which is counted as not verified.
3. **Physics and manufacturing.** FEA under stated loads and deeper analysis of one chosen variant.
   - Exit: FEA results land within a stated error of hand calculations on beam and plate cases with known answers.
4. **Web app.** Chat, 3D viewer, scorecards, the mode switcher, Auto mode with its stopping rules, and accounts with usage limits.
   - Exit: a change asked for in chat rebuilds the variant and updates its scorecard without a page reload, and Auto mode stops correctly on a brief whose requirements conflict.
5. **Onshape.** Send a variant to Onshape, and read a part from an Onshape document into a project as a context part, through the REST API.
   - Exit: a variant sent from the workspace opens in Onshape with the volume and bounding box its scorecard reports, and a part read from an Onshape document becomes a context part that the fit check measures against.

Track progress with three numbers on a private set of briefs that spans at least five domains. The first is the strict pass rate, graded by executable checks, not "valid STL" rates. The second is the share of requirements covered by reviewed checks, which shows whether the "checks decide" claim holds as the agent takes on new domains. The third is friction: how many times you are asked to confirm something, and how many minutes pass, from brief to first scorecard. A change that raises friction needs a stated reason. Report public benchmarks such as Text2CAD-Bench and BenchCAD-Edit alongside.

The canonical private brief set is the 20 per-brief files in `~/cad-evals/briefs/`, across 7 domains. It stays outside the repo, so a session under test cannot read it. The older `briefs.yaml` is retired.

## Out of scope for the first version

- Converting blueprints or drawings into models. Drawings are context only. Image-to-code scored 0.32 to 0.40 on [BenchCAD](https://arxiv.org/html/2605.10865v1), depending on the model's mode.
- Freeform and loft-heavy shapes as a goal.
- Engineering skills and domain checks.
- Voice input.
- Robot simulation export and comparing predictions with measured test data.
- The Onshape extension panel.
- Self-hosting the server.
- Printability checks. You know your printer better than we do, many designs are never printed, and the product's job is the design.
- Print time and cost from a slicer. Slicing is bound up with printability, because the slice read its print orientation from the printability check, and the same reasons hold. The choice of PrusaSlicer stays recorded in [ADR-0005](docs/adr/0005-checks-run-in-an-analysis-image.md) for when slicing returns.
- Drawing generation, CNC and sheet-metal quotes, and SolidWorks and Fusion plugins.

## Risks

- **Adam is already inside Onshape.** We win on checks the agent cannot change and on variant comparison, not on having an Onshape integration.
- **Licensed standards.** ASME, ISO, AGMA and DIN documents are paid. We implement formulas and cite the clause, and never ship a standard's text or tables. DIN also forbids AI use of its documents, which matters when users upload standard PDFs.
- **Silent edit damage.** About 64% of edits that look successful break unrelated features ([BenchCAD](https://arxiv.org/html/2605.10865v1)), so regression checks run on every commit.
- **Running AI-written code.** Every variant is code an AI wrote, and outside MCP clients can send code too. The sandbox ships in phase 1.
- **Compute cost.** Any MCP client can trigger FEA on our servers, so accounts and usage limits ship in phase 4, the phase that hosts the server.
- **Auto mode relies on the agent to stop.** If the agent never judges itself stuck, a run keeps spending until the account's usage limit refuses a build. Watch run lengths and costs from the first Auto run.
- **Speed.** FEA takes seconds to minutes. The scorecard fills in as results arrive while the viewer stays live.
- **Onshape API limits.** Onshape tracks API usage per user or company. Check the published limits before relying on live sync.
- **Vendor terms.** Most vendors' data terms are unknown. The data policy above holds until each vendor gives written permission.

## Open questions

- [ ] What do novices actually get wrong, such as fits, wall thickness or fastener sizing?
- [ ] Which domain gets the first engineering skill?
- [ ] Will WCP, REV, igus, Misumi and SDP-SI give written permission to build catalogs from their data?
- [ ] Do we keep checks and tables private or open-source them? The answer decides whether self-hosting makes sense.
