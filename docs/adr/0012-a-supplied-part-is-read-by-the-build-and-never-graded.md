# A supplied part is read by the build and never graded as the agent's body

Status: Accepted, 2026-11-11. The operator made six calls on 2026-11-11 that it records: uploading counts as confirming, STL is accepted with the units the person picks, geometry the reader cannot read is dropped and counted, the agent may place and copy a supplied part, assembly checks come later, and modifying a supplied part ships.

Many real projects need parts the person brings: a motor, a board, wheels, a vendor bracket. The person says what they want, and the agent designs with those parts. Today a person cannot add any file to a project (#199). A context part can only be a variant the agent built, and the agent learns its shape from a bounding box. This ADR records how a part the person supplies enters a project, how the build uses it, and why the checks still decide.

The research behind it is in the plan of 2026-11-11, which measured real STEP and STL files in the pinned images. Every large real STEP file failed the existing ingest. A NEMA 17 held 4 loose shells, a Faulhaber motor held 5 open shells, and a Raspberry Pi 4B held 1978 loose shells and a tolerance over 1e-3 mm. An STL is a mesh with no units.

## The decision

### A supplied part is the person's geometry

A person adds a STEP or STL file to a project from the workspace, by drag and drop or a button. The person-only route `POST /v1/projects/{project_id}/files` takes it. No MCP tool takes a file, a path or a URL.

**Uploading counts as confirming.** Only a signed-in person can upload, so the upload handler records the person's confirmation in the same request. It writes one signed context-part record whose origin, `FromUpload`, names the file, its SHA-256, how it was read, and the account and session that sent it. The store treats that record as confirmed, so the part never waits on the card. The part's row in the workspace keeps a Decline control. Decline appends a `PageAnswer` that declines the part, through the same ledger the card writes, and from then on no check measures against it. A part the agent proposes from a variant still waits on the card, as before.

**STEP keeps the units in its header.** OCCT converts the file to millimetres.

**STL has no units, so the person always picks them.** The upload asks "millimetres or inches?" every time. There is no default and no size guess. The choice is recorded in `FromUpload`, and the row shows the size in millimetres so a wrong choice is visible.

**Geometry the reader cannot read is dropped and counted.** The ingest keeps the solids of the file and drops the rest: open shells, loose faces, and solids that still fail `BRepCheck_Analyzer` after it caps the tolerance at 1e-3 mm. The row says how much was dropped, for example "1 of 89 bodies could not be read". The fit check measures only what was kept. Refusing the whole file would refuse every large real file we measured.

The part id is `part-` and the first 16 hex digits of the SHA-256 of the normalised, solids-only BREP. The build and the fit check read the same bytes. The file as sent is kept beside it under its own SHA-256.

The ingest also reports facts: the solid count, volume and bounding box as today, and now the holes (diameter, centre, axis), the largest flats, the STEP product names, and what was left out. Team code computes them in the analysis image. The agent and the person read them. No check reads them.

### `result` is the agent's body

Every check scores `result`, the shape the agent's code builds, and only that. A supplied part is never inside `result`. So `closed_solid`, `mass`, `extents`, `fea`, `interference` and `fit` keep their meaning, and none of them grades the person's geometry as the agent's work.

### A brief uses a supplied part in one of two ways

The distinction lives in how a brief uses the part, not on the part. The same wheel can be something one brief's hub must fit and a component of another brief's drivetrain.

- **A fit target** is a confirmed part the new part must fit with. A part is a fit target of a brief when it was proposed for that brief from a variant, as today, or when a confirmed requirement of that brief names it: `fits_with`, `min_clearance` or `max_clearance`. The person confirms those requirements on the card with the rest of the brief, so the person decides which parts the design must fit. A fit target stays in its own frame. The fit check reads its BREP from the signed project store at identity, never from the build. A build may read a fit target to cut a pocket or copy a hole pattern, but a build that places or copies a fit target of its brief is refused, because the picture on the card would then show the part where the check did not measure it.
- **A component** is any other confirmed part of the project that a build uses. The agent decides to use it, and it may place and copy it. The person imports one wheel, and the agent puts four on a robot drivetrain. Every placement, the part id and its location, is recorded in the build manifest and covered by the variant id. The scorecard lists each one as "supplied by you, placed by the agent", and the viewer draws each one. No check reads a placement.

Moving a fit target could pass a clearance check, so the agent never moves one. A component's placement is the agent's design, like its code, and is shown as such.

`fits_with` is a new requirement kind. It holds the variant to not overlapping the part, with no number, for a brief such as "a bracket that holds this servo". The fit check decides it.

### The build reads parts by id

A build names the parts it reads, each with its placements. The server sends their confirmed BREP bytes on stdin, after the code, so build containers still have no mounts. Build code calls `part(id)` to get the solids at the part's own frame. The variant id hashes the SHA-256 of each part's BREP and each placement, so one id never names two shapes. A rebuild under the ADR-0003 amendment fetches each part by its SHA-256, so an updated part rebuilds an old variant with the old geometry.

### The scorecard says which geometry the person supplied

The card gains a `supplied` list: each part the variant read, with its name, its origin, its BREP's SHA-256 and its placements. The card's BREP hash is relabelled "made by the agent". The tracer checks that each `supplied` entry equals an entry of the scored variant's manifest, and names a part confirmed in the card's project whose stored BREP has that SHA-256. Otherwise the card fails.

### Modifying a supplied part

A build may name one supplied part it modifies, such as "add a 5 mm hole at the centre of this board". It must also read that part. Its `result` is then an edit of the person's geometry. The fit check skips the modified part for that variant and measures every other fit target. A new background check, `derived`, measures `result` against the modified part's stored BREP: `kept_volume`, `removed_volume` and `added_volume`. A person holds them to a limit through `measure_limit`. The card says "an edit of your part". The material follows the existing rule: a confirmed `made_of` names it, or the agent chooses it and the card says so.

### Later: whole-assembly checks

Two checks of the assembly, `result` plus each placed component, are wanted and not built yet:

- **Assembly extents.** The bounding box of the whole assembly. It is deterministic and reads no material.
- **Total mass.** The agent body's mass plus each supplied part's mass. A supplied part's mass is unknown, so it is researched under ADR-0009: a cited `mass_g` in the project overlay for that part, and every verdict that reads it is labelled researched and counted apart.

### Documents and images are project sources

A person also adds PDF, Markdown, plain text, PNG and JPEG files through the same route. Each is stored by its SHA-256 as a project source, the person's own attachment. The chat agent reads one with `read_file`, which takes the project and the file's id, never a path. A requirement may quote a file instead of the brief. For Markdown and plain text the server checks that the quote is in the file. For a PDF it checks the quote against the text the reader image takes from the PDF, the same reader and the same match that a researched value's quote gets (ADR-0009). For an image, or a PDF with no text layer such as a scan, the server cannot read the words, so the card shows the agent's quote with the file's name, labelled as read by the agent, and the person confirms it like any requirement. A number from a file reaches a check only as a requirement the person confirms (SPEC, Knowledge).

## Consequences

- **ADR-0003** is amended. The variant id and `build.json` cover the SHA-256 of each part a build read and each placement. The rebuild fetches parts by SHA-256. "Build containers have no mounts" stands.
- **ADR-0004** is amended. The upload handler is a second person-only handler that records a confirmation, for the part it writes. Decline on that part writes a `PageAnswer`. "No tool takes a path, a program or a URL" stands, because the upload is a web route and not a tool. A one-time upload URL for an agent with a shell (#60) would be a further amendment.
- **ADR-0007** holds. Facts and `part()` queries are information. A load still anchors on `result`, and the `fea` check resolves it with its fixed code. A load that acts through a supplied part, such as a motor's torque, stays unchecked until a check models it.
- **ADR-0008** holds. What the agent's build code reads from a part is its own number in its own build. It informs the design and never reaches a check.
- **ADR-0009** holds. A supplied part's mass, when a check reads it, is researched and labelled.
- A Boolean against a detailed motor took 32 s of the 60 s build wall. The tool text tells the agent to cut against a simple envelope when a part has many solids.
- A STEP file whose header names the wrong units is the wrong size. The size on the row is the person's defence.

## Considered options

- **Refuse a file that holds any geometry the reader cannot read.** Rejected. It refused 3 of the 3 large real files measured.
- **Guess the units of an STL from its size, as PrusaSlicer does.** Rejected by the operator on 2026-11-11. A guess can be wrong silently. The person picks every time.
- **An uploaded part waits on the card like a proposed one.** Rejected by the operator on 2026-11-11. Only the person can upload, so the upload is the confirmation, and a second click is friction.
- **Keep every supplied part in its own frame.** Rejected by the operator on 2026-11-11. It rules out four wheels on a drivetrain. The fit-target rule keeps the clearance checks honest instead.
- **A role field on the part.** Not chosen. A part can be a fit target of one brief and a component of another. The requirements the person confirms already say what a brief must fit.
- **Ship the part inside `result`.** Rejected. It would fail `closed_solid`, make `mass` and `fea` grade the person's geometry, and overlap the part by its whole volume in the fit check.
- **Mount the parts into the build container.** Rejected. Stdin keeps "build containers have no mounts".

## Delivery

1. Upload of STEP and STL with the normalising ingest, `FromUpload`, the richer facts, the upload and decline routes, the workspace controls, `fits_with`, and documents and images as project sources.
2. Build code reads parts with `part(id)`, places components, `supplied` on the card, the tracer rule and the viewer.
3. Modifying a supplied part and the `derived` check.
4. An Onshape origin (#60), through the same ingest. It waits on the operator's Onshape key.
